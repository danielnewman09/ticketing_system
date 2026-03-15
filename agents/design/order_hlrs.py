"""
Agent that determines the optimal design order for HLRs.

Analyzes all HLRs and orders them so foundational requirements (data models,
core abstractions, infrastructure) are designed before requirements that
depend on them (UI, error handling, reporting).

This ensures that when designing classes for a later HLR, the classes it
depends on already exist in the ontology.
"""

from agents.llm_client import call_tool
from db.models.requirements import format_hlrs_for_prompt


SYSTEM_PROMPT = """\
You are a software architecture analyst. Given a set of high-level requirements
(HLRs), your job is to determine the optimal order in which they should be
designed as classes and interfaces.

Foundational requirements should come first:
- Data models and core domain objects
- Core business logic and algorithms
- Infrastructure and shared services
- Interfaces and contracts

Dependent requirements should come later:
- UI and presentation layers (they depend on the core domain)
- Error handling and validation (they wrap core operations)
- Reporting and history features (they observe core objects)
- Integration and orchestration (they compose multiple core components)

For each HLR, provide:
- **id**: the HLR's ID (integer)
- **rationale**: a brief explanation of why it belongs at this position
  in the ordering (what it depends on, or what depends on it)

You MUST use the order_hlrs tool to return your result. Return ALL HLR IDs
exactly once, ordered from most foundational to most dependent.
"""

TOOL_DEFINITION = {
    "name": "order_hlrs",
    "description": "Return the HLRs in optimal design order (foundational first)",
    "input_schema": {
        "type": "object",
        "properties": {
            "ordered_hlrs": {
                "type": "array",
                "description": "HLRs in design order, foundational first",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "integer",
                            "description": "The HLR ID",
                        },
                        "rationale": {
                            "type": "string",
                            "description": "Why this HLR belongs at this position",
                        },
                    },
                    "required": ["id", "rationale"],
                },
            },
        },
        "required": ["ordered_hlrs"],
    },
}


def order_hlrs(
    hlrs: list[dict],
    model: str = "",
    prompt_log_file: str = "",
) -> list[dict]:
    """Order HLRs by design dependency (foundational first).

    Args:
        hlrs: List of dicts with 'id' and 'description' keys.
        model: LLM model override.
        prompt_log_file: Optional path to log the prompt.

    Returns:
        List of dicts with 'id' and 'rationale', ordered foundational-first.
        Any HLR IDs missing from the LLM response are appended at the end.
    """
    if len(hlrs) <= 1:
        return [{"id": hlrs[0]["id"], "rationale": "only requirement"} for h in hlrs]

    hlr_text = format_hlrs_for_prompt(hlrs)

    result = call_tool(
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Determine the optimal design order for these {len(hlrs)} HLRs:\n\n"
                    f"{hlr_text}"
                ),
            }
        ],
        tools=[TOOL_DEFINITION],
        tool_name="order_hlrs",
        model=model,
        prompt_log_file=prompt_log_file,
    )

    ordered = result.get("ordered_hlrs", [])

    # Ensure all HLR IDs are present (append any missing ones at the end)
    all_ids = {h["id"] for h in hlrs}
    seen_ids = set()
    validated = []
    for entry in ordered:
        hlr_id = entry.get("id")
        if hlr_id in all_ids and hlr_id not in seen_ids:
            seen_ids.add(hlr_id)
            validated.append(entry)

    for hlr_id in all_ids - seen_ids:
        validated.append({"id": hlr_id, "rationale": "not ordered by agent"})

    return validated
