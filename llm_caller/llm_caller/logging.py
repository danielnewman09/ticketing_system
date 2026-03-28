"""
Prompt and conversation logging utilities for traceability.
"""

import json
import os


def write_prompt_log(path, system, messages, tool_name=""):
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


def write_raw_log(prompt_log_file, raw_text):
    """Write the raw model response text alongside the formatted log."""
    if not prompt_log_file:
        return
    base, _ = os.path.splitext(prompt_log_file)
    raw_path = f"{base}_raw.txt"
    os.makedirs(os.path.dirname(raw_path), exist_ok=True)
    with open(raw_path, "w") as f:
        f.write(raw_text)


def write_conversation_log(path, system, history, final_tool_name=""):
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


def make_turn_logger(prompt_log_file, system, final_tool_name):
    """Return an on_turn callback that rewrites the log file after each turn."""
    import logging
    log = logging.getLogger("llm_caller.tool_loop")

    def on_turn(turn_number, history):
        write_conversation_log(prompt_log_file, system, history, final_tool_name)
        log.debug("Log updated after turn %d: %s", turn_number, prompt_log_file)
    return on_turn
