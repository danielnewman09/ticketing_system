"""
Agent that decomposes a high-level requirement description into
low-level requirements with verification methods.

Can be used standalone (CLI) or imported by Django views/management commands.
"""

import json

from llm_caller import call_tool
from backend.db.models.requirements import format_hlr_dict
from backend.requirements.schemas import DecomposedRequirementSchema as DecomposedRequirement


SYSTEM_PROMPT = """\
You are a requirements engineering agent. Your job is to decompose a high-level
requirement description into low-level requirements.

For the high-level requirement itself, provide a clear prose description that
captures the intent.

Then, decompose it into low-level requirements.
Each LLR shall:
- Include a prose description of the specific behavior
- Have one or more verification methods, each with:
  - method: one of "automated", "review", or "inspection"
  - confirmation: how we know the requirement is met (e.g., "the operator field
    is populated with the ADDITION enum value")
  - test_name: a snake_case test function name that would verify this
    (e.g., "user_presses_addition_key")

Guidelines:
- LLRs shall be atomic and testable
- Each LLR shall map to a single observable behavior
- Prefer "automated" verification where the behavior is programmatically testable
- Use "review" for design/UX concerns and "inspection" for documentation/process
- test_name should be descriptive and follow snake_case convention
- Generate enough LLRs to fully cover the HLR, but no more than necessary
- Focus strictly on the scope of the target HLR. If other HLRs are provided as
  context, do NOT generate LLRs that belong to those other HLRs. Use them only
  to understand boundaries and avoid overlap.

You MUST use the decompose_requirement tool to return your result.
"""

TOOL_DEFINITION = {
    "name": "decompose_requirement",
    "description": "Return the structured decomposition of a high-level requirement",
    "input_schema": DecomposedRequirement.model_json_schema(),
}


def _format_sibling_context(other_hlrs: list[dict]) -> str:
    """Format sibling HLRs into a context block for the prompt."""
    if not other_hlrs:
        return ""
    lines = [
        "\n\nOther HLRs in the system (for context only — do NOT decompose these, "
        "only use them to understand scope boundaries):\n"
    ]
    for hlr in other_hlrs:
        lines.append(f"- {format_hlr_dict(hlr, include_component=True)}")
    return "\n".join(lines)


def _format_dependency_context(dependency_context: dict) -> str:
    """Format dependency assessment into a context block for the prompt."""
    if not dependency_context:
        return ""
    rec = dependency_context.get("recommendation", "none")
    if rec == "none":
        return ""
    lines = ["\n\n## Available Dependencies\n"]
    lines.append(f"- Recommendation: {rec}")
    dep_name = dependency_context.get("dependency_name", "")
    if dep_name:
        lines.append(f"- Dependency: {dep_name}")
    structures = dependency_context.get("relevant_structures", [])
    if structures:
        lines.append(f"- Relevant structures: {', '.join(structures)}")
    rationale = dependency_context.get("rationale", "")
    if rationale:
        lines.append(f"- Rationale: {rationale}")
    lines.append(
        "\nDo not create LLRs for functionality the dependency already handles."
    )
    return "\n".join(lines)


def decompose(
    description: str,
    other_hlrs: list[dict] | None = None,
    component: str = "",
    dependency_context: dict | None = None,
    model: str = "",
    prompt_log_file: str = "",
) -> DecomposedRequirement:
    """
    Takes a human-written HLR description and returns a structured decomposition.

    other_hlrs: Optional list of sibling HLR dicts ({id, description,
        component__name}) to provide scope context and ensure separation
        of concerns.
    component: Name of the architectural component this HLR belongs to.
    """
    user_content = f"Decompose this high-level requirement:\n\n{description}"
    if component:
        user_content += (
            f"\n\nThis HLR belongs to the **{component}** component. "
            "Keep LLRs focused on this component's scope."
        )
    user_content += _format_sibling_context(other_hlrs or [])
    user_content += _format_dependency_context(dependency_context or {})

    result = call_tool(
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": user_content,
            }
        ],
        tools=[TOOL_DEFINITION],
        tool_name="decompose_requirement",
        model=model,
        prompt_log_file=prompt_log_file,
    )

    return DecomposedRequirement.model_validate(result)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m requirements.agents.decompose_hlr 'description of requirement'")
        sys.exit(1)

    description = " ".join(sys.argv[1:])
    result = decompose(description)
    print(json.dumps(result.model_dump(), indent=2))
