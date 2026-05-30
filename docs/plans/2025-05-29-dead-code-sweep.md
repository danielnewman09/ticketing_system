# Dead Code Sweep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surgically remove confirmed dead code from the backend: deprecated functions, unused modules, dead helper functions, and commented-out imports.

**Architecture:** Six independent tasks, each removing a specific dead code unit. Migrations use the existing `design_data` module (`ClassDiagram.to_draft_lookup()`, `class_diagram_from_oo_design()`) as drop-in replacements. Each task is independently testable and committable.

**Tech Stack:** Python 3.12+, pytest, existing project test suite

---

### Task 1: Remove deprecated `build_verification_context()`

This function was replaced by `build_verification_context_from_diagram()` and has zero callers (only referenced in deprecation comments).

**Files:**
- Modify: `backend/requirements/services/persistence.py` (delete lines ~70–138)
- Test: `pytest tests/test_persistence.py` (existing)

- [ ] **Step 1: Delete the `build_verification_context` function**

In `backend/requirements/services/persistence.py`, delete the entire function body from line 70 through line 138 (the `def build_verification_context(...)` block including its docstring). Keep `build_verification_context_from_diagram` untouched.

- [ ] **Step 2: Update the deprecation comment in `build_verification_context_from_diagram`**

In the same file, find the docstring of `build_verification_context_from_diagram`. It currently references the old function in two places:

```python
This is the preferred replacement for build_verification_context().
...
build_verification_context()).
```

Replace the entire docstring with:

```python
"""Build verification context using the design_data module.

Uses DesignDataRepository to query Neo4j and return typed ClassDiagram
objects, then extracts verification dicts.

Args:
    neo4j_session: A Neo4j session.
    component_id: Optional component filter.

Returns:
    List of dicts with verification context.
"""
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_persistence.py -v
```

Expected: All tests pass. The removed function had no callers.

- [ ] **Step 4: Commit**

```bash
git add backend/requirements/services/persistence.py
git commit -m "chore: remove deprecated build_verification_context"
```

---

### Task 2: Remove unused `_build_class_lookup()`

This function has zero callers — it was replaced by the `design_data` module in recent commits.

**Files:**
- Modify: `backend/ticketing_agent/design/design_per_hlr.py` (delete lines ~94–110)

- [ ] **Step 1: Delete `_build_class_lookup`**

In `backend/ticketing_agent/design/design_per_hlr.py`, delete the entire function from line 94 through line 110:

```python
def _build_class_lookup(oo: OODesignSchema) -> dict[str, str]:
    """Build a name -> qualified_name mapping from an OO design.

    Used to seed map_oo_to_ontology's class_lookup so cross-HLR
    references (inheritance, associations, etc.) resolve correctly.
    """
    lookup: dict[str, str] = {}
    for cls in oo.classes:
        qname = f"{cls.module}::{cls.name}" if cls.module else cls.name
        lookup[cls.name] = qname
    for iface in oo.interfaces:
        qname = f"{iface.module}::{iface.name}" if iface.module else iface.name
        lookup[iface.name] = qname
    for enum in oo.enums:
        qname = f"{enum.module}::{enum.name}" if enum.module else enum.name
        lookup[enum.name] = qname
    return lookup
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/ -k "design" -v
```

Expected: All tests pass. The removed function had zero callers.

- [ ] **Step 3: Commit**

```bash
git add backend/ticketing_agent/design/design_per_hlr.py
git commit -m "chore: remove unused _build_class_lookup"
```

---

### Task 3: Remove `build_draft_lookup()` and `draft_summary()`, migrate callers to `ClassDiagram` methods

`draft_state.py` has three functions: `build_draft_lookup`, `draft_summary`, and `check_enum_collisions`. The first two can be replaced by `class_diagram_from_oo_design(design).to_draft_lookup()` and a new `to_summary()` method on `ClassDiagram`. `check_enum_collisions` moves to `design_validation.py`.

