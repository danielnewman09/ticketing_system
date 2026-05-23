# Pipeline Validation Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two critical pipeline issues — missing cross-component associations and invalid verification qualified names — through prompt improvements, validation guardrails, formatting standards, and validate-and-retry loops.

**Architecture:** Five targeted fixes across four source files plus one documentation file. Prompt changes use XML contract tags and anti-pattern examples. The validation guardrail adds a qname filter to `verification.py`. The retry loop wraps existing `call_tool` invocations with agent-specific validation. All changes are backwards-compatible — the pipeline still works if no retry is needed.

**Tech Stack:** Python, Pydantic, Neo4j, LLM tool-calling

---

### Task 1: Add `_is_valid_verification_qname` validation function

**Files:**
- Modify: `backend/db/neo4j/repositories/verification.py`
- Test: `tests/test_verification_repository.py`

- [ ] **Step 1: Write the failing test**

Add unit tests for the `_is_valid_verification_qname` function in a new test class in `tests/test_verification_repository.py`:

```python
class TestValidVerificationQname:
    """Unit tests for _is_valid_verification_qname (no Neo4j needed)."""

    def test_valid_qualified_name(self):
        from backend.db.neo4j.repositories.verification import _is_valid_verification_qname
        is_valid, corrected = _is_valid_verification_qname("calculation_engine::CalculatorEngine::add")
        assert is_valid is True
        assert corrected is None

    def test_valid_two_part_qname(self):
        from backend.db.neo4j.repositories.verification import _is_valid_verification_qname
        is_valid, corrected = _is_valid_verification_qname("user_interface::CalculatorWindow")
        assert is_valid is True
        assert corrected is None

    def test_dot_separator_auto_corrected(self):
        from backend.db.neo4j.repositories.verification import _is_valid_verification_qname
        is_valid, corrected = _is_valid_verification_qname("user_interface::CalculatorWindow.equalsButton")
        assert is_valid is True
        assert corrected == "user_interface::CalculatorWindow::equalsButton"

    def test_nested_dot_separator_auto_corrected(self):
        from backend.db.neo4j.repositories.verification import _is_valid_verification_qname
        is_valid, corrected = _is_valid_verification_qname("CalculatorEngine.last_result.is_success")
        assert is_valid is True
        assert corrected == "CalculatorEngine::last_result::is_success"

    def test_reject_test_prefix(self):
        from backend.db.neo4j.repositories.verification import _is_valid_verification_qname
        is_valid, corrected = _is_valid_verification_qname("test_validate_input_syntax")
        assert is_valid is False

    def test_reject_result_of_prefix(self):
        from backend.db.neo4j.repositories.verification import _is_valid_verification_qname
        is_valid, corrected = _is_valid_verification_qname("result_of_first_call")
        assert is_valid is False

    def test_reject_bare_lowercase(self):
        from backend.db.neo4j.repositories.verification import _is_valid_verification_qname
        is_valid, corrected = _is_valid_verification_qname("value")
        assert is_valid is False

    def test_reject_empty_string(self):
        from backend.db.neo4j.repositories.verification import _is_valid_verification_qname
        is_valid, corrected = _is_valid_verification_qname("")
        assert is_valid is False

    def test_reject_none(self):
        from backend.db.neo4j.repositories.verification import _is_valid_verification_qname
        is_valid, corrected = _is_valid_verification_qname(None)
        assert is_valid is False

    def test_reject_decimal_number(self):
        from backend.db.neo4j.repositories.verification import _is_valid_verification_qname
        is_valid, corrected = _is_valid_verification_qname("5.0")
        assert is_valid is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/danielnewman/dev/ticketing_system && source .venv/bin/activate && pytest tests/test_verification_repository.py::TestValidVerificationQname -v`
Expected: FAIL — `_is_valid_verification_qname` not yet defined

- [ ] **Step 3: Implement `_is_valid_verification_qname`**

Add the function above `augment_missing_design_nodes` in `backend/db/neo4j/repositories/verification.py`:

```python
import re

_INVALID_QNAME_PATTERNS = re.compile(
    r'^(test_|result_of_|verify_|check_)'  # test/local identifiers
    | r'^[a-z]+$'                             # bare lowercase word
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
        # Only correct if all parts look like identifier segments (not decimals)
        if all(p and (p[0].isupper() or p[0].islower() or p[0] == '_') for p in parts):
            corrected = '::'.join(parts)
            return True, corrected

    # Require at least one :: separator (namespace::Class or Class::member)
    if '::' not in qname:
        return False, None

    return True, None
```

- [ ] **Step 4: Modify `augment_missing_design_nodes` to use the validator**

In `augment_missing_design_nodes`, replace the simple `if not qname: continue` check with:

