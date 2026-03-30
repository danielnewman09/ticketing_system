"""
Agent: integrate a Conan dependency using the tool loop in two phases.

Phase 1 (write): Creates the conan recipe, registers it in the root conanfile,
    updates VS Code tasks, and wires into the consuming library's CMakeLists.
Phase 2 (build): Fresh context via the verify-build skill to compile and test.
"""

import logging
import os

from llm_caller.skill_runner import build_system_prompt, run_skill
from llm_caller.tool_loop import call_tool_loop
from llm_caller.tools.terminal import TOOL_DEFINITIONS, make_dispatcher

log = logging.getLogger(__name__)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
_VERIFY_BUILD_SKILL = os.path.join(_REPO_ROOT, "skills", "verify-build")

_WRITE_COMPLETE_TOOL = {
    "name": "write_complete",
    "description": (
        "Call this tool when you have finished creating/editing ALL files for "
        "the dependency integration (conan recipe, root conanfile, VS Code tasks, "
        "consuming CMakeLists). Do NOT run any build commands — a separate phase "
        "handles build verification."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "Brief summary of what was created/modified.",
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


def integrate_dependency(
    skill_dir: str,
    dep_name: str,
    source_url: str,
    version: str,
    consuming_lib: str,
    working_directory: str,
    model: str = "",
    max_tokens: int = 4096,
    max_turns: int = 50,
    prompt_log_file: str = "",
) -> dict:
    """Integrate a Conan dependency in two phases.

    Phase 1 (write): Research the library, create the conan recipe, register
    it, update VS Code tasks, and wire into the consuming CMakeLists.

    Phase 2 (build): Fresh context via verify-build skill. Runs conan create,
    conan install, cmake, and tests. Fixes errors if needed.

    Args:
        skill_dir: Path to the add-conan-dependency skill directory.
        dep_name: Library name (e.g. "fltk", "spdlog").
        source_url: Git repo or download URL.
        version: Version or git tag.
        consuming_lib: Library that uses this dependency.
        working_directory: Absolute path to the project root.
        model: LLM model override.
        max_tokens: Max tokens per LLM turn.
        max_turns: Safety limit for the build verification phase.
        prompt_log_file: If set, write conversation logs here.

    Returns:
        Dict with keys: summary, files_modified, build_success
    """
    dispatcher = make_dispatcher(working_directory)

    # --- Phase 1: Write all files ---
    log.info("Phase 1 (write): integrating %s into %s", dep_name, consuming_lib)

    write_system = build_system_prompt(skill_dir)
    write_system += (
        "\n\n## IMPORTANT\n\n"
        "Create/edit ALL necessary files (conan recipe, root conanfile, "
        "VS Code tasks, consuming CMakeLists), then call `write_complete`. "
        "Do NOT run any build or conan commands — a separate build phase "
        "handles verification."
    )

    user_msg = (
        f"Add `{dep_name}` as a locally-built Conan dependency.\n\n"
        f"**Dependency name:** `{dep_name}`\n"
        f"**Source URL:** `{source_url}`\n"
        f"**Version/tag:** `{version}`\n"
        f"**Consuming library:** `{consuming_lib}`\n\n"
        f"Follow the skill instructions: research the library, create the "
        f"conan recipe, register it in the root conanfile, update VS Code "
        f"tasks, and wire into the consuming library's CMakeLists. "
        f"Call write_complete when all files are ready."
    )

    write_log = ""
    if prompt_log_file:
        base, ext = os.path.splitext(prompt_log_file)
        write_log = f"{base}_write{ext}"

    write_tools = TOOL_DEFINITIONS + [_WRITE_COMPLETE_TOOL]

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
    log.info("Phase 1 complete: %d files modified", len(files_written))

    # --- Phase 2: Build verification (fresh context) ---
    log.info("Phase 2 (build): verifying %s integration", dep_name)

    build_log = ""
    if prompt_log_file:
        base, ext = os.path.splitext(prompt_log_file)
        build_log = f"{base}_build{ext}"

    files_list = "\n".join(f"- {f}" for f in files_written)
    build_msg = (
        f"Verify the build after adding `{dep_name}` as a Conan dependency.\n\n"
        f"First, create the local Conan package:\n"
        f"```bash\n"
        f"conan create conan/{dep_name} --build=missing -s build_type=Debug\n"
        f"```\n\n"
        f"Then run the standard build pipeline to verify integration.\n\n"
        f"Files modified:\n{files_list}"
    )

    build_result = run_skill(
        skill_dir=_VERIFY_BUILD_SKILL,
        user_message=build_msg,
        working_directory=working_directory,
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
        "Integration complete: %d files, build_success=%s",
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
