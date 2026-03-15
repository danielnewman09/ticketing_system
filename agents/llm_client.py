"""
LLM client abstraction for agent modules.

Supports three backends:
- "anthropic": Anthropic API (uses ANTHROPIC_API_KEY)
- "openai": OpenAI-compatible API (e.g., LMStudio, ollama, vLLM)
- "gemini": Google Gemini API (uses GEMINI_API_KEY)

Two calling patterns:
- call_tool(): single model does reasoning + tool calling (original)
- call_reasoned_tool(): reasoner model produces free-form text, then a
  separate formatter model structures it into a tool call

Configure via environment variables:
    LLM_BACKEND=openai
    LLM_BASE_URL=http://10.0.0.17:3001/v1
    LLM_API_KEY=not-needed          # some servers require a dummy key
    LLM_MODEL=my-local-model        # override default model

    # Formatter model (for reasoner/formatter pipeline)
    LLM_FORMATTER_BACKEND=openai
    LLM_FORMATTER_BASE_URL=http://10.0.0.17:8002/v1
    LLM_FORMATTER_API_KEY=not-needed
    LLM_FORMATTER_MODEL=my-small-model
"""

import json
import os
import re


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BACKEND = os.environ.get("LLM_BACKEND", "openai")
BASE_URL = os.environ.get("LLM_BASE_URL", "http://10.0.0.17:8001/v1")
API_KEY = os.environ.get("LLM_API_KEY", "not-needed")
DEFAULT_MODEL = os.environ.get("LLM_MODEL", "unsloth/Qwen3.5-9B-GGUF:Q4_K_M")

# Formatter defaults: separate port for the smaller tool-calling model
FORMATTER_BACKEND = os.environ.get("LLM_FORMATTER_BACKEND", BACKEND)
FORMATTER_BASE_URL = os.environ.get("LLM_FORMATTER_BASE_URL", "http://10.0.0.17:8002/v1")
FORMATTER_API_KEY = os.environ.get("LLM_FORMATTER_API_KEY", API_KEY)
FORMATTER_MODEL = os.environ.get("LLM_FORMATTER_MODEL", DEFAULT_MODEL)


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


def _strip_think_tags(text):
    """Extract useful content from model output that may contain <think> blocks.

    If there is content outside the think tags, return that.
    If the entire response is inside think tags (common with reasoning models),
    return the think content itself — for a reasoner, the thinking IS the output.
    """
    # Try stripping think tags first
    stripped = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    if stripped:
        return stripped

    # Everything was inside think tags — extract the thinking content
    think_match = re.search(r"<think>(.*?)</think>", text, flags=re.DOTALL)
    if think_match:
        return think_match.group(1).strip()

    # No think tags at all, return as-is
    return text.strip()


# ---------------------------------------------------------------------------
# Backend: Anthropic
# ---------------------------------------------------------------------------

def _call_anthropic(system, messages, tools, tool_name, model, max_tokens):
    """Call the Anthropic API with tool use.

    Returns (parsed_result, raw_text).
    """
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

    # Capture full raw response
    raw_parts = []
    for block in response.content:
        if block.type == "text":
            raw_parts.append(block.text)
        elif block.type == "tool_use":
            raw_parts.append(f"[tool_call: {block.name}]\n{json.dumps(block.input, indent=2)}")
            return block.input, "\n\n".join(raw_parts)

    raise RuntimeError("Anthropic: agent did not return a tool call")


def _call_anthropic_text(system, messages, model, max_tokens):
    """Call the Anthropic API for free-form text (no tool use).

    Returns (text, raw_text). For Anthropic these are the same.
    """
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )

    text = response.content[0].text
    return text, text


# ---------------------------------------------------------------------------
# Backend: Gemini
# ---------------------------------------------------------------------------

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

    # Capture raw response and extract the function call
    raw_parts = []
    for part in response.candidates[0].content.parts:
        if part.text:
            raw_parts.append(part.text)
        if part.function_call:
            args = dict(part.function_call.args)
            raw_parts.append(f"[tool_call: {part.function_call.name}]\n{json.dumps(args, indent=2)}")
            return args, "\n\n".join(raw_parts)

    raise RuntimeError("Gemini: agent did not return a function call")


