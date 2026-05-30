# High Priority: Replace build_verification_context and all_oo_classes

## H1. Replace `build_verification_context()` calls with `build_verification_context_from_diagram()`

### What

Replace the direct `build_verification_context(neo4j_session)` call sites with the new
`build_verification_context_from_diagram(neo4j_session, component_id)` that goes through
the design_data module.

### Why

`build_verification_context()` in `persistence.py` runs a hand-written Cypher query that
mirrors what `DesignDataRepository.get_class_diagram()` now does with typed models. The new
path through `ClassDiagram.to_verification_dicts()` is:
- More maintainable (one model definition, not duplicated query + dict construction)
- Type-safe (Pydantic models, not anonymous dicts)
- Testable without Neo4j (unit-test the transform)

### Call sites (2)

1. **`backend/pipeline/orchestrator.py` line ~167:**
   ```python
   class_contexts = build_verification_context(ns)
   ```
   Replace with:
   ```python
   from backend.requirements.services.persistence import build_verification_context_from_diagram
   class_contexts = build_verification_context_from_diagram(ns)
   ```

2. **`backend/ticketing_agent/verify/verify_llr.py` line ~215:**
   ```python
   class_contexts = build_verification_context(ns)
   ```
   Replace with:
   ```python
   from backend.requirements.services.persistence import build_verification_context_from_diagram
   class_contexts = build_verification_context_from_diagram(ns)
   ```

### Changes

| File | Change |
|---|---|
| `backend/pipeline/orchestrator.py` | Replace import + call site |
| `backend/ticketing_agent/verify/verify_llr.py` | Replace import + call site |

### Verification

- Existing integration tests should continue to pass (the output format is identical)
- `build_verification_context()` is NOT removed yet (only deprecated) — other callers may exist in NiceGUI views or dashboard code

---

## H2. Replace `all_oo_classes` dict construction with `class_diagram_from_oo_design`

### What

The pipeline orchestrator builds `all_oo_classes: list[dict]` by manually iterating `oo.classes`
and constructing ad-hoc dicts with `name`, `module`, `attributes`, `methods`. This is then passed
to `generate_tasks()`, `generate_skeleton()`, `check_design_against_code()`, and
`sync_hooks.check_design_against_code()` as `oo_design={"classes": all_oo_classes}`.

Replace this with `class_diagram_from_oo_design()` and use typed access or
`oo_design_from_class_diagram()` to get back the OODesignSchema-compatible dict shape that
downstream consumers need.

### Why

The `all_oo_classes` construction is an ad-hoc partial reconstruction of data that the design_data
module now handles properly. It only captures `name`, `module`, `attributes[{name, type_name}]`,
and `methods[{name, parameters, return_type}]` — missing description, visibility, associations,
interfaces, enums, and all the context that the full `ClassDiagram`/`OODesignSchema` carries.

By routing through `class_diagram_from_oo_design` → `oo_design_from_class_diagram`, we get:
- Complete data (not just class subsets)
- Type-safe transformation
- Consistent qualified names
- Easy filtering by module/component from the typed model

### Current code (lines 198–238 of orchestrator.py)

```python
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
```

### Proposed replacement

```python
from backend.design_data import class_diagram_from_oo_design

accumulated_diagrams: list[ClassDiagram] = []

for hlr in hlrs_neo4j:
    ...
    diagram = class_diagram_from_oo_design(oo, component_id=hlr.component_id)
    accumulated_diagrams.append(diagram)
```

Then at each consumption point:

**Phase 5: Task generation** (currently uses `hlr_classes` filtered by module):
```python
# Instead of filtering all_oo_classes by module:
hlr_diagram = accumulated_diagrams[idx]  # or accumulate across HLRs in same component
oo_for_hlr = oo_design_from_class_diagram(hlr_diagram)
batch = generate_tasks(
    hlr=hlr_dict,
    llrs=llrs_for_hlr,
    oo_design=oo_for_hlr.model_dump(),
    verifications=all_verifications,
    model=model,
)
```

**Phase 6: Skeleton generation:**
```python
from backend.design_data import oo_design_from_class_diagram

# Merge all diagrams into one for skeleton generation
all_oo = oo_design_from_class_diagram(
    ClassDiagram(
        module_names=[m for d in accumulated_diagrams for m in d.module_names],
        classes=[c for d in accumulated_diagrams for c in d.classes],
        interfaces=[i for d in accumulated_diagrams for i in d.interfaces],
        enums=[e for d in accumulated_diagrams for e in d.enums],
        associations=[a for d in accumulated_diagrams for a in d.associations],
    )
)
skeleton_results = generate_skeleton(
    oo_design=all_oo,
    workspace_dir=workspace_dir,
)
```

**Phase 9: Sync hooks** (currently passes `{"classes": all_oo_classes}`):
```python
design_report = check_design_against_code(
    oo_design=all_oo.model_dump(),
    source_files=source_files,
)
```

### Downstream compatibility

The downstream consumers (`generate_tasks`, `generate_skeleton`, `check_design_against_code`)
all accept `dict` shaped like `OODesignSchema.model_dump()`. The key difference is they currently
receive `{"classes": [...]}` (partial, no interfaces/enums/associations), while
`oo_design_from_class_diagram()` produces the full schema.

This is safe because:
- `generate_skeleton` already handles `OODesignSchema` instances
- `check_design_against_code` accesses `oo_design.get("classes", [])` and `oo_design.get("interfaces", [])`
- `generate_tasks` accesses `oo_design.get("classes", [])`

### Changes

| File | Change |
|---|---|
| `backend/pipeline/orchestrator.py` | Replace `all_oo_classes` accumulation and all consumption points |
| `backend/pipeline/orchestrator.py` | Add imports for `class_diagram_from_oo_design`, `oo_design_from_class_diagram`, `ClassDiagram` |
| No changes to downstream consumers | They already accept the full `OODesignSchema` dict shape |

### Verification

- Pipeline smoke test (if available) should produce identical output
- `check_design_against_code` test should pass with full schema input
- Skeleton generation should handle full `OODesignSchema` (already does)

### Risk

Low. The main risk is that `oo_design_from_class_diagram()` reverses the forward transform,
producing a **complete** `OODesignSchema` where the current code passes a **partial** one
(just `{"classes": [...]}`). Downstream code that assumes the partial shape could break if
it doesn't handle `interfaces`/`enums`/`associations` keys. But all three consumers use
`.get("classes", [])` and `.get("interfaces", [])` patterns that gracefully handle the
additional keys.

If we want to be **maximally conservative**, we can pass `all_oo.model_dump()` to
`generate_skeleton` and `check_design_against_code` (which handle full schemas), but keep
the `hlr_classes` filtering logic for `generate_tasks` using
`oo_design_from_class_diagram(hlr_diagram)` for per-HLR isolation.