**Files:**
- Modify: `backend/ticketing_agent/tools/design_verify/draft_design.py` (migrate imports)
- Modify: `backend/ticketing_agent/tools/design_verify/commit.py` (migrate import)
- Modify: `backend/ticketing_agent/tools/design_verify/dispatcher.py` (migrate import)
- Modify: `backend/ticketing_agent/tools/design_verify/validate_design.py` (migrate `check_enum_collisions` import)
- Modify: `backend/ticketing_agent/tools/helpers/design_validation.py` (add `check_enum_collisions`)
- Modify: `backend/design_data/models.py` (add `to_summary()` method)
- Delete: `backend/ticketing_agent/tools/helpers/draft_state.py`

- [ ] **Step 1: Add `to_summary()` method to `ClassDiagram`**

In `backend/design_data/models.py`, add this method to the `ClassDiagram` class (after `to_draft_lookup`):

```python
    def to_summary(self) -> dict:
        """Return a summary dict of this diagram for tool responses.

        Returns counts of all top-level entities, attributes, and methods.
        """
        total_attrs = sum(len(c.attributes) for c in self.classes)
        total_methods = sum(len(c.methods) for c in self.classes)
        return {
            "classes": len(self.classes),
            "interfaces": len(self.interfaces),
            "enums": len(self.enums),
            "associations": len(self.associations),
            "attributes": total_attrs,
            "methods": total_methods,
        }
```

- [ ] **Step 2: Write a test for `to_summary()`**

In a new test section of `tests/test_design_data_models.py`, add:

```python
    def test_to_summary(self, diagram):
        summary = diagram.to_summary()
        assert summary["classes"] == 2
        assert summary["interfaces"] == 1
        assert summary["enums"] == 1
        assert summary["associations"] == 1
        assert summary["attributes"] == 2  # speed + lastResult
        assert summary["methods"] == 4  # Calculator: add,subtract; Display: show + Interface: execute
```

- [ ] **Step 3: Run the test to verify it passes**

```bash
pytest tests/test_design_data_models.py::TestClassDiagram::test_to_summary -v
```

Expected: PASS

- [ ] **Step 4: Move `check_enum_collisions` to `design_validation.py`**

In `backend/ticketing_agent/tools/helpers/design_validation.py`, add this function at the end of the file:

```python
def check_enum_collisions(design: "OODesignSchema", prior_class_lookup: dict[str, str]) -> list[str]:
    """Warn if enum names collide with prior designs.

    Returns a list of warning strings. Empty list means no collisions.
    """
    warnings = []
    for enum in design.enums:
        enum_qname = f"{enum.module}::{enum.name}" if enum.module else enum.name
        if enum.name in prior_class_lookup:
            existing_qname = prior_class_lookup[enum.name]
            if existing_qname != enum_qname:
                warnings.append(
                    f"Enum '{enum.name}' already exists as '{existing_qname}' in a "
                    f"prior design. Consider referencing the existing enum or "
                    f"renaming yours to avoid confusion."
                )
    return warnings
```

Add the import at the top of the file:

```python
from backend.codebase.schemas import OODesignSchema
```

- [ ] **Step 5: Update `draft_design.py` to use `ClassDiagram` directly**

In `backend/ticketing_agent/tools/design_verify/draft_design.py`, replace:

```python
from backend.ticketing_agent.tools.helpers.draft_state import (
    build_draft_lookup,
    check_enum_collisions,
    draft_summary,
)
```

with:

```python
from backend.design_data import class_diagram_from_oo_design
from backend.ticketing_agent.tools.helpers.design_validation import check_enum_collisions
```

Then replace the body of `handle()` where `build_draft_lookup` and `draft_summary` are called:

```python
    ctx.draft_design = design
    ctx.draft_lookup = build_draft_lookup(design)

    return json.dumps({
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "draft_summary": draft_summary(design),
    })
```

Replace with:

```python
    ctx.draft_design = design
    diagram = class_diagram_from_oo_design(design)
    ctx.draft_lookup = diagram.to_draft_lookup()

    return json.dumps({
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "draft_summary": diagram.to_summary(),
    })
```