def _call_gemini_text(system, messages, model, max_tokens):
    """Call the Google Gemini API for free-form text (no tool use).

    Returns (text, raw_text). For Gemini these are the same.
    """
    from google import genai
    from google.genai import types

    client = genai.Client()

    contents = []
    for msg in messages:
        role = "model" if msg["role"] == "assistant" else "user"
        contents.append(types.Content(role=role, parts=[types.Part.from_text(text=msg["content"])]))

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
        ),
    )

    text = response.candidates[0].content.parts[0].text
    return text, text


# ---------------------------------------------------------------------------
# Backend: OpenAI-compatible
# ---------------------------------------------------------------------------

_OPENAI_MAX_RETRIES = 3

def _call_openai_compatible(system, messages, tools, tool_name, model, max_tokens,
                            *, base_url=None, api_key=None):
    """Call an OpenAI-compatible API (LMStudio, ollama, vLLM, etc.).

    Returns (parsed_result, raw_text) where raw_text is the raw response
    for logging purposes.
    """
    from openai import OpenAI

    client = OpenAI(base_url=base_url or BASE_URL, api_key=api_key or API_KEY)

    # Build messages with system prompt; disable Qwen think mode for tool calls
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
        # Capture raw text: reasoning + content + tool call arguments
        raw_parts = []
        reasoning = getattr(choice.message, "reasoning_content", None)
        if reasoning:
            raw_parts.append(f"<reasoning>\n{reasoning}\n</reasoning>")
        if choice.message.content:
            raw_parts.append(choice.message.content)

        if not choice.message.tool_calls:
            last_error = RuntimeError(
                "OpenAI-compatible: agent did not return a tool call"
            )
            continue

        call = choice.message.tool_calls[0]
        raw_parts.append(f"[tool_call: {call.function.name}]\n{call.function.arguments}")
        raw_text = "\n\n".join(raw_parts)

        try:
            return json.loads(call.function.arguments), raw_text
        except json.JSONDecodeError:
            last_error = json.JSONDecodeError(
                f"Malformed tool arguments (attempt {attempt + 1}/"
                f"{_OPENAI_MAX_RETRIES}): {call.function.arguments[:200]}",
                call.function.arguments or "",
                0,
            )
            continue

    raise last_error


