"""
Multi-turn tool loop for LLM agents.

Lets the LLM call tools iteratively until it calls a designated "final tool"
that terminates the loop.  Supports the same three backends as llm_client:
Anthropic, OpenAI-compatible, and Google Gemini.
"""

import json
import logging
import os
from typing import Callable

from agents.llm_client import (
    BACKEND,
    BASE_URL,
    API_KEY,
    _resolve_model,
    _resolve_refs,
    _convert_tool_anthropic_to_openai,
)

log = logging.getLogger("agents.llm_tool_loop")

_NUDGE_MESSAGE = (
    "Please call one of the available tools. When you have gathered enough "
    "information, call the final output tool to return your result."
)


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------

def _call_anthropic_loop(system, messages, tools, final_tool_name,
                         tool_dispatcher, model, max_tokens, max_turns,
                         on_turn=None):
    """Multi-turn Anthropic loop. Returns (final_tool_input, message_history)."""
    import anthropic

    client = anthropic.Anthropic()
    history = list(messages)

    for turn in range(max_turns):
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=history,
            tools=tools,
        )

        tool_calls = [b for b in response.content if b.type == "tool_use"]

        if not tool_calls:
            log.debug("Tool loop turn %d: text-only response, nudging", turn + 1)
            history.append({"role": "assistant", "content": response.content})
            history.append({"role": "user", "content": _NUDGE_MESSAGE})
            if on_turn:
                on_turn(turn + 1, history)
            continue

        # Check if any call is the final tool
        for block in tool_calls:
            if block.name == final_tool_name:
                if on_turn:
                    on_turn(turn + 1, history)
                return block.input, history

        # Dispatch intermediate tool calls
        history.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in tool_calls:
            log.debug("Tool loop turn %d: dispatching %s", turn + 1, block.name)
            result_str = tool_dispatcher(block.name, block.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result_str,
            })
        history.append({"role": "user", "content": tool_results})
        if on_turn:
            on_turn(turn + 1, history)

    raise RuntimeError(f"Tool loop exceeded max_turns={max_turns}")


# ---------------------------------------------------------------------------
# OpenAI-compatible
# ---------------------------------------------------------------------------

def _call_openai_loop(system, messages, tools, final_tool_name,
                      tool_dispatcher, model, max_tokens, max_turns,
                      *, base_url=None, api_key=None, on_turn=None):
    """Multi-turn OpenAI-compatible loop. Returns (final_tool_input, message_history)."""
    from openai import OpenAI

    client = OpenAI(base_url=base_url or BASE_URL, api_key=api_key or API_KEY)
    oai_tools = [_convert_tool_anthropic_to_openai(t) for t in tools]
    history = [{"role": "system", "content": system + " /no_think"}]
    history.extend(messages)

    for turn in range(max_turns):
        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=history,
            tools=oai_tools,
            tool_choice="auto",
        )

        choice = response.choices[0]

        if not choice.message.tool_calls:
            log.debug("Tool loop turn %d: text-only response, nudging", turn + 1)
            history.append({
                "role": "assistant",
                "content": choice.message.content or "",
            })
            history.append({"role": "user", "content": _NUDGE_MESSAGE})
            if on_turn:
                on_turn(turn + 1, history)
            continue

        # Check for the final tool call
        for call in choice.message.tool_calls:
            if call.function.name == final_tool_name:
                if on_turn:
                    on_turn(turn + 1, history)
                return json.loads(call.function.arguments), history

        # Append the full assistant message (OpenAI requires all tool_calls
        # to be present when responding with tool results)
        history.append({
            "role": "assistant",
            "content": choice.message.content or "",
            "tool_calls": [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {
                        "name": c.function.name,
                        "arguments": c.function.arguments,
                    },
                }
                for c in choice.message.tool_calls
            ],
        })

        # Dispatch each intermediate tool call
        for call in choice.message.tool_calls:
            log.debug("Tool loop turn %d: dispatching %s", turn + 1, call.function.name)
            args = json.loads(call.function.arguments)
            result_str = tool_dispatcher(call.function.name, args)
            history.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": result_str,
            })

        if on_turn:
            on_turn(turn + 1, history)

    raise RuntimeError(f"Tool loop exceeded max_turns={max_turns}")


# ---------------------------------------------------------------------------
# Google Gemini
# ---------------------------------------------------------------------------

