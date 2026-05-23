# Pipeline Validation Fixes: Intercomponent Associations & Verification Qualified Names

**Date**: 2025-05-23
**Scope**: Critical issues in design pipeline scripts 01-03 that produce disconnected ontology nodes and orphan stubs, plus a prompt formatting standard to prevent recurrence.

## Problem Statement

Two critical issues were identified from a full pipeline run (flush → setup → design):

### Issue 1: No cross-component links between `user_interface` and `calculation_engine`

The design agent for HLR 1 (user_interface) received `CalculatorResult` correctly as an intercomponent class but produced **zero associations** pointing to it or to `CalculatorEngine`. The prompt section `build_intercomponent_section()` says *"Do NOT include them in your output"* — which the LLM interprets as excluding them from associations, not just from the classes array. The result: two entirely disconnected subgraphs in the ontology, with no `DEPENDS_ON` or `USES` relationships bridging them.

### Issue 2: Verification agent creates orphan stub nodes with invalid qualified names

The verify agent generates qualified names that don't match any Design node, and `augment_missing_design_nodes()` creates stubs for all of them without validation. Observed pathologies:

- **Dot separator** instead of `::`: `user_interface::CalculatorWindow.equalsButton`
- **Nested attribute paths**: `CalculatorEngine::last_result.is_success`
- **Test-local identifiers**: `result_of_first_call`, `test_perform_multiplication`

These become orphan nodes disconnected from the ontology hierarchy — no `COMPOSES` parent, no `TRACES_TO` link, visible as disconnected dots on the `/ontology/graph` dashboard.

## Design

### Fix 1: Intercomponent association prompt (design_oo_prompt.py)

**File**: `backend/ticketing_agent/design/design_oo_prompt.py`

**Change `build_intercomponent_section()`** — replace the current discouraging instruction with a clear contract:

Current:
```
"You may reference, depend on, or associate with these but do NOT redesign
or duplicate them. Do NOT include them in your output."
```

Proposed: Wrap the instruction in a `<CONTRACT>` block:

```xml
<CONTRACT>
You MUST create associations from your classes to intercomponent classes
when your design depends on them (e.g., calls their methods, receives their
return types, holds references to them). Omitting them creates disconnected
components in the design.

Do NOT redesign or duplicate these classes in your output classes — only
reference their qualified names in associations, inherits_from, attribute
types, and method return types.
</CONTRACT>
```

**Add an example** to the intercomponent section showing the expected association pattern:

```
### Example: cross-component association
If your class `user_interface::CalculatorWindow` calls methods on
`calculation_engine::CalculatorEngine` and receives
`calculation_engine::CalculatorResult`, include these associations:
  - from_class: CalculatorWindow, to_class: calculation_engine::CalculatorEngine, kind: depends_on
  - from_class: CalculatorWindow, to_class: calculation_engine::CalculatorResult, kind: depends_on

Note: Use the qualified name (with namespace prefix) for intercomponent
classes in from_class/to_class.
```

**Add a contract line to the Associations guidance** in the system-level `SYSTEM_PROMPT`:

```xml
<CONTRACT>
When a class in your component interacts with an intercomponent class
(listed in the cross-component section), you MUST include an association
to that class. This is how inter-component dependencies are tracked.
Omitting them creates disconnected components in the design.
</CONTRACT>
```

### Fix 2: Verification qualified-name contract (verify_llr_prompt.py)

**File**: `backend/ticketing_agent/verify/verify_llr_prompt.py`

**Add a `<FORMAT-CONTRACT>` block** to `SYSTEM_PROMPT` between the design context and instructions:

```xml
<FORMAT-CONTRACT name="qualified-names">
All `subject_qualified_name`, `object_qualified_name`, `callee_qualified_name`,
and `caller_qualified_name` fields MUST use qualified names that exactly match
the design context section above.

Pattern: <namespace>::<ClassName>::<memberName>

✓ calculation_engine::CalculatorEngine::validateInput
✓ user_interface::CalculatorWindow::equalsButton
✗ user_interface::CalculatorWindow.equalsButton
  → Dot separator — use :: everywhere
✗ calculation_engine::CalculatorEngine::last_result.is_success
  → Nested attribute path — reference the outer attribute directly
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

**Strengthen the existing guideline** — change:

> "Keep conditions specific and testable — avoid vague assertions"

To:

> "Keep conditions specific and testable. Every qualified name you write MUST exactly match a name shown in the design context section. If no exact match exists, do not fabricate one — omit the reference field or use expected_value alone."

### Fix 3: Validation guardrail in augment_missing_design_nodes()

**File**: `backend/db/neo4j/repositories/verification.py`

Add a `_is_valid_verification_qname()` function before `augment_missing_design_nodes()`:

```python
import re

