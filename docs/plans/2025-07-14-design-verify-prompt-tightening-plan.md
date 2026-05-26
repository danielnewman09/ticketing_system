# design-verify-prompt-tightening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tighten the design_verify agent definition by removing redundant tool descriptions, embedding full LLR definitions, removing excessive container seeding from the prompt, replacing the flat workflow with a dot diagram, and aligning the FORMAT-CONTRACT style with other agents.

**Architecture:** Four independent changes to `combined_prompt.py`, `combined_loop.py`, and `formatting.py`. Each change is self-contained and can be tested independently. The prompt changes are text-only (no runtime behavior change), the formatter change adds a new function, and the loop change wires it together.

**Tech Stack:** Python, Pydantic, Neo4j (for fetching verification data), NiceGUI (frontend unaffected)

---

### Task 1: Remove tool descriptions and section headers from SYSTEM_PROMPT

**Files:**
- Modify: `backend/ticketing_agent/design_verify/combined_prompt.py`

This is a text-only change to the SYSTEM_PROMPT string. Remove the entire tool description block.

- [ ] **Step 1: Remove tool descriptions from SYSTEM_PROMPT**

In `backend/ticketing_agent/design_verify/combined_prompt.py`, find the SYSTEM_PROMPT string and remove the block starting from the line containing `"You have twelve tools available:"` through the end of the `commit_design_and_verifications` description (the paragraph ending with "call draft_design again to add the missing member, then continue verifying.").

The removed block starts with:
```
You have twelve tools available:

### Discovery tools

### list_sources
...
```
and ends just before the `{specializations_section}` placeholder.

This removes:
- "You have twelve tools available:" header
- "### Discovery tools" section header and all five tool descriptions (list_sources, search_symbols, get_compound, browse_namespace, find_inheritance)
- "### Design & verification tools" section header and all six tool descriptions (draft_design, validate_design, check_class_name, validate_qualified_names, lookup_design_element, commit_design_and_verifications)

The SYSTEM_PROMPT should flow directly from the opening paragraph to `{specializations_section}`:

```python
SYSTEM_PROMPT = """\
You are a software architect and verification engineer. Given design context
and requirements, your job is to produce an object-oriented class design AND
verification procedures that validate the design satisfies those requirements.

{specializations_section}
{namespace_section}
{dependency_api_section}
{as_built_section}
{existing_classes_section}
{intercomponent_section}
```

- [ ] **Step 2: Verify the prompt renders correctly in a Python shell**

Run:
```bash
cd /Users/danielnewman/dev/ticketing_system && python -c "
from backend.ticketing_agent.design_verify.combined_prompt import SYSTEM_PROMPT
rendered = SYSTEM_PROMPT.format(
    specializations_section='',
    namespace_section='',
    dependency_api_section='',
    as_built_section='',
    existing_classes_section='',
    intercomponent_section='',
)
print(rendered[:500])
print('---')
print('Tool descriptions absent:', 'twelve tools' not in rendered)
print('twelve tools' not in rendered)
"
```
Expected: `Tool descriptions absent: True`

- [ ] **Step 3: Run existing tests to confirm no breakage**

Run: `pytest tests/ -x -q --timeout=30 2>&1 | tail -20`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add backend/ticketing_agent/design_verify/combined_prompt.py
git commit -m "refactor: remove redundant tool descriptions from design_verify SYSTEM_PROMPT"
```

---

### Task 2: Replace "Recommended workflow" with dot diagram

**Files:**
- Modify: `backend/ticketing_agent/design_verify/combined_prompt.py`

- [ ] **Step 1: Replace the "Recommended workflow" section in SYSTEM_PROMPT**

In `combined_prompt.py`, find the `**Recommended workflow:**` block (which was already right before `{specializations_section}` — after Task 1 it should be the only numbered-list block remaining). Replace it with the dot diagram:

Old text to find (starting from `**Recommended workflow:**` and ending just before `{specializations_section}`):
```
**Recommended workflow:**