def _call_openai_compatible_text(system, messages, model, max_tokens,
                                 *, base_url=None, api_key=None,
                                 disable_thinking=False):
    """Call an OpenAI-compatible API for free-form text (no tool use).

    Handles three reasoning output formats:
    1. Content with <think> tags (Qwen default)
    2. Separate reasoning_content field (OpenAI reasoning models, some backends)
    3. Plain content (non-reasoning models)

    Args:
        disable_thinking: If True, append /no_think to suppress Qwen thinking
            mode. Use when the prompt already specifies the output format and
            thinking causes the model to spiral without producing output.

    Returns (processed_text, raw_text).
    """
    from openai import OpenAI

    client = OpenAI(base_url=base_url or BASE_URL, api_key=api_key or API_KEY)

    sys_content = system + " /no_think" if disable_thinking else system
    oai_messages = [{"role": "system", "content": sys_content}]
    oai_messages.extend(messages)

    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=oai_messages,
    )

    message = response.choices[0].message
    content = message.content or ""
    reasoning = getattr(message, "reasoning_content", None) or ""

    # Build raw text from all available fields
    raw_parts = []
    if reasoning:
        raw_parts.append(f"<reasoning>\n{reasoning}\n</reasoning>")
    if content:
        raw_parts.append(content)
    raw_text = "\n\n".join(raw_parts)

    # For the processed result, prefer content if non-empty after stripping
    # think tags. Fall back to reasoning_content (the thinking IS the output
    # for reasoner models that put everything there).
    processed = _strip_think_tags(content) if content else ""
    if not processed and reasoning:
        processed = reasoning

    return processed, raw_text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _write_prompt_log(path, system, messages, tool_name=""):
    """Write the full prompt (system + messages) to a file for traceability."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        if tool_name:
            f.write(f"# Tool: {tool_name}\n\n")
        f.write("## System Prompt\n\n")
        f.write(system)
        f.write("\n\n")
        for msg in messages:
            role = msg["role"].upper()
            f.write(f"## {role}\n\n")
            f.write(msg["content"])
            f.write("\n\n")


def _write_raw_log(prompt_log_file, raw_text):
    """Write the raw model response text alongside the formatted log."""
    if not prompt_log_file:
        return
    base, _ = os.path.splitext(prompt_log_file)
    raw_path = f"{base}_raw.txt"
    os.makedirs(os.path.dirname(raw_path), exist_ok=True)
    with open(raw_path, "w") as f:
        f.write(raw_text)


def _resolve_model(model, backend):
    """Resolve a model name, falling back to backend-specific defaults."""
    if model:
        return model
    if backend == "openai":
        return DEFAULT_MODEL or "default"
    elif backend == "gemini":
        return "gemini-2.5-flash"
    else:
        return "claude-sonnet-4-20250514"


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

    This is the single-model entry point: one model does both reasoning
    and tool calling. For models that struggle with tool calling, use
    call_reasoned_tool() instead.

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

    model = _resolve_model(model, BACKEND)

    if BACKEND == "openai":
        result, raw = _call_openai_compatible(system, messages, tools, tool_name, model, max_tokens)
    elif BACKEND == "gemini":
        result, raw = _call_gemini(system, messages, tools, tool_name, model, max_tokens)
    else:
        result, raw = _call_anthropic(system, messages, tools, tool_name, model, max_tokens)

    if prompt_log_file:
        _write_raw_log(prompt_log_file, raw)
        response_path = os.path.splitext(prompt_log_file)[0] + "_response.json"
        with open(response_path, "w") as f:
            json.dump(result, f, indent=2)

    return result


def call_text(
    system: str,
    messages: list[dict],
    model: str = "",
    max_tokens: int = 4096,
    prompt_log_file: str = "",
    disable_thinking: bool = False,
) -> str:
    """Call an LLM for free-form text output (no tool use).

    The model is free to reason/think. For OpenAI-compatible backends,
    <think> tags are stripped from the output automatically.

    Args:
        system: System prompt text.
        messages: List of message dicts (role + content).
        model: Model name override.
        max_tokens: Maximum tokens to generate.
        prompt_log_file: If set, write the prompt to this path.
        disable_thinking: If True, suppress thinking mode on backends that
            support it (e.g., Qwen /no_think). Use when the prompt already
            specifies the output format and thinking causes spiraling.

    Returns:
        The model's text response (thinking stripped).
    """
    if prompt_log_file:
        _write_prompt_log(prompt_log_file, system, messages)

    model = _resolve_model(model, BACKEND)

    if BACKEND == "openai":
        result, raw = _call_openai_compatible_text(
            system, messages, model, max_tokens,
            disable_thinking=disable_thinking,
        )
    elif BACKEND == "gemini":
        result, raw = _call_gemini_text(system, messages, model, max_tokens)
    else:
        result, raw = _call_anthropic_text(system, messages, model, max_tokens)

    if prompt_log_file:
        _write_raw_log(prompt_log_file, raw)
        response_path = os.path.splitext(prompt_log_file)[0] + "_response.md"
        with open(response_path, "w") as f:
            f.write(result)

    return result


# ---------------------------------------------------------------------------
# Formatter: structures free-form text into tool calls
# ---------------------------------------------------------------------------

_FORMATTER_SYSTEM = """\
You are a precise data extraction agent. You will be given a design document
in markdown format produced by another agent. Your ONLY job is to extract
the information from that document and structure it into the required tool
call. Do not add, remove, or modify any design decisions — faithfully
transcribe what the document describes.

CRITICAL: You MUST include ALL nested arrays from the document. Every class
must include its "attributes" and "methods" arrays — do NOT omit them even
if the tool call gets large. Dropping nested data is the worst failure mode.

If the document is ambiguous or missing information for a required field,
use reasonable defaults (empty string for text, empty list for arrays).

