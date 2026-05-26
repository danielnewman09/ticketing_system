# Draft Verifications Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `draft_verifications` tool to the design_verify combined loop so the agent can iteratively draft and validate verification method references against the design before committing.

**Architecture:** Mirror the existing `draft_design` → `validate_design` → `commit` pattern by adding a `draft_verifications` tool that stores verification data in dispatcher state and validates all qualified name references against the current design draft and context. Refactor the shared qname resolution logic from `_dispatch_commit` into reusable helpers. Update the system prompt to instruct the agent to resolve verification stubs against the design using the new tool.

**Tech Stack:** Python, Pydantic, Neo4j

---

## Task 1: Add Pydantic `field_validator` for `VerificationConditionSchema.operator`

Ensure conditions always have a valid operator, even when the LLM sends `null` or omits the field.

**Files:**
- Modify: `backend/requirements/schemas.py`
- Test: `tests/test_requirements_schemas.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_requirements_schemas.py`:

```python
def test_condition_schema_defaults_none_operator():
    """VerificationConditionSchema defaults None/empty operator to '=='."""
    cond = VerificationConditionSchema(
        subject_qualified_name="ns::Class::attr",
        expected_value="5.0",
    )
    assert cond.operator == "=="


def test_condition_schema_defaults_empty_operator():
    """VerificationConditionSchema defaults empty string operator to '=='."""
    cond = VerificationConditionSchema(
        subject_qualified_name="ns::Class::attr",
        operator="",
        expected_value="5.0",
    )
    assert cond.operator == "=="


def test_condition_schema_preserves_explicit_operator():
    """VerificationConditionSchema preserves explicit non-default operators."""
    cond = VerificationConditionSchema(
        subject_qualified_name="ns::Class::attr",
        operator="is_true",
        expected_value="true",
    )
    assert cond.operator == "is_true"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/danielnewman/dev/ticketing_system && python -m pytest tests/test_requirements_schemas.py -v -k "test_condition_schema"`
Expected: `test_condition_schema_defaults_none_operator` PASSES (Pydantic already defaults missing fields). `test_condition_schema_defaults_empty_operator` may PASS or FAIL depending on whether `""` is treated as the default. The real fix is ensuring `None` is handled.

- [ ] **Step 3: Add `field_validator` to `VerificationConditionSchema`**

Modify `backend/requirements/schemas.py` — add import and validator:

```python
from pydantic import BaseModel, field_validator


class VerificationConditionSchema(BaseModel):
    subject_qualified_name: str
    operator: str = "=="
    expected_value: str = ""
    object_qualified_name: str = ""

    @field_validator("operator", mode="before")
    @classmethod
    def default_operator(cls, v):
        if v is None or v == "":
            return "=="
        return v
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/danielnewman/dev/ticketing_system && python -m pytest tests/test_requirements_schemas.py -v -k "test_condition_schema"`
Expected: All 3 tests PASS.

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `cd /Users/danielnewman/dev/ticketing_system && python -m pytest tests/ -v --tb=short`
Expected: All existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add backend/requirements/schemas.py tests/test_requirements_schemas.py
git commit -m "feat: add field_validator to default VerifyConditionSchema.operator to '=='
"
```

---

## Task 2: Add shared `_qname_resolves` and `_suggest_qname` helpers

Extract qname resolution logic from `_dispatch_commit` into reusable helpers that both `draft_verifications` and `_dispatch_commit` will share.

**Files:**
- Modify: `backend/ticketing_agent/design_verify/combined_tools.py`
- Test: `tests/test_combined_tools.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_combined_tools.py`:

```python
class TestQnameResolves:
    def test_resolves_in_draft_lookup(self):
        """_qname_resolves finds qname in draft lookup."""
        from backend.ticketing_agent.design_verify.combined_tools import _qname_resolves
        draft_lookup = {"ns::Calculator": {"kind": "class"}}
        assert _qname_resolves("ns::Calculator", draft_lookup=draft_lookup) is True

    def test_resolves_in_prior_lookup_values(self):
        """_qname_resolves finds qname as a value in prior_class_lookup."""
        from backend.ticketing_agent.design_verify.combined_tools import _qname_resolves
        prior_lookup = {"Calculator": "ns::Calculator"}
        assert _qname_resolves("ns::Calculator", prior_class_lookup=prior_lookup) is True

    def test_resolves_in_prior_lookup_keys(self):
        """_qname_resolves finds qname as a key in prior_class_lookup."""
        from backend.ticketing_agent.design_verify.combined_tools import _qname_resolves
        prior_lookup = {"Calculator": "ns::Calculator"}
        assert _qname_resolves("Calculator", prior_class_lookup=prior_lookup) is True

    def test_resolves_in_dep_lookup(self):
        """_qname_resolves finds qname in dependency lookup."""
        from backend.ticketing_agent.design_verify.combined_tools import _qname_resolves
        dep_lookup = {"std::vector": "std::vector"}
        assert _qname_resolves("std::vector", dep_lookup=dep_lookup) is True

    def test_resolves_in_intercomponent(self):
        """_qname_resolves finds qname in intercomponent classes."""
        from backend.ticketing_agent.design_verify.combined_tools import _qname_resolves
        ic = [{"qualified_name": "user_interface::Display"}]
        assert _qname_resolves("user_interface::Display", intercomponent_classes=ic) is True

    def test_returns_false_for_unknown(self):
        """_qname_resolves returns False for unknown qnames."""
        from backend.ticketing_agent.design_verify.combined_tools import _qname_resolves
        assert _qname_resolves("ns::NonExistent") is False


