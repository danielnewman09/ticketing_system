"""
Google Gemini backend for single-call and multi-turn tool loop.
"""

import json
import logging

from llm_caller.schema_utils import resolve_refs

log = logging.getLogger("llm_caller.backends.gemini")

_NUDGE_MESSAGE = (
    "Please call one of the available tools. When you have gathered enough "
    "information, call the final output tool to return your result."
)


def _build_function_declarations(tools):
    """Build Gemini FunctionDeclaration list from Anthropic tool definitions."""
    from google.genai import types

    function_declarations = []
    for tool in tools:
        schema = resolve_refs(tool["input_schema"])
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
    return function_declarations


def _convert_messages(messages):
    """Convert standard message dicts to Gemini Content format."""
    from google.genai import types

    contents = []
    for msg in messages:
        role = "model" if msg["role"] == "assistant" else "user"
        contents.append(types.Content(role=role, parts=[types.Part.from_text(text=msg["content"])]))
    return contents


def call_gemini(system, messages, tools, tool_name, model, max_tokens):
    """Call the Google Gemini API."""
    from google import genai
    from google.genai import types

    client = genai.Client()

    function_declarations = _build_function_declarations(tools)
    gemini_tools = [types.Tool(function_declarations=function_declarations)]
    tool_config = types.ToolConfig(
        function_calling_config=types.FunctionCallingConfig(
            mode="ANY",
            allowed_function_names=[tool_name],
        )
    )

    contents = _convert_messages(messages)

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


def call_gemini_text(system, messages, model, max_tokens):
    """Call the Google Gemini API for free-form text (no tool use).

    Returns (text, raw_text). For Gemini these are the same.
    """
    from google import genai
    from google.genai import types

    client = genai.Client()
    contents = _convert_messages(messages)

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


def call_gemini_loop(system, messages, tools, final_tool_name,
                     tool_dispatcher, model, max_tokens, max_turns,
                     on_turn=None):
    """Multi-turn Gemini loop. Returns (final_tool_input, message_history)."""
    from google import genai
    from google.genai import types

    client = genai.Client()

    function_declarations = _build_function_declarations(tools)
    gemini_tools = [types.Tool(function_declarations=function_declarations)]
    all_names = [tool["name"] for tool in tools]
    tool_config = types.ToolConfig(
        function_calling_config=types.FunctionCallingConfig(
            mode="ANY",
            allowed_function_names=all_names,
        )
    )

    # Build initial contents
    contents = _convert_messages(messages)

    for turn in range(max_turns):
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

        parts = response.candidates[0].content.parts
        func_calls = [p for p in parts if p.function_call]

        if not func_calls:
            log.debug("Tool loop turn %d: text-only response, nudging", turn + 1)
            contents.append(response.candidates[0].content)
            contents.append(
                types.Content(role="user", parts=[types.Part.from_text(text=_NUDGE_MESSAGE)])
            )
            if on_turn:
                on_turn(turn + 1, contents)
            continue

        # Check for the final tool call
        for part in func_calls:
            if part.function_call.name == final_tool_name:
                if on_turn:
                    on_turn(turn + 1, contents)
                return dict(part.function_call.args), contents

        # Append model response and dispatch intermediate calls
        contents.append(response.candidates[0].content)
        response_parts = []
        for part in func_calls:
            fc = part.function_call
            log.debug("Tool loop turn %d: dispatching %s", turn + 1, fc.name)
            result_str = tool_dispatcher(fc.name, dict(fc.args))
            response_parts.append(
                types.Part.from_function_response(
                    name=fc.name,
                    response={"result": result_str},
                )
            )
        contents.append(types.Content(role="user", parts=response_parts))
        if on_turn:
            on_turn(turn + 1, contents)

    raise RuntimeError(f"Tool loop exceeded max_turns={max_turns}")
