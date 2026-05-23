# Agent Prompt Formatting Guide

This guide documents the formatting patterns used in agent prompts throughout the ticketing system. All new and edited prompts should follow these standards.

## Standard Section Ordering

Every agent prompt follows this section order. Sections marked ✓ appear in every prompt; sections marked conditional appear only when the agent has that concern.

| # | Section | Required | Purpose |
|---|---------|----------|---------|
| 1 | Role definition | ✓ | Who the agent is and what it produces |
| 2 | `<CONTRACT>` block | ✓ | Inviolable rules — constraints every output must satisfy |
| 3 | Context sections | conditional | Dependency API, intercomponent classes, existing classes, other HLRs |
| 4 | `<FORMAT-CONTRACT>` block | conditional | Output format constraints — syntax rules for structured fields |
| 5 | Anti-patterns | conditional | ✗/✓ examples of observed failure modes |
| 6 | Guidelines | ✓ | Soft guidance, heuristics, preferences (no enforcement language) |
| 7 | Tool definition | ✓ | JSON schema for the structured output |

## Formatting Patterns

### `<CONTRACT>` — Inviolable Rules

Used for constraints where violations produce graph-disconnected or structurally invalid output. Written as imperative statements, never suggestions.

```xml
<CONTRACT>
Every class MUST include "attributes" and "methods" arrays.
Do NOT omit them — dropping arrays is the worst failure mode.

When a class in your component interacts with an intercomponent class,
you MUST include an association to that class in the associations array.
Omitting them creates disconnected components.
</CONTRACT>
```

**Rules for `<CONTRACT>`:**
- Use "MUST" / "Do NOT" / "NEVER" — not "should" or "prefer"
- Each rule addresses a specific, observed failure mode
- Keep to 3-5 rules per contract block
- Every `<CONTRACT>` rule should be testable — "does violation of this rule produce a disconnected graph, invalid output, or data corruption?"

### `<FORMAT-CONTRACT>` — Output Syntax Constraints

Used for field-level format rules where the LLM must produce text matching a specific grammar. Includes the formal pattern, positive examples, negative examples with explanations, and a fallback rule.

```xml
<FORMAT-CONTRACT name="qualified-names">
All qualified_name fields MUST use names that exactly match the design
context section above.

Pattern: <namespace>::<ClassName>::<memberName>

✓ calculation_engine::CalculatorEngine::validateInput
✓ user_interface::CalculatorWindow::equalsButton
✗ user_interface::CalculatorWindow.equalsButton
  → Dot separator — use :: everywhere
✗ calculation_engine::CalculatorEngine::last_result.is_success
  → Nested attribute path — reference the attribute directly
    (calculation_engine::CalculatorEngine::last_result)
    and the inner class member separately
    (calculation_engine::CalculatorResult::is_success)
✗ result_of_first_call
  → Test variable, not a design element
✗ test_validate_input_syntax
  → Test function, not a design element

If no exact match exists in the design context, do NOT fabricate a name.
Omit the reference field or use expected_value alone.
</FORMAT-CONTRACT>
```

**Rules for `<FORMAT-CONTRACT>`:**
- Always includes the formal pattern
- At least 2 positive and 2 negative examples
- Each ✗ example has a `→` explanation
- Named with `name` attribute for cross-reference between prompts
- Always includes a fallback rule ("what to do if no match exists")

### Anti-Pattern Blocks

Used for behavioral failure modes the LLM commonly falls into. Presented as `<Bad>`/`<Good>` pairs plus a scannable table:

```xml
## Anti-patterns

<Bad>
"associations": []
<!-- No associations to intercomponent classes -->
</Bad>

<Good>
"associations": [
  {"from_class": "CalculatorWindow", "to_class": "calculation_engine::CalculatorEngine", "kind": "depends_on"},
  {"from_class": "CalculatorWindow", "to_class": "calculation_engine::CalculatorResult", "kind": "depends_on"}
]
</Good>

| Anti-pattern | What goes wrong | Instead |
|---|---|---|
| Omitting intercomponent associations | Components become disconnected subgraphs | Create `depends_on` or `invokes` associations to every intercomponent class you reference |
| Using dot (`.`) in qualified names | Creates orphan stub nodes in the ontology | Always use `::` separator |
| Fabricating test-local names as qualified names | Non-existent design nodes pollute the graph | Only use names from the design context |
```

**Rules for anti-patterns:**
- At least one `<Bad>`/`<Good>` pair per anti-pattern
- The table gives a quick scannable reference
- Every anti-pattern corresponds to a real failure observed in pipeline output

### Context Section Builders

The existing `build_*_section()` functions gain `<CONTRACT>` language where needed. The `build_intercomponent_section()` function is the primary example:

- **Before**: "You may reference, depend on, or associate with these but do NOT redesign or duplicate them. Do NOT include them in your output."
- **After**: Wrapped in `<CONTRACT>` with explicit requirement to create associations, plus a concrete example

## Checklist for Reviewing Prompts

When reviewing a new or edited agent prompt, check:

- [ ] Does it follow the standard section ordering?
- [ ] Are inviolable rules in `<CONTRACT>` blocks (not in guideline prose)?
- [ ] Are format constraints in `<FORMAT-CONTRACT>` blocks with ✓/✗ examples?
- [ ] Are observed failure modes documented as anti-patterns?
- [ ] Is the tool definition correct and complete?
- [ ] Does the prompt avoid "should" or "prefer" where "MUST" or "Do NOT" is needed?

## Observed Failure Modes and Their Fixes

| Failure | Root Cause | Fix Applied |
|---|---|---|
| Missing intercomponent associations | "Do NOT include them in your output" discouraged all references | `<CONTRACT>` block mandating associations |
| Dot separators in qualified names | LLM used `.` instead of `::` for member access | `<FORMAT-CONTRACT>` with ✓/✗ examples |
| Nested attribute paths (e.g., `last_result.is_success`) | LLM treated attributes as path expressions | `<FORMAT-CONTRACT>` with explanation of "reference attribute directly" |
| Test-local variable names (e.g., `result_of_first_call`) | LLM fabricated names outside the design context | `<FORMAT-CONTRACT>` "do NOT fabricate a name" rule + validation guardrail in `verification.py` |
| Orphan stub nodes in graph | `augment_missing_design_nodes()` created stubs for all qnames without validation | `_is_valid_verification_qname()` filter + auto-correction of `.` → `::` |
| LLM ignoring soft guidelines | "may" / "prefer" / "should" treated as optional | `<CONTRACT>` uses "MUST" / "Do NOT" / "NEVER" |