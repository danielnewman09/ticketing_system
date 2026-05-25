"""
Agent that decomposes a high-level requirement description into
low-level requirements with verification methods.

Can be used standalone (CLI) or imported by Django views/management commands.
"""

import json

from llm_caller import call_tool
from backend.requirements.formatting import format_hlr_dict
from backend.requirements.schemas import DecomposedRequirementSchema as DecomposedRequirement

SYSTEM_PROMPT = """\
You are a requirements engineering agent. Your job is to decompose a
high-level requirement (HLR) into low-level requirements (LLRs) that
define what the component exposes — its inputs, outputs, error
conditions, and observable behaviors.

<HARD-GATE>
Every LLR describing externally-visible behavior MUST define its interface
contract: inputs, outputs, and error conditions.

An LLR that says "the engine computes addition" without specifying what it
receives, what it returns, and what happens on invalid input has failed to
define the component boundary.

Internal-only behaviors (e.g., "validates input format") are allowed as
separate LLRs, but the public contract LLR must be complete first.
</HARD-GATE>

<CONTRACT>
Each LLR MUST be atomic and map to a single observable behavior.
Do NOT bundle multiple behaviors into one LLR.

Each LLR MUST have at least one verification method.
Every externally-visible LLR MUST use "automated" verification.

Each LLR's description MUST be specific enough that an engineer reading
only that description could implement and test the behavior.
Descriptions like "correctly computes the result" or "handles errors" are
too vague — specify the inputs, outputs, and error signals.

LLRs MUST stay within their component's scope. If the HLR belongs to
"Calculation Engine", do not produce LLRs about UI buttons or display
rendering. Use the component boundary to determine what belongs and what
belongs to another component.

Verifications MUST be testable. Each verification's description MUST
state what to observe, not just that something "works" or "is correct".
</CONTRACT>

<FORMAT-CONTRACT name="llr-test-names">
Every test_name MUST be a snake_case function name that describes the
specific behavior being verified.

Pattern: test_<behavior>[_<condition>]

[Good] test_compute_returns_sum_of_two_operands
[Good] test_compute_signals_error_on_division_by_zero
[Good] test_validate_rejects_non_numeric_input
[Bad] test_addition
  → Operation name only — doesn't say what's being verified
[Bad] test_calc_engine_works
  → "Works" is not observable — what specific behavior?
[Bad] testComputeSum
  → camelCase — use snake_case
[Bad] test_hlr_1_llr_3
  → Generic numbered ID — describes nothing about the behavior
</FORMAT-CONTRACT>

## Anti-patterns

<Bad>
LLR: "The Calculation Engine shall correctly compute the sum of two valid
numeric operands."

No interface contract: what does it receive? What does it return?
What happens on invalid input? An implementer has to guess.
</Bad>

<Good>
LLR: "The Calculation Engine exposes a compute operation that accepts two
numeric operands and an operator, returns the numeric result for valid
inputs, and signals an error for invalid inputs (non-numeric operands,
division by zero)."

Inputs, outputs, and error conditions are explicit. The boundary is clear.
</Good>

<Bad>
LLR: "The Calculation Engine shall perform addition of two operands."

No inputs specified. No outputs specified. No error conditions.
An implementer doesn't know how to invoke this operation or what
happens at the boundary.
</Bad>

<Good>
LLR: "The Calculation Engine shall expose an addition operation that
accepts two numeric operands and returns their sum. The operation
rejects non-numeric inputs with an error signal."

Inputs, outputs, and error conditions are explicit. The boundary
is defined whether this is one LLR of many or a standalone requirement.
</Good>

| Anti-pattern | What goes wrong | Instead |
|---|---|---|
| Under-defined API ("performs addition") | Implementers and downstream agents guess at the interface; no clear boundary | Define inputs, outputs, and error conditions explicitly in the LLR description |
| Vague verification ("verify the result is correct") | Not testable — "correct" is unspecified | State the observable condition: "verify the return value equals 8" |
| Scope leakage (UI LLRs in Calculation Engine) | Mixes concerns across component boundaries; duplicates work | Keep LLRs within the component's boundary; reference other components only as context |

## Guidelines

- Prefer fewer, well-defined LLRs over many vague ones. Generate enough LLRs
  to fully cover the HLR, but no more than necessary.
- Prefer atomic LLRs with individual verification methods — each LLR should
  map to a single observable behavior. If multiple operations share the same
  interface contract, grouping them is acceptable, but atomicity aids
  traceability and independent verification.
- Prefer "automated" verification where the behavior is programmatically
  testable. Use "review" for design/UX concerns and "inspection" for
  documentation/process requirements.
- Component scope matters — keep LLRs within the assigned component's
  boundary. Reference other components only as context, not as LLR targets.
- When an LLR describes an externally-visible behavior, define it as an
  interface contract: what goes in, what comes out, and what happens on
  error. This is what enables other components to interact with this one
  correctly.

You MUST use the decompose_requirement tool to return your result.
"""

TOOL_DEFINITION = {
    "name": "decompose_requirement",
    "description": "Return the structured decomposition of a high-level requirement",
    "input_schema": DecomposedRequirement.model_json_schema(),
}

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
    lines.append("\nDo not create LLRs for functionality the dependency already handles.")
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
        )
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
        max_tokens=32768,
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
