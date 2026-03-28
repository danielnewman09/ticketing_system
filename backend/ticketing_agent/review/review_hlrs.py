"""
Agent that reviews a set of high-level requirements and proposes
a more robust, complete set with rationale for each change.

Used interactively: the user sees the proposals and decides which to keep.
"""

from llm_caller import call_tool
from backend.db.models.requirements import format_hlrs_for_prompt

from backend.ticketing_agent.review.review_hlrs_prompt import (
    SYSTEM_PROMPT,
    TOOL_DEFINITION,
    ProposedHLR,
    HLRReviewResult,
)

# Re-export for backward compatibility
__all__ = ["ProposedHLR", "HLRReviewResult", "review_hlrs"]


def review_hlrs(
    hlrs: list[dict],
    model: str = "",
    prompt_log_file: str = "",
) -> HLRReviewResult:
    """
    Review a set of HLRs and propose improvements.

    Each HLR dict: {id, description}
    """
    requirements_text = format_hlrs_for_prompt(hlrs)

    result = call_tool(
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    "Review these high-level requirements and propose improvements:\n\n"
                    f"{requirements_text}"
                ),
            }
        ],
        tools=[TOOL_DEFINITION],
        tool_name="propose_hlrs",
        model=model,
        prompt_log_file=prompt_log_file,
    )

    return HLRReviewResult.model_validate(result)