You MUST use the {tool_name} tool to return your result.
"""


def _extract_design_from_reasoning(text):
    """Extract final design decisions from verbose reasoning output.

    Reasoning models produce long streams of consciousness with self-correction,
    backtracking, and deliberation. The formatter only needs the final decisions.
    This function extracts structured sections (markdown headers, lists) and
    discards meta-commentary like "Wait, let me reconsider..." or "Actually...".
    """
    lines = text.split("\n")
    output = []
    in_final_section = False

    for line in lines:
        stripped = line.strip()

        # Markdown headers signal structured content
        if stripped.startswith("#"):
            in_final_section = True
            output.append(line)
            continue

        # Skip common reasoning noise patterns
        if any(stripped.lower().startswith(p) for p in (
            "wait,", "actually,", "let me", "let's",
            "hmm", "i think", "i will", "i need",
            "so ", "ok ", "okay", "now,",
            "*wait", "*actually", "*let me", "*let's",
            "*refinement", "*self-correction", "*check",
            "thinking process", "1. ", "2. ", "3. ", "4. ",
        )):
            # But keep numbered items inside a structured section
            if in_final_section and stripped[:1].isdigit():
                output.append(line)
            continue

        # Keep lines that look like design content
        if in_final_section or stripped.startswith("-") or stripped.startswith("*"):
            output.append(line)

    result = "\n".join(output).strip()

    # If extraction produced too little, fall back to full text
    # (better to give the formatter too much than nothing)
    if len(result) < 100:
        return text

    return result


def call_reasoned_tool(
    reasoner_system: str,
    messages: list[dict],
    tools: list[dict],
    tool_name: str,
    reasoner_model: str = "",
    formatter_model: str = "",
    reasoner_max_tokens: int = 16384,
    formatter_max_tokens: int = 8192,
    prompt_log_file: str = "",
) -> dict:
    """Two-stage pipeline: reasoner produces text, formatter structures it.

    Stage 1 (Reasoner): Calls the primary LLM with no tool forcing, letting
    it reason freely and produce a markdown-formatted design document.

    Stage 2 (Formatter): Passes the reasoner's output to a second model
    (typically smaller, better at following schemas) which structures it
    into the required tool call.

    Args:
        reasoner_system: System prompt for the reasoning stage.
        messages: User messages for the reasoning stage.
        tools: Tool definitions (Anthropic format) for the formatting stage.
        tool_name: The tool the formatter must call.
        reasoner_model: Model override for the reasoner. Defaults to LLM_MODEL.
        formatter_model: Model override for the formatter. Defaults to
            LLM_FORMATTER_MODEL.
        reasoner_max_tokens: Max tokens for the reasoner.
        formatter_max_tokens: Max tokens for the formatter.
        prompt_log_file: Base path for prompt logs. Creates separate files
            for reasoner and formatter stages.

    Returns:
        The parsed tool input as a dict.
    """
    # --- Stage 1: Reasoner ---
    reasoner_log = ""
    if prompt_log_file:
        base, ext = os.path.splitext(prompt_log_file)
        reasoner_log = f"{base}_reasoner{ext}"

    reasoner_output = call_text(
        system=reasoner_system,
        messages=messages,
        model=reasoner_model,
        max_tokens=reasoner_max_tokens,
        prompt_log_file=reasoner_log,
        disable_thinking=True,
    )

    # Clean up reasoning output: extract design decisions, discard deliberation
    design_doc = _extract_design_from_reasoning(reasoner_output)

    # --- Stage 2: Formatter ---
    formatter_sys = _FORMATTER_SYSTEM.format(tool_name=tool_name)

    formatter_messages = [
        {
            "role": "user",
            "content": (
                "Extract and structure the following design document into "
                f"the {tool_name} tool call.\n\n"
                "--- DESIGN DOCUMENT ---\n\n"
                f"{design_doc}"
            ),
        }
    ]

    formatter_log = ""
    if prompt_log_file:
        base, ext = os.path.splitext(prompt_log_file)
        formatter_log = f"{base}_formatter{ext}"

    # Use formatter-specific config
    fmt_model = formatter_model or FORMATTER_MODEL
    fmt_model = _resolve_model(fmt_model, FORMATTER_BACKEND)

    if prompt_log_file:
        _write_prompt_log(formatter_log, formatter_sys, formatter_messages, tool_name)

    if FORMATTER_BACKEND == "openai":
        result, raw = _call_openai_compatible(
            formatter_sys, formatter_messages, tools, tool_name,
            fmt_model, formatter_max_tokens,
            base_url=FORMATTER_BASE_URL, api_key=FORMATTER_API_KEY,
        )
    elif FORMATTER_BACKEND == "gemini":
        result, raw = _call_gemini(
            formatter_sys, formatter_messages, tools, tool_name,
            fmt_model, formatter_max_tokens,
        )
    else:
        result, raw = _call_anthropic(
            formatter_sys, formatter_messages, tools, tool_name,
            fmt_model, formatter_max_tokens,
        )

    if prompt_log_file:
        _write_raw_log(formatter_log, raw)
        response_path = os.path.splitext(formatter_log)[0] + "_response.json"
        with open(response_path, "w") as f:
            json.dump(result, f, indent=2)

    return result
