"""
Agent: scaffold a project using the tool loop and terminal tools.

Thin wrapper around :func:`agents.skill_runner.run_skill` that builds
the user message from structured project parameters.

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

from agents.skill_runner import run_skill
from agents.design.scaffold_project_prompt import build_user_message


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

    Args:
        skill_dir: Path to the skill directory.
        project_name: Kebab-case project name (e.g. "my-engine").
        libraries: List of library specs (name, header_only, depends_on, external_deps).
        working_directory: Absolute path where the project dir will be created.
        extra_dependencies: Additional Conan dependencies for the whole project.
        cpp_standard: C++ standard version (20, 23, or 26).
        model: LLM model override.
        max_tokens: Max tokens per LLM turn.
        max_turns: Safety limit — scaffold typically needs 20-40 turns.
        prompt_log_file: If set, write the full conversation log here.

    Returns:
        Dict with keys: summary, files_modified, build_success
    """
    user_msg = build_user_message(
        project_name=project_name,
        libraries=libraries,
        extra_dependencies=extra_dependencies,
        cpp_standard=cpp_standard,
    )

    return run_skill(
        skill_dir=skill_dir,
        user_message=user_msg,
        working_directory=working_directory,
        model=model,
        max_tokens=max_tokens,
        max_turns=max_turns,
        prompt_log_file=prompt_log_file,
    )