```python
    created = []
    for raw_qn in qualified_names:
        if not raw_qn:
            continue

        # Validate and optionally correct the qualified name
        is_valid, corrected = _is_valid_verification_qname(raw_qn)
        if not is_valid:
            log.warning("augment: skipping invalid verification qname: %r", raw_qn)
            created.append(raw_qn)  # track attempted but skipped names
            continue

        qn = corrected if corrected else raw_qn

        # Check if :Design node already exists (with corrected name)
        result = self._session.run(
            "MATCH (d:Design {qualified_name: $qn}) RETURN count(d) AS cnt",
            {"qn": qn},
        )
        if result.single()["cnt"] > 0:
            # If we corrected the name, also check if the original name matches
            # (in case the original is also a valid node)
            continue

        # Parse parent and member name for stub creation
        name = qn.rsplit("::", 1)[-1] if "::" in qn else qn

        # Create the stub :Design node
        self._session.run(
            """
            MERGE (d:Design {qualified_name: $qn})
            SET d.name = $name, d.kind = 'member', d.source_type = 'verification',
                d.description = 'Auto-created from verification reference'
            """,
            {"qn": qn, "name": name},
        )
        created.append(qn)
        log.info("augment: created verification stub :Design node %s", qn)
```

Note: The original `created` list tracked which qualified_names were successfully created as stubs. We need to update the return to only include names that were actually created (not skipped). Also update the return type to include corrected names when applicable.

- [ ] **Step 5: Run the new unit tests to verify they pass**

Run: `cd /Users/danielnewman/dev/ticketing_system && source .venv/bin/activate && pytest tests/test_verification_repository.py::TestValidVerificationQname -v`
Expected: All 10 tests PASS

- [ ] **Step 6: Run existing integration tests to verify no regressions**

Run: `cd /Users/danielnewman/dev/ticketing_system && source .venv/bin/activate && pytest tests/test_verification_repository.py -v --skip-except-neo4j`
Expected: Existing tests still pass (the neo4j tests are skipped without the env var)

- [ ] **Step 7: Commit**

```bash
cd /Users/danielnewman/dev/ticketing_system && git add backend/db/neo4j/repositories/verification.py tests/test_verification_repository.py && git commit -m "feat: add qname validation guardrail to prevent orphan stub nodes

Add _is_valid_verification_qname() to filter out test artifact names,
bare lowercase identifiers, and auto-correct dot separators to ::.
Integrate into augment_missing_design_nodes() so invalid qnames are
skipped with a warning instead of creating disconnected stub nodes."
```

---

### Task 2: Update `design_oo_prompt.py` with CONTRACT and anti-patterns

**Files:**
- Modify: `backend/ticketing_agent/design/design_oo_prompt.py`
- Test: `tests/test_design_oo_prompt.py` (new)

- [ ] **Step 1: Write failing test for prompt content**

Create `tests/test_design_oo_prompt.py`:

```python
"""Tests for design_oo_prompt contract and anti-pattern content."""

from backend.ticketing_agent.design.design_oo_prompt import (
    SYSTEM_PROMPT,
    build_intercomponent_section,
)


class TestIntercomponentSection:
    def test_intercomponent_section_contains_contract(self):
        classes = [
            {
                "qualified_name": "calculation_engine::CalculatorResult",
                "kind": "class",
                "description": "Result wrapper",
                "component_name": "calculation_engine",
                "methods": [{"name": "get_value", "visibility": "public"}],
            }
        ]
        section = build_intercomponent_section(classes)
        assert "<CONTRACT>" in section
        assert "</CONTRACT>" in section
        assert "MUST create associations" in section

    def test_intercomponent_section_contains_example(self):
        classes = [
            {
                "qualified_name": "calculation_engine::CalculatorResult",
                "kind": "class",
                "description": "Result wrapper",
                "component_name": "calculation_engine",
                "methods": [{"name": "get_value", "visibility": "public"}],
            }
        ]
        section = build_intercomponent_section(classes)
        assert "Example" in section or "example" in section.lower()
        assert "depends_on" in section or "associat" in section.lower()

    def test_intercomponent_section_does_not_say_do_not_include(self):
        """The old discouraging text should be removed."""
        classes = [
            {
                "qualified_name": "calc::Result",
                "kind": "class",
                "description": "Result",
                "component_name": "calc",
                "methods": [],
            }
        ]
        section = build_intercomponent_section(classes)
        assert "Do NOT include them in your output" not in section

    def test_empty_classes_returns_empty(self):
        section = build_intercomponent_section([])
        assert section == ""


class TestSystemPromptContract:
    def test_system_prompt_contains_association_contract(self):
        assert "<CONTRACT>" in SYSTEM_PROMPT
        assert "inter-component" in SYSTEM_PROMPT.lower() or "intercomponent" in SYSTEM_PROMPT.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/danielnewman/dev/ticketing_system && source .venv/bin/activate && pytest tests/test_design_oo_prompt.py -v`
