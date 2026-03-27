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

from agents.design.order_hlrs_prompt import SYSTEM_PROMPT, TOOL_DEFINITION


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