1. DISCOVERY PHASE: Before designing, discover dependency classes relevant to
   the requirements. Use list_sources to see what's indexed, then search_symbols
   to find candidate classes. Use get_compound on promising classes to inspect
   their full API (methods, attributes, inheritance). Use find_inheritance to
   verify base classes for your inherits_from references. This ensures your
   design will have accurate dependency links.

2. DESIGN PHASE: Draft your OO design using draft_design. Use check_class_name
   to verify references to external classes. Use validate_design to check for
   structural issues (including enum name collisions with prior designs).
   Revise until the design is clean.

3. VERIFICATION PHASE: For each LLR, write verification procedures that
   reference the design. Use lookup_design_element to find correct qualified
   names. Use validate_qualified_names to verify references. If you find a
   reference that doesn't exist in the design, call draft_design again to add
   the missing member, then continue verifying.

4. COMMIT: When both design and all verifications are clean, call
   commit_design_and_verifications.
```

Replace with:
```
**Workflow:**

digraph design_verify_workflow {
    rankdir=TB;
    discovery [label="Discovery\nlist_sources → search_symbols\n→ get_compound → find_inheritance"];
    design [label="Design\ndraft_design → validate_design\n→ check_class_name"];
    verification [label="Verification\nlookup_design_element\n→ validate_qualified_names"];
    commit [label="Commit\ncommit_design_and_verifications"];
    discovery -> design;
    design -> verification;
    verification -> commit;
    verification -> design [label="missing member\nfound"];
    commit -> verification [label="commit fails\n(qname errors)"];
}
```

- [ ] **Step 2: Verify the prompt renders correctly**

Run:
```bash
cd /Users/danielnewman/dev/ticketing_system && python -c "
from backend.ticketing_agent.design_verify.combined_prompt import SYSTEM_PROMPT
rendered = SYSTEM_PROMPT.format(
    specializations_section='',
    namespace_section='',
    dependency_api_section='',
    as_built_section='',
    existing_classes_section='',
    intercomponent_section='',
)
print('Has dot diagram:', 'digraph design_verify_workflow' in rendered)
print('No old workflow:', 'DISCOVERY PHASE' not in rendered)
"
```
Expected: `Has dot diagram: True`, `No old workflow: True`

- [ ] **Step 3: Commit**

```bash
git add backend/ticketing_agent/design_verify/combined_prompt.py
git commit -m "refactor: replace recommended workflow with dot diagram in design_verify prompt"
```

---

### Task 3: Convert FORMAT-CONTRACT qualified-names to [Good]/[Bad] + anti-patterns table

**Files:**
- Modify: `backend/ticketing_agent/design_verify/combined_prompt.py`

- [ ] **Step 1: Replace the FORMAT-CONTRACT block**

In `combined_prompt.py`, find the entire `<FORMAT-CONTRACT name="qualified-names">` block and replace it with:

```
<FORMAT-CONTRACT name="qualified-names">
All `subject_qualified_name`, `object_qualified_name`, `callee_qualified_name`,
and `caller_qualified_name` fields MUST use qualified names that exactly match
the design context or the current draft.

Pattern: <namespace>::<ClassName>::<memberName>

[Good] calculation_engine::CalculatorEngine::validateInput
[Good] user_interface::CalculatorWindow::equalsButton
[Bad] user_interface::CalculatorWindow.equalsButton
  → Dot separator — use :: everywhere
[Bad] calculation_engine::CalculatorEngine::last_result.is_success
  → Nested attribute path — reference the outer attribute directly
    (calculation_engine::CalculatorEngine::lastResult)
    and the inner class member separately
    (calculation_engine::CalculationResult::isSuccess)
[Bad] result_of_first_call
  → Test variable, not a design element
[Bad] test_validate_input_syntax
  → Test function, not a design element

If no exact match exists in the design context or current draft, do NOT
fabricate a name. Call draft_design to add the missing member, or omit the
reference field and use expected_value alone.