Expected: FAIL — `<CONTRACT>` not yet in output

- [ ] **Step 3: Update `build_intercomponent_section()` in `design_oo_prompt.py`**

Replace the current discouraging text in `build_intercomponent_section()`:

**Current** (around line starting with "The following classes..."):
```python
    lines = [
        "## Cross-component interfaces (read-only context)\n",
        "The following classes/interfaces belong to OTHER components and are ",
        "marked as inter-component boundaries. You may reference, depend on, ",
        "or associate with these but do NOT redesign or duplicate them. ",
        "Do NOT include them in your output.\n",
    ]
```

**Replace with:**
```python
    lines = [
        "## Cross-component interfaces (read-only context)\n",
        "The following classes/interfaces belong to OTHER components and are ",
        "marked as inter-component boundaries.\n",
        "<CONTRACT>\n",
        "You MUST create associations from your classes to intercomponent classes ",
        "when your design depends on them (e.g., calls their methods, receives ",
        "their return types, holds references to them). Omitting them creates ",
        "disconnected components in the design.\n\n",
        "Do NOT redesign or duplicate these classes in your output classes — ",
        "only reference their qualified names in associations, inherits_from, ",
        "attribute types, and method return types.\n",
        "</CONTRACT>\n",
    ]
```

Then, after the per-class block loop and before the final `"".join(lines)`, add the example:

```python
    # Example showing expected cross-component associations
    if len(classes) > 0:
        example_class = classes[0]
        example_qname = example_class["qualified_name"]
        example_component = example_class.get("component_name", "other_component")
        lines.append("")
        lines.append("### Example: cross-component association")
        lines.append(f"If your class calls methods on `{example_qname}`, include an association like:")
        lines.append(f"  - from_class: YourClass, to_class: {example_qname}, kind: depends_on")
        lines.append("")
        lines.append("Note: Use the qualified name (with namespace prefix) for intercomponent")
        lines.append("classes in from_class/to_class fields of associations.")

    return "\n".join(lines)
```

- [ ] **Step 4: Add CONTRACT to the Associations guidance in the SYSTEM_PROMPT**

In `SYSTEM_PROMPT` in `design_oo_prompt.py`, after the "### Associations" section and before the "## Visibility" section, add:

```python
<CONTRACT>
When a class in your component interacts with an intercomponent class
(listed in the cross-component section), you MUST include an association
to that class. This is how inter-component dependencies are tracked.
Omitting them creates disconnected components in the design.
</CONTRACT>
```

Add the above as a string in the SYSTEM_PROMPT template, between the associations section and the visibility section.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/danielnewman/dev/ticketing_system && source .venv/bin/activate && pytest tests/test_design_oo_prompt.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/danielnewman/dev/ticketing_system && git add backend/ticketing_agent/design/design_oo_prompt.py tests/test_design_oo_prompt.py && git commit -m "feat: add CONTRACT blocks and intercomponent associations example to design_oo prompt

Replace discouraging 'Do NOT include them in your output' with explicit
contract to create associations to intercomponent classes. Add example
showing the expected association pattern."
```

---

### Task 3: Update `verify_llr_prompt.py` with FORMAT-CONTRACT

**Files:**
- Modify: `backend/ticketing_agent/verify/verify_llr_prompt.py`
- Test: `tests/test_verify_llr_prompt.py` (new)

- [ ] **Step 1: Write failing test for prompt content**

Create `tests/test_verify_llr_prompt.py`:

```python
"""Tests for verify_llr_prompt FORMAT-CONTRACT content."""

from backend.ticketing_agent.verify.verify_llr_prompt import SYSTEM_PROMPT


class TestVerifyPromptFormatContract:
    def test_system_prompt_contains_format_contract(self):
        assert "<FORMAT-CONTRACT" in SYSTEM_PROMPT

    def test_system_prompt_contains_qualified_name_pattern(self):
        assert "::<ClassName>::<memberName>" in SYSTEM_PROMPT or "<namespace>::<ClassName>" in SYSTEM_PROMPT

    def test_system_prompt_contains_negative_examples(self):
        assert "✗" in SYSTEM_PROMPT
        assert "Dot separator" in SYSTEM_PROMPT or "dot separator" in SYSTEM_PROMPT

    def test_system_prompt_contains_positive_examples(self):
        assert "✓" in SYSTEM_PROMPT
        assert "CalculatorEngine" in SYSTEM_PROMPT or "CalculatorWindow" in SYSTEM_PROMPT

    def test_system_prompt_strengthens_qualified_name_guidance(self):
        """The strengthened guidance should mention 'fabricate'."""
        assert "fabricate" in SYSTEM_PROMPT.lower() or "exactly match" in SYSTEM_PROMPT.lower()


