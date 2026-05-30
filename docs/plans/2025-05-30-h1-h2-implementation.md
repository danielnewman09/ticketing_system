# Implementation Plan: Replace build_verification_context and all_oo_classes

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the two remaining high-priority ad-hoc data patterns — `build_verification_context()` direct calls and `all_oo_classes` manual dict construction — with the design_data module.

**Architecture:** Both replacements produce the same output shapes as before, but route through typed `ClassDiagram` models. No downstream consumer changes required.

**Tech Stack:** Python 3.12+, Pydantic v2, existing codebase

---

## Task 1: Replace `build_verification_context()` calls with `build_verification_context_from_diagram()`

**Files:**
- Modify: `backend/pipeline/orchestrator.py`
- Modify: `backend/ticketing_agent/verify/verify_llr.py`

**Context:** `build_verification_context_from_diagram()` was added in the design_data module work. It queries Neo4j via `DesignDataRepository`, builds a `ClassDiagram`, and calls `.to_verification_dicts()`. The output format is identical to `build_verification_context()`. The two call sites simply need their import and function name swapped.

- [ ] **Step 1: Replace call in `orchestrator.py` Phase 3**

In `backend/pipeline/orchestrator.py`, around line 161-167:

```python
# BEFORE:
from backend.requirements.services.persistence import (
    build_verification_context,
    persist_verification,
)
...
class_contexts = build_verification_context(ns)

# AFTER:
from backend.requirements.services.persistence import (
    build_verification_context_from_diagram,
    persist_verification,
)
...
class_contexts = build_verification_context_from_diagram(ns)
```

- [ ] **Step 2: Replace call in `verify_llr.py` `__main__` block**

In `backend/ticketing_agent/verify/verify_llr.py`, lines 192-215 (`__main__` block):

```python
# BEFORE:
from backend.requirements.services.persistence import build_verification_context
...
class_contexts = build_verification_context(ns)

# AFTER:
from backend.requirements.services.persistence import build_verification_context_from_diagram
...
class_contexts = build_verification_context_from_diagram(ns)
```

**Note:** The `verify()` function itself does NOT call `build_verification_context` — it receives `class_contexts` as a parameter. Only the `__main__` block and the orchestrator call it.

- [ ] **Step 3: Verify no other callers of old function**

Search for remaining references:

```bash
grep -rn "build_verification_context\b" backend/ --include='*.py' | grep -v "__pycache__" | grep -v "build_verification_context_from_diagram"
```

