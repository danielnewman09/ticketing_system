"""Shared agent activity log for the dashboard console.

Patches llm_caller's public API (call_tool, call_text, call_reasoned_tool)
to capture LLM requests and responses into an in-memory buffer that the
frontend can display.  These wrappers fire regardless of whether
prompt_log_file is set.
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


def _preview_messages(messages: list[dict]) -> str:
    """Extract a short preview from the last user message."""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                return content[:200]
    return ""


def install_hooks():
    """Wrap llm_caller's public call functions to push to the agent log.

    This patches call_tool, call_text, and call_reasoned_tool directly,
    so entries appear even when prompt_log_file is not set.
    """
    try:
        import llm_caller.client as client
    except ImportError:
        print("ERROR: Could not import llm_caller.client")
        return

    _orig_call_tool = client.call_tool
    _orig_call_text = client.call_text
    _orig_call_reasoned_tool = client.call_reasoned_tool

    def patched_call_tool(system, messages, tools, tool_name, **kwargs):
        preview = _preview_messages(messages)
        agent_log.push("request", f"call_tool: {tool_name}", preview)
        result = _orig_call_tool(system, messages, tools, tool_name, **kwargs)
        agent_log.push("response", f"call_tool: {tool_name} complete")
        return result

    def patched_call_text(system, messages, **kwargs):
        preview = _preview_messages(messages)
        agent_log.push("request", "call_text", preview)
        result = _orig_call_text(system, messages, **kwargs)
        agent_log.push("response", "call_text complete", result[:200] if isinstance(result, str) else "")
        return result

    def patched_call_reasoned_tool(reasoner_system, messages, tools, tool_name, **kwargs):
        preview = _preview_messages(messages)
        agent_log.push("request", f"call_reasoned_tool: {tool_name}", preview)
        result = _orig_call_reasoned_tool(reasoner_system, messages, tools, tool_name, **kwargs)
        agent_log.push("response", f"call_reasoned_tool: {tool_name} complete")
        return result

    # Patch the module-level references
    client.call_tool = patched_call_tool
    client.call_text = patched_call_text
    client.call_reasoned_tool = patched_call_reasoned_tool

    # Also patch the top-level package imports (from llm_caller import call_tool)
    try:
        import llm_caller
        llm_caller.call_tool = patched_call_tool
        llm_caller.call_text = patched_call_text
        llm_caller.call_reasoned_tool = patched_call_reasoned_tool
    except (ImportError, AttributeError):
        pass

    # Patch any already-imported modules that did `from llm_caller import call_tool`
    import sys
    for mod in list(sys.modules.values()):
        if mod is None or mod is client:
            continue
        try:
            if getattr(mod, "call_tool", None) is _orig_call_tool:
                mod.call_tool = patched_call_tool
            if getattr(mod, "call_text", None) is _orig_call_text:
                mod.call_text = patched_call_text
            if getattr(mod, "call_reasoned_tool", None) is _orig_call_reasoned_tool:
                mod.call_reasoned_tool = patched_call_reasoned_tool
        except Exception:
            pass

    # Patch tool_loop which has its own on_turn logging
    try:
        import llm_caller.tool_loop as tool_loop
        _orig_tool_loop_run = tool_loop.run_tool_loop

        def patched_tool_loop_run(system, messages, tools, final_tool_name, **kwargs):
            agent_log.push("request", f"tool_loop: {final_tool_name}", _preview_messages(messages))

            # Wrap on_turn if provided to also log turns
            orig_on_turn = kwargs.get("on_turn")

            def logging_on_turn(turn_number, history):
                agent_log.push("turn", f"Turn {turn_number} ({final_tool_name})")
                if orig_on_turn:
                    return orig_on_turn(turn_number, history)

            kwargs["on_turn"] = logging_on_turn
            result = _orig_tool_loop_run(system, messages, tools, final_tool_name, **kwargs)
            agent_log.push("response", f"tool_loop: {final_tool_name} complete")
            return result

        tool_loop.run_tool_loop = patched_tool_loop_run
    except (ImportError, AttributeError):
        pass