_INVALID_QNAME_PATTERNS = re.compile(
    r'^(test_|result_of_|verify_|check_)'  # test/local identifiers
    | r'^[a-z]+$'                             # bare lowercase word (e.g., "value")
)

def _is_valid_verification_qname(qname: str) -> tuple[bool, str | None]:
    """Check whether a qualified name is valid before creating a stub node.

    Returns (is_valid, corrected_qname_or_None).
    corrected_qname is provided for the common error of using '.' instead of '::'.
    """
    if not qname or not qname.strip():
        return False, None

    # Reject obvious test artifacts and local variable names
    if _INVALID_QNAME_PATTERNS.match(qname):
        return False, None

    # Reject bare lowercase identifiers (not a qualified name)
    if '::' not in qname and qname.islower():
        return False, None

    # Auto-correct dot separators to ::
    if '.' in qname:
        parts = qname.split('.')
        if all(p and (p[0].isupper() or p[0].islower()) for p in parts):
            corrected = '::'.join(parts)
            return True, corrected

    # Require at least one :: separator (namespace::Class or Class::member)
    if '::' not in qname:
        return False, None

    return True, None
```

Modify `augment_missing_design_nodes()` to call the validator on each raw qualified name before creating a stub:

```python
def augment_missing_design_nodes(self, qualified_names: list[str]) -> list[str]:
    # ... existing docstring ...

    if not qualified_names:
        return []

    created = []
    for raw_qn in qualified_names:
        if not raw_qn:
            continue

        # Validate and optionally correct the qualified name
        is_valid, corrected = _is_valid_verification_qname(raw_qn)
        if not is_valid:
            log.warning("augment: skipping invalid verification qname: %r", raw_qn)
            continue

        qn = corrected if corrected else raw_qn

        # Check if :Design node already exists (with corrected name)
        result = self._session.run(
            "MATCH (d:Design {qualified_name: $qn}) RETURN count(d) AS cnt",
            {"qn": qn},
        )
        if result.single()["cnt"] > 0:
            continue

        # ... rest of existing stub creation logic, using qn instead of raw_qn ...
```

### Fix 4: Prompt Formatting Contract (applied to all agent prompts)

#### Standard Section Ordering

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

#### Formatting Patterns

**`<CONTRACT>` — Inviolable Rules**

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

Rules for `<CONTRACT>`:
- Use "MUST" / "Do NOT" / "NEVER" — not "should" or "prefer"
- Each rule addresses a specific, observed failure mode
- Keep to 3-5 rules per contract block

**`<FORMAT-CONTRACT>` — Output Syntax Constraints**

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

Rules for `<FORMAT-CONTRACT>`:
- Always includes the formal pattern
- At least 2 positive and 2 negative examples
- Each ✗ example has a `→` explanation
- Named with `name` attribute for cross-reference
- Always includes a fallback rule ("what to do if no match exists")

**Anti-Pattern Blocks**

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

Rules for anti-patterns:
- At least one `<Bad>`/`<Good>` pair per anti-pattern
- The table gives a quick scannable reference
- Every anti-pattern corresponds to a real failure observed in pipeline output

**Context Section Builders (enhanced)**

The existing `build_*_section()` functions gain `<CONTRACT>` language where needed. The `build_intercomponent_section()` function is the primary example — it changes from prose discouragement to an explicit contract (detailed in Fix 1 above).

#### Formatting Guide Document

A new document at `docs/prompt-formatting-guide.md` will codify these patterns with:
- The standard section ordering table
- Each formatting pattern with examples
- A checklist for reviewing new/edited prompts
- The list of observed failure modes that each pattern addresses

This guide serves as the reference for all future prompt edits — including the 13 other agent prompts that we'll roll out to incrementally.

### Fix 5: Validate-and-retry loop for agent tool calls

After the LLM produces its tool call result, validate the output against known-good data. If validation fails, feed the specific errors back to the LLM as a follow-up message and retry. This catches residual errors that prompt formatting alone may not prevent.

**Architecture**: Agent-level retry wrapper. Each agent function owns its validation logic and retry loop. This avoids adding domain-specific callbacks to `call_tool` and keeps each agent self-contained.

**Shared constants** (new file `backend/ticketing_agent/retry.py` or top of each agent):

```python
MAX_TOOL_RETRIES = 2  # 3 total attempts (initial + 2 retries)
```

**Pattern** (applied to both `design_oo` and `verify`):

```python
for attempt in range(MAX_TOOL_RETRIES + 1):
    result = call_tool(system=..., messages=messages, tools=[TOOL_DEFINITION], ...)

    validation_errors = validate(result, context)

    if not validation_errors:
        break  # All valid, proceed

    if attempt < MAX_TOOL_RETRIES:
        # Feed errors back to LLM
        error_msg = format_validation_errors(validation_errors)
        messages.append({"role": "assistant", "content": json.dumps(result)})
        messages.append({"role": "user", "content": error_msg})
        continue

    # Final attempt still has errors — log and proceed
    log.warning("Agent produced invalid output after %d attempts: %s",
                MAX_TOOL_RETRIES + 1, validation_errors)
    break
