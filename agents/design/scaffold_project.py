"""
Agent: scaffold a project using the tool loop and terminal tools.

Uses the LLM tool loop to drive a local model that creates project files
via terminal tools (write_file, run_command, etc.), guided by the templates
discovered from a skill directory.

Usage
-----
::

    from agents.design.scaffold_project import scaffold_project

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

from agents.llm_tool_loop import call_tool_loop
from agents.tools.terminal import TOOL_DEFINITIONS, make_dispatcher
from agents.design.scaffold_project_prompt import (
    build_system_prompt,
    build_user_message,
    FINAL_TOOL_NAME,
    FINAL_TOOL_DEFINITION,
)

log = logging.getLogger("agents.design.scaffold")


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
    """Scaffold a project via the LLM tool loop.

    Templates and references are discovered automatically from *skill_dir*
    (any ``.md`` files under ``assets/`` and ``references/``).

    The LLM creates all project files using terminal tools (write_file,
    run_command, list_directory, read_file) and verifies the build,
    then calls scaffold_complete to return a summary.

    Args:
        skill_dir: Path to the skill directory containing SKILL.md,
            assets/, and optionally references/.
        project_name: Kebab-case project name (e.g. "my-engine").
        libraries: List of library specs, each a dict with:
            - name (str): Library name
            - header_only (bool, optional): True for INTERFACE libs
            - depends_on (list[str], optional): Other library names
            - external_deps (list[str], optional): Conan package refs
        working_directory: Absolute path where the project dir will be created.
        extra_dependencies: Additional Conan dependencies for the whole project.
        cpp_standard: C++ standard version (20, 23, or 26).
        model: LLM model override (uses LLM_MODEL env var by default).
        max_tokens: Max tokens per LLM turn.
        max_turns: Safety limit — scaffold typically needs 20-40 turns.
        prompt_log_file: If set, write the full conversation log here.

    Returns:
        Dict from the scaffold_complete tool call with keys:
            summary, files_created, build_success
    """
    system = build_system_prompt(skill_dir)
    user_msg = build_user_message(
        project_name=project_name,
        libraries=libraries,
        extra_dependencies=extra_dependencies,
        cpp_standard=cpp_standard,
    )

    messages = [{"role": "user", "content": user_msg}]

    # All tools: terminal tools + the final "done" tool
    tools = TOOL_DEFINITIONS + [FINAL_TOOL_DEFINITION]

    # Dispatcher handles the terminal tools; the final tool terminates the loop
    dispatcher = make_dispatcher(working_directory)

    log.info(
        "Starting scaffold: skill=%s, project=%s, libs=%s, cwd=%s",
        skill_dir,
        project_name,
        [lib["name"] for lib in libraries],
        working_directory,
    )

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

    files = result.get("files_created", [])
    log.info(
        "Scaffold complete: %d files, build_success=%s",
        len(files),
        result.get("build_success"),
    )

    return result
