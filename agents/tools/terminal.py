"""Terminal command tool for the LLM tool loop.

Provides a sandboxed ``run_command`` tool that executes shell commands
**only** inside the configured project working directory.  The working
directory is read from the ``ProjectMeta`` table so it stays in sync
with whatever the user set in the dashboard.

Usage
-----
::

    from agents.tools.terminal import TOOL_DEFINITIONS, make_dispatcher

    dispatcher = make_dispatcher()          # reads working_directory from DB
    # -- or supply it explicitly --
    dispatcher = make_dispatcher("/abs/path/to/project")

    # Feed TOOL_DEFINITIONS + dispatcher into call_tool_loop's extra_tools
    # and tool_dispatcher respectively.
"""

import json
import logging
import os
import shlex
import subprocess
from pathlib import Path

log = logging.getLogger("agents.tools.terminal")

# Hard cap on stdout/stderr returned to the LLM to avoid blowing up context.
_MAX_OUTPUT_CHARS = 30_000

# Commands that are never allowed regardless of working directory.
_BLOCKED_COMMANDS = frozenset({
    "rm", "rmdir", "mkfs", "dd", "shutdown", "reboot",
    "halt", "poweroff", "kill", "killall", "pkill",
    "chmod", "chown", "chgrp", "sudo", "su", "doas",
    "curl", "wget", "nc", "ncat", "ssh", "scp", "sftp",
    "nohup", "disown",
})

# ---------------------------------------------------------------------------
# Tool definition (Anthropic format)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "run_command",
        "description": (
            "Execute a shell command inside the project working directory and "
            "return its stdout and stderr.  The command is run with a timeout "
            "and is restricted to the project directory — it cannot cd out or "
            "access files outside the project tree.  Use this to inspect the "
            "project: list files, read source code, run builds, execute tests, "
            "check git status, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": (
                        "The shell command to execute.  Examples: "
                        "'ls -la src/', 'cat CMakeLists.txt', "
                        "'grep -rn TODO src/', 'git log --oneline -10', "
                        "'cmake --build build'"
                    ),
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "list_directory",
        "description": (
            "List the contents of a directory inside the project working "
            "directory.  Returns file names, sizes, and types.  Use '.' or "
            "omit path for the project root."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Relative path within the project directory.  "
                        "Defaults to '.' (project root)."
                    ),
                    "default": ".",
                },
                "show_hidden": {
                    "type": "boolean",
                    "description": "Include hidden (dot) files.",
                    "default": False,
                },
            },
            "required": [],
        },
    },
    {
        "name": "read_file",
        "description": (
            "Read the contents of a file inside the project working directory.  "
            "Returns the file text, optionally limited to a line range."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the file within the project.",
                },
                "start_line": {
                    "type": "integer",
                    "description": "First line to read (1-based). Omit to start from the beginning.",
                },
                "end_line": {
                    "type": "integer",
                    "description": "Last line to read (inclusive). Omit to read to the end.",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "edit_file",
        "description": (
            "Replace an exact string match in a file with new content.  "
            "Prefer this over write_file for targeted fixes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the file within the project.",
                },
                "old_string": {
                    "type": "string",
                    "description": (
                        "The exact text to find in the file.  Must match exactly "
                        "including whitespace and indentation."
                    ),
                },
                "new_string": {
                    "type": "string",
                    "description": "The replacement text.",
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace all occurrences, not just the first.",
                    "default": False,
                },
            },
            "required": ["path", "old_string", "new_string"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Create or overwrite a file inside the project working directory.  "
            "Parent directories are created automatically.  Use this to generate "
            "source files, configuration files, build scripts, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path for the file within the project.",
                },
                "content": {
                    "type": "string",
                    "description": "The full text content to write to the file.",
                },
            },
            "required": ["path", "content"],
        },
    },
]


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _resolve_working_directory(working_directory: str | None) -> Path:
    """Return a validated absolute Path for the project root."""
    if working_directory:
        p = Path(working_directory).expanduser().resolve()
    else:
        # Fall back to DB-stored value
        try:
            from frontend.data import fetch_project_meta
            meta = fetch_project_meta()
            p = Path(meta["working_directory"]).expanduser().resolve()
        except Exception:
            raise ValueError(
                "No working directory supplied and could not read one from "
                "the project metadata table.  Configure it in the dashboard "
                "or pass it explicitly."
            )
    if not p.is_dir():
        raise ValueError(f"Working directory does not exist: {p}")
    return p


def _is_safe_path(root: Path, target: Path) -> bool:
    """Return True if *target* is inside *root* (after resolution)."""
    try:
        target.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _check_command_safety(command: str) -> str | None:
    """Return an error message if the command is unsafe, else None."""
    try:
        tokens = shlex.split(command)
    except ValueError as e:
        return f"Could not parse command: {e}"

    if not tokens:
        return "Empty command"

    # Check the base command name (strip any path prefix)
    base = os.path.basename(tokens[0])
    if base in _BLOCKED_COMMANDS:
        return f"Command '{base}' is not allowed"

    # Block piping into blocked commands
    for i, token in enumerate(tokens):
        if token in ("|", "&&", "||", ";") and i + 1 < len(tokens):
            next_base = os.path.basename(tokens[i + 1])
            if next_base in _BLOCKED_COMMANDS:
                return f"Piping into '{next_base}' is not allowed"

    return None


# ---------------------------------------------------------------------------
# Individual tool handlers
# ---------------------------------------------------------------------------

