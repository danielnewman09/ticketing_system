"""
Agent: scaffold a project using the tool loop and terminal tools.

Splits the work into two phases with separate LLM contexts:
  1. **Write phase** — generates all project files using skill templates
  2. **Build phase** — fresh context via the verify-build skill

Usage
-----
::

    from backend.ticketing_agent.design.scaffold_project import scaffold_project

    result = scaffold_project(
        skill_dir="skills/cpp-project-scaffold",
        project_name="my-engine",
        libraries=[
            {"name": "core"},
            {"name": "physics", "depends_on": ["core"]},
        ],
        working_directory="/tmp/projects",
    )
"""

import logging
import os

from llm_caller.skill_runner import build_system_prompt, run_skill
from llm_caller.tool_loop import call_tool_loop
from llm_caller.tools.terminal import TOOL_DEFINITIONS, make_dispatcher

from backend.ticketing_agent.design.scaffold_project_prompt import build_user_message

log = logging.getLogger(__name__)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
_VERIFY_BUILD_SKILL = os.path.join(_REPO_ROOT, "skills", "verify-build")

# Phase-1 final tool: signals that file generation is done
_WRITE_COMPLETE_TOOL = {
    "name": "write_complete",
    "description": (
        "Call this tool when you have finished generating ALL project files. "
        "Do NOT run any build or test commands — a separate phase handles that."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "Brief summary of the files generated.",
            },
            "files_modified": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of file paths that were created or modified.",
            },
        },
        "required": ["summary", "files_modified"],
    },
}


def scaffold_project(
    skill_dir: str,
    project_name: str,
    libraries: list[dict],
    working_directory: str,
    extra_dependencies: list[str] | None = None,
    cpp_standard: int = 20,
    model: str = "",
    max_tokens: int = 4096,
    max_turns: int = 50,
    prompt_log_file: str = "",
) -> dict:
    """Scaffold a project via the LLM tool loop in two phases.

    Phase 1 (write): Generates all project files using the skill's templates
    and instructions. Ends when the LLM calls write_complete.

    Phase 2 (build): Fresh context via the verify-build skill. Runs conan
    install, cmake, and ctest. Fixes errors if needed.

    Args:
        skill_dir: Path to the skill directory.
        project_name: Kebab-case project name (e.g. "my-engine").
        libraries: List of library specs (name, header_only, depends_on, external_deps).
        working_directory: Absolute path where the project dir will be created.
        extra_dependencies: Additional Conan dependencies for the whole project.
        cpp_standard: C++ standard version (20, 23, or 26).
        model: LLM model override.
        max_tokens: Max tokens per LLM turn.
        max_turns: Safety limit for the build verification phase.
        prompt_log_file: If set, write conversation logs here.

    Returns:
        Dict with keys: summary, files_modified, build_success
    """
    user_msg = build_user_message(
        project_name=project_name,
        libraries=libraries,
        extra_dependencies=extra_dependencies,
        cpp_standard=cpp_standard,
    )

    dispatcher = make_dispatcher(working_directory)

    # --- Phase 1: Write all project files ---
    log.info("Phase 1 (write): skill=%s, cwd=%s", skill_dir, working_directory)

    write_system = build_system_prompt(skill_dir)
    write_system += (
        "\n\n## IMPORTANT\n\n"
        "Generate ALL project files, then call `write_complete`. "
        "Do NOT run any build commands (conan, cmake, ctest). "
        "A separate build phase will handle verification."
    )

    write_log = ""
    if prompt_log_file:
        base, ext = os.path.splitext(prompt_log_file)
        write_log = f"{base}_write{ext}"

    write_tools = TOOL_DEFINITIONS + [_WRITE_COMPLETE_TOOL]

    # Write phase is predictable file generation — give it a generous
    # fixed budget that doesn't eat into the retry budget.
    write_result = call_tool_loop(
        system=write_system,
        messages=[{"role": "user", "content": user_msg}],
        tools=write_tools,
        final_tool_name="write_complete",
        tool_dispatcher=dispatcher,
        model=model,
        max_tokens=max_tokens,
        max_turns=100,
        prompt_log_file=write_log,
    )

    files_written = write_result.get("files_modified", [])
    log.info("Phase 1 complete: %d files written", len(files_written))

    # --- Phase 2: Build verification (fresh context via verify-build skill) ---
    # The full max_turns budget goes here — this is where retries matter.
    log.info("Phase 2 (build): verifying project builds")

    build_log = ""
    if prompt_log_file:
        base, ext = os.path.splitext(prompt_log_file)
        build_log = f"{base}_build{ext}"

    project_dir = os.path.join(working_directory, project_name)
    files_list = "\n".join(f"- {f}" for f in files_written)
    build_msg = (
        f"Verify the build for `{project_name}`.\n\n"
        f"The project was just scaffolded. Files created:\n{files_list}"
    )

    build_result = run_skill(
        skill_dir=_VERIFY_BUILD_SKILL,
        user_message=build_msg,
        working_directory=project_dir,
        model=model,
        max_tokens=max_tokens,
        max_turns=max_turns,
        prompt_log_file=build_log,
    )

    # Merge results
    all_files = list(dict.fromkeys(
        files_written + build_result.get("files_modified", [])
    ))

    log.info(
        "Scaffold complete: %d files, build_success=%s",
        len(all_files), build_result.get("build_success"),
    )

    return {
        "summary": (
            f"Write phase: {write_result.get('summary', '')}\n\n"
            f"Build phase: {build_result.get('summary', '')}"
        ),
        "files_modified": all_files,
        "build_success": build_result.get("build_success", False),
    }
