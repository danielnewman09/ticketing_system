# Design Data Module — Follow-On Work

Completed implementation of the core `backend/design_data/` module (read models, transforms,
repository, convenience methods). This document tracks remaining work to fully replace ad-hoc
data reconstruction patterns across the codebase.

## TODO: Medium Priority

### M1. Replace `_extract_existing_classes` and `_extract_intercomponent_context`

**File:** `backend/ticketing_agent/design/design_per_hlr.py` (lines 36, 113)

**Current state:** Both functions take `OODesignSchema` and produce `list[dict]`. Marked with
`# TODO: Replace with design_data module once prompt builders accept ClassNode directly`.

**The blocker:** Downstream prompt builders (`build_existing_classes_section`,
`build_intercomponent_section` in `design_oo_prompt.py`, and the combined-loop equivalents in
`design_verify/combined_loop.py`) all consume `list[dict]`. Changing their input type means
refactoring every caller.

**Proposed approach — two phases:**

1. **Adapter phase (low risk):** Add `.to_existing_classes_dicts()` and
   `.to_public_api_dicts(component_name, exclude_component_id)` methods to `ClassDiagram`. These
   produce the exact same `list[dict]` shape the prompt builders expect. Replace `_extract_existing_classes`
   with `class_diagram_from_oo_design(oo).to_existing_classes_dicts()` and
   `_extract_intercomponent_context` with `diagram.to_public_api_dicts(...)`. Delete the old
   functions.

2. **Typed phase (follow-up):** Refactor prompt builders to accept a `ClassDiagram` (or slices
   of it) directly instead of `list[dict]`. This eliminates the dict contract entirely and lets
   prompt formatting access typed fields with autocomplete/documentation.

**Downstream callers of `existing_classes: list[dict]`:**
- `design_hlr()` → `design_oo()` → `design_oo_prompt.build_existing_classes_section()`
- `design_verify/combined_loop.py` → `build_existing_classes_section()`
- `design_verify/combined_loop.py` → `build_as_built_section()`
- `generate_tasks.py` → `build_task_context()`

**Downstream callers of `intercomponent_classes: list[dict]`:**
- `design_oo_prompt.build_intercomponent_section()`
- `design_verify/combined_loop.py` → `build_intercomponent_section()`
- `design_oo_tools.py` → `check_class_name()` and validation helpers
- `qname.py` → `qname_resolves()`, `suggest_qname()`
- `design_validation.py` → several validation checks

### M2. Refactor prompt builders to accept typed models

**Files:** `backend/ticketing_agent/design/design_oo_prompt.py`,
`backend/ticketing_agent/design_verify/combined_prompt.py`

Today `build_existing_classes_section(existing_classes: list[dict])` and
`build_intercomponent_section(intercomponent_classes: list[dict])` are the two formatters.
Refactoring them to accept typed models (or `ClassDiagram` slices) would:

- Eliminate a large class of key-typo bugs
- Make the prompt format self-documenting (field names come from model definitions)
- Let us delete the dict-construction functions entirely

This should happen after M1's "adapter phase" is done, so we have a working baseline.

### M3. Add `ClassDiagram` acceptance path to `generate_skeleton.py`

**File:** `backend/ticketing_agent/generate_skeleton.py`

Currently `generate_skeleton()` accepts `dict | OODesignSchema`. Adding `ClassDiagram` as a
third accepted type would enable "generate skeleton from persisted design data in Neo4j"
without re-running the LLM. The implementation:

```python
if isinstance(oo_design, ClassDiagram):
    oo_design = oo_design_from_class_diagram(oo_design)
```

This is a 3-line change plus an import, but it unlocks a new workflow: query Neo4j for an
existing design, convert to `ClassDiagram`, then to `OODesignSchema`, and generate skeleton
code from persisted data.

### M4. Expand integration tests for `DesignDataRepository`

**File:** `tests/test_design_data_repository.py`

Current integration tests only cover `get_class()` and `get_class_diagram(component_id)`.
Missing coverage for:

- `get_interface()` and `get_enum()` single-entity queries
- `get_hlr_subgraph()` — requires seeding HLR nodes and TRACES_TO edges
- `get_classes_for_component()` — multiple classes in one component
- `get_public_api()` — `is_intercomponent=True` filtering
- Association hydration in `get_class_diagram()` — seeding AGGREGATES/REFERENCES edges
- Round-trip: persist design → query with repository → compare with original schema

## TODO: Low Priority

### L1. Add `inherits_from`/`realizes` hydration to `DesignDataRepository._hydrate_class`

The `_hydrate_class` method currently returns `inherits_from=[]` and `realizes=[]` because these
relationships come from Neo4j edges (INHERITS_FROM, REALIZES), not from COMPOSES member nodes.
To hydrate these:

1. After fetching the parent entity, run a separate MATCH for `(d)-[:INHERITS_FROM]->(parent:Design)`
   and `(d)-[:REALIZES]->(iface:Design)`.
2. Collect `parent.qualified_name` into `inherits_from` and `iface.qualified_name` into `realizes`.
3. Add tests seeding inheritance/interface-realization edges and verifying hydration.

### L2. Add component filtering to association queries in `DesignDataRepository`

The current `_fetch_associations` method fetches ALL associations between Design nodes, regardless
of component. The `get_class_diagram(component_id=...)` method should filter associations to only
those where both subject and object belong to the specified component (or are cross-component).

### L3. Layer-aware querying in `DesignDataRepository.get_class_diagram`

The `layer` parameter in `get_class_diagram` is defined but the source_type → layer mapping is
approximate. The repository should support:
- `layer="design"` — only design-layer nodes (source_type=None, "member", or empty)
- `layer="as-built"` — only compound-layer nodes (source_type="compound")
- `layer="dependency"` — only dependency-layer nodes (source_type="dependency")
- Mixed queries (design + as-built for verification context)