```

**Validation for `design_oo`** (`backend/ticketing_agent/design/design_oo.py`):

Two checks after `produce_oo_design` returns:

1. **Unknown association targets**: Every `from_class` and `to_class` in `associations` must resolve to either:
   - A class/interface/enum name defined in the current design output
   - A name in `prior_class_lookup` (from previously designed HLRs)
   - A name in `dependency_lookup` (from discover_classes phase)
   - A qualified name in `intercomponent_classes`

   Unknown targets produce an error like: `"CalculatorWindow -> UnknownClass: UnknownClass is not defined in this design or in the provided context"`

2. **Missing intercomponent associations**: If `intercomponent_classes` is non-empty and any class in the design holds a reference (attribute type or method return type) matching an intercomponent class, but no association references that intercomponent class, produce an error: `"CalculatorWindow references calculation_engine::CalculatorResult in attributes/methods but has no association to it"`

   The retry message includes the specific intercomponent classes that should have associations.

**Validation for `verify`** (`backend/ticketing_agent/verify/verify_llr.py`):

One check after `produce_verifications` returns:

1. **Unresolved qualified names**: Already partially implemented via `VerificationRepository.validate_references()`. Currently this only populates `resolved`/`unresolved` lists. The retry loop uses these:
   - If `unresolved` is non-empty and attempts remain, feed the list back to the LLM with the `<FORMAT-CONTRACT>` reminder.
   - If `unresolved` is still non-empty after max retries, proceed (the `_is_valid_verification_qname` guardrail from Fix 3 prevents the worst stubs from being created).

**Retry message template**:

The retry message follows a consistent format:

```
Your previous output had the following issues:

<issues>
1. Unknown class reference: "UnknownClass" in association from CalculatorWindow.
   This name does not exist in the current design or the provided context.
2. Missing intercomponent association: CalculatorWindow references
   calculation_engine::CalculatorResult but has no association to it.
</issues>

Please correct these issues and respond again with the fixed output.
```

For the verify agent, the retry message includes the `<FORMAT-CONTRACT>` block as a reminder:

```
Your previous output referenced qualified names that do not exist in the
design context:

<issues>
1. "user_interface::CalculatorWindow.equalsButton" - dot separator, use ::
2. "result_of_first_call" - not a design element, remove this reference
3. "test_validate_input_syntax" - test function, not a design element
</issues>

<FORMAT-CONTRACT name="qualified-names">
... (same contract block from the system prompt) ...
</FORMAT-CONTRACT>

Please correct these issues and respond again with the fixed output.
```

**Important**: The retry appends the assistant's previous tool call result and the validation error as new messages to the conversation. The LLM sees its own prior output and the specific errors, giving it the context to fix them.

## Scope

- **In scope**:
  - Fix 1: Prompt changes to `design_oo_prompt.py`
  - Fix 2: Prompt changes to `verify_llr_prompt.py`
  - Fix 3: Validation guardrail in `verification.py`
  - Fix 4: Formatting guide document + immediate application to the two critical prompts
  - Fix 5: Validate-and-retry loop in `design_oo.py` and `verify_llr.py`
- **Not in scope**:
  - Fixing existing orphan nodes in the running Neo4j (a `01_flush_db.py` re-run will clear those)
  - Fuzzy matching of qualified names
  - Runtime inference of missing associations from return types or method signatures
  - Reformatting all 15 agent prompts immediately (done incrementally per Fix 4)
  - Changing `map_to_ontology.py` to infer missing cross-component associations
  - Adding retry loops to other agents (decompose, assign_components, order_hlrs, discover_classes) — done incrementally as needed

## Expected Outcome

After re-running the pipeline:
1. `CalculatorWindow` will have `depends_on` or `invokes` associations pointing to `calculation_engine::CalculatorEngine` and `calculation_engine::CalculatorResult`
2. Verification stubs will use correct `::` separators and reference real design nodes
3. No orphan `result_of_*` or `test_*` stubs in the ontology graph
4. The `/ontology/graph` dashboard will show connected subgraphs with visible cross-component edges
5. All future agent prompts follow a consistent formatting contract that prevents these failure modes
6. LLM output that still contains invalid references after prompt improvements will be caught and retried, reducing residual errors to near-zero