class TestSuggestQname:
    def test_suggests_bare_name_match(self):
        """_suggest_qname finds match by bare name in prior/dep lookup."""
        from backend.ticketing_agent.design_verify.combined_tools import _suggest_qname
        result = _suggest_qname(
            "Calculator",
            draft_lookup={},
            prior_class_lookup={"Calculator": "calculation_engine::Calculator"},
            dep_lookup={},
            intercomponent_classes=[],
        )
        assert result == "calculation_engine::Calculator"

    def test_suggests_member_name_match(self):
        """_suggest_qname finds match by member name in draft lookup."""
        from backend.ticketing_agent.design_verify.combined_tools import _suggest_qname
        draft_lookup = {
            "calculation_engine::Calculator": {"kind": "class"},
            "calculation_engine::Calculator::add": {"kind": "method"},
        }
        result = _suggest_qname(
            "add",
            draft_lookup=draft_lookup,
            prior_class_lookup={},
            dep_lookup={},
            intercomponent_classes=[],
        )
        assert result == "calculation_engine::Calculator::add"

    def test_strips_stub_suffixes(self):
        """_suggest_qname strips .output/.result/.return_value before matching."""
        from backend.ticketing_agent.design_verify.combined_tools import _suggest_qname
        result = _suggest_qname(
            "Calculator.add.output",
            draft_lookup={
                "calculation_engine::Calculator::add": {"kind": "method"},
            },
            prior_class_lookup={},
            dep_lookup={},
            intercomponent_classes=[],
        )
        assert result == "calculation_engine::Calculator::add"

    def test_returns_none_for_no_match(self):
        """_suggest_qname returns None when no match found."""
        from backend.ticketing_agent.design_verify.combined_tools import _suggest_qname
        result = _suggest_qname(
            "CompletelyUnknown",
            draft_lookup={},
            prior_class_lookup={},
            dep_lookup={},
            intercomponent_classes=[],
        )
        assert result is None

    def test_substring_match(self):
        """_suggest_qname finds partial matches via substring."""
        from backend.ticketing_agent.design_verify.combined_tools import _suggest_qname
        draft_lookup = {"calculation_engine::CalculationResult": {"kind": "class"}}
        result = _suggest_qname(
            "CalculationResult",
            draft_lookup=draft_lookup,
            prior_class_lookup={},
            dep_lookup={},
            intercomponent_classes=[],
        )
        assert result == "calculation_engine::CalculationResult"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/danielnewman/dev/ticketing_system && python -m pytest tests/test_combined_tools.py -v -k "TestQnameResolves or TestSuggestQname"`
Expected: FAIL — `_qname_resolves` and `_suggest_qname` not yet defined as module-level functions.

- [ ] **Step 3: Add `_qname_resolves` and `_suggest_qname` as module-level functions**

Add these to `backend/ticketing_agent/design_verify/combined_tools.py`, after the existing imports and before the tool definitions section. These are pure functions that accept their dependencies as parameters (no closure over dispatcher state):

```python
# ---------------------------------------------------------------------------
# Shared qname resolution helpers
# ---------------------------------------------------------------------------


def _qname_resolves(
    qname: str,
    draft_lookup: dict[str, dict] | None = None,
    prior_class_lookup: dict[str, str] | None = None,
    dep_lookup: dict[str, str] | None = None,
    intercomponent_classes: list[dict] | None = None,
    neo4j_session=None,
) -> bool:
    """Check whether a qualified name exists in the design context.

    Checks draft lookup, prior class lookup, dependency lookup,
    intercomponent classes, and (optionally) Neo4j persistent store.
    """
    if draft_lookup and qname in draft_lookup:
        return True
    if prior_class_lookup:
        if qname in prior_class_lookup.values():
            return True
        if qname in prior_class_lookup:
            return True
    if dep_lookup:
        if qname in dep_lookup:
            return True
        if qname in dep_lookup.values():
            return True
    if intercomponent_classes:
        ic_qnames = {c["qualified_name"] for c in intercomponent_classes}
        if qname in ic_qnames:
            return True
    if neo4j_session is not None:
        from backend.db.neo4j.repositories.design import DesignRepository
        repo = DesignRepository(neo4j_session)
        nodes = repo.find_nodes(search=qname, exclude_source_types=["verification"])
        if any(n.qualified_name == qname for n in nodes):
            return True
    return False


def _suggest_qname(
    unresolved: str,
    draft_lookup: dict[str, dict],
    prior_class_lookup: dict[str, str],
    dep_lookup: dict[str, str],
    intercomponent_classes: list[dict],
) -> str | None:
    """Find the closest matching qualified name for an unresolved reference.

    Searches by bare name, member name, and substring matching.
    Strips common stub suffixes (.output, .result, .return_value).

    Does NOT query Neo4j — only in-memory lookups for speed.
    """
    # Strip common stub suffixes
    cleaned = unresolved
    for suffix in (".output", ".result", ".return_value"):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)]

    # Strategy 1: bare name match in prior/dep lookups
    bare = unresolved.rsplit("::", 1)[-1].rsplit(".", 1)[-1]
    for name, qname in {**prior_class_lookup, **dep_lookup}.items():
        if name == bare or name.lower() == bare.lower():
            return qname

    # Strategy 2: member name match in draft
    for qname, info in draft_lookup.items():
        kind = info.get("kind", "")
        if kind in ("method", "attribute") and qname.endswith(f"::{bare}"):
            return qname

    # Strategy 3: class/interface/enum name match in draft
    for qname, info in draft_lookup.items():
        kind = info.get("kind", "")
        if kind in ("class", "interface", "enum"):
            # Match the class name (last segment after ::)
            class_name = qname.rsplit("::", 1)[-1]
            if class_name == bare or class_name.lower() == bare.lower():
                return qname

    # Strategy 4: substring match in draft and dep lookups
    cleaned_lower = cleaned.lower()
    for qname in draft_lookup:
        if cleaned_lower in qname.lower():
            return qname
    for qname in dep_lookup.values():
        if cleaned_lower in qname.lower():
            return qname

    return None