**object_qualified_name** must be a qualified name from the design context or
draft. Use expected_value for literal values and constants:
[Good] object_qualified_name: "Operator::MULTIPLY", expected_value: "active"
[Bad] object_qualified_name: "×"
  → Label, not a qname — use expected_value instead
[Bad] object_qualified_name: "division operator button"
  → Description, not a qname — use expected_value instead

Do not reference constructors (ClassName::ClassName) unless they are
explicitly designed as methods in the design context or your draft.

| Anti-pattern | What goes wrong | Instead |
|---|---|---|
| Dot separator in qname (Window.button) | Parser cannot split on :: — reference undefined | Use :: everywhere: Namespace::Class::member |
| Nested attribute path (Engine::result.is_success) | Cannot reference nested members through a single qname | Reference outer attribute and inner member separately |
| Test variable as qname (result_of_first_call) | Not a design element — lookup fails | Use design element qnames or expected_value for values |
| Test function as qname (test_validate_input) | Not a design element — lookup fails | Reference the method being tested: Namespace::Class::method |
| Label as object_qualified_name ("×") | Not a qname — object_qualified_name expects a design reference | Use expected_value for literal values and constants |
| Description as object_qualified_name ("division operator button") | Not a qname — descriptions don't resolve | Use expected_value for descriptive text, qname for design references |
| Constructor reference (ClassName::ClassName) | No such method unless explicitly designed | Only reference constructors if they appear in the design |
</FORMAT-CONTRACT>
```

Note: The opening paragraph, pattern line, all example pairs, the "do NOT fabricate" paragraph, the object_qualified_name paragraph, and the constructor rule are all preserved — only the markup changes from ✓/✗ to [Good]/[Bad], and the anti-patterns table is added at the end.

- [ ] **Step 2: Verify the change**

Run:
```bash
cd /Users/danielnewman/dev/ticketing_system && python -c "
from backend.ticketing_agent.design_verify.combined_prompt import SYSTEM_PROMPT
rendered = SYSTEM_PROMPT.format(
    specializations_section='',
    namespace_section='',
    dependency_api_section='',
    as_built_section='',
    existing_classes_section='',
    intercomponent_section='',
)
print('Has [Good] format:', '[Good]' in rendered)
print('Has anti-patterns table:', 'Dot separator in qname' in rendered)
print('No old checkmarks:', '✓' not in rendered)
print('No old x marks:', '✗' not in rendered)
"
```
Expected: All four checks True.

- [ ] **Step 3: Commit**

```bash
git add backend/ticketing_agent/design_verify/combined_prompt.py
git commit -m "refactor: convert FORMAT-CONTRACT qualified-names to [Good]/[Bad] style with anti-patterns table"
```

---

### Task 4: Remove container seeding from the prompt in combined_loop.py

**Files:**
- Modify: `backend/ticketing_agent/design_verify/combined_loop.py`

- [ ] **Step 1: Remove `get_container_class_info` import**

In `combined_loop.py`, remove `get_container_class_info` from the import line:

```python
# Before:
from backend.ticketing_agent.design.container_lookup import seed_container_lookup, get_container_class_info

# After:
from backend.ticketing_agent.design.container_lookup import seed_container_lookup
```

- [ ] **Step 2: Remove container_classes from the dependency section building**

In `combined_loop.py`, find and remove the `container_classes` variable and the code that uses it. Specifically:

1. Remove the line:
```python
container_classes = []
```

2. Remove the block:
```python
if neo4j_session is not None:
    container_lookup = seed_container_lookup(neo4j_session)
    if container_lookup:
        container_classes = get_container_class_info(neo4j_session)
```

3. Remove the comment and block that adds container_classes to the dependency context:
```python
all_dep_classes = list(dep_lookup.items())
if container_classes:
    # Add container classes to the dependency context
    all_dep_classes.extend((c["name"], c["qualified_name"]) for c in container_classes)
```

4. Change the conditional:
```python
# Before:
if all_dep_classes:
    dep_classes = [{"qualified_name": qname, "name": bare} for bare, qname in all_dep_classes]
    dep_api_section = build_dependency_api_section(dep_classes)