Expected remaining references:
- `backend/requirements/services/persistence.py` — the original function definition (keep for now, it's the fallback)
- Any NiceGUI views or scripts that call it (leave those for a separate cleanup)

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_design_data_models.py tests/test_design_data_transforms.py -v
python -c "from backend.pipeline.orchestrator import run_pipeline; print('OK')"
python -c "from backend.ticketing_agent.verify.verify_llr import verify; print('OK')"
```

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline/orchestrator.py backend/ticketing_agent/verify/verify_llr.py
git commit -m "refactor: replace build_verification_context with build_verification_context_from_diagram"
```

---

## Task 2: Replace `all_oo_classes` dict construction with `class_diagram_from_oo_design`

**Files:**
- Modify: `backend/pipeline/orchestrator.py`

**Context:** The orchestrator manually builds `all_oo_classes: list[dict]` by iterating `oo.classes` and constructing partial dicts with only `name`, `module`, `attributes`, `methods`. This loses description, visibility, associations, interfaces, and enums. The replacement routes through `class_diagram_from_oo_design()` and accumulates `ClassDiagram` objects, then converts back to `OODesignSchema` dicts for downstream consumption.

The replacement is conservative: downstream consumers (`generate_tasks`, `generate_skeleton`, `check_design_against_code`) already handle `OODesignSchema.model_dump()` format with `.get()` accessors. The full schema is a superset of the partial dict, so passing complete data is safe.

- [ ] **Step 1: Add imports and replace accumulation loop**

In `backend/pipeline/orchestrator.py`, at the top of `run_pipeline()`, add to the imports inside Phase 4:

```python
from backend.design_data import class_diagram_from_oo_design, oo_design_from_class_diagram
from backend.design_data.models import ClassDiagram
```

Replace the `all_oo_classes` accumulation (lines ~198-238):

```python
# BEFORE:
all_oo_classes: list[dict] = []

for hlr in hlrs_neo4j:
    ...
    for cls in oo.classes:
        all_oo_classes.append(
            {
                "name": cls.name,
                "module": cls.module,
                "attributes": [
                    {"name": a.name, "type_name": a.type_name} for a in cls.attributes
                ],
                "methods": [
                    {
                        "name": m.name,
                        "parameters": m.parameters,
                        "return_type": m.return_type,
                    }
                    for m in cls.methods
                ],
            }
        )

# AFTER:
accumulated_diagram = ClassDiagram()

for hlr in hlrs_neo4j:
    ...
    diagram = class_diagram_from_oo_design(oo, component_id=hlr.component_id)
    accumulated_diagram.classes.extend(diagram.classes)
    accumulated_diagram.interfaces.extend(diagram.interfaces)
    accumulated_diagram.enums.extend(diagram.enums)
    accumulated_diagram.associations.extend(diagram.associations)
    for mod in diagram.module_names:
        if mod not in accumulated_diagram.module_names:
            accumulated_diagram.module_names.append(mod)
```

**Important:** The `ClassDiagram.model_post_init` rebuilds `_entity_index`. After mutation we must call it manually, or create a fresh `ClassDiagram` from accumulated lists. The simplest approach — since `ClassDiagram` uses `PrivateAttr` for `_entity_index` — is to rebuild when needed:

```python
def _merge_diagrams(base: ClassDiagram, new: ClassDiagram) -> ClassDiagram:
    """Merge new diagram into base, returning a fresh ClassDiagram with rebuilt index."""
    return ClassDiagram(
        module_names=list(dict.fromkeys(base.module_names + new.module_names)),
        classes=base.classes + new.classes,
        interfaces=base.interfaces + new.interfaces,
        enums=base.enums + new.enums,
        associations=base.associations + new.associations,
    )
```

Add this helper near the top of `orchestrator.py` (module-level) or as a private function.

Then inside the loop:

```python
accumulated_diagram = _merge_diagrams(accumulated_diagram, diagram)
```

- [ ] **Step 2: Build `all_oo_schema` for downstream consumption**

After the Phase 4 loop, before Phase 5, create the full schema dict:

```python
all_oo_schema = oo_design_from_class_diagram(accumulated_diagram)
```

This gives us a full `OODesignSchema` we can pass to downstream consumers.

- [ ] **Step 3: Replace Phase 5 (task generation) usage**

The current code filters `all_oo_classes` by component module name:

```python
comp_name = _get_component_name(hlr.component_id) or ""
hlr_classes = [
    c for c in all_oo_classes if c.get("module") == comp_name
] or all_oo_classes[:3]
```

Replace with:

```python
comp_name = _get_component_name(hlr.component_id) or ""
hlr_diagram = accumulated_diagram.classes_in_module(comp_name)
if not hlr_diagram:
    hlr_diagram = accumulated_diagram.classes[:3]

# Build per-HLR OODesignSchema for task generation
hlr_oo = oo_design_from_class_diagram(
    ClassDiagram(
        module_names=accumulated_diagram.module_names,
        classes=hlr_diagram if hlr_diagram else accumulated_diagram.classes[:3],
        interfaces=accumulated_diagram.interfaces,
        enums=accumulated_diagram.enums,
        associations=accumulated_diagram.associations,
    )
)

batch = generate_tasks(
    hlr=hlr_dict,
    llrs=llrs_for_hlr,
    oo_design=hlr_oo.model_dump(),
    verifications=all_verifications,
    model=model,
)
```

**Conservative alternative:** If we want to exactly match the current behavior (partial classes only), we can instead filter by module on the schema dict:

```python
comp_name = _get_component_name(hlr.component_id) or ""
all_oo_dict = all_oo_schema.model_dump()
hlr_classes = [
    c for c in all_oo_dict["classes"] if c.get("module") == comp_name
] or all_oo_dict["classes"][:3]

batch = generate_tasks(
    hlr=hlr_dict,
    llrs=llrs_for_hlr,
    oo_design={"classes": hlr_classes},
    verifications=all_verifications,
    model=model,
)
```

This matches the current behavior exactly and is the safer path. Use this approach.

- [ ] **Step 4: Replace Phase 6 (skeleton generation) usage**

```python
# BEFORE:
skeleton_results = generate_skeleton(
    oo_design={"classes": all_oo_classes},
    workspace_dir=workspace_dir,
)

# AFTER:
skeleton_results = generate_skeleton(
    oo_design=all_oo_schema,
    workspace_dir=workspace_dir,
)
```

`generate_skeleton()` already handles `OODesignSchema` instances (it calls `model_dump()` internally), so passing the Pydantic model directly is cleaner than the partial-dict approach.

- [ ] **Step 5: Replace Phase 9 (sync hooks) usage**

```python
# BEFORE:
design_report = check_design_against_code(
    oo_design={"classes": all_oo_classes},
    source_files=source_files,
)

# AFTER:
design_report = check_design_against_code(
    oo_design=all_oo_schema.model_dump(),
    source_files=source_files,
)
```

`check_design_against_code` accesses `oo_design.get("classes", [])` and `oo_design.get("interfaces", [])`, so passing the full schema dict is safe — the additional keys are simply ignored.

- [ ] **Step 6: Remove the `DesignNode` import if no longer needed**

Check if `from backend.db.neo4j.repositories.models import DesignNode` and `qname_to_node` are still used elsewhere in orchestrator.py. They are — `qname_to_node` is passed to `persist_design()`. Keep that import.

- [ ] **Step 7: Run tests**

```bash
python -c "from backend.pipeline.orchestrator import run_pipeline; print('OK')"
python -m pytest tests/test_design_data_models.py tests/test_design_data_transforms.py -v
```

- [ ] **Step 8: Commit**

```bash
git add backend/pipeline/orchestrator.py
git commit -m "refactor: replace all_oo_classes dict construction with class_diagram_from_oo_design"
```

---

## Task 3: Verification and cleanup

- [ ] **Step 1: Search for remaining `all_oo_classes` or `build_verification_context` usages**

```bash
grep -rn "all_oo_classes\|build_verification_context\b" backend/ --include='*.py' | grep -v "__pycache__" | grep -v "build_verification_context_from_diagram"
```

Verify no remaining direct references to the old patterns in production code (test files are OK).

- [ ] **Step 2: Run full test suite**

```bash
python -m pytest tests/test_design_data_models.py tests/test_design_data_transforms.py tests/test_design_oo_tools.py -v
python -c "
from backend.pipeline.orchestrator import run_pipeline
from backend.ticketing_agent.verify.verify_llr import verify
from backend.requirements.services.persistence import build_verification_context_from_diagram
from backend.design_data import class_diagram_from_oo_design, oo_design_from_class_diagram, ClassDiagram
print('All imports OK')
"
```

- [ ] **Step 3: Mark old functions as deprecated (optional)**

If desired, add deprecation comments to `build_verification_context()` in `persistence.py`:

```python
def build_verification_context(neo4j_session: "Neo4jSession") -> list[dict]:
    """Build structured class-level context for the verification agent.

    DEPRECATED: Use build_verification_context_from_diagram() instead.
    This function is kept as a fallback but will be removed in a future version.
    ...
    """
```

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: verify design_data integration, deprecate build_verification_context"
```