- [ ] **Step 6: Update `commit.py` to use `ClassDiagram` directly**

In `backend/ticketing_agent/tools/design_verify/commit.py`, replace:

```python
from backend.ticketing_agent.tools.helpers.draft_state import build_draft_lookup
```

with:

```python
from backend.design_data import class_diagram_from_oo_design
```

Then replace the `build_draft_lookup` call:

```python
    commit_lookup = build_draft_lookup(schema.oo_design)
```

with:

```python
    commit_lookup = class_diagram_from_oo_design(schema.oo_design).to_draft_lookup()
```

- [ ] **Step 7: Update `dispatcher.py` to remove `draft_state` import**

In `backend/ticketing_agent/tools/design_verify/dispatcher.py`, remove:

```python
from backend.ticketing_agent.tools.helpers.draft_state import build_draft_lookup
```

(This import is unused — `draft_lookup` is built in `draft_design.py` and stored on `ctx`, never constructed in `dispatcher.py`.)

- [ ] **Step 8: Update `validate_design.py` to import from `design_validation`**

In `backend/ticketing_agent/tools/design_verify/validate_design.py`, replace:

```python
from backend.ticketing_agent.tools.helpers.draft_state import check_enum_collisions
```

with:

```python
from backend.ticketing_agent.tools.helpers.design_validation import check_enum_collisions
```

- [ ] **Step 9: Delete `draft_state.py`**

```bash
rm backend/ticketing_agent/tools/helpers/draft_state.py
```

- [ ] **Step 10: Run tests**

```bash
pytest tests/test_combined_tools.py tests/test_combined_handlers.py tests/test_design_data_models.py tests/test_design_verify* -v
```

Expected: All tests pass. `draft_state.py` no longer exists. All former callers use `ClassDiagram` methods directly.

- [ ] **Step 11: Commit**

```bash
git add -A
git commit -m "refactor: replace draft_state with ClassDiagram methods, move check_enum_collisions to design_validation"
```

---

### Task 4: Remove dead formatting functions from `verification_formatting.py`

These four functions (`format_action`, `format_condition`, `format_verification_method`, `format_verification_method_prompt`) have no callers outside their own module. The working equivalents are `_format_action`, `_format_condition` etc. in `formatting.py`. Keep the module-level constants (`VERIFICATION_METHODS`, `CONDITION_OPERATORS`) since they're re-exported.

**Files:**
- Modify: `backend/requirements/verification_formatting.py` (delete four functions)

- [ ] **Step 1: Delete the four dead functions**

In `backend/requirements/verification_formatting.py`, delete:

1. `format_verification_method(vm)` — the function and its docstring
2. `format_verification_method_prompt(vm)` — the function and its docstring
3. `format_condition(c)` — the function and its docstring
4. `format_action(a)` — the function and its docstring

The file should end up containing only the imports and the two constants:

```python
"""Constants for verification data.

Provides the VERIFICATION_METHODS and CONDITION_OPERATORS constants
that were previously defined on the deleted model file.
"""

from backend.db.neo4j.repositories.models.verification import (
    ActionNode,
    ConditionNode,
    VerificationMethodNode,
)

VERIFICATION_METHODS = ["automated", "review", "inspection"]

CONDITION_OPERATORS = [
    ("==", "equals"),
    ("!=", "not equals"),
    ("<", "less than"),
    (">", "greater than"),
    ("<=", "less than or equal"),
    (">=", "greater than or equal"),
    ("is_true", "is true"),
    ("is_false", "is false"),
    ("contains", "contains"),
    ("not_null", "is not null"),
]
```

Remove the three unused imports (`ActionNode`, `ConditionNode`, `VerificationMethodNode`) since they were only used by the deleted functions. The file becomes:

