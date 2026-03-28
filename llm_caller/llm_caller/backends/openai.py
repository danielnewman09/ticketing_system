"""
OpenAI-compatible backend for single-call and multi-turn tool loop.

Supports LMStudio, ollama, vLLM, and other OpenAI-compatible servers.
"""

import json
import logging

from llm_caller.config import BASE_URL, API_KEY
from llm_caller.schema_utils import convert_tool_anthropic_to_openai, strip_think_tags

log = logging.getLogger("llm_caller.backends.openai")

_MAX_RETRIES = 3

_NUDGE_MESSAGE = (
    "Please call one of the available tools. When you have gathered enough "
    "information, call the final output tool to return your result."
)


def call_openai_compatible(system, messages, tools, tool_name, model, max_tokens,
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
    oai_tools = [convert_tool_anthropic_to_openai(t) for t in tools]

    last_error = None
    for attempt in range(_MAX_RETRIES):
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
                f"{_MAX_RETRIES}): {call.function.arguments[:200]}",
                call.function.arguments or "",
                0,
            )
            continue

    raise last_error


def call_openai_compatible_text(system, messages, model, max_tokens,
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
    processed = strip_think_tags(content) if content else ""
    if not processed and reasoning:
        processed = reasoning

    return processed, raw_text


def call_openai_loop(system, messages, tools, final_tool_name,
                     tool_dispatcher, model, max_tokens, max_turns,
                     *, base_url=None, api_key=None, on_turn=None):
    """Multi-turn OpenAI-compatible loop. Returns (final_tool_input, message_history)."""
    from openai import OpenAI

    client = OpenAI(base_url=base_url or BASE_URL, api_key=api_key or API_KEY)
    oai_tools = [convert_tool_anthropic_to_openai(t) for t in tools]
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
