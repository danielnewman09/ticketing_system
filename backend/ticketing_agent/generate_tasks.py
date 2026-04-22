"""Agent: generate scoped implementation tasks from OO design + verification."""

import logging

from llm_caller import call_tool

from backend.pipeline.schemas import TaskBatchSchema
from backend.ticketing_agent.generate_tasks_prompt import (
    SYSTEM_PROMPT,
    TOOL_DEFINITION,
    build_task_context,
)

log = logging.getLogger("agents.generate_tasks")


def generate_tasks(
    hlr: dict,
    llrs: list[dict],
    oo_design: dict,
    verifications: list[dict],
    existing_classes: list[dict] | None = None,
    model: str = "",
    prompt_log_file: str = "",
) -> TaskBatchSchema:
    """Generate implementation tasks from design and verification context.

    Args:
        hlr: HLR dict with {id, description, component_name}.
        llrs: LLR dicts for this HLR.
        oo_design: Dict representation of the OODesignSchema
            (classes, interfaces, etc.).
        verifications: Verification dicts from verification methods.
        existing_classes: Already-designed classes to exclude.
        model: LLM model override.
        prompt_log_file: Log path for the prompt conversation.

    Returns:
        TaskBatchSchema with ordered, dependency-linked tasks.
    """
    context = build_task_context(
        classes=oo_design.get("classes", []),
        verifications=verifications,
        existing_classes=existing_classes or [],
    )

    component_name = hlr.get("component_name", "")
    user_msg = (
        f"Generate implementation tasks for component '{component_name}' "
        f"(HLR {hlr['id']}).\n\n{context}"
    )

    result = call_tool(
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
        tools=[TOOL_DEFINITION],
        tool_name="generate_tasks",
        model=model,
        prompt_log_file=prompt_log_file,
    )

    return TaskBatchSchema.model_validate(result)