```python
"""Constants for verification data.

Provides the VERIFICATION_METHODS and CONDITION_OPERATORS constants
previously defined on deleted models.
"""

VERIFICATION_METHODS = ["automated", "review", "inspection"]

CONDITION_OPERATORS = [
    ("==", "equals"),
    ("!=", "not equals"),
    ("<", "less than"),
    (">", "greater than"),
    ("<=", "less than or equal"),
    (">=", "greater than or equal"),
    ("is_true", "is true"),
    ("is_false", "is false"),
    ("contains", "contains"),
    ("not_null", "is not null"),
]
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_conftest_smoke.py tests/test_requirements_schemas.py -v
```

These tests verify `VERIFICATION_METHODS` and `CONDITION_OPERATORS` are still accessible.

- [ ] **Step 3: Commit**

```bash
git add backend/requirements/verification_formatting.py
git commit -m "chore: remove dead formatting functions from verification_formatting"
```

---

### Task 5: Remove `backend/services/neo4j_service.py` and `apply_remediation()`

The entire `neo4j_service.py` module is never imported. `apply_remediation` in `mcp_server.py` is registered but never invoked by any agent, pipeline, or script.

**Files:**
- Delete: `backend/services/neo4j_service.py`
- Delete: `backend/services/` directory (if empty after deletion)
- Modify: `backend/ticketing_agent/mcp_server.py` (delete `apply_remediation` function and its decorator)

- [ ] **Step 1: Delete `neo4j_service.py`**

```bash
rm backend/services/neo4j_service.py
rmdir backend/services/
```

- [ ] **Step 2: Delete `apply_remediation` from `mcp_server.py`**

In `backend/ticketing_agent/mcp_server.py`, delete the `@mcp.tool()` decorator and `def apply_remediation(...)` function from line 293 through line ~459 (ending just before `@mcp.tool()\ndef ensure_predicates`).

The last line before `apply_remediation` is the closing `}` of the `save_verification` function's return dict (around line 292). The next function after `apply_remediation` is `ensure_predicates` starting around line 461.

- [ ] **Step 3: Check for any unused imports exposed by the deletion**

After deleting `apply_remediation`, look at the top of `mcp_server.py` for imports that were only used by `apply_remediation`. These may include:

- `get_session`, `OntologyTriple`, `OntologyNode`, `Predicate` (used for SQLAlchemy operations)
- `RequirementRepository`, `VerificationRepository` (if not used by other functions)

Scan the remaining code and remove any imports that are now unused.

- [ ] **Step 4: Run tests**

```bash
pytest tests/ -v --timeout=30
```

Expected: All tests pass. Neither the deleted module nor the deleted function had any callers.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: remove dead neo4j_service module and unused apply_remediation MCP tool"
```

---

### Task 6: Remove commented-out imports from `design_hlr.py`

Two commented-out imports with "no longer called from pipeline" notes.

**Files:**
- Modify: `backend/ticketing_agent/design/design_hlr.py` (delete 2 lines)

- [ ] **Step 1: Delete the commented-out imports**

In `backend/ticketing_agent/design/design_hlr.py`, delete lines 14–15:

```python
# from backend.ticketing_agent.design.design_oo import design_oo  # no longer called from pipeline
# from backend.ticketing_agent.design.discover_classes import discover_classes  # no longer called from pipeline
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/ -k "design" -v --timeout=30
```

Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add backend/ticketing_agent/design/design_hlr.py
git commit -m "chore: remove commented-out imports from design_hlr"
```

---

## Revision Note

The original design spec listed `_extract_existing_classes()` and `_extract_intercomponent_context()` as deprecated functions to remove. Upon closer analysis, these functions are **actively called** (each has one caller in `design_per_hlr.py`), and their output format differs from `ClassDiagram.to_verification_dicts()`. The prompt builder (`build_existing_classes_section`) expects a specific dict shape (simple `methods: [{name, visibility}]`, `associations: [{target, kind, description}]`) that is not the same as the verification context format. Migrating these would require adding new ClassDiagram methods and modifying the prompt builder — beyond the scope of a surgical dead code sweep. They have TODO comments marking them for future migration, which remains the right approach.