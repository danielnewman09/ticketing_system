"""Prompt and tool definitions for the project scaffold agent.

Generic: discovers templates from any skill directory that follows
the convention of having ``assets/`` and optionally ``references/``
subdirectories with ``.md`` files, plus a ``SKILL.md`` manifest.
"""

from pathlib import Path


def _collect_files(directory: Path) -> dict[str, str]:
    """Recursively read all .md files under *directory*.

    Returns a dict mapping display names (relative path minus the .md
    suffix) to file contents.  Sorted alphabetically for determinism.
    """
    if not directory.is_dir():
        return {}
    result = {}
    for f in sorted(directory.rglob("*.md")):
        # Use the path relative to the directory, strip .md suffix
        key = str(f.relative_to(directory)).removesuffix(".md")
        result[key] = f.read_text()
    return result


# ---------------------------------------------------------------------------
# Final tool — the LLM calls this when it's done scaffolding
# ---------------------------------------------------------------------------

FINAL_TOOL_NAME = "scaffold_complete"

FINAL_TOOL_DEFINITION = {
    "name": FINAL_TOOL_NAME,
    "description": (
        "Call this tool when you have finished creating all project files "
        "and verified the project builds successfully.  Provide a summary "
        "of what was created."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "A brief summary of the files created and build status.",
            },
            "files_created": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of file paths that were created (relative to project root).",
            },
            "build_success": {
                "type": "boolean",
                "description": "Whether the project built and tests passed successfully.",
            },
        },
        "required": ["summary", "files_created"],
    },
}


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

def build_system_prompt(skill_dir: str | Path) -> str:
    """Build the full system prompt by discovering templates from *skill_dir*.

    Expects the skill directory to contain:
    - ``SKILL.md``  — skill manifest (instructions for the LLM)
    - ``assets/``   — file templates (globbed recursively)
    - ``references/`` (optional) — naming conventions, patterns, etc.

    All ``.md`` files under assets/ and references/ are inlined into the
    prompt so the LLM has full context for file generation.
    """
    skill_dir = Path(skill_dir).resolve()
    if not skill_dir.is_dir():
        raise ValueError(f"Skill directory does not exist: {skill_dir}")

    # Read the skill manifest
    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists():
        # Strip YAML frontmatter (between --- delimiters)
        raw = skill_md.read_text()
        parts = raw.split("---", 2)
        skill_body = parts[2].strip() if len(parts) >= 3 else raw
    else:
        skill_body = ""

    # Discover assets and references
    assets = _collect_files(skill_dir / "assets")
    references = _collect_files(skill_dir / "references")

    # Build the references section
    reference_sections = []
    for name, content in references.items():
        reference_sections.append(f"### Reference: {name}\n\n{content}")
    references_text = "\n\n---\n\n".join(reference_sections) if reference_sections else ""

    # Build the templates section
    template_sections = []
    for name, content in assets.items():
        template_sections.append(f"### Template: {name}\n\n{content}")
    templates_text = "\n\n---\n\n".join(template_sections) if template_sections else ""

    return f"""\
You are a project scaffolding agent.  Your job is to create a complete,
buildable project skeleton by writing files into the working directory
using the tools available to you.

You have access to terminal tools: write_file, read_file, list_directory,
and run_command.  Use write_file to create each project file, and run_command
to verify the build at the end.

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

- Write files ONE AT A TIME using the write_file tool.
- The project directory is created inside the current working directory.
- Do NOT skip any files — generate the complete skeleton.
- After writing all files, run the build verification commands from the
  skill instructions above.
- If a build fails, read the error output, fix the file, and retry.
- When done, call scaffold_complete with the final summary.
"""


def build_user_message(
    project_name: str,
    libraries: list[dict],
    extra_dependencies: list[str] | None = None,
    cpp_standard: int = 20,
) -> str:
    """Build the user message describing the project to scaffold.

    Args:
        project_name: Kebab-case project name (e.g. "my-engine").
        libraries: List of dicts, each with:
            - name: Library name (e.g. "core")
            - header_only: bool (default False)
            - depends_on: list of other library names (default [])
            - external_deps: list of Conan package refs (default [])
        extra_dependencies: Additional Conan dependencies for the whole project.
        cpp_standard: C++ standard version (20, 23, or 26).
    """
    lines = [
        "Scaffold a C++ project with the following parameters:",
        "",
        f"**Project name:** `{project_name}`",
        f"**C++ standard:** C++{cpp_standard}",
    ]

    if extra_dependencies:
        deps_str = ", ".join(f"`{d}`" for d in extra_dependencies)
        lines.append(f"**Additional Conan dependencies:** {deps_str}")

    lines.append("")
    lines.append("**Libraries:**")
    lines.append("")

    for lib in libraries:
        name = lib["name"]
        kind = "header-only (INTERFACE)" if lib.get("header_only") else "compiled"
        lines.append(f"- **{name}** ({kind})")

        deps = lib.get("depends_on", [])
        if deps:
            lines.append(f"  - Depends on: {', '.join(deps)}")

        ext = lib.get("external_deps", [])
        if ext:
            lines.append(f"  - External dependencies: {', '.join(ext)}")

    lines.append("")
    lines.append(
        "Create ALL project files and verify the build passes.  "
        "Call scaffold_complete when done."
    )

    return "\n".join(lines)