# After:
if dep_lookup:
    dep_classes = [{"qualified_name": qname, "name": bare} for bare, qname in dep_lookup.items()]
    dep_api_section = build_dependency_api_section(dep_classes)
```

The `seed_container_lookup` call (the one further down that populates `dep_lookup`) stays unchanged.

- [ ] **Step 3: Run existing tests**

Run: `pytest tests/ -x -q --timeout=30 2>&1 | tail -20`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add backend/ticketing_agent/design_verify/combined_loop.py
git commit -m "refactor: remove container class info from design_verify prompt (keep dep_lookup seeding)"
```

---

### Task 5: Add `format_llrs_with_verifications_for_prompt` to formatting.py

**Files:**
- Modify: `backend/requirements/formatting.py`
- Create: `tests/test_formatting_verifications.py`

This new function formats LLRs with their full verification stubs (preconditions, actions, postconditions) for inclusion in the design_verify prompt.

- [ ] **Step 1: Write the failing test**

Create `tests/test_formatting_verifications.py`:

```python
"""Tests for format_llrs_with_verifications_for_prompt."""

from backend.requirements.formatting import format_llrs_with_verifications_for_prompt


def test_single_llr_no_verifications():
    """An LLR with no verifications formats cleanly."""
    llrs = [
        {"id": 1, "description": "The engine computes addition.", "hlr_id": 1},
    ]
    llr_verifications = {}  # no verifications for any LLR
    result = format_llrs_with_verifications_for_prompt(llrs, llr_verifications)
    assert "LLR 1: The engine computes addition." in result
    assert "Verifications" not in result


def test_single_llr_with_verification():
    """An LLR with one verification includes method, test_name, and description."""
    llrs = [
        {"id": 1, "description": "The engine computes addition.", "hlr_id": 1},
    ]
    llr_verifications = {
        1: [
            {
                "method": "automated",
                "test_name": "test_compute_returns_sum",
                "description": "Verify that 2 + 3 returns 5.",
                "preconditions": [],
                "actions": [
                    {
                        "description": "Call compute(2, 3, '+')",
                        "callee_qualified_name": "calc::Engine::compute",
                        "caller_qualified_name": "TestSuite",
                    }
                ],
                "postconditions": [
                    {
                        "subject_qualified_name": "calc::Engine::result",
                        "operator": "==",
                        "expected_value": "5",
                        "object_qualified_name": "",
                    }
                ],
            }
        ],
    }
    result = format_llrs_with_verifications_for_prompt(llrs, llr_verifications)
    assert "[automated] test_compute_returns_sum" in result
    assert "Verify that 2 + 3 returns 5." in result
    assert "Actions: TestSuite → calc::Engine::compute" in result
    assert "calc::Engine::result == 5" in result


def test_llr_with_preconditions_and_object():
    """Preconditions and object_qualified_name are formatted correctly."""
    llrs = [
        {"id": 2, "description": "Engine validates input.", "hlr_id": 1},
    ]
    llr_verifications = {
        2: [
            {
                "method": "automated",
                "test_name": "test_validate_rejects_non_numeric",
                "description": "Verify non-numeric input is rejected.",
                "preconditions": [
                    {
                        "subject_qualified_name": "calc::Engine::initialized",
                        "operator": "is_true",
                        "expected_value": "",
                        "object_qualified_name": "",
                    }
                ],
                "actions": [
                    {
                        "description": "Call validate('abc')",
                        "callee_qualified_name": "calc::Engine::validate",
                        "caller_qualified_name": "",
                    }
                ],
                "postconditions": [
                    {
                        "subject_qualified_name": "calc::Engine::errorState",
                        "operator": "==",
                        "expected_value": "INVALID_INPUT",
                        "object_qualified_name": "calc::ErrorType::INVALID_INPUT",
                    }
                ],
            }
        ],
    }
    result = format_llrs_with_verifications_for_prompt(llrs, llr_verifications)
    assert "Pre-conditions:" in result
    assert "calc::Engine::initialized is_true" in result
    assert "calc::Engine::errorState == INVALID_INPUT" in result
    assert "calc::ErrorType::INVALID_INPUT" in result


def test_empty_conditions_and_actions():
    """Verification with no preconditions, actions, or postconditions shows (none)."""
    llrs = [
        {"id": 3, "description": "Engine returns immediately.", "hlr_id": 1},
    ]
    llr_verifications = {
        3: [
            {
                "method": "inspection",
                "test_name": "test_immediate_response",
                "description": "Verify synchronous response.",
                "preconditions": [],
                "actions": [],
                "postconditions": [],
            }
        ],
    }
    result = format_llrs_with_verifications_for_prompt(llrs, llr_verifications)
    assert "[inspection] test_immediate_response" in result
    assert "(none)" in result


def test_multiple_llrs():
    """Multiple LLRs are formatted sequentially."""
    llrs = [
        {"id": 1, "description": "First LLR.", "hlr_id": 1},
        {"id": 2, "description": "Second LLR.", "hlr_id": 1},
    ]
    llr_verifications = {
        1: [
            {
                "method": "automated",
                "test_name": "test_first_llr",
                "description": "Verify first.",
                "preconditions": [],
                "actions": [],
                "postconditions": [],
            }
        ],
        2: [
            {
                "method": "automated",
                "test_name": "test_second_llr",
                "description": "Verify second.",
                "preconditions": [],
                "actions": [],
                "postconditions": [],
            }
        ],
    }
    result = format_llrs_with_verifications_for_prompt(llrs, llr_verifications)
    assert "LLR 1: First LLR." in result
    assert "LLR 2: Second LLR." in result
    assert "test_first_llr" in result
    assert "test_second_llr" in result
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_formatting_verifications.py -v`
Expected: FAIL — `format_llrs_with_verifications_for_prompt` not found.

