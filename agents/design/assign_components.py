"""
Agent that assigns HLRs to architectural components.

Given all HLR descriptions and any existing components, determines which
component each HLR belongs to — creating new components where needed.

This runs before decomposition so that each HLR has architectural context,
which helps the decompose agent maintain separation of concerns.
"""

from agents.llm_client import call_tool
from db.models.requirements import format_hlrs_for_prompt


SYSTEM_PROMPT = """\
You are a software architect. Given a set of high-level requirements (HLRs)
and any existing architectural components, your job is to assign each HLR to
exactly one component.

Components represent major architectural building blocks of the system (e.g.,
"Core Engine", "User Interface", "Error Handling", "Data Persistence"). They
are coarse-grained — typically a system has 3–8 components, not one per HLR.

Rules:
- Every HLR must be assigned to exactly one component.
- Reuse existing components where they fit. Only create a new component when
  no existing one covers the HLR's scope.
- Component names should be short and descriptive (2–4 words).
- Multiple HLRs can share the same component. This is expected and desirable
  when they address different aspects of the same architectural concern.
- Do NOT create a new component for each HLR — group related HLRs together.

You MUST use the assign_components tool to return your result.
"""

TOOL_DEFINITION = {
    "name": "assign_components",
    "description": "Assign each HLR to an architectural component",
    "input_schema": {
        "type": "object",
        "properties": {
            "assignments": {
                "type": "array",
                "description": "One entry per HLR",
                "items": {
                    "type": "object",
                    "properties": {
                        "hlr_id": {
                            "type": "integer",
                            "description": "The HLR ID",
                        },
                        "component_name": {
                            "type": "string",
                            "description": (
                                "Name of the component (existing or new). "
                                "Must match an existing component name exactly "
                                "if reusing one."
                            ),
                        },
                        "rationale": {
                            "type": "string",
                            "description": "Why this HLR belongs to this component",
                        },
                    },
                    "required": ["hlr_id", "component_name", "rationale"],
                },
            },
        },
        "required": ["assignments"],
    },
}


def assign_components(
    hlrs: list[dict],
    existing_components: list[str] | None = None,
    model: str = "",
    prompt_log_file: str = "",
) -> list[dict]:
    """Assign each HLR to an architectural component.

    Args:
        hlrs: List of dicts with 'id' and 'description' keys.
        existing_components: Optional list of component names already in the DB.
        model: LLM model override.
        prompt_log_file: Optional path to log the prompt.

    Returns:
        List of dicts with 'hlr_id', 'component_name', and 'rationale'.
    """
    hlr_text = format_hlrs_for_prompt(hlrs)

    components_text = ""
    if existing_components:
        components_text = (
            "\n\nExisting components (reuse where appropriate):\n"
            + "\n".join(f"- {name}" for name in existing_components)
        )

    result = call_tool(
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Assign these {len(hlrs)} HLRs to architectural components:\n\n"
                    f"{hlr_text}"
                    f"{components_text}"
                ),
            }
        ],
        tools=[TOOL_DEFINITION],
        tool_name="assign_components",
        model=model,
        prompt_log_file=prompt_log_file,
    )

    assignments = result.get("assignments", [])

    # Validate: every HLR should have an assignment
    all_ids = {h["id"] for h in hlrs}
    assigned_ids = {a["hlr_id"] for a in assignments}
    for missing_id in all_ids - assigned_ids:
        assignments.append({
            "hlr_id": missing_id,
            "component_name": "Unassigned",
            "rationale": "not assigned by agent",
        })

    return assignments
