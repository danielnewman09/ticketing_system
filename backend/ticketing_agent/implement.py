"""Agent: fill in skeleton code with real implementation logic.

Takes a task, its skeleton code, design context, and verification methods
and produces working Python implementations.

Usage:
    from backend.ticketing_agent.implement import implement_task

    result = implement_task(
        task=task_schema,
        skeleton_code=source_code,
        design_classes=design,
        verifications=verifications,
        test_code=test_source,
    )
"""

import logging
from dataclasses import dataclass, field

from backend.ticketing_agent.implement_prompt import (
    SYSTEM_PROMPT,
    TOOL_DEFINITION,
    build_implementation_context,
)

log = logging.getLogger("agents.implement")


@dataclass
class ImplementationFile:
    """One implemented source file."""
    file_path: str
    content: str
    classes_modified: list[str] = field(default_factory=list)


def implement_task(
    task_title: str,
    task_description: str,
    skeleton_code: str = "",
    design_classes: list[dict] | None = None,
    verifications: list[dict] | None = None,
    test_code: str = "",
    llr_description: str = "",
    model: str = "",
    prompt_log_file: str = "",
) -> list[ImplementationFile]:
    """Generate implementation for one task.

    Args:
        task_title: Short name of the task.
        task_description: What the task builds.
        skeleton_code: The empty class/method stubs to fill in.
        design_classes: Design context for the classes this task touches.
        verifications: Verification methods for this task.
        test_code: Test source that must pass.
        llr_description: LLR description for context.
        model: LLM model override.
        prompt_log_file: Log path for prompt conversation.

    Returns:
        List of ImplementationFile with filled-in source code.
    """
    context = build_implementation_context(
        task_title=task_title,
        task_description=task_description,
        skeleton_code=skeleton_code,
        design_classes=design_classes,
        verifications=verifications,
        test_code=test_code,
        llr_description=llr_description,
    )

    user_msg = (
        f"Implement the following task by filling in the skeleton code:\n\n{context}"
    )

    from llm_caller import call_tool

    result = call_tool(
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
        tools=[TOOL_DEFINITION],
        tool_name="produce_implementation",
        model=model,
        prompt_log_file=prompt_log_file,
    )

    return [
        ImplementationFile(
            file_path=f["file_path"],
            content=f["content"],
            classes_modified=f.get("classes_modified", []),
        )
        for f in result["files"]
    ]


# ---------------------------------------------------------------------------
# Deterministic implementation (bootstrap / fallback)
# ---------------------------------------------------------------------------

def implement_deterministic(
    task_title: str,
    task_description: str,
    skeleton_code: str = "",
    verifications: list[dict] | None = None,
    llr_id: int = 0,
) -> list[ImplementationFile]:
    """Generate a basic implementation without LLM.

    Adds minimal pass bodies with TODO comments referencing verifications.
    Useful for bootstrapping — the real implementation comes from the LLM.
    """
    return [ImplementationFile(
        file_path="src/implemented.py",  # placeholder
        content=skeleton_code or "# No skeleton provided\npass\n",
        classes_modified=[],
    )]


def write_implementation_files(
    implementations: list[ImplementationFile],
    workspace_dir: str,
) -> list[str]:
    """Write implementation files to disk.

    Args:
        implementations: List of ImplementationFile from implement_task.
        workspace_dir: Root directory for output.

    Returns:
        List of written file paths.
    """
    from pathlib import Path

    written = []
    for impl in implementations:
        full_path = Path(workspace_dir) / impl.file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(impl.content)
        written.append(str(full_path))
        log.info("Wrote implementation: %s", full_path)

    return written