- [ ] **Step 3: Implement `format_llrs_with_verifications_for_prompt`**

Add to `backend/requirements/formatting.py`:

```python
def _format_condition(cond: dict) -> str:
    """Format a single condition (pre or post) as a readable string."""
    subject = cond.get("subject_qualified_name", "")
    operator = cond.get("operator", "==")
    expected = cond.get("expected_value", "")
    obj = cond.get("object_qualified_name", "")
    parts = [subject, operator]
    if expected:
        parts.append(expected)
    if obj:
        parts.append(f"(ref: {obj})")
    return " ".join(parts)


def _format_action(action: dict) -> str:
    """Format a single action as a readable string."""
    desc = action.get("description", "")
    callee = action.get("callee_qualified_name", "")
    caller = action.get("caller_qualified_name", "")
    if caller and callee:
        return f"{caller} → {callee}" + (f": {desc}" if desc else "")
    elif callee:
        return callee + (f": {desc}" if desc else "")
    return desc


def _format_verification(v: dict) -> list[str]:
    """Format a single verification stub as indented lines."""
    lines = []
    method = v.get("method", "")
    test_name = v.get("test_name", "")
    desc = v.get("description", "")
    title = f"[{method}]"
    if test_name:
        title += f" {test_name}"
    lines.append(f"    {title}")
    if desc:
        lines.append(f"      {desc}")

    preconditions = v.get("preconditions", [])
    if preconditions:
        lines.append("      Pre-conditions:")
        for cond in preconditions:
            lines.append(f"        {_format_condition(cond)}")
    else:
        lines.append("      Pre-conditions: (none)")

    actions = v.get("actions", [])
    if actions:
        lines.append("      Actions:")
        for action in actions:
            lines.append(f"        {_format_action(action)}")
    else:
        lines.append("      Actions: (none)")

    postconditions = v.get("postconditions", [])
    if postconditions:
        lines.append("      Post-conditions:")
        for cond in postconditions:
            lines.append(f"        {_format_condition(cond)}")
    else:
        lines.append("      Post-conditions: (none)")

    return lines


def format_llrs_with_verifications_for_prompt(
    llrs: list[dict],
    llr_verifications: dict[int, list[dict]],
) -> str:
    """Format LLRs with their full verification stubs for the design_verify prompt.

    Args:
        llrs: List of LLR dicts with at least id, description, hlr_id.
        llr_verifications: Dict mapping LLR ID to list of verification dicts.
            Each verification dict has: method, test_name, description,
            preconditions, actions, postconditions. Each condition dict has:
            subject_qualified_name, operator, expected_value, object_qualified_name.
            Each action dict has: description, callee_qualified_name, caller_qualified_name.

    Returns:
        Formatted text suitable for inclusion in an agent prompt.
    """
    lines = []
    for llr in llrs:
        lines.append(f"LLR {llr['id']}: {llr['description']}")
        verifs = llr_verifications.get(llr["id"], [])
        if verifs:
            lines.append("  Verifications:")
            for v in verifs:
                lines.extend(_format_verification(v))
        else:
            lines.append("  (No verification stubs)")
        lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_formatting_verifications.py -v`