def _call_gemini_loop(system, messages, tools, final_tool_name,
                      tool_dispatcher, model, max_tokens, max_turns,
                      on_turn=None):
    """Multi-turn Gemini loop. Returns (final_tool_input, message_history)."""
    from google import genai
    from google.genai import types

    client = genai.Client()

    # Build function declarations
    function_declarations = []
    for tool in tools:
        schema = _resolve_refs(tool["input_schema"])
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
    all_names = [tool["name"] for tool in tools]
    tool_config = types.ToolConfig(
        function_calling_config=types.FunctionCallingConfig(
            mode="ANY",
            allowed_function_names=all_names,
        )
    )

    # Build initial contents
    contents = []
    for msg in messages:
        role = "model" if msg["role"] == "assistant" else "user"
        contents.append(
            types.Content(role=role, parts=[types.Part.from_text(text=msg["content"])])
        )

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


# ---------------------------------------------------------------------------
# Conversation logging
# ---------------------------------------------------------------------------

def _write_conversation_log(path, system, history, final_tool_name=""):
    """Write a multi-turn conversation to a file for traceability."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write(f"# Tool Loop (final: {final_tool_name})\n\n")
        f.write("## System Prompt\n\n")
        f.write(system)
        f.write("\n\n")
        for msg in history:
            role = msg.get("role", "unknown") if isinstance(msg, dict) else "unknown"
            f.write(f"## {role.upper()}\n\n")
            content = msg.get("content", "") if isinstance(msg, dict) else str(msg)
            if isinstance(content, str):
                f.write(content)
            else:
                f.write(json.dumps(content, indent=2, default=str))
            f.write("\n\n")


def _make_turn_logger(prompt_log_file, system, final_tool_name):
    """Return an on_turn callback that rewrites the log file after each turn."""
    def on_turn(turn_number, history):
        _write_conversation_log(prompt_log_file, system, history, final_tool_name)
        log.debug("Log updated after turn %d: %s", turn_number, prompt_log_file)
    return on_turn


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def call_tool_loop(
    system: str,
    messages: list[dict],
    tools: list[dict],
    final_tool_name: str,
    tool_dispatcher: Callable[[str, dict], str],
    model: str = "",
    max_tokens: int = 4096,
    max_turns: int = 10,
    prompt_log_file: str = "",
) -> dict:
    """Multi-turn tool loop: the LLM calls tools iteratively until it
    calls the designated final tool.

    Non-final tool calls are dispatched to tool_dispatcher(name, args) -> str,
    and the result is fed back as a tool result message.

    When *prompt_log_file* is set, the conversation log is **rewritten after
    every turn** so you can tail the file and watch progress in real time.

    Args:
        system: System prompt text.
        messages: Initial message list (role + content).
        tools: All tool definitions (Anthropic format) — includes both
               intermediate query tools and the final output tool.
        final_tool_name: The tool call that terminates the loop.
        tool_dispatcher: Callable that executes a non-final tool call.
            Signature: (tool_name: str, tool_input: dict) -> str
            Must return a JSON-serialized string result.
        model: Model name override.
        max_tokens: Max tokens per turn.
        max_turns: Safety limit on loop iterations.
        prompt_log_file: If set, write the full conversation to this path
            after every turn (not just at the end).

    Returns:
        The parsed input dict from the final tool call.
    """
    model = _resolve_model(model, BACKEND)

    on_turn = None
    if prompt_log_file:
        on_turn = _make_turn_logger(prompt_log_file, system, final_tool_name)

    if BACKEND == "openai":
        result, history = _call_openai_loop(
            system, messages, tools, final_tool_name,
            tool_dispatcher, model, max_tokens, max_turns,
            on_turn=on_turn,
        )
    elif BACKEND == "gemini":
        result, history = _call_gemini_loop(
            system, messages, tools, final_tool_name,
            tool_dispatcher, model, max_tokens, max_turns,
            on_turn=on_turn,
        )
    else:
        result, history = _call_anthropic_loop(
            system, messages, tools, final_tool_name,
            tool_dispatcher, model, max_tokens, max_turns,
            on_turn=on_turn,
        )

    # Final write to ensure the complete conversation is captured
    if prompt_log_file:
        _write_conversation_log(prompt_log_file, system, history, final_tool_name)
        response_path = os.path.splitext(prompt_log_file)[0] + "_response.json"
        os.makedirs(os.path.dirname(response_path) or ".", exist_ok=True)
        with open(response_path, "w") as f:
            json.dump(result, f, indent=2)

    return result
