"""
LLM client abstraction for agent modules.

Supports three backends:
- "anthropic": Anthropic API (uses ANTHROPIC_API_KEY)
- "openai": OpenAI-compatible API (e.g., LMStudio, ollama, vLLM)
- "gemini": Google Gemini API (uses GEMINI_API_KEY)

Configure via environment variables:
    LLM_BACKEND=openai
    LLM_BASE_URL=http://10.0.0.17:3001/v1
    LLM_API_KEY=not-needed          # some servers require a dummy key
    LLM_MODEL=my-local-model        # override default model
"""

import json
import os


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BACKEND = os.environ.get("LLM_BACKEND", "openai")
BASE_URL = os.environ.get("LLM_BASE_URL", "http://10.0.0.17:8001/v1")
API_KEY = os.environ.get("LLM_API_KEY", "not-needed")
DEFAULT_MODEL = os.environ.get("LLM_MODEL", "unsloth/Qwen3.5-9B-GGUF:Q4_K_M")


def _collect_all_defs(schema):
    """Collect all $defs from every level of a JSON Schema."""
    all_defs = {}
    if isinstance(schema, dict):
        if "$defs" in schema:
            all_defs.update(schema["$defs"])
        for v in schema.values():
            all_defs.update(_collect_all_defs(v))
    elif isinstance(schema, list):
        for item in schema:
            all_defs.update(_collect_all_defs(item))
    return all_defs


def _resolve_refs(schema, defs=None):
    """Recursively inline all $ref references in a JSON Schema."""
    if defs is None:
        defs = _collect_all_defs(schema)

    if isinstance(schema, dict):
        if "$ref" in schema:
            ref_name = schema["$ref"].rsplit("/", 1)[-1]
            return _resolve_refs(defs[ref_name], defs)
        result = {}
        for k, v in schema.items():
            if k == "$defs":
                continue
            result[k] = _resolve_refs(v, defs)
        return result
    elif isinstance(schema, list):
        return [_resolve_refs(item, defs) for item in schema]
    return schema


def _convert_tool_anthropic_to_openai(tool):
    """Convert an Anthropic tool definition to OpenAI format."""
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": _resolve_refs(tool["input_schema"]),
        },
    }


def _call_anthropic(system, messages, tools, tool_name, model, max_tokens):
    """Call the Anthropic API."""
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
        tools=tools,
        tool_choice={"type": "tool", "name": tool_name},
    )

    for block in response.content:
        if block.type == "tool_use":
            return block.input

    raise RuntimeError("Anthropic: agent did not return a tool call")

def _call_gemini(system, messages, tools, tool_name, model, max_tokens):
    """Call the Google Gemini API."""
    from google import genai
    from google.genai import types

    client = genai.Client()

    # Build function declarations from Anthropic tool definitions
    function_declarations = []
    for tool in tools:
        schema = _resolve_refs(tool["input_schema"])
        # Gemini doesn't accept top-level 'title' or 'required' on the
        # function parameters object — wrap properties under type=OBJECT.
        params = {
            "type": "OBJECT",
            "properties": schema.get("properties", {}),
        }
        if "required" in schema:
            params["required"] = schema["required"]

        function_declarations.append(
            types.FunctionDeclaration(
                name=tool["name"],
                description=tool.get("description", ""),
                parameters=params,
            )
        )

    gemini_tools = [types.Tool(function_declarations=function_declarations)]
    tool_config = types.ToolConfig(
        function_calling_config=types.FunctionCallingConfig(
            mode="ANY",
            allowed_function_names=[tool_name],
        )
    )

    # Convert messages to Gemini Content format
    contents = []
    for msg in messages:
        role = "model" if msg["role"] == "assistant" else "user"
        contents.append(types.Content(role=role, parts=[types.Part.from_text(text=msg["content"])]))

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system,
            tools=gemini_tools,
            tool_config=tool_config,
            max_output_tokens=max_tokens,
        ),
    )

    # Extract the function call
    for part in response.candidates[0].content.parts:
        if part.function_call:
            # function_call.args is a proto MapComposite; convert to dict
            return dict(part.function_call.args)

    raise RuntimeError("Gemini: agent did not return a function call")

def _call_openai_compatible(system, messages, tools, tool_name, model, max_tokens):
    """Call an OpenAI-compatible API (LMStudio, ollama, vLLM, etc.)."""
    from openai import OpenAI

    client = OpenAI(base_url=BASE_URL, api_key=API_KEY)

    # Build messages with system prompt; disable Qwen think mode
    oai_messages = [{"role": "system", "content": system + " /no_think"}]
    oai_messages.extend(messages)

    # Convert tool definitions
    oai_tools = [_convert_tool_anthropic_to_openai(t) for t in tools]

    last_error = None
    for attempt in range(_OPENAI_MAX_RETRIES):
        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=oai_messages,
            tools=oai_tools,
            tool_choice="required",
        )

        choice = response.choices[0]
        if not choice.message.tool_calls:
            last_error = RuntimeError(
                "OpenAI-compatible: agent did not return a tool call"
            )
            continue

        call = choice.message.tool_calls[0]
        try:
            return json.loads(call.function.arguments)
        except json.JSONDecodeError:
            last_error = json.JSONDecodeError(
                f"Malformed tool arguments (attempt {attempt + 1}/"
                f"{_OPENAI_MAX_RETRIES}): {call.function.arguments[:200]}",
                call.function.arguments or "",
                0,
            )
            continue

    raise last_error


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _write_prompt_log(path, system, messages, tool_name):
    """Write the full prompt (system + messages) to a file for traceability."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(f"# Tool: {tool_name}\n\n")
        f.write("## System Prompt\n\n")
        f.write(system)
        f.write("\n\n")
        for msg in messages:
            role = msg["role"].upper()
            f.write(f"## {role}\n\n")
            f.write(msg["content"])
            f.write("\n\n")


def call_tool(
    system: str,
    messages: list[dict],
    tools: list[dict],
    tool_name: str,
    model: str = "",
    max_tokens: int = 4096,
    prompt_log_file: str = "",
) -> dict:
    """Call an LLM with tool use and return the structured tool input.

    This is the single entry point for all agent LLM calls. It abstracts
    over Anthropic and OpenAI-compatible backends.

    Args:
        system: System prompt text.
        messages: List of message dicts (role + content).
        tools: List of tool definitions in Anthropic format
               (name, description, input_schema).
        tool_name: The tool the model must call.
        model: Model name. Falls back to LLM_MODEL env var, then backend default.
        max_tokens: Maximum tokens to generate.
        prompt_log_file: If set, write the full prompt to this path.

    Returns:
        The parsed tool input as a dict.
    """
    if prompt_log_file:
        _write_prompt_log(prompt_log_file, system, messages, tool_name)

    if not model:
        model = DEFAULT_MODEL

    if BACKEND == "openai":
        if not model:
            model = "default"
        return _call_openai_compatible(system, messages, tools, tool_name, model, max_tokens)
    elif BACKEND == "gemini":
        if not model:
            model = "gemini-2.5-flash"
        return _call_gemini(system, messages, tools, tool_name, model, max_tokens)
    else:
        if not model:
            model = "claude-sonnet-4-20250514"
        return _call_anthropic(system, messages, tools, tool_name, model, max_tokens)
