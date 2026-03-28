"""
Generic skill runner: execute any skill directory via the LLM tool loop.

Discovers templates from the skill's ``assets/`` and ``references/``
directories, builds a system prompt from ``SKILL.md``, and gives the
LLM terminal tools to create/edit files and run commands.

Usage
-----
::

    from llm_caller.skill_runner import run_skill

    result = run_skill(
        skill_dir="skills/cpp-project-scaffold",
        user_message="Scaffold a C++ project called my-engine with libraries core and physics",
        working_directory="/tmp/projects",
    )
"""

import logging
from pathlib import Path

from llm_caller.tool_loop import call_tool_loop
from llm_caller.tools.terminal import TOOL_DEFINITIONS, make_dispatcher

log = logging.getLogger("llm_caller.skill_runner")


# ---------------------------------------------------------------------------
# Skill directory loading
# ---------------------------------------------------------------------------

def _collect_files(directory: Path) -> dict[str, str]:
    """Recursively read all .md files under *directory*.

    Returns a dict mapping display names (relative path minus the .md
    suffix) to file contents.  Sorted alphabetically for determinism.
    """
    if not directory.is_dir():
        return {}
    result = {}
    for f in sorted(directory.rglob("*.md")):
        key = str(f.relative_to(directory)).removesuffix(".md")
        result[key] = f.read_text()
    return result


def build_system_prompt(skill_dir: str | Path) -> str:
    """Build the full system prompt by discovering templates from *skill_dir*.

    Expects the skill directory to contain:
    - ``SKILL.md``  — skill manifest (instructions for the LLM)
    - ``assets/``   — file templates (globbed recursively)
    - ``references/`` (optional) — naming conventions, patterns, etc.
    """
    skill_dir = Path(skill_dir).resolve()
    if not skill_dir.is_dir():
        raise ValueError(f"Skill directory does not exist: {skill_dir}")

    # Read the skill manifest
    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists():
        raw = skill_md.read_text()
        parts = raw.split("---", 2)
        skill_body = parts[2].strip() if len(parts) >= 3 else raw
    else:
        skill_body = ""

    # Discover assets and references
    assets = _collect_files(skill_dir / "assets")
    references = _collect_files(skill_dir / "references")

    reference_sections = []
    for name, content in references.items():
        reference_sections.append(f"### Reference: {name}\n\n{content}")
    references_text = "\n\n---\n\n".join(reference_sections) if reference_sections else ""

    template_sections = []
    for name, content in assets.items():
        template_sections.append(f"### Template: {name}\n\n{content}")
    templates_text = "\n\n---\n\n".join(template_sections) if template_sections else ""

    return f"""\
You are an agent that modifies a project by writing and editing files.
You have access to terminal tools: write_file, edit_file, read_file,
list_directory, and run_command.

## Skill Instructions

{skill_body}

## Reference Materials

{references_text}

## File Templates

Use these templates as the basis for each generated file.  Replace template
variables with the actual values from the user's specification.  Adapt
conditional sections as needed.

{templates_text}

## Important Rules

- Start by reading the existing project files to understand the current state.
- Use write_file for new files, edit_file for modifying existing files.
- After making changes, run the build verification commands from the
  skill instructions above.
- If a build fails, read the error output and use edit_file to make
  targeted fixes.
- When done, call task_complete with your summary.
"""


# ---------------------------------------------------------------------------
# Final tool
# ---------------------------------------------------------------------------

FINAL_TOOL_NAME = "task_complete"

FINAL_TOOL_DEFINITION = {
    "name": FINAL_TOOL_NAME,
    "description": (
        "Call this tool when you have finished the task and verified "
        "the build succeeds.  Provide a summary of what was done."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "A brief summary of what was done.",
            },
            "files_modified": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of file paths that were created or modified.",
            },
            "build_success": {
                "type": "boolean",
                "description": "Whether the project built and tests passed.",
            },
        },
        "required": ["summary", "files_modified"],
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_skill(
    skill_dir: str,
    user_message: str,
    working_directory: str,
    model: str = "",
    max_tokens: int = 4096,
    max_turns: int = 50,
    prompt_log_file: str = "",
) -> dict:
    """Run a skill via the LLM tool loop with terminal tools.

    Args:
        skill_dir: Path to the skill directory (SKILL.md + assets/ + references/).
        user_message: The task description for the LLM.
        working_directory: Absolute path to the project root.
        model: LLM model override.
        max_tokens: Max tokens per LLM turn.
        max_turns: Safety limit on loop iterations.
        prompt_log_file: If set, conversation log is written here after every turn.

    Returns:
        Dict from the task_complete tool call with keys:
            summary, files_modified, build_success
    """
    system = build_system_prompt(skill_dir)
    messages = [{"role": "user", "content": user_message}]
    tools = TOOL_DEFINITIONS + [FINAL_TOOL_DEFINITION]
    dispatcher = make_dispatcher(working_directory)

    log.info("Running skill=%s, cwd=%s", skill_dir, working_directory)

    result = call_tool_loop(
        system=system,
        messages=messages,
        tools=tools,
        final_tool_name=FINAL_TOOL_NAME,
        tool_dispatcher=dispatcher,
        model=model,
        max_tokens=max_tokens,
        max_turns=max_turns,
        prompt_log_file=prompt_log_file,
    )

    log.info(
        "Skill complete: %d files, build_success=%s",
        len(result.get("files_modified", [])),
        result.get("build_success"),
    )

    return result
