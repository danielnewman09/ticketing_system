"""
Node conflict review agent.

When the remediation sanity check finds that a proposed new node shares
a name with an existing node, this agent decides the correct resolution
from an Object-Oriented design perspective:

- Should the existing node be renamed/replaced by the proposed one?
- Should the proposed node be dropped in favor of the existing one?
- Should both be kept (genuinely distinct entities)?

It also ensures that any resolution correctly updates triples and
preserves HLR/LLR mapping integrity.
"""

from agents.llm_client import call_tool

from agents.review.review_node_conflict_prompt import (
    SYSTEM_PROMPT,
    TOOL_DEFINITION,
    NodeResolution,
    ConflictReviewResult,
    format_conflicts,
)

# Re-export for backward compatibility
__all__ = ["NodeResolution", "ConflictReviewResult", "review_conflicts"]


def review_conflicts(
    conflicts: list[dict],
    model: str = "",
    prompt_log_file: str = "",
) -> ConflictReviewResult:
    """Review naming conflicts and decide on resolutions.

    Args:
        conflicts: list of conflict dicts (see format_conflicts for shape).
        model: optional LLM model override.

    Returns:
        ConflictReviewResult with a resolution for each conflict.
    """
    user_message = (
        f"## Node Naming Conflicts\n\n"
        f"{format_conflicts(conflicts)}\n\n"
        f"Resolve each conflict with the correct OO hierarchy decision."
    )

    result = call_tool(
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
        tools=[TOOL_DEFINITION],
        tool_name="resolve_conflicts",
        model=model,
        prompt_log_file=prompt_log_file,
    )

    return ConflictReviewResult.model_validate(result)
