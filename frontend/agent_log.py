"""Shared agent activity log for the dashboard console.

Patches llm_caller's public API (call_tool, call_text, call_reasoned_tool)
to capture LLM requests and responses into an in-memory buffer that the
frontend can display.  These wrappers fire regardless of whether
prompt_log_file is set.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

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

# ---------------------------------------------------------------------------
# File trace logger — writes full untruncated data to logs/agent_trace.jsonl
# ---------------------------------------------------------------------------

_TRACE_DIR = Path(__file__).resolve().parent.parent / "logs"


class TraceLogger:
    """Append-only JSONL file logger for full agent traces."""

    def __init__(self):
        self._lock = threading.Lock()
        self._file = None
        self._path = None

    def _ensure_open(self):
        if self._file is None:
            _TRACE_DIR.mkdir(parents=True, exist_ok=True)
            self._path = _TRACE_DIR / "agent_trace.jsonl"
            self._file = open(self._path, "a", encoding="utf-8")

    def write(self, event: str, **data):
        """Write one JSON line with timestamp, event type, and arbitrary data."""
        with self._lock:
            self._ensure_open()
            record = {
                "ts": time.time(),
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "event": event,
                **data,
            }
            self._file.write(json.dumps(record, default=str) + "\n")
            self._file.flush()

    def close(self):
        with self._lock:
            if self._file:
                self._file.close()
                self._file = None


trace = TraceLogger()


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
        trace.write("call_tool_request", tool_name=tool_name, system=system, messages=messages)
        result = _orig_call_tool(system, messages, tools, tool_name, **kwargs)
        agent_log.push("response", f"call_tool: {tool_name} complete")
        trace.write("call_tool_response", tool_name=tool_name, result=result)
        return result

    def patched_call_text(system, messages, **kwargs):
        preview = _preview_messages(messages)
        agent_log.push("request", "call_text", preview)
        trace.write("call_text_request", system=system, messages=messages)
        result = _orig_call_text(system, messages, **kwargs)
        agent_log.push("response", "call_text complete", result[:200] if isinstance(result, str) else "")
        trace.write("call_text_response", result=result)
        return result

    def patched_call_reasoned_tool(reasoner_system, messages, tools, tool_name, **kwargs):
        preview = _preview_messages(messages)
        agent_log.push("request", f"call_reasoned_tool: {tool_name}", preview)
        trace.write("call_reasoned_tool_request", tool_name=tool_name, system=reasoner_system, messages=messages)
        result = _orig_call_reasoned_tool(reasoner_system, messages, tools, tool_name, **kwargs)
        agent_log.push("response", f"call_reasoned_tool: {tool_name} complete")
        trace.write("call_reasoned_tool_response", tool_name=tool_name, result=result)
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

    # Patch call_tool_loop which drives the multi-turn skill runner.
    # Must match the exact signature — no **kwargs.
    try:
        import llm_caller.tool_loop as tool_loop
        _orig_call_tool_loop = tool_loop.call_tool_loop
        _orig_make_turn_logger = tool_loop.make_turn_logger

        def _summarize_tool_input(name, args):
            """Build a concise summary of a tool call's input."""
            if not isinstance(args, dict):
                return ""
            parts = [name]
            for key in ("path", "command", "file_path", "pattern"):
                if key in args:
                    parts.append(f"{key}={str(args[key])[:150]}")
            # For edit_file, show what's being changed
            if name == "edit_file" and "new_content" in args:
                preview = str(args["new_content"])[:80].replace("\n", "\\n")
                parts.append(f"content={preview}")
            elif name == "write_file" and "content" in args:
                lines = str(args["content"]).count("\n") + 1
                parts.append(f"({lines} lines)")
            return "  ".join(parts)

        # Tools that mutate files — only these count against the edit budget
        _EDIT_TOOLS = {"edit_file", "write_file"}

        def _wrap_dispatcher(dispatcher, final_tool_name, edit_budget):
            """Wrap tool_dispatcher to log calls/results and enforce edit budget.

            Only edit/write tool calls consume budget. Read, list, and run
            operations are free.
            """
            state = {"edits_remaining": edit_budget}

            def logging_dispatcher(name, args):
                input_summary = _summarize_tool_input(name, args)
                trace.write("tool_call", tool=name, input=args)

                # Enforce edit budget
                if name in _EDIT_TOOLS:
                    if state["edits_remaining"] <= 0:
                        msg = (
                            f"Edit budget exhausted ({edit_budget} edits). "
                            f"You must call {final_tool_name} now with your "
                            f"current progress."
                        )
                        agent_log.push("info", f"tool BLOCKED: {name}", msg)
                        trace.write("tool_blocked", tool=name, reason=msg)
                        return msg
                    state["edits_remaining"] -= 1
                    agent_log.push(
                        "info",
                        f"tool call: {name} (edits left: {state['edits_remaining']})",
                        input_summary,
                    )
                else:
                    agent_log.push("info", f"tool call: {name}", input_summary)

                result = dispatcher(name, args)
                trace.write("tool_result", tool=name, output=result)
                # Log the tool output (truncated for console)
                if result:
                    output = str(result)[:300].replace("\n", "\\n")
                    agent_log.push("info", f"tool result: {name}", output)
                return result
            return logging_dispatcher

        def _wrap_on_turn(orig_on_turn, final_tool_name):
            """Wrap an on_turn callback to also push to agent_log."""
            def logging_on_turn(turn_number, history):
                # Write full history of last two messages (assistant + tool results) to trace
                recent = []
                for msg in reversed(history):
                    if isinstance(msg, dict):
                        recent.append(msg)
                    if len(recent) >= 2:
                        break
                trace.write("turn", turn=turn_number, final_tool=final_tool_name, messages=list(reversed(recent)))

                # Summarize the latest assistant message — show ALL tool calls and text
                details = []
                for msg in reversed(history):
                    if not isinstance(msg, dict) or msg.get("role") != "assistant":
                        continue
                    content = msg.get("content", "")
                    if isinstance(content, str) and content.strip():
                        details.append(f"text: {content[:200]}")
                    elif isinstance(content, list):
                        for block in content:
                            if not isinstance(block, dict):
                                continue
                            if block.get("type") == "tool_use":
                                inp = block.get("input", {})
                                details.append(_summarize_tool_input(
                                    block.get("name", "?"), inp,
                                ))
                            elif block.get("type") == "text" and block.get("text", "").strip():
                                details.append(f"text: {block['text'][:150]}")
                    break
                detail = " | ".join(details) if details else "(no tool calls)"
                agent_log.push("turn", f"Turn {turn_number} ({final_tool_name})", detail)
                if orig_on_turn:
                    return orig_on_turn(turn_number, history)
            return logging_on_turn

        # Hard ceiling on total LLM calls to prevent runaway loops.
        # The real budget is the edit budget enforced by the dispatcher.
        _HARD_TURN_CEILING = 200

        def patched_call_tool_loop(
            system, messages, tools, final_tool_name, tool_dispatcher,
            model="", max_tokens=4096, max_turns=10, prompt_log_file="",
        ):
            agent_log.push(
                "request",
                f"tool_loop: {final_tool_name} (edit budget: {max_turns})",
                _preview_messages(messages),
            )
            trace.write(
                "tool_loop_start",
                final_tool=final_tool_name,
                edit_budget=max_turns,
                system=system,
                messages=messages,
            )
            # max_turns becomes the edit budget; the backend gets a high ceiling
            wrapped_dispatcher = _wrap_dispatcher(
                tool_dispatcher, final_tool_name, edit_budget=max_turns,
            )

            # Always create an on_turn callback for the agent console,
            # wrapping the original file-logger if prompt_log_file is set.
            orig_on_turn = None
            if prompt_log_file:
                orig_on_turn = _orig_make_turn_logger(prompt_log_file, system, final_tool_name)
            logging_on_turn = _wrap_on_turn(orig_on_turn, final_tool_name)

            # Call the backends directly with our on_turn, bypassing the
            # original call_tool_loop which only creates on_turn for file logging.
            from llm_caller.config import BACKEND, resolve_model
            resolved_model = resolve_model(model, BACKEND)

            if BACKEND == "openai":
                from llm_caller.backends.openai import call_openai_loop
                result, history = call_openai_loop(
                    system, messages, tools, final_tool_name,
                    wrapped_dispatcher, resolved_model, max_tokens, _HARD_TURN_CEILING,
                    on_turn=logging_on_turn,
                )
            elif BACKEND == "gemini":
                from llm_caller.backends.gemini import call_gemini_loop
                result, history = call_gemini_loop(
                    system, messages, tools, final_tool_name,
                    wrapped_dispatcher, resolved_model, max_tokens, _HARD_TURN_CEILING,
                    on_turn=logging_on_turn,
                )
            else:
                from llm_caller.backends.anthropic import call_anthropic_loop
                result, history = call_anthropic_loop(
                    system, messages, tools, final_tool_name,
                    wrapped_dispatcher, resolved_model, max_tokens, _HARD_TURN_CEILING,
                    on_turn=logging_on_turn,
                )

            # Write final conversation log if logging is enabled
            if prompt_log_file:
                import json
                from llm_caller.logging import write_conversation_log
                write_conversation_log(prompt_log_file, system, history, final_tool_name)
                response_path = os.path.splitext(prompt_log_file)[0] + "_response.json"
                os.makedirs(os.path.dirname(response_path) or ".", exist_ok=True)
                with open(response_path, "w") as f:
                    json.dump(result, f, indent=2)

            agent_log.push("response", f"tool_loop: {final_tool_name} complete")
            trace.write("tool_loop_end", final_tool=final_tool_name, result=result)
            return result

        tool_loop.call_tool_loop = patched_call_tool_loop

        # Also patch the top-level export
        try:
            import llm_caller
            if hasattr(llm_caller, "call_tool_loop"):
                llm_caller.call_tool_loop = patched_call_tool_loop
        except (ImportError, AttributeError):
            pass

    except (ImportError, AttributeError):
        pass
