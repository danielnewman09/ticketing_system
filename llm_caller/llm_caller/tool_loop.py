"""
Multi-turn tool loop for LLM agents.

Lets the LLM call tools iteratively until it calls a designated "final tool"
that terminates the loop.  Supports Anthropic, OpenAI-compatible, and
Google Gemini backends.
"""

import json
import logging
import os
from typing import Callable

from llm_caller.config import BACKEND, resolve_model
from llm_caller.logging import write_conversation_log, make_turn_logger

log = logging.getLogger("llm_caller.tool_loop")


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
    model = resolve_model(model, BACKEND)

    on_turn = None
    if prompt_log_file:
        on_turn = make_turn_logger(prompt_log_file, system, final_tool_name)

    if BACKEND == "openai":
        from llm_caller.backends.openai import call_openai_loop
        result, history = call_openai_loop(
            system, messages, tools, final_tool_name,
            tool_dispatcher, model, max_tokens, max_turns,
            on_turn=on_turn,
        )
    elif BACKEND == "gemini":
        from llm_caller.backends.gemini import call_gemini_loop
        result, history = call_gemini_loop(
            system, messages, tools, final_tool_name,
            tool_dispatcher, model, max_tokens, max_turns,
            on_turn=on_turn,
        )
    else:
        from llm_caller.backends.anthropic import call_anthropic_loop
        result, history = call_anthropic_loop(
            system, messages, tools, final_tool_name,
            tool_dispatcher, model, max_tokens, max_turns,
            on_turn=on_turn,
        )

    # Final write to ensure the complete conversation is captured
    if prompt_log_file:
        write_conversation_log(prompt_log_file, system, history, final_tool_name)
        response_path = os.path.splitext(prompt_log_file)[0] + "_response.json"
        os.makedirs(os.path.dirname(response_path) or ".", exist_ok=True)
        with open(response_path, "w") as f:
            json.dump(result, f, indent=2)

    return result
