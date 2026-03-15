"""
Agent that reviews a set of high-level requirements and proposes
a more robust, complete set with rationale for each change.

Used interactively: the user sees the proposals and decides which to keep.
"""

import json
from typing import Literal

from pydantic import BaseModel

from agents.llm_client import call_tool
from db.models.requirements import format_hlrs_for_prompt


class ProposedHLR(BaseModel):
    """A single proposed high-level requirement."""
    action: Literal["keep", "modify", "add", "delete"]
    original_id: int | None = None  # ID of the original HLR (None for new additions)
    description: str
    rationale: str


class HLRReviewResult(BaseModel):
    proposals: list[ProposedHLR]


SYSTEM_PROMPT = """\
You are a requirements engineering reviewer. Given a set of high-level
requirements (HLRs), your job is to propose a more robust, complete, and
well-structured set.

For each proposed HLR, specify:
- **action**: what you are proposing
  - "keep" — the original HLR is good as-is (include it unchanged)
  - "modify" — revise the wording for clarity, testability, or scope
  - "add" — a new HLR that fills a gap in coverage
  - "delete" — an original HLR that should be removed (explain why)
- **original_id**: the ID of the original HLR this relates to (null for "add")
- **description**: the proposed HLR text (for "delete", copy the original)
- **rationale**: why you are proposing this change

## Guidelines

- Each HLR should describe a single, cohesive area of functionality
- HLRs should be decomposable into testable low-level requirements
- Avoid overlap between HLRs — if two HLRs cover similar ground, merge or
  restructure them
- Look for gaps: important functionality that no HLR covers
- HLRs should be technology-agnostic where possible (describe what, not how)
- Keep the total number of HLRs manageable — enough for complete coverage
  but not so many that they become redundant
- Prefer modifying existing HLRs over deleting and re-adding
- Every original HLR must appear in your output (as keep, modify, or delete)

You MUST use the propose_hlrs tool to return your result.
"""

TOOL_DEFINITION = {
    "name": "propose_hlrs",
    "description": "Return the proposed set of high-level requirements with rationale",
    "input_schema": HLRReviewResult.model_json_schema(),
}


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
