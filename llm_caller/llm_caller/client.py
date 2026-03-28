"""
Public API for single-call LLM invocations.

Two calling patterns:
- call_tool(): single model does reasoning + tool calling
- call_reasoned_tool(): reasoner model produces free-form text, then a
  separate formatter model structures it into a tool call
- call_text(): free-form text output (no tool use)
"""

import json
import logging
import os
import re

from llm_caller.config import (
    BACKEND,
    FORMATTER_BACKEND,
    FORMATTER_BASE_URL,
    FORMATTER_API_KEY,
    FORMATTER_MODEL,
    resolve_model,
)
from llm_caller.logging import write_prompt_log, write_raw_log

log = logging.getLogger("llm_caller.client")


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
        write_prompt_log(prompt_log_file, system, messages, tool_name)

    model = resolve_model(model, BACKEND)

    if BACKEND == "openai":
        from llm_caller.backends.openai import call_openai_compatible
        result, raw = call_openai_compatible(system, messages, tools, tool_name, model, max_tokens)
    elif BACKEND == "gemini":
        from llm_caller.backends.gemini import call_gemini
        result, raw = call_gemini(system, messages, tools, tool_name, model, max_tokens)
    else:
        from llm_caller.backends.anthropic import call_anthropic
        result, raw = call_anthropic(system, messages, tools, tool_name, model, max_tokens)

    if prompt_log_file:
        write_raw_log(prompt_log_file, raw)
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
        write_prompt_log(prompt_log_file, system, messages)

    model = resolve_model(model, BACKEND)

    if BACKEND == "openai":
        from llm_caller.backends.openai import call_openai_compatible_text
        result, raw = call_openai_compatible_text(
            system, messages, model, max_tokens,
            disable_thinking=disable_thinking,
        )
    elif BACKEND == "gemini":
        from llm_caller.backends.gemini import call_gemini_text
        result, raw = call_gemini_text(system, messages, model, max_tokens)
    else:
        from llm_caller.backends.anthropic import call_anthropic_text
        result, raw = call_anthropic_text(system, messages, model, max_tokens)

    if prompt_log_file:
        write_raw_log(prompt_log_file, raw)
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
    fmt_model = resolve_model(fmt_model, FORMATTER_BACKEND)

    if prompt_log_file:
        write_prompt_log(formatter_log, formatter_sys, formatter_messages, tool_name)

    if FORMATTER_BACKEND == "openai":
        from llm_caller.backends.openai import call_openai_compatible
        result, raw = call_openai_compatible(
            formatter_sys, formatter_messages, tools, tool_name,
            fmt_model, formatter_max_tokens,
            base_url=FORMATTER_BASE_URL, api_key=FORMATTER_API_KEY,
        )
    elif FORMATTER_BACKEND == "gemini":
        from llm_caller.backends.gemini import call_gemini
        result, raw = call_gemini(
            formatter_sys, formatter_messages, tools, tool_name,
            fmt_model, formatter_max_tokens,
        )
    else:
        from llm_caller.backends.anthropic import call_anthropic
        result, raw = call_anthropic(
            formatter_sys, formatter_messages, tools, tool_name,
            fmt_model, formatter_max_tokens,
        )

    if prompt_log_file:
        write_raw_log(formatter_log, raw)
        response_path = os.path.splitext(formatter_log)[0] + "_response.json"
        with open(response_path, "w") as f:
            json.dump(result, f, indent=2)

    return result