Expected: All 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/requirements/formatting.py tests/test_formatting_verifications.py
git commit -m "feat: add format_llrs_with_verifications_for_prompt to formatting.py"
```

---

### Task 6: Wire the new formatter into combined_loop.py and fetch verification data from Neo4j

**Files:**
- Modify: `backend/ticketing_agent/design_verify/combined_loop.py`

This task modifies `design_and_verify` to fetch full verification data from Neo4j and use the new formatter instead of `format_hlrs_for_prompt`.

- [ ] **Step 1: Add import for the new formatter and VerificationRepository**

In `combined_loop.py`, add the import at the top:

```python
from backend.requirements.formatting import format_llrs_with_verifications_for_prompt
from backend.db.neo4j.repositories.verification import VerificationRepository
```

- [ ] **Step 2: Fetch verification data from Neo4j and build llr_verifications dict**

In `design_and_verify`, after the `requirements_text` line (which currently uses `format_hlrs_for_prompt`), add code to fetch verification stubs from Neo4j and build the rich LLR text. Find the line:

```python
    requirements_text = format_hlrs_for_prompt([hlr], llrs, include_component=True)
```

Replace it with:

```python
    # Format requirements with full verification stubs from decompose
    llr_verifications: dict[int, list[dict]] = {}
    if neo4j_session is not None and llrs:
        ver_repo = VerificationRepository(neo4j_session)
        for llr in llrs:
            llr_id = llr["id"]
            vms = ver_repo.list_verifications(llr_id)
            if vms:
                verifs_for_llr = []
                for vm in vms:
                    conditions = ver_repo.list_conditions(vm.id)
                    actions = ver_repo.list_actions(vm.id)
                    preconds = [
                        {
                            "subject_qualified_name": c.subject_qualified_name,
                            "operator": c.operator,
                            "expected_value": c.expected_value,
                            "object_qualified_name": c.object_qualified_name,
                        }
                        for c in conditions
                        if c.phase == "pre"
                    ]
                    postconds = [
                        {
                            "subject_qualified_name": c.subject_qualified_name,
                            "operator": c.operator,
                            "expected_value": c.expected_value,
                            "object_qualified_name": c.object_qualified_name,
                        }
                        for c in conditions
                        if c.phase == "post"
                    ]
                    action_dicts = [
                        {
                            "description": a.description,
                            "callee_qualified_name": a.callee_qualified_name,
                            "caller_qualified_name": a.caller_qualified_name,
                        }
                        for a in actions
                    ]
                    verifs_for_llr.append({
                        "method": vm.method,
                        "test_name": vm.test_name,
                        "description": vm.description,
                        "preconditions": preconds,
                        "actions": action_dicts,
                        "postconditions": postconds,
                    })
                llr_verifications[llr_id] = verifs_for_llr

    requirements_text = format_llrs_with_verifications_for_prompt(llrs, llr_verifications)

    # Prepend the HLR description
    hlr_line = format_hlr_dict(hlr, include_component=True)
    requirements_text = f"{hlr_line}\n\n{requirements_text}"