```

- [ ] **Step 4: Refactor `_dispatch_commit` to use `_qname_resolves`**

In `combined_tools.py`, inside `_dispatch_commit`, replace the inline qname existence check block (the `for qn in all_qnames` loop starting around line 340) with calls to `_qname_resolves`. Replace:

```python
        for qn in all_qnames:
            if qn in commit_lookup:
                continue
            # Check prior designs
            if qn in prior_class_lookup.values():
                continue
            if qn in prior_class_lookup:
                continue
            if qn in dep_lookup:
                continue
            if qn in dep_lookup.values():
                continue
            if intercomponent_classes:
                ic_qnames = {c["qualified_name"] for c in intercomponent_classes}
                if qn in ic_qnames:
                    continue
            # Check Neo4j
            if neo4j_session is not None:
                from backend.db.neo4j.repositories.design import DesignRepository
                repo = DesignRepository(neo4j_session)
                nodes = repo.find_nodes(search=qn, exclude_source_types=["verification"])
                if any(n.qualified_name == qn for n in nodes):
                    continue
            errors.append(f"Unresolved reference: '{qn}' does not exist in the design context or prior designs.")
```

With:

```python
        for qn in all_qnames:
            if _qname_resolves(qn, commit_lookup, prior_class_lookup, dep_lookup, intercomponent_classes, neo4j_session):
                continue
            suggestion = _suggest_qname(qn, commit_lookup, prior_class_lookup, dep_lookup, intercomponent_classes or [])
            error_msg = f"Unresolved reference: '{qn}' does not exist in the design context."
            if suggestion:
                error_msg += f" Did you mean '{suggestion}'?"
            errors.append(error_msg)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/danielnewman/dev/ticketing_system && python -m pytest tests/test_combined_tools.py -v`
Expected: All existing tests + new helper tests PASS.

- [ ] **Step 6: Run full test suite**

Run: `cd /Users/danielnewman/dev/ticketing_system && python -m pytest tests/ -v --tb=short`
Expected: All tests pass. The `_dispatch_commit` refactored code should behave identically.

- [ ] **Step 7: Commit**

```bash
git add backend/ticketing_agent/design_verify/combined_tools.py tests/test_combined_tools.py
git commit -m "feat: add _qname_resolves and _suggest_qname helpers, refactor _dispatch_commit"
```

---

## Task 3: Implement `_dispatch_draft_verifications` and `DRAFT_VERIFICATIONS_TOOL`

Add the new tool definition, dispatcher function, and wire it into the dispatcher.

**Files:**
- Modify: `backend/ticketing_agent/design_verify/combined_tools.py`
- Test: `tests/test_combined_tools.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_combined_tools.py`:

```python
class TestDraftVerifications:
    def test_draft_verifications_accepts_valid_references(self):
        """draft_verifications accepts verifications with references that exist in the draft."""
        dispatcher = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            neo4j_session=None,
        )
        # First draft a design so references can resolve
        dispatcher("draft_design", {"design": _minimal_design_dict()})

        result = json.loads(dispatcher("draft_verifications", {
            "verifications": {
                "1": [{
                    "method": "automated",
                    "test_name": "test_add",
                    "description": "Test addition",
                    "preconditions": [],
                    "actions": [{
                        "description": "Call add",
                        "callee_qualified_name": "calculation_engine::Calculator::add",
                    }],
                    "postconditions": [{
                        "subject_qualified_name": "calculation_engine::Calculator::lastResult",
                        "operator": "==",
                        "expected_value": "5.0",
                    }],
                }]
            }
        }))
        assert result["valid"] is True
        assert result["errors"] == []
        assert "1" in result["verification_summary"]

    def test_draft_verifications_rejects_bad_qnames(self):
        """draft_verifications reports unresolved qname references."""
        dispatcher = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            neo4j_session=None,
        )
        dispatcher("draft_design", {"design": _minimal_design_dict()})

        result = json.loads(dispatcher("draft_verifications", {
            "verifications": {
                "1": [{
                    "method": "automated",
                    "test_name": "test_bad_ref",
                    "description": "Test with bad reference",
                    "preconditions": [{
                        "subject_qualified_name": "nonexistent::GhostClass",
                        "operator": "not_null",
                        "expected_value": "exists",
                    }],
                    "actions": [],
                    "postconditions": [],
                }]
            }
        }))
        assert result["valid"] is False
        assert any("GhostClass" in e for e in result["errors"])
        assert len(result["unresolved_details"]) > 0

    def test_draft_verifications_suggests_correction(self):
        """draft_verifications suggests corrections for near-miss qnames."""
        dispatcher = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            neo4j_session=None,
        )
        dispatcher("draft_design", {"design": _minimal_design_dict()})

        result = json.loads(dispatcher("draft_verifications", {
            "verifications": {
                "1": [{
                    "method": "automated",
                    "test_name": "test_suggestion",
                    "description": "Test with near-miss reference",
                    "preconditions": [{
                        "subject_qualified_name": "Calculator",
                        "operator": "not_null",
                        "expected_value": "exists",
                    }],
                    "actions": [],
                    "postconditions": [],
                }]
            }
        }))
        assert len(result["unresolved_details"]) > 0
        detail = result["unresolved_details"][0]
        assert detail["value"] == "Calculator"
        assert "suggestion" in detail
        assert "calculation_engine::Calculator" in detail["suggestion"]

    def test_draft_verifications_warns_about_unqualified_caller(self):
        """draft_verifications warns when caller_qualified_name is not a qname."""
        dispatcher = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            neo4j_session=None,
        )
        dispatcher("draft_design", {"design": _minimal_design_dict()})

        result = json.loads(dispatcher("draft_verifications", {
            "verifications": {
                "1": [{
                    "method": "automated",
                    "test_name": "test_caller",
                    "description": "Test with unqualified caller",
                    "preconditions": [],
                    "actions": [{
                        "description": "Call add",
                        "callee_qualified_name": "calculation_engine::Calculator::add",
                        "caller_qualified_name": "TestSuite",
                    }],
                    "postconditions": [],
                }]
            }
        }))
        assert any("TestSuite" in w for w in result["warnings"])

    def test_draft_verifications_warns_about_enum_in_expected_value(self):
        """draft_verifications warns when expected_value contains :: (possible design reference)."""
        dispatcher = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            neo4j_session=None,
        )
        dispatcher("draft_design", {"design": _minimal_design_dict()})

        result = json.loads(dispatcher("draft_verifications", {
            "verifications": {
                "1": [{
                    "method": "automated",
                    "test_name": "test_enum_ref",
                    "description": "Test with enum in expected_value",
                    "preconditions": [],
                    "actions": [{
                        "description": "Call add",
                        "callee_qualified_name": "calculation_engine::Calculator::add",
                    }],
                    "postconditions": [{
                        "subject_qualified_name": "calculation_engine::Calculator::lastResult",
                        "operator": "==",
                        "expected_value": "calculation_engine::CalculationError::invalid_input",
                    }],
                }]
            }
        }))
        assert any("::" in w and "expected_value" in w for w in result["warnings"])

    def test_draft_verifications_with_no_design_draft_warns(self):
        """draft_verifications warns when no design draft exists."""
        dispatcher = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            neo4j_session=None,
        )
        # No draft_design call — so no design draft exists

        result = json.loads(dispatcher("draft_verifications", {
            "verifications": {
                "1": [{
                    "method": "automated",
                    "test_name": "test_no_draft",
                    "description": "Test without draft",
                    "preconditions": [],
                    "actions": [{
                        "description": "Call add",
                        "callee_qualified_name": "calculation_engine::Calculator::add",
                    }],
                    "postconditions": [],
                }]
            }
        }))
        assert any("no design draft" in w.lower() for w in result["warnings"])

    def test_draft_verifications_strips_stub_suffix(self):
        """draft_verifications suggests corrections for stub-style references like 'CalculationEngine.add.output'."""
        dispatcher = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            neo4j_session=None,
        )
        dispatcher("draft_design", {"design": _minimal_design_dict()})

        result = json.loads(dispatcher("draft_verifications", {
            "verifications": {
                "1": [{
                    "method": "automated",
                    "test_name": "test_stub_ref",
                    "description": "Test with stub-style reference",
                    "preconditions": [],
                    "actions": [],
                    "postconditions": [{
                        "subject_qualified_name": "Calculator.add.output",
                        "operator": "==",
                        "expected_value": "5.0",
                    }],
                }]
            }
        }))
        # Should report unresolved with a suggestion
        assert result["valid"] is False
        details = result["unresolved_details"]
        assert len(details) > 0
        assert any("suggestion" in d for d in details)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/danielnewman/dev/ticketing_system && python -m pytest tests/test_combined_tools.py -v -k "TestDraftVerifications"`
Expected: FAIL — `draft_verifications` tool not found, dispatcher returns error.

- [ ] **Step 3: Add `DRAFT_VERIFICATIONS_TOOL` definition**

Add to `backend/ticketing_agent/design_verify/combined_tools.py`, after the `LOOKUP_DESIGN_ELEMENT_TOOL` and before `COMMIT_TOOL`:

```python
DRAFT_VERIFICATIONS_TOOL = {
    "name": "draft_verifications",
    "description": (
        "Submit or revise verification procedures for LLRs. Validates all "
        "qualified name references against the current design draft and "
        "design context (prior classes, dependency APIs, intercomponent). "
        "Returns a validation report showing which references resolved and "
        "which didn't, with suggestions for corrections. Use this after "
        "drafting your design to iteratively resolve verification stub "
        "references before committing."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "verifications": {
                "type": "object",
                "description": (
                    "Map of LLR ID (integer string) to list of verification "
                    "procedures. Keys MUST be LLR IDs like \"1\", \"2\" — "
                    "NOT test names."
                ),
                "additionalProperties": {
                    "type": "array",
                    "items": VerificationSchema.model_json_schema(),
                },
            },
        },
        "required": ["verifications"],
    },
}
```

- [ ] **Step 4: Add `_draft_verifications` state variable and `_dispatch_draft_verifications` function**

Add `_draft_verifications` to the closure variables in `make_combined_dispatcher`:

```python
_draft_verifications: dict[int, list[VerificationSchema]] = {}
```

Add the dispatch function after `_dispatch_lookup_design_element`:

```python
    def _dispatch_draft_verifications(tool_input: dict) -> str:
        nonlocal _draft_verifications
        verifs_input = tool_input.get("verifications", {})
        if not verifs_input:
            return json.dumps({"valid": False, "errors": ["No verifications provided"]})

        parsed: dict[int, list[VerificationSchema]] = {}
        parse_errors = []
        for llr_id_str, v_list in verifs_input.items():
            try:
                llr_id = int(llr_id_str)
            except (ValueError, TypeError):
                parse_errors.append(f"Non-integer LLR ID key: '{llr_id_str}'")
                continue
            parsed[llr_id] = []
            for v in v_list:
                try:
                    parsed[llr_id].append(VerificationSchema.model_validate(v))
                except Exception as e:
                    parse_errors.append(f"LLR {llr_id_str}: invalid verification: {e}")

        if parse_errors:
            return json.dumps({"valid": False, "errors": parse_errors})

        # Validate all qname references
        warnings = []
        unresolved_details = []
        verification_summary = {}

        # Warn if no design draft exists
        if not _draft_design:
            warnings.append(
                "No design draft exists. Verification references cannot be "
                "validated against design elements. Call draft_design first."
            )

        for llr_id, verifs in parsed.items():
            llr_key = str(llr_id)
            resolved = 0
            total = 0
            for v in verifs:
                test_label = v.test_name or v.method
                for cond in v.preconditions + v.postconditions:
                    if cond.subject_qualified_name:
                        total += 1
                        if _qname_resolves(cond.subject_qualified_name, _draft_lookup, prior_class_lookup, dep_lookup, intercomponent_classes or [], neo4j_session):
                            resolved += 1
                        else:
                            suggestion = _suggest_qname(cond.subject_qualified_name, _draft_lookup, prior_class_lookup, dep_lookup, intercomponent_classes or [])
                            detail = {
                                "llr_id": llr_key,
                                "verification": test_label,
                                "field": "subject_qualified_name",
                                "value": cond.subject_qualified_name,
                            }
                            if suggestion:
                                detail["suggestion"] = suggestion
                            unresolved_details.append(detail)
                    if cond.object_qualified_name:
                        total += 1
                        if _qname_resolves(cond.object_qualified_name, _draft_lookup, prior_class_lookup, dep_lookup, intercomponent_classes or [], neo4j_session):
                            resolved += 1
                        else:
                            suggestion = _suggest_qname(cond.object_qualified_name, _draft_lookup, prior_class_lookup, dep_lookup, intercomponent_classes or [])
                            detail = {
                                "llr_id": llr_key,
                                "verification": test_label,
                                "field": "object_qualified_name",
                                "value": cond.object_qualified_name,
                            }
                            if suggestion:
                                detail["suggestion"] = suggestion
                            unresolved_details.append(detail)
                    # Warn about missing operator
                    if not cond.operator or cond.operator == "":
                        warnings.append(
                            f"LLR {llr_key} '{test_label}': condition on "
                            f"'{cond.subject_qualified_name}' has no operator — "
                            f"will default to '=='"
                        )
                    # Warn about expected_value that looks like a qname
                    if cond.expected_value and "::" in cond.expected_value:
                        warnings.append(
                            f"LLR {llr_key} '{test_label}': expected_value "
                            f"'{cond.expected_value}' contains '::' — if this "
                            f"references a design member, move it to "
                            f"object_qualified_name and use the display text "
                            f"as expected_value instead"
                        )
                for action in v.actions:
                    if action.callee_qualified_name:
                        total += 1
                        if _qname_resolves(action.callee_qualified_name, _draft_lookup, prior_class_lookup, dep_lookup, intercomponent_classes or [], neo4j_session):
                            resolved += 1
                        else:
                            suggestion = _suggest_qname(action.callee_qualified_name, _draft_lookup, prior_class_lookup, dep_lookup, intercomponent_classes or [])
                            detail = {
                                "llr_id": llr_key,
                                "verification": test_label,
                                "field": "callee_qualified_name",
                                "value": action.callee_qualified_name,
                            }
                            if suggestion:
                                detail["suggestion"] = suggestion
                            unresolved_details.append(detail)
                    # Warn about unqualified caller references
                    if action.caller_qualified_name and "::" not in action.caller_qualified_name:
                        warnings.append(
                            f"LLR {llr_key} '{test_label}': caller "
                            f"'{action.caller_qualified_name}' is not a "
                            f"qualified name — leave empty if the caller is "
                            f"the test harness"
                        )

            verification_summary[llr_key] = {
                "methods": len(verifs),
                "resolved_references": resolved,
                "unresolved_references": total - resolved,
            }

        # Store drafted verifications
        _draft_verifications = parsed

        errors = [
            f"Unresolved reference: '{d['value']}'"
            + (f" Did you mean '{d['suggestion']}'?" if "suggestion" in d else "")
            for d in unresolved_details
        ]

        return json.dumps({
            "valid": len(unresolved_details) == 0 and len(parse_errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "verification_summary": verification_summary,
            "unresolved_details": unresolved_details,
        })
```

- [ ] **Step 5: Add `draft_verifications` dispatch route to the dispatcher**

In the `dispatch` function inside `make_combined_dispatcher`, add after the `lookup_design_element` case:

```python
        elif tool_name == "draft_verifications":
            return _dispatch_draft_verifications(tool_input)
```

- [ ] **Step 6: Add `DRAFT_VERIFICATIONS_TOOL` to `ALL_TOOLS`**

In the `ALL_TOOLS` list, add `DRAFT_VERIFICATIONS_TOOL` between `LOOKUP_DESIGN_ELEMENT_TOOL` and `COMMIT_TOOL`:

```python
ALL_TOOLS = [
    LIST_SOURCES_TOOL,
    SEARCH_SYMBOLS_TOOL,
    GET_COMPOUND_TOOL,
    BROWSE_NAMESPACE_TOOL,
    FIND_INHERITANCE_TOOL,
    DRAFT_DESIGN_TOOL,
    VALIDATE_DESIGN_TOOL,
    CHECK_CLASS_NAME_TOOL,
    FIND_MECHANISM_TOOL,
    VALIDATE_QNAMES_TOOL,
    LOOKUP_DESIGN_ELEMENT_TOOL,
    DRAFT_VERIFICATIONS_TOOL,
    COMMIT_TOOL,
]
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd /Users/danielnewman/dev/ticketing_system && python -m pytest tests/test_combined_tools.py -v`
Expected: All tests pass, including `TestDraftVerifications`.

- [ ] **Step 8: Run full test suite**

Run: `cd /Users/danielnewman/dev/ticketing_system && python -m pytest tests/ -v --tb=short`
Expected: All tests pass.

- [ ] **Step 9: Commit**

```bash
git add backend/ticketing_agent/design_verify/combined_tools.py tests/test_combined_tools.py
git commit -m "feat: add draft_verifications tool with suggestion logic and validation"
```

---

## Task 4: Add verification quality checks to `design_and_verify()` post-loop

Add warning generation for common verification quality issues after the loop completes.

**Files:**
- Modify: `backend/ticketing_agent/design_verify/combined_loop.py`
- Test: `tests/test_integration_combined_loop.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_integration_combined_loop.py`:

```python
def test_design_verify_warns_about_unqualified_caller():
    """design_and_verify adds warnings for caller_qualified_name without :: separators."""
    from backend.ticketing_agent.design_verify.combined_loop import DesignVerifyResult

    # Simulate verification with unqualified caller
    verifications = {
        1: [VerificationSchema(
            method="automated",
            test_name="test_call",
            description="Test",
            preconditions=[],
            actions=[VerificationActionSchema(
                description="Call method",
                callee_qualified_name="calculation_engine::Calculator::add",
                caller_qualified_name="TestSuite",
            )],
            postconditions=[],
        )]
    }
    result = DesignVerifyResult(
        oo_design=OODesignSchema(
            modules=["calculation_engine"],
            classes=[],
            interfaces=[],
            enums=[],
            associations=[],
        ),
        verifications=verifications,
    )
    # We can't test the full pipeline, but we can test the warning logic directly
    # by importing the helper function we'll add
    from backend.ticketing_agent.design_verify.combined_loop import _collect_verification_warnings
    warnings = _collect_verification_warnings(verifications)
    assert any("TestSuite" in w and "not a qualified name" in w for w in warnings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/danielnewman/dev/ticketing_system && python -m pytest tests/test_integration_combined_loop.py -v -k "test_design_verify_warns"`
Expected: FAIL — `_collect_verification_warnings` not yet defined.

- [ ] **Step 3: Add `_collect_verification_warnings` helper function**

Add to `backend/ticketing_agent/design_verify/combined_loop.py`:

```python
def _collect_verification_warnings(
    verifications: dict[int, list[VerificationSchema]],
) -> list[str]:
    """Collect quality warnings from verification data.

    Checks for common issues:
    - Conditions with no operator (will default to ==)
    - Empty preconditions (may indicate missing setup)
    - Unqualified caller_qualified_name values
    """
    warnings = []
    for llr_id, verifs in verifications.items():
        for v in verifs:
            test_label = v.test_name or v.method
            # Check for empty preconditions
            if not v.preconditions:
                warnings.append(
                    f"LLR {llr_id} '{test_label}': no preconditions specified"
                )
            # Check for conditions without operators
            for cond in v.preconditions + v.postconditions:
                if not cond.operator:
                    warnings.append(
                        f"LLR {llr_id} '{test_label}': condition on "
                        f"'{cond.subject_qualified_name}' has no operator — "
                        f"defaulting to '=='"
                    )
            # Check for unqualified caller references
            for action in v.actions:
                if action.caller_qualified_name and "::" not in action.caller_qualified_name:
                    warnings.append(
                        f"LLR {llr_id} '{test_label}': action caller "
                        f"'{action.caller_qualified_name}' is not a valid "
                        f"qualified name — leave empty if the caller is "
                        f"the test harness"
                    )
    return warnings
```

- [ ] **Step 4: Wire warnings into `DesignVerifyResult` in `design_and_verify()`**

In the `design_and_verify()` function, after parsing verifications, add:

```python
    # Collect verification quality warnings
    verification_warnings = _collect_verification_warnings(verifications)
```

And update the return:

```python
    return DesignVerifyResult(
        oo_design=oo_design,
        verifications=verifications,
        design_warnings=design_warnings,
        verification_warnings=verification_warnings,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/danielnewman/dev/ticketing_system && python -m pytest tests/test_integration_combined_loop.py tests/test_combined_tools.py -v`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/ticketing_agent/design_verify/combined_loop.py tests/test_integration_combined_loop.py
git commit -m "feat: add verification quality warning checks to design_and_verify"
```

---

## Task 5: Update the system prompt with verification stub resolution instructions

Add the new prompt section and update the workflow diagram and guidelines.

**Files:**
- Modify: `backend/ticketing_agent/design_verify/combined_prompt.py`

- [ ] **Step 1: Update the workflow diagram**

In the `SYSTEM_PROMPT` string in `combined_prompt.py`, replace the current digraph:

```
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

With:

```
digraph design_verify_workflow {
    rankdir=TB;
    discovery [label="Discovery\nlist_sources → search_symbols\n→ get_compound → find_inheritance"];
    design [label="Design\ndraft_design → validate_design\n→ check_class_name"];
    verification [label="Verification\ndraft_verifications\n→ validate_qualified_names"];
    commit [label="Commit\ncommit_design_and_verifications"];
    discovery -> design;
    design -> verification;
    verification -> commit;
    verification -> design [label="missing member\nfound"];
    commit -> verification [label="commit fails\n(qname errors)"];
    commit -> verification [label="unresolved\nreferences"];
}
```

- [ ] **Step 2: Add "Resolving Verification Stubs" section**

After the existing "For verification procedures:" section and before the `<FORMAT-CONTRACT name="verification-key-format">` section, add:

```
### Resolving Verification Stubs

The requirements include seeded verification stubs — preconditions, actions,
and postconditions that describe test scenarios in plain terms but use
placeholder references. Your job is to translate each stub into a fully
resolved verification method that references actual design members.

For each verification stub:
1. Identify what design element each reference targets
   - "result" → the return type or result attribute of the called method
   - "error_signal" → the error/signal attribute or enum value
   - "is_valid" → the boolean return or attribute indicating validity
2. Replace placeholder references with qualified names from your draft
   - "CalculationEngine.add" → "calculation_engine::CalculationEngine::add"
   - "CalculationResult.result_value" → "calculation_engine::CalculationResult::result_value"
3. Use draft_verifications to validate that every reference resolves
4. If a reference can't resolve, either:
   a. Add the missing member to your design via draft_design, OR
   b. Use expected_value alone for literal values (don't fabricate qnames)

Common patterns for resolving stubs:
| Stub pattern | Resolution |
|---|---|
| `ClassName.method.output` | Use the method's return type: `ns::ReturnType::attribute` |
| `result == X` | `ns::ResultClass::result_value == X` |
| `error_signal == Y` | `ns::ResultClass::error_signal == Y` where error_signal is an enum attribute |
| `caller_qualified_name: TestSuite` | Leave empty (omit) — the test framework is not a design element |
```

- [ ] **Step 3: Update verification guidelines**

Replace the current guidelines block:

```
Guidelines:
- Reference ONLY real qualified names from the design context or your draft
- If a verification needs a member that doesn't exist, add it to the design
  via draft_design before referencing it
- Keep conditions specific and testable
- Process LLRs one at a time during verification
```

With:

```
Guidelines:
- Reference ONLY real qualified names from the design context or your draft
- If a verification needs a member that doesn't exist, add it to the design
  via draft_design before referencing it
- After writing verification procedures, ALWAYS call draft_verifications
  to validate that all references resolve before committing
- If draft_verifications reports unresolved references, either add the
  missing design member or correct the reference and re-draft
- Process LLRs one at a time during verification
- Leave caller_qualified_name empty if the caller is the test harness
  (not a design element). Do NOT use "TestSuite" or other test class
  names as caller qnames.

Every condition MUST include an operator. The default is "==" if not
specified, but be explicit:
- Use "==" for equality checks (result_value == 5.0)
- Use "is_true" / "is_false" for boolean checks (success is_true)
- Use "not_null" for existence checks (engine not_null)
- Use "contains" for collection membership
```

- [ ] **Step 4: Commit**

```bash
git add backend/ticketing_agent/design_verify/combined_prompt.py
git commit -m "feat: update system prompt with draft_verifications workflow and stub resolution"
```

---

## Task 6: Add debug logging for unmatched CALLER/CALLEE edges in verification repo

Add `log.debug` messages when `:CALLER` or `:CALLEE` edges can't be created because the referenced `:Design` node doesn't exist.

**Files:**
- Modify: `backend/db/neo4j/repositories/verification.py`

- [ ] **Step 1: Update `add_action` method to log unmatched edges**

In `backend/db/neo4j/repositories/verification.py`, in the `add_action` method, after each `MERGE` query for `:CALLER` and `:CALLEE` edges, add a check:

```python
        # Create :CALLER edge if referenced :Design node exists
        if caller_qualified_name:
            result = self._session.run(
                """
                MATCH (a:Action {id: $aid})
                MATCH (d:Design {qualified_name: $qn})
                MERGE (a)-[:CALLER]->(d)
                """,
                {"aid": next_id, "qn": caller_qualified_name},
            )
            summary = result.consume().counters
            if summary.relationships_created == 0:
                log.debug(
                    "No :CALLER edge created for action %d: "
                    ":Design node '%s' not found",
                    next_id, caller_qualified_name,
                )

        # Create :CALLEE edge if referenced :Design node exists
        if callee_qualified_name:
            result = self._session.run(
                """
                MATCH (a:Action {id: $aid})
                MATCH (d:Design {qualified_name: $qn})
                MERGE (a)-[:CALLEE]->(d)
                """,
                {"aid": next_id, "qn": callee_qualified_name},
            )
            summary = result.consume().counters
            if summary.relationships_created == 0:
                log.debug(
                    "No :CALLEE edge created for action %d: "
                    ":Design node '%s' not found",
                    next_id, callee_qualified_name,
                )
```

- [ ] **Step 2: Similarly update `add_condition` method for `:LEFT_OPERAND`/`:RIGHT_OPERAND` edges**

In the same file, in the `add_condition` method, after the `:LEFT_OPERAND` and `:RIGHT_OPERAND` merge queries:

```python
        # Create :LEFT_OPERAND edge if subject :Design node exists
        if subject_qualified_name:
            result = self._session.run(
                """
                MATCH (c:Condition {id: $cid})
                MATCH (d:Design {qualified_name: $qn})
                MERGE (c)-[:LEFT_OPERAND]->(d)
                """,
                {"cid": next_id, "qn": subject_qualified_name},
            )
            summary = result.consume().counters
            if summary.relationships_created == 0:
                log.debug(
                    "No :LEFT_OPERAND edge created for condition %d: "
                    ":Design node '%s' not found",
                    next_id, subject_qualified_name,
                )

        # Create :RIGHT_OPERAND edge if object :Design node exists
        if object_qualified_name:
            result = self._session.run(
                """
                MATCH (c:Condition {id: $cid})
                MATCH (d:Design {qualified_name: $qn})
                MERGE (c)-[:RIGHT_OPERAND]->(d)
                """,
                {"cid": next_id, "qn": object_qualified_name},
            )
            summary = result.consume().counters
            if summary.relationships_created == 0:
                log.debug(
                    "No :RIGHT_OPERAND edge created for condition %d: "
                    ":Design node '%s' not found",
                    next_id, object_qualified_name,
                )
```

- [ ] **Step 3: Run existing verification repo tests**

Run: `cd /Users/danielnewman/dev/ticketing_system && python -m pytest tests/test_verification_repository.py -v --tb=short`
Expected: All existing tests pass (this only adds logging, no behavior change).

- [ ] **Step 4: Commit**

```bash
git add backend/db/neo4j/repositories/verification.py
git commit -m "feat: add debug logging for unmatched CALLER/CALLEE/OPERAND edges"
```

---

## Task 7: Final integration test

Add an integration test that exercises the full `draft_verifications` workflow: draft design, draft verifications, validate references, fix unresolved ones, then commit.

**Files:**
- Modify: `tests/test_integration_combined_loop.py`

- [ ] **Step 1: Write the integration test**

Add to `tests/test_integration_combined_loop.py`:

```python
def test_draft_verifications_then_commit_workflow():
    """Full workflow: draft design → draft_verifications → commit."""
    dispatcher = make_combined_dispatcher(
        prior_class_lookup={},
        dependency_lookup=None,
        intercomponent_classes=None,
        neo4j_session=None,
    )

    # Step 1: Draft the design
    draft_result = json.loads(dispatcher("draft_design", {"design": _minimal_design_dict()}))
    assert draft_result["valid"] is True

    # Step 2: Draft verifications with unresolved references
    bad_verifs = {
        "1": [{
            "method": "automated",
            "test_name": "test_add_bad_ref",
            "description": "Test with placeholder reference",
            "preconditions": [],
            "actions": [{
                "description": "Call add",
                "callee_qualified_name": "Calculator.add",
            }],
            "postconditions": [{
                "subject_qualified_name": "Calculator.add.output",
                "operator": "==",
                "expected_value": "5.0",
            }],
        }]
    }
    draft_verif_result = json.loads(dispatcher("draft_verifications", {"verifications": bad_verifs}))
    assert draft_verif_result["valid"] is False
    assert len(draft_verif_result["unresolved_details"]) >= 2  # callee + subject
    # Should have suggestions
    suggestions = [d for d in draft_verif_result["unresolved_details"] if "suggestion" in d]
    assert len(suggestions) >= 1

    # Step 3: Re-draft with resolved references
    good_verifs = {
        "1": [{
            "method": "automated",
            "test_name": "test_add",
            "description": "Test addition",
            "preconditions": [],
            "actions": [{
                "description": "Call add",
                "callee_qualified_name": "calculation_engine::Calculator::add",
            }],
            "postconditions": [{
                "subject_qualified_name": "calculation_engine::Calculator::lastResult",
                "operator": "==",
                "expected_value": "5.0",
            }],
        }]
    }
    draft_verif_result2 = json.loads(dispatcher("draft_verifications", {"verifications": good_verifs}))
    assert draft_verif_result2["valid"] is True
    assert draft_verif_result2["errors"] == []

    # Step 4: Commit with the resolved verifications
    commit_result = json.loads(dispatcher(
        "commit_design_and_verifications",
        {
            "oo_design": _minimal_design_dict(),
            "verifications": good_verifs,
        },
    ))
    assert commit_result["committed"] is True
```

- [ ] **Step 2: Run the full test suite**

Run: `cd /Users/danielnewman/dev/ticketing_system && python -m pytest tests/ -v --tb=short`
Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration_combined_loop.py
git commit -m "test: add integration test for draft_verifications workflow"
```

---

## Self-Review

**Spec coverage:**
- Section 1 (draft_verifications tool): Task 3 ✅
- Section 2 (commit integration + post-loop checks): Tasks 2, 4 ✅
- Section 3 (prompt changes): Task 5 ✅
- Section 4 (dispatcher implementation + helpers): Tasks 2, 3 ✅
- Section 5 (minor fixes): Tasks 1, 6 ✅
- `operator` default: Task 1 ✅
- `caller_qualified_name` warning: Task 3 ✅
- Debug logging: Task 6 ✅
- Integration test: Task 7 ✅

**Placeholder scan:** No TBDs, TODOs, or "implement later" in any step. All code is complete. ✅

**Type consistency:** `_qname_resolves` signature in Task 2 matches usage in Tasks 3 and 4. `_suggest_qname` signature matches test expectations. `DRAFT_VERIFICATIONS_TOOL` schema uses `VerificationSchema.model_json_schema()` matching the existing pattern. ✅