class TestFormatStructuredContext:
    def test_empty_context(self):
        from backend.ticketing_agent.verify.verify_llr_prompt import format_structured_context
        result = format_structured_context([])
        assert result == "(no design context)"

    def test_single_class_context(self):
        from backend.ticketing_agent.verify.verify_llr_prompt import format_structured_context
        ctx = [
            {
                "qualified_name": "calc::Engine",
                "kind": "class",
                "description": "An engine",
                "attributes": [],
                "methods": [],
                "relationships": [],
            }
        ]
        result = format_structured_context(ctx)
        assert "calc::Engine" in result
        assert "class" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/danielnewman/dev/ticketing_system && source .venv/bin/activate && pytest tests/test_verify_llr_prompt.py -v`
Expected: FAIL — FORMAT-CONTRACT not yet in SYSTEM_PROMPT

- [ ] **Step 3: Add FORMAT-CONTRACT to `verify_llr_prompt.py` SYSTEM_PROMPT**

In `backend/ticketing_agent/verify/verify_llr_prompt.py`, insert the FORMAT-CONTRACT block into the SYSTEM_PROMPT between the design context placeholder and the "## Instructions" section. The SYSTEM_PROMPT string currently starts with:

```python
SYSTEM_PROMPT = """\
You are a verification engineer. Given a low-level requirement and the
ontology design (classes, structs, enums, etc.), your job is to produce
a detailed, structured verification procedure.

## Design context

{design_context}

## Instructions
...
```

Insert a FORMAT-CONTRACT section after `{design_context}` and before `## Instructions`:

```python
SYSTEM_PROMPT = """\
You are a verification engineer. Given a low-level requirement and the
ontology design (classes, structs, enums, etc.), your job is to produce
a detailed, structured verification procedure.

## Design context

{design_context}

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

## Instructions
...
```

Also update the guideline line. Find:

```python
- Keep conditions specific and testable — avoid vague assertions
```

Replace with:

```python
- Keep conditions specific and testable. Every qualified name you write MUST exactly match a name shown in the design context section. If no exact match exists, do not fabricate one — omit the reference field or use expected_value alone.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/danielnewman/dev/ticketing_system && source .venv/bin/activate && pytest tests/test_verify_llr_prompt.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/danielnewman/dev/ticketing_system && git add backend/ticketing_agent/verify/verify_llr_prompt.py tests/test_verify_llr_prompt.py && git commit -m "feat: add FORMAT-CONTRACT block and strengthened qname guidance to verify prompt

Add explicit qualified-name grammar with ✓/✗ examples, rule against
fabricating names, and strengthen the 'specific and testable' guideline
to mandate exact matches to design context."
```

---

### Task 4: Add validate-and-retry loop to `design_oo.py`

**Files:**
- Modify: `backend/ticketing_agent/design/design_oo.py`
- Test: `tests/test_design_oo_retry.py` (new)

- [ ] **Step 1: Write failing tests for the retry validation functions**

Create `tests/test_design_oo_retry.py`:

```python
"""Tests for design_oo validate-and-retry loop."""

from backend.codebase.schemas import AssociationSchema, ClassSchema, OODesignSchema, MethodSchema, AttributeSchema