```

Also add the import for `format_hlr_dict`:
```python
from backend.requirements.formatting import format_hlr_dict
```

And remove the now-unused import:
```python
from backend.requirements.formatting import format_hlrs_for_prompt
```

- [ ] **Step 3: Remove the `existing_verifications` display from the user message**

The verification data is now in the `requirements_text`. Remove the old `existing_verifs_text` block and its usage. Find and remove:

```python
    # Format existing verification stubs
    existing_verifs_text = ""
    if existing_verifications:
        lines = ["Existing verification stubs:"]
        for v in existing_verifications:
            lines.append(f"  - [{v['method']}] {v.get('test_name', '')}: {v.get('description', '')}")
        existing_verifs_text = "\n".join(lines)
```

And find this line in the user_content section:
```python
    if existing_verifs_text:
        user_content += f"\n\n{existing_verifs_text}"
```

Remove it as well, since verification data is now embedded in `requirements_text`.

- [ ] **Step 4: Run existing tests**

Run: `pytest tests/ -x -q --timeout=30 2>&1 | tail -20`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/ticketing_agent/design_verify/combined_loop.py
git commit -m "feat: wire format_llrs_with_verifications into design_verify prompt"
```

---

### Task 7: Integration test — verify the full prompt renders correctly

**Files:**
- Create: `tests/test_combined_prompt_rendering.py`

- [ ] **Step 1: Write a test that verifies the complete SYSTEM_PROMPT renders without error and contains expected sections**

```python
"""Integration test: verify design_verify SYSTEM_PROMPT renders correctly."""

from backend.ticketing_agent.design_verify.combined_prompt import SYSTEM_PROMPT


def test_system_prompt_renders():
    """SYSTEM_PROMPT renders with all placeholder sections empty."""
    rendered = SYSTEM_PROMPT.format(
        specializations_section="",
        namespace_section="",
        dependency_api_section="",
        as_built_section="",
        existing_classes_section="",
        intercomponent_section="",
    )
    # Should contain the key structural elements
    assert "FORMAT-CONTRACT" in rendered
    assert "digraph design_verify_workflow" in rendered
    assert "[Good]" in rendered
    assert "[Bad]" in rendered
    # Should NOT contain removed elements
    assert "twelve tools available" not in rendered
    assert "### Discovery tools" not in rendered
    assert "### Design & verification tools" not in rendered
    assert "DISCOVERY PHASE" not in rendered
    assert "✓" not in rendered
    assert "✗" not in rendered
    # Should contain FORMAT-CONTRACT content
    assert "qualified-names" in rendered
    assert "verification-key-format" in rendered
    # Should contain instructions
    assert "Instructions" in rendered


def test_system_prompt_renders_with_sections():
    """SYSTEM_PROMPT renders with non-empty placeholder sections."""
    rendered = SYSTEM_PROMPT.format(
        specializations_section="## Specializations\n- C++",
        namespace_section="The required namespace is: `calculation_engine`",
        dependency_api_section="## Dependency API\n### class: `std::vector`",
        as_built_section="",
        existing_classes_section="",
        intercomponent_section="",
    )
    assert "Specializations" in rendered
    assert "calculation_engine" in rendered
    assert "std::vector" in rendered
```

- [ ] **Step 2: Run the integration test**

Run: `pytest tests/test_combined_prompt_rendering.py -v`
Expected: Both tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_combined_prompt_rendering.py
git commit -m "test: add integration test for design_verify SYSTEM_PROMPT rendering"
```

---

### Task 8: Full test suite run

- [ ] **Step 1: Run the complete test suite**

Run: `pytest tests/ -x -q --timeout=30 2>&1 | tail -30`
Expected: All tests pass.

- [ ] **Step 2: Final commit if any fixups needed**

If any tests needed fixups, commit those here. If all passed, skip this step.