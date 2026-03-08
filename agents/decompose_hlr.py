"""
Agent that decomposes a high-level requirement description into
low-level requirements with verification methods.

Can be used standalone (CLI) or imported by Django views/management commands.
"""

import json
import anthropic

from requirements.schemas import DecomposedRequirementSchema as DecomposedRequirement


SYSTEM_PROMPT = """\
You are a requirements engineering agent. Your job is to decompose a high-level
requirement description into low-level requirements.

For the high-level requirement itself, provide a clear prose description that
captures the intent.

Then decompose it into low-level requirements. Each LLR should:
- Include a prose description of the specific behavior
- Have one or more verification methods, each with:
  - method: one of "automated", "review", or "inspection"
  - confirmation: how we know the requirement is met (e.g., "the operator field
    is populated with the ADDITION enum value")
  - test_name: a snake_case test function name that would verify this
    (e.g., "user_presses_addition_key")

Guidelines:
- LLRs should be atomic and testable
- Each LLR should map to a single observable behavior
- Prefer "automated" verification where the behavior is programmatically testable
- Use "review" for design/UX concerns and "inspection" for documentation/process
- test_name should be descriptive and follow snake_case convention
- Generate enough LLRs to fully cover the HLR, but no more than necessary

You MUST use the decompose_requirement tool to return your result.
"""

TOOL_DEFINITION = {
    "name": "decompose_requirement",
    "description": "Return the structured decomposition of a high-level requirement",
    "input_schema": DecomposedRequirement.model_json_schema(),
}


def decompose(description: str, model: str = "claude-sonnet-4-20250514") -> DecomposedRequirement:
    """
    Takes a human-written HLR description and returns a structured decomposition.
    """
    client = anthropic.Anthropic()

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Decompose this high-level requirement:\n\n{description}",
            }
        ],
        tools=[TOOL_DEFINITION],
        tool_choice={"type": "tool", "name": "decompose_requirement"},
    )

    for block in response.content:
        if block.type == "tool_use":
            return DecomposedRequirement.model_validate(block.input)

    raise RuntimeError("Agent did not return a tool call")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m agents.decompose_hlr 'description of requirement'")
        sys.exit(1)

    description = " ".join(sys.argv[1:])
    result = decompose(description)
    print(json.dumps(result.model_dump(), indent=2))
