"""Agent that decomposes a high-level requirement into low-level requirements.

Migrated from ``backend.ticketing_agent.decompose.decompose_hlr`` — no imports
from ``backend/``. Uses ``backend_migrated.requirements`` for schemas and
formatting, and ``llm_caller`` for LLM tool calls.

Usage::

    from backend_migrated.agents.decompose_hlr import decompose

    result = decompose(
        description="The system shall provide a calculator...",
        component="Calculation Engine",
    )
"""

import json
import logging
import re

from llm_caller import call_tool

from backend_migrated.requirements.schemas import (
    DecomposedRequirementSchema as DecomposedRequirement,
)
from backend_migrated.requirements.formatting import format_hlr_dict

log = logging.getLogger(__name__)

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

Every verification method MUST include preconditions, actions, and
postconditions. These are NOTIONAL descriptions written before any
design exists — they describe what to check, what to do, and what to
expect in plain, human-readable terms. A downstream agent will later
resolve them into qualified design names.

Do NOT leave preconditions, actions, or postconditions empty.
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

<FORMAT-CONTRACT name="verification-stubs">
Each verification method MUST include three sections: preconditions,
actions, and postconditions. These are NOTIONAL — no design exists yet,
so use human-readable, conceptual references, not qualified names.

### Preconditions
Assertions on the system state that must hold before the test action.
Each precondition has a subject (what is being checked), an operator,
and an expected value.

[Good] subject_qualified_name: "Engine", operator: "is_true", expected: "initialized"
[Good] subject_qualified_name: "Engine.last_result", operator: "==", expected: "null"
[Bad] subject_qualified_name: "calculation_engine::CalculatorEngine::is_initialized"
  → Qualified design name — no design exists at this stage
[Bad] subject_qualified_name: "", operator: "==", expected: ""
  → Empty — provides no information to downstream agents
[Bad] (no preconditions at all)
  → Even a simple "system is initialized" pre tells the verify agent
    what setup is needed

### Actions
Ordered stimulus steps that the test performs. Each action has a
human-readable description of what happens and, where applicable,
a notional target (what operation is invoked).

[Good] description: "Invoke the add operation with operands 10 and 20",
       callee_qualified_name: "Engine.add"
[Good] description: "Submit a non-numeric string as the first operand",
       callee_qualified_name: "Engine.add"
[Good] description: "Invoke the divide operation with operands 10 and 0",
       callee_qualified_name: "Engine.divide"
[Bad] description: "Call the method",
  → Which method? With what inputs? Not specific enough.
[Bad] callee_qualified_name: "calculation_engine::CalculatorEngine::add"
  → Qualified design name — not available at this stage.
  Use a notional reference like "Engine.add" instead.

### Postconditions
Assertions on the expected system state after the actions. Same
format as preconditions.

[Good] subject_qualified_name: "Engine.result", operator: "==", expected: "30"
[Good] subject_qualified_name: "Engine.error_signal", operator: "==", expected: "InvalidInput"
[Good] subject_qualified_name: "Engine.is_success", operator: "is_false"
[Bad] subject_qualified_name: "calculation_engine::CalculationResult::result_value"
  → Qualified design name — no design exists at this stage.
  Use a notional reference like "Engine.result" instead.
[Bad] subject_qualified_name: "", operator: "==", expected: "correct result"
  → Not observable — what is the specific expected value?
[Bad] (no postconditions at all)
  → Without postconditions, the verification has no pass/fail criteria.

### Notional reference style

Notional references are conceptual names that describe what something
IS, not where it lives in a namespace. They use simple dot-separated
paths like "Engine.result" or "Display.current_value". A downstream
design agent will map these to qualified names (e.g.,
"calculation_engine::CalculatorEngine::last_result").

| Notional reference | Resolved form (after design) |
|---|---|
| Engine.result | calculation_engine::CalculatorResult::result_value |
| Engine.error_signal | calculation_engine::CalculatorResult::error_signal |
| Engine.is_success | calculation_engine::CalculatorResult::is_success |
| Engine.last_operator | calculation_engine::CalculatorEngine::last_operator |
| Display.current_value | user_interface::CalculatorDisplay::current_value |

Do NOT try to predict namespace prefixes or design-qualified names.
Use short, descriptive notional names that make the test scenario
clear to a human reader. The verify agent handles the name resolution.
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
| Empty verification stubs (no preconditions/actions/postconditions) | Downstream verify agent has nothing to resolve — must invent from scratch, losing the decomposition's intent | Always include notional preconditions, actions, and postconditions |
| Qualified design names in stubs (ns::Class::member) | No design exists at decomposition time — these names are fabricated and won't match | Use notional references (Engine.result) that the verify agent can resolve |

## Verification Stub Examples

### Happy-path verification

<Good>
Verification for: "The Calculation Engine exposes an addition operation
that accepts two numeric operands and returns their sum."

method: automated
test_name: test_add_returns_sum_of_two_valid_operands
description: Invoke the addition operation with numeric operands and
  verify the returned result is their sum.
preconditions:
  - subject_qualified_name: Engine.is_initialized, operator: is_true, expected: true
actions:
  - description: Invoke the add operation with operands 10 and 20,
    callee_qualified_name: Engine.add
postconditions:
  - subject_qualified_name: Engine.result, operator: ==, expected: "30"
  - subject_qualified_name: Engine.is_success, operator: is_true, expected: true
</Good>

### Error-path verification

<Good>
Verification for: "The Calculation Engine rejects non-numeric inputs
with an error signal."

method: automated
test_name: test_add_rejects_non_numeric_operand
description: Invoke the addition operation with a non-numeric operand
  and verify the error signal indicates invalid input.
preconditions:
  - subject_qualified_name: Engine.is_initialized, operator: is_true, expected: true
actions:
  - description: Invoke the add operation with a non-numeric string
    operand, callee_qualified_name: Engine.add
postconditions:
  - subject_qualified_name: Engine.error_signal, operator: ==, expected: InvalidInput
  - subject_qualified_name: Engine.is_success, operator: is_false, expected: false
</Good>

### Empty verification stubs — WRONG

<Bad>
Verification for: "The Calculation Engine exposes an addition operation."

method: automated
test_name: test_add_returns_sum
description: Verify the addition operation works.
preconditions: (none)
actions: (none)
postconditions: (none)

No observable setup, no stimulus, no expected outcome. A downstream
agent reading this stub would have to guess the entire test scenario.
</Bad>

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
- Every verification method MUST include notional preconditions, actions,
  and postconditions. These stubs are the bridge between requirements and
  test implementation — a downstream design agent resolves the notional
  references into qualified design names. Leaving them empty breaks this
  chain.

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


def _recover_mixed_xml_json(result: dict) -> dict:
    """Recover when an LLM embeds <parameter=...> XML tags inside a JSON string value.

    Some models (especially smaller quantized ones) produce tool calls like:
        {"description": "...actual text...</description>\n<parameter=low_level_requirements>\n[...]"}
    instead of proper JSON with separate top-level keys.

    This function detects that pattern and extracts the embedded JSON arrays,
    promoting them to top-level keys in the result dict.
    """
    recovered = {}
    for key, value in result.items():
        if not isinstance(value, str) or '<parameter=' not in value:
            recovered[key] = value
            continue

        # Extract the clean value for this key (before any XML tags)
        clean_value = value
        end_tag = f'</{key}>'
        end_tag_idx = value.find(end_tag)
        if end_tag_idx >= 0:
            clean_value = value[:end_tag_idx].strip()
        else:
            # No closing tag — strip everything from the first <parameter=
            param_idx = value.find('<parameter=')
            if param_idx >= 0:
                clean_value = value[:param_idx].strip()

        recovered[key] = clean_value

        # Now extract all <parameter=name>...</> or <parameter=name>\n[json] blocks
        param_pattern = re.compile(
            r'<parameter=(\w+)>\s*(.*?)(?=\Z|<parameter=\w+>)',
            re.DOTALL,
        )
        for match in param_pattern.finditer(value):
            param_name = match.group(1)
            param_value_str = match.group(2).strip()
            # Remove trailing closing tags like </description> that might be left
            closing_tag = f'</{param_name}>'
            if param_value_str.endswith(closing_tag):
                param_value_str = param_value_str[: -len(closing_tag)].strip()

            try:
                parsed = json.loads(param_value_str)
                recovered[param_name] = parsed
                log.info(
                    "Recovered embedded parameter '%s' from XML-in-JSON "
                    "(type: %s, length: %d)",
                    param_name, type(parsed).__name__,
                    len(parsed) if isinstance(parsed, (list, dict, str)) else 0,
                )
            except json.JSONDecodeError:
                log.warning(
                    "Could not parse embedded parameter '%s' as JSON, "
                    "storing as string",
                    param_name,
                )
                recovered[param_name] = param_value_str

    return recovered


def decompose(
    description: str,
    component: str = "",
    dependency_context: dict | None = None,
    model: str = "",
    prompt_log_file: str = "",
) -> DecomposedRequirement:
    """Decompose a high-level requirement description into LLRs with verification stubs.

    Takes a human-written HLR description and returns a structured decomposition
    with low-level requirements and their verification methods.

    Args:
        description: The HLR description text.
        component: Name of the architectural component this HLR belongs to.
        dependency_context: Optional dict with dependency assessment context
            (recommendation, dependency_name, relevant_structures, rationale).
        model: LLM model identifier to use.
        prompt_log_file: Path to write raw prompt/response for debugging.

    Returns:
        A DecomposedRequirement with description and low_level_requirements.
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

    # Recover from models that return nested JSON as a string (DeepSeek does this).
    # Some backends double-stringify: the tool args are a JSON string rather than
    # a parsed object, or the low_level_requirements value is a serialized list.
    if isinstance(result, str):
        try:
            result = json.loads(result)
            log.info("Deserialized entire result from JSON string")
        except json.JSONDecodeError:
            pass
    if isinstance(result, dict) and isinstance(result.get("low_level_requirements"), str):
        try:
            result["low_level_requirements"] = json.loads(result["low_level_requirements"])
            log.info("Deserialized low_level_requirements from JSON string")
        except json.JSONDecodeError:
            log.warning("Failed to parse low_level_requirements as JSON: %.200s", result["low_level_requirements"])

    # Recover from models that embed <parameter=...> XML tags inside JSON values
    if isinstance(result, dict) and "low_level_requirements" not in result:
        recovered = _recover_mixed_xml_json(result)
        if "low_level_requirements" in recovered:
            log.info(
                "Recovered low_level_requirements from embedded XML in description"
            )
            result = recovered

    return DecomposedRequirement.model_validate(result)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m backend_migrated.agents.decompose_hlr 'description of requirement'")
        sys.exit(1)

    description = " ".join(sys.argv[1:])
    result = decompose(description)
    print(json.dumps(result.model_dump(), indent=2))