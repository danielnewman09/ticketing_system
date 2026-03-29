"""Shared agent activity log for the dashboard console.

Patches llm_caller's logging functions to capture LLM requests and responses
into an in-memory buffer that the frontend can display.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass

MAX_ENTRIES = 200


@dataclass
class LogEntry:
    timestamp: float
    kind: str  # "request", "response", "turn", "info"
    summary: str
    detail: str = ""


class AgentLog:
    """Thread-safe, bounded log buffer."""

    def __init__(self, maxlen: int = MAX_ENTRIES):
        self._entries: deque[LogEntry] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._version = 0

    def push(self, kind: str, summary: str, detail: str = ""):
        with self._lock:
            self._entries.append(LogEntry(
                timestamp=time.time(), kind=kind, summary=summary, detail=detail,
            ))
            self._version += 1

    @property
    def version(self) -> int:
        return self._version

    def entries(self, since_version: int = 0) -> list[LogEntry]:
        """Return all entries (or only new ones if since_version is given)."""
        with self._lock:
            if since_version <= 0:
                return list(self._entries)
            # Return entries added after since_version
            skip = len(self._entries) - (self._version - since_version)
            if skip < 0:
                skip = 0
            return list(self._entries)[skip:]

    def clear(self):
        with self._lock:
            self._entries.clear()
            self._version += 1


# Singleton
agent_log = AgentLog()


def install_hooks():
    """Monkey-patch llm_caller.logging to also push to the agent log."""
    try:
        import llm_caller.logging as llm_logging
    except ImportError:
        print('ERROR: Could not import llm_caller logs')
        return

    _orig_write_prompt = llm_logging.write_prompt_log
    _orig_write_raw = llm_logging.write_raw_log
    _orig_make_turn_logger = llm_logging.make_turn_logger

    def patched_write_prompt_log(path, system, messages, tool_name=""):
        # Summarize the request
        user_msgs = [m for m in messages if m.get("role") == "user"]
        preview = ""
        if user_msgs:
            content = user_msgs[-1].get("content", "")
            if isinstance(content, str):
                preview = content[:200]
        label = f"Tool: {tool_name}" if tool_name else "Text call"
        agent_log.push("request", label, preview)
        return _orig_write_prompt(path, system, messages, tool_name)

    def patched_write_raw(prompt_log_file, raw_text):
        if raw_text:
            preview = raw_text[:300]
            agent_log.push("response", "LLM response", preview)
        return _orig_write_raw(prompt_log_file, raw_text)

    def patched_make_turn_logger(prompt_log_file, system, final_tool_name):
        orig_callback = _orig_make_turn_logger(prompt_log_file, system, final_tool_name)

        def on_turn(turn_number, history):
            # Summarize the latest assistant message
            last_assistant = ""
            for msg in reversed(history):
                if isinstance(msg, dict) and msg.get("role") == "assistant":
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        last_assistant = content[:200]
                    elif isinstance(content, list):
                        # Tool use blocks
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "tool_use":
                                last_assistant = f"Tool call: {block.get('name', '?')}"
                                break
                    break
            agent_log.push(
                "turn",
                f"Turn {turn_number} (target: {final_tool_name})",
                last_assistant,
            )
            return orig_callback(turn_number, history)

        return on_turn

    # Patch the module-level references
    llm_logging.write_prompt_log = patched_write_prompt_log
    llm_logging.write_raw_log = patched_write_raw
    llm_logging.make_turn_logger = patched_make_turn_logger

    # Also patch the already-imported references in client and tool_loop,
    # since they use `from llm_caller.logging import ...` at import time
    try:
        import llm_caller.client as _client
        _client.write_prompt_log = patched_write_prompt_log
        _client.write_raw_log = patched_write_raw
    except (ImportError, AttributeError):
        print('ERROR: Could not import llm_caller logs')
    try:
        import llm_caller.tool_loop as _tool_loop
        _tool_loop.write_conversation_log = llm_logging.write_conversation_log
        _tool_loop.make_turn_logger = patched_make_turn_logger
    except (ImportError, AttributeError):
        print('ERROR: Could not import llm_caller logs')