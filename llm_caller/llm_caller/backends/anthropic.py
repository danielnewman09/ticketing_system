"""
Anthropic backend for single-call and multi-turn tool loop.
"""

import json
import logging

log = logging.getLogger("llm_caller.backends.anthropic")


def call_anthropic(system, messages, tools, tool_name, model, max_tokens):
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


def call_anthropic_text(system, messages, model, max_tokens):
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


_NUDGE_MESSAGE = (
    "Please call one of the available tools. When you have gathered enough "
    "information, call the final output tool to return your result."
)


def call_anthropic_loop(system, messages, tools, final_tool_name,
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