class TestValidateDesignAssociations:
    """Test _validate_oo_design association validation."""

    def test_unknown_association_target_flagged(self):
        from backend.ticketing_agent.design.design_oo import _validate_oo_design
        oo = OODesignSchema(
            modules=["ui"],
            classes=[
                ClassSchema(name="CalculatorWindow", module="ui", attributes=[], methods=[]),
            ],
            associations=[
                AssociationSchema(
                    from_class="CalculatorWindow",
                    to_class="NonExistentClass",
                    kind="depends_on",
                    description="Unknown ref",
                ),
            ],
        )
        errors = _validate_oo_design(
            oo,
            prior_class_lookup={},
            dependency_lookup={},
            intercomponent_classes=[],
        )
        assert any("NonExistentClass" in e for e in errors)

    def test_known_intercomponent_class_not_flagged(self):
        from backend.ticketing_agent.design.design_oo import _validate_oo_design
        oo = OODesignSchema(
            modules=["ui"],
            classes=[
                ClassSchema(name="CalculatorWindow", module="ui", attributes=[], methods=[]),
            ],
            associations=[
                AssociationSchema(
                    from_class="CalculatorWindow",
                    to_class="calculation_engine::CalculatorEngine",
                    kind="depends_on",
                    description="Uses engine",
                ),
            ],
        )
        errors = _validate_oo_design(
            oo,
            prior_class_lookup={},
            dependency_lookup={},
            intercomponent_classes=[
                {"qualified_name": "calculation_engine::CalculatorEngine", "kind": "class"},
            ],
        )
        assert len(errors) == 0

    def test_missing_intercomponent_association_flagged(self):
        from backend.ticketing_agent.design.design_oo import _validate_oo_design
        oo = OODesignSchema(
            modules=["ui"],
            classes=[
                ClassSchema(
                    name="CalculatorWindow",
                    module="ui",
                    attributes=[
                        AttributeSchema(name="result", type_name="CalculatorResult", visibility="private", description=""),
                    ],
                    methods=[
                        MethodSchema(name="calculate", visibility="public", description="", parameters=[], return_type="CalculatorResult"),
                    ],
                ),
            ],
            associations=[],
        )
        errors = _validate_oo_design(
            oo,
            prior_class_lookup={},
            dependency_lookup={},
            intercomponent_classes=[
                {"qualified_name": "calculation_engine::CalculatorResult", "kind": "class"},
            ],
        )
        assert any("CalculatorResult" in e and "no association" in e for e in errors)

    def test_valid_design_no_errors(self):
        from backend.ticketing_agent.design.design_oo import _validate_oo_design
        oo = OODesignSchema(
            modules=["ui"],
            classes=[
                ClassSchema(name="CalculatorWindow", module="ui", attributes=[], methods=[]),
            ],
            associations=[],
        )
        errors = _validate_oo_design(
            oo,
            prior_class_lookup={},
            dependency_lookup={},
            intercomponent_classes=[],
        )
        assert len(errors) == 0

    def test_dependency_lookup_target_not_flagged(self):
        from backend.ticketing_agent.design.design_oo import _validate_oo_design
        oo = OODesignSchema(
            modules=["ui"],
            classes=[
                ClassSchema(name="CalculatorWindow", module="ui", attributes=[], methods=[]),
            ],
            associations=[
                AssociationSchema(
                    from_class="CalculatorWindow",
                    to_class="Fl_Button",
                    kind="aggregates",
                    description="Uses buttons",
                ),
            ],
        )
        errors = _validate_oo_design(
            oo,
            prior_class_lookup={},
            dependency_lookup={"Fl_Button": "Fl_Button"},
            intercomponent_classes=[],
        )
        assert len(errors) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/danielnewman/dev/ticketing_system && source .venv/bin/activate && pytest tests/test_design_oo_retry.py -v`
Expected: FAIL — `_validate_oo_design` not yet defined

- [ ] **Step 3: Implement `_validate_oo_design` in `design_oo.py`**

Add the following function and constant near the top of `backend/ticketing_agent/design/design_oo.py` (after imports):

```python
import json
import logging

log = logging.getLogger("agents.design")

MAX_TOOL_RETRIES = 2


def _validate_oo_design(
    oo: OODesignSchema,
    prior_class_lookup: dict[str, str],
    dependency_lookup: dict[str, str],
    intercomponent_classes: list[dict],
) -> list[str]:
    """Validate an OO design for association target resolution and intercomponent coverage.

    Returns a list of error strings. Empty list means valid.
    """
    errors = []

    # Build set of known names
    design_class_names = {cls.name for cls in oo.classes}
    design_iface_names = {iface.name for iface in oo.interfaces}
    design_enum_names = {enum.name for enum in oo.enums}
    all_design_names = design_class_names | design_iface_names | design_enum_names

    # Set of intercomponent qualified names for lookup
    intercomp_qnames = {c["qualified_name"] for c in intercomponent_classes}
    intercomp_bare = {qname.rsplit("::", 1)[-1] for qname in intercomp_qnames}

    # Check 1: Unknown association targets
    for assoc in oo.associations:
        for ref in [assoc.from_class, assoc.to_class]:
            if ref in all_design_names:
                continue
            if ref in prior_class_lookup:
                continue
            if ref in dependency_lookup:
                continue
            if ref in intercomp_qnames or ref in intercomp_bare:
                continue
            errors.append(
                f"Unknown class reference: \"{ref}\" in association "
                f"({assoc.from_class} -[{assoc.kind}]-> {assoc.to_class}). "
                f"\"{ref}\" is not defined in this design or the provided context."
            )

    # Check 2: Missing intercomponent associations
    if intercomponent_classes:
        for cls in oo.classes:
            # Check if this class references any intercomponent class in attributes/methods
            referenced_intercomp = set()
            for attr in cls.attributes:
                for ic in intercomponent_classes:
                    ic_name = ic["qualified_name"].rsplit("::", 1)[-1]
                    if attr.type_name and (ic_name in attr.type_name or ic["qualified_name"] in attr.type_name):
                        referenced_intercomp.add(ic["qualified_name"])
            for method in cls.methods:
                if method.return_type:
                    for ic in intercomponent_classes:
                        ic_name = ic["qualified_name"].rsplit("::", 1)[-1]
                        if ic_name in method.return_type or ic["qualified_name"] in method.return_type:
                            referenced_intercomp.add(ic["qualified_name"])

            if referenced_intercomp:
                # Check if there's an association to each referenced intercomponent class
                assoc_targets = {assoc.to_class for assoc in oo.associations} | {assoc.from_class for assoc in oo.associations}
                for ic_qname in referenced_intercomp:
                    if ic_qname not in assoc_targets:
                        ic_bare = ic_qname.rsplit("::", 1)[-1]
                        if ic_bare not in assoc_targets:
                            errors.append(
                                f"Missing intercomponent association: {cls.name} references "
                                f"{ic_qname} in attributes/methods but has no association to it."
                            )

    return errors


def _format_design_validation_errors(errors: list[str]) -> str:
    """Format design validation errors into a retry message."""
    issue_lines = "\n".join(f"{i+1}. {e}" for i, e in enumerate(errors))
    return (
        "Your previous output had the following issues:\n\n"
        f"<issues>\n{issue_lines}\n</issues>\n\n"
        "Please correct these issues and respond again with the fixed output."
    )
```

- [ ] **Step 4: Integrate retry loop into `design_oo()` function**

Modify the `design_oo()` function to wrap the `call_tool` invocation in a retry loop. The current code ends with:

```python
    result = call_tool(
        system=system,
        messages=[user_message],
        tools=[TOOL_DEFINITION],
        tool_name="produce_oo_design",
        model=model,
        prompt_log_file=prompt_log_file,
    )

    schema = OODesignSchema.model_validate(result)
    ...
    return schema
```

Replace with:

```python
    messages = [user_message]

    for attempt in range(MAX_TOOL_RETRIES + 1):
        result = call_tool(
            system=system,
            messages=messages,
            tools=[TOOL_DEFINITION],
            tool_name="produce_oo_design",
            model=model,
            prompt_log_file=prompt_log_file if attempt == 0 else "",
        )

        schema = OODesignSchema.model_validate(result)

        # Validate associations
        errors = _validate_oo_design(
            schema,
            prior_class_lookup=prior_class_lookup or {},
            dependency_lookup=dependency_lookup or {},
            intercomponent_classes=intercomponent_classes or [],
        )

        if not errors:
            break  # Valid output, proceed

        if attempt < MAX_TOOL_RETRIES:
            log.warning(
                "design_oo: validation errors on attempt %d/%d: %s",
                attempt + 1, MAX_TOOL_RETRIES + 1, errors,
            )
            error_msg = _format_design_validation_errors(errors)
            messages.append({"role": "assistant", "content": json.dumps(result)})
            messages.append({"role": "user", "content": error_msg})
            continue

        # Final attempt still has errors — log and proceed
        log.warning(
            "design_oo: %d validation errors after %d attempts: %s",
            len(errors), MAX_TOOL_RETRIES + 1, errors,
        )

    for cls in schema.classes:
        if not cls.methods and not cls.attributes:
            log.warning(
                "design_oo: class %s has no methods or attributes — "
                "the model may have dropped nested arrays",
                cls.name,
            )

    return schema
```

Note: Add `import json` at the top of the file if not already present.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/danielnewman/dev/ticketing_system && source .venv/bin/activate && pytest tests/test_design_oo_retry.py -v`
Expected: All tests PASS

- [ ] **Step 6: Run existing design tests to verify no regressions**

Run: `cd /Users/danielnewman/dev/ticketing_system && source .venv/bin/activate && pytest tests/test_map_to_ontology.py tests/test_oo_design_schema.py -v`
Expected: All existing tests still PASS

- [ ] **Step 7: Commit**

```bash
cd /Users/danielnewman/dev/ticketing_system && git add backend/ticketing_agent/design/design_oo.py tests/test_design_oo_retry.py && git commit -m "feat: add validate-and-retry loop to design_oo agent

Add _validate_oo_design() to check for unknown association targets
and missing intercomponent associations. Wrap call_tool in retry loop
that feeds validation errors back to the LLM for up to 2 retries."
```

---

### Task 5: Add validate-and-retry loop to `verify_llr.py`

**Files:**
- Modify: `backend/ticketing_agent/verify/verify_llr.py`
- Test: `tests/test_verify_retry.py` (new)

- [ ] **Step 1: Write failing test for the validation+retry integration**

Create `tests/test_verify_retry.py`:

```python
"""Tests for verify_llr validate-and-retry integration."""

import json
from unittest.mock import MagicMock, patch

from backend.requirements.schemas import VerificationSchema, ConditionSchema, ActionSchema


class TestVerifyRetryLoop:
    """Test that verify() retries when validation finds unresolved references."""

    def test_format_verification_validation_errors(self):
        from backend.ticketing_agent.verify.verify_llr import _format_verification_validation_errors
        errors = [
            "user_interface::CalculatorWindow.equalsButton — dot separator, use ::",
            "result_of_first_call — not a design element",
        ]
        msg = _format_verification_validation_errors(errors)
        assert "<issues>" in msg
        assert "CalculatorWindow.equalsButton" in msg
        assert "result_of_first_call" in msg
        assert "correct these issues" in msg

    def test_collect_qualified_names_from_verifications(self):
        from backend.ticketing_agent.verify.verify_llr import _collect_qualified_names
        vs = [
            VerificationSchema(
                method="automated",
                test_name="test_add",
                description="Test add",
                preconditions=[
                    ConditionSchema(subject_qualified_name="calc::Engine::precision", operator="==", expected_value="2"),
                ],
                actions=[
                    ActionSchema(description="Call add", callee_qualified_name="calc::Engine::add"),
                ],
                postconditions=[
                    ConditionSchema(subject_qualified_name="calc::Engine::result", operator="==", expected_value="5"),
                ],
            ),
        ]
        qnames = _collect_qualified_names(vs)
        assert "calc::Engine::precision" in qnames
        assert "calc::Engine::add" in qnames
        assert "calc::Engine::result" in qnames
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/danielnewman/dev/ticketing_system && source .venv/bin/activate && pytest tests/test_verify_retry.py -v`
Expected: FAIL — `_format_verification_validation_errors` not yet defined

- [ ] **Step 3: Add validation retry loop to `verify_llr.py`**

Add constants and helper functions near the top of `backend/ticketing_agent/verify/verify_llr.py` (after the existing imports):

```python
import json
import logging

log = logging.getLogger("agents.verify")

MAX_TOOL_RETRIES = 2
```

Add the validation error formatter after the `_collect_qualified_names` function:

```python
def _format_verification_validation_errors(unresolved: list[str]) -> str:
    """Format unresolved qualified name errors into a retry message.

    Includes the FORMAT-CONTRACT reminder so the LLM sees the syntax rules again.
    """
    issue_lines = "\n".join(f"{i+1}. \"{qn}\"" for i, qn in enumerate(unresolved))
    return (
        "Your previous output referenced qualified names that do not exist "
        "in the design context:\n\n"
        f"<issues>\n{issue_lines}\n</issues>\n\n"
        "Please correct these issues by referencing ONLY names that appear "
        "in the design context section above. Use :: separators (not dots). "
        "Do not fabricate test-local variable names.\n\n"
        "Respond again with the corrected verifications."
    )
```

- [ ] **Step 4: Modify the `verify()` function to use retry loop**

The current `verify()` function calls `call_tool` once and then validates. Modify it to wrap in a retry loop. The current code after `verifications = [VerificationSchema...`:

Replace the existing validation and return section starting from the `# Validate references` comment:

```python
    # Validate references against :Design nodes in Neo4j
    resolved = []
    unresolved = []
    if neo4j_session is not None:
        from backend.db.neo4j.repositories.verification import VerificationRepository

        qnames = _collect_qualified_names(verifications)
        if qnames:
            repo = VerificationRepository(neo4j_session)
            resolved, unresolved = repo.validate_references(qnames)

    return VerifyResult(verifications=verifications, resolved=resolved, unresolved=unresolved)
```

With a retry loop:

```python
    # Validate references against :Design nodes in Neo4j and retry if needed
    for attempt in range(MAX_TOOL_RETRIES + 1):
        resolved = []
        unresolved = []

        if neo4j_session is not None:
            from backend.db.neo4j.repositories.verification import VerificationRepository

            qnames = _collect_qualified_names(verifications)
            if qnames:
                repo = VerificationRepository(neo4j_session)
                resolved, unresolved = repo.validate_references(qnames)

        if not unresolved:
            break  # All references valid, proceed

        if attempt < MAX_TOOL_RETRIES:
            log.warning(
                "verify: %d unresolved references on attempt %d/%d: %s",
                len(unresolved), attempt + 1, MAX_TOOL_RETRIES + 1, unresolved,
            )
            error_msg = _format_verification_validation_errors(unresolved)
            messages.append({"role": "assistant", "content": json.dumps(result)})
            messages.append({"role": "user", "content": error_msg})

            # Retry: call the LLM again
            result = call_tool(
                system=system_prompt,
                messages=messages,
                tools=[TOOL_DEFINITION],
                tool_name="produce_verifications",
                model=model,
                prompt_log_file="",
            )
            verifications = [VerificationSchema.model_validate(v) for v in result["verifications"]]
            continue

        # Final attempt still has unresolved — log and proceed
        log.warning(
            "verify: %d unresolved references after %d attempts: %s",
            len(unresolved), MAX_TOOL_RETRIES + 1, unresolved,
        )

    return VerifyResult(verifications=verifications, resolved=resolved, unresolved=unresolved)
```

Important: We need to restructure the function slightly so that `system_prompt` and `messages` are available throughout the retry loop. The current function builds `system_prompt` and `user_message` before calling `call_tool`. We need to keep these accessible for retries. This means changing `[user_message]` to a `messages` list that we can append to:

In the `verify()` function, change:

```python
    result = call_tool(
        system=system_prompt,
        messages=[user_message],
        ...
    )
```

to:

```python
    messages = [user_message]

    result = call_tool(
        system=system_prompt,
        messages=messages,
        ...
    )
```

And then the validation+retry loop uses the `messages` list.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/danielnewman/dev/ticketing_system && source .venv/bin/activate && pytest tests/test_verify_retry.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/danielnewman/dev/ticketing_system && git add backend/ticketing_agent/verify/verify_llr.py tests/test_verify_retry.py && git commit -m "feat: add validate-and-retry loop to verify_llr agent

When verification references don't match design nodes, feed the errors
back to the LLM with a format-contract reminder. Retry up to 2 times
before proceeding with unresolved references (which are filtered by
the _is_valid_verification_qname guardrail)."
```

---

### Task 6: Create the prompt formatting guide document

**Files:**
- Create: `docs/prompt-formatting-guide.md`

- [ ] **Step 1: Write the formatting guide**

Create `docs/prompt-formatting-guide.md` with the content from Fix 4 of the design spec. This includes:
- Standard section ordering table
- `<CONTRACT>` pattern with rules
- `<FORMAT-CONTRACT>` pattern with rules
- Anti-pattern `<Bad>`/`<Good>` pairs and tables with rules
- Context section builder enhancement notes
- Checklist for reviewing new/edited prompts

The content is directly from the approved spec section "Fix 4: Prompt Formatting Contract".

- [ ] **Step 2: Commit**

```bash
cd /Users/danielnewman/dev/ticketing_system && git add docs/prompt-formatting-guide.md && git commit -m "docs: add prompt formatting guide for agent prompts

Documents the CONTRACT, FORMAT-CONTRACT, and anti-pattern formatting
patterns used in agent prompts, with rules and examples. Serves as
reference for all future prompt edits."
```

---

### Task 7: End-to-end pipeline validation

**Files:**
- No new files — manual testing

- [ ] **Step 1: Flush the database and run the full pipeline**

```bash
cd /Users/danielnewman/dev/ticketing_system
source .venv/bin/activate
python scripts/01_flush_db.py
python scripts/02_setup_project.py
python scripts/03_design_requirements.py
```

- [ ] **Step 2: Verify cross-component associations exist**

Run a Neo4j query to check for cross-component relationships:

```python
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'msd-local-dev'))
with driver.session() as session:
    result = session.run('''
        MATCH (d1:Design)-[r]->(d2:Design)
        WHERE d1.qualified_name STARTS WITH 'user_interface'
          AND d2.qualified_name STARTS WITH 'calculation_engine'
        RETURN d1.qualified_name AS from_qn, type(r) AS rtype, d2.qualified_name AS to_qn
    ''')
    rows = list(result)
    if rows:
        print("Cross-component links found:")
        for r in rows:
            print(f"  {r['from_qn']} --{r['rtype']}--> {r['to_qn']}")
    else:
        print("WARNING: No cross-component links found between user_interface and calculation_engine")
driver.close()
```

Expected: At least one `depends_on` or `invokes` association from `CalculatorWindow` to `calculation_engine::CalculatorEngine` and/or `calculation_engine::CalculatorResult`.

- [ ] **Step 3: Verify no orphan stub nodes from verification**

Run a Neo4j query to check for disconnected stub nodes:

```python
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'msd-local-dev'))
with driver.session() as session:
    result = session.run('''
        MATCH (d:Design)
        WHERE NOT (d)-[:COMPOSES]->() AND NOT ()-[:COMPOSES]->(d)
          AND NOT (d:Design)-[:TRACES_TO]-()
        RETURN d.qualified_name AS qname, d.kind AS kind, d.source_type AS source_type
        ORDER BY qname
    ''')
    orphans = list(result)
    if orphans:
        print(f"WARNING: {len(orphans)} orphan nodes found:")
        for r in orphans:
            print(f"  {r['qname']} ({r['kind']}) source={r['source_type']}")
    else:
        print("No orphan nodes found — all nodes are connected.")
driver.close()
```

Expected: No `test_*`, `result_of_*`, or `*.equalsButton`-style nodes. Any remaining orphans should be legitimate stubs with `::` separators.

- [ ] **Step 4: Commit any fixes if needed**

If Issues are found during validation, fix them and commit.