def _handle_run_command(root: Path, command: str) -> dict:
    safety_err = _check_command_safety(command)
    if safety_err:
        return {"error": safety_err}

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "HOME": str(Path.home())},
        )
        stdout = result.stdout[:_MAX_OUTPUT_CHARS]
        stderr = result.stderr[:_MAX_OUTPUT_CHARS]
        return {
            "exit_code": result.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }
    except subprocess.TimeoutExpired:
        return {"error": "Command timed out after 30 seconds"}
    except Exception as e:
        return {"error": str(e)}


def _handle_list_directory(root: Path, path: str = ".", show_hidden: bool = False) -> dict:
    target = (root / path).resolve()
    if not _is_safe_path(root, target):
        return {"error": f"Path '{path}' is outside the project directory"}
    if not target.is_dir():
        return {"error": f"Not a directory: {path}"}

    entries = []
    try:
        for item in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if not show_hidden and item.name.startswith("."):
                continue
            entries.append({
                "name": item.name,
                "type": "directory" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else None,
            })
    except PermissionError:
        return {"error": f"Permission denied: {path}"}

    return {"path": str(target.relative_to(root)), "entries": entries}


def _handle_edit_file(
    root: Path, path: str, old_string: str, new_string: str, replace_all: bool = False,
) -> dict:
    target = (root / path).resolve()
    if not _is_safe_path(root, target):
        return {"error": f"Path '{path}' is outside the project directory"}
    if not target.is_file():
        return {"error": f"Not a file: {path}"}

    try:
        content = target.read_text(errors="replace")
    except PermissionError:
        return {"error": f"Permission denied: {path}"}

    if old_string not in content:
        return {"error": "old_string not found in file"}

    if replace_all:
        count = content.count(old_string)
        new_content = content.replace(old_string, new_string)
    else:
        count = 1
        new_content = content.replace(old_string, new_string, 1)

    target.write_text(new_content)
    return {
        "path": str(target.relative_to(root)),
        "replacements": count,
    }


def _handle_write_file(root: Path, path: str, content: str) -> dict:
    target = (root / path).resolve()
    if not _is_safe_path(root, target):
        return {"error": f"Path '{path}' is outside the project directory"}

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return {
            "path": str(target.relative_to(root)),
            "bytes_written": len(content.encode()),
        }
    except PermissionError:
        return {"error": f"Permission denied: {path}"}
    except OSError as e:
        return {"error": str(e)}


def _handle_read_file(
    root: Path, path: str, start_line: int | None = None, end_line: int | None = None,
) -> dict:
    target = (root / path).resolve()
    if not _is_safe_path(root, target):
        return {"error": f"Path '{path}' is outside the project directory"}
    if not target.is_file():
        return {"error": f"Not a file: {path}"}

    try:
        lines = target.read_text(errors="replace").splitlines(keepends=True)
    except PermissionError:
        return {"error": f"Permission denied: {path}"}

    total = len(lines)
    start = max(1, start_line or 1)
    end = min(total, end_line or total)
    selected = lines[start - 1:end]
    content = "".join(selected)

    if len(content) > _MAX_OUTPUT_CHARS:
        content = content[:_MAX_OUTPUT_CHARS] + "\n... (truncated)"

    return {
        "path": str(target.relative_to(root)),
        "total_lines": total,
        "start_line": start,
        "end_line": end,
        "content": content,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def make_dispatcher(working_directory: str | None = None):
    """Create a tool dispatcher for terminal tools.

    Args:
        working_directory: Absolute path to the project root.
            If *None*, reads from the ``ProjectMeta`` table.

    Returns:
        A callable ``(tool_name, tool_input) -> str`` suitable for
        :func:`call_tool_loop`'s *tool_dispatcher* parameter.
    """
    root = _resolve_working_directory(working_directory)
    log.info("Terminal tools active — project root: %s", root)

    handler_map = {
        "run_command": lambda args: _handle_run_command(root, **args),
        "list_directory": lambda args: _handle_list_directory(root, **args),
        "read_file": lambda args: _handle_read_file(root, **args),
        "edit_file": lambda args: _handle_edit_file(root, **args),
        "write_file": lambda args: _handle_write_file(root, **args),
    }

    def dispatch(tool_name: str, tool_input: dict) -> str:
        handler = handler_map.get(tool_name)
        if not handler:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
        try:
            result = handler(tool_input)
            return json.dumps(result, default=str)
        except Exception as e:
            log.warning("Terminal tool %s failed: %s", tool_name, e, exc_info=True)
            return json.dumps({"error": str(e)})

    return dispatch


def make_composite_dispatcher(
    *dispatchers: tuple,
    working_directory: str | None = None,
):
    """Create a dispatcher that tries terminal tools first, then falls through.

    Use this to combine terminal tools with other tool dispatchers::

        from agents.tools.terminal import TOOL_DEFINITIONS, make_composite_dispatcher

        dispatcher = make_composite_dispatcher(
            existing_dispatcher,
            working_directory="/path/to/project",
        )

    Args:
        *dispatchers: Additional dispatcher callables to fall through to.
        working_directory: Project root (same as :func:`make_dispatcher`).

    Returns:
        A combined ``(tool_name, tool_input) -> str`` dispatcher.
    """
    terminal_dispatch = make_dispatcher(working_directory)
    terminal_names = {t["name"] for t in TOOL_DEFINITIONS}

    def dispatch(tool_name: str, tool_input: dict) -> str:
        if tool_name in terminal_names:
            return terminal_dispatch(tool_name, tool_input)
        for d in dispatchers:
            try:
                return d(tool_name, tool_input)
            except Exception:
                continue
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    return dispatch
