# Design: Dependency Graph Linkages

## Problem

When the design pipeline creates an OO design, it references dependency classes
(e.g., `Fl_Button`, `Fl_Window`) in associations, inheritance, and attribute
types. These references are currently lost — `map_oo_to_ontology` doesn't know
which names refer to dependency classes, so it produces triples with bare
strings like `"Fl_Button"` as target qualified names. `persist_design` then
skips these triples because the target isn't in the design's `qname_to_node`
map. Result: **no edges from design nodes to dependency Compounds in Neo4j**.

## Root Cause

The dependency information is available from `discover_classes` (which outputs
each class with `qualified_name`, `source`, `category`, etc.), but it flows only
to the `design_oo` LLM prompt — not to `map_oo_to_ontology`. The mapper has a
`class_lookup` for design-internal classes but no equivalent for dependency
classes.

## Solution

Pass dependency metadata through the pipeline so `map_oo_to_ontology` can
resolve dependency class references and produce triples that link to the
correct Neo4j Compound nodes.

### 1. Build `dependency_lookup` in `design_hlr`

From the `dependency_classes` list (already available in `design_hlr`),
build a `dict[str, str]` mapping bare class name → qualified name:

```python
dependency_lookup = {cls["name"]: cls["qualified_name"] for cls in (dependency_classes or [])}
```

For FLTK classes where `name == qualified_name` (no namespace), this maps
`"Fl_Button" → "Fl_Button"`. For namespaced dependencies like `"string"`,
it could map `"string" → "std::string"`.

### 2. Pass `dependency_lookup` to `map_oo_to_ontology`

Add a `dependency_lookup` parameter. The mapper uses it alongside
`class_lookup` to resolve references in:

- **Association `to_class`/`from_class`**: If the target resolves via
  `dependency_lookup` but not `class_lookup`, it's a dependency reference.
  The association triple is created with the dependency's qualified name.
- **`inherits_from`**: `DigitButton inherits Fl_Button` becomes a
  `generalizes` triple to `"Fl_Button"`.
- **Attribute `type_name` and method `return_type`**: Scan for dependency
  class names (heuristic: capitalized words that match a key in
  `dependency_lookup`). Create a `depends_on` triple from the design class
  to the dependency class.

All of these triples use the dependency's **qualified name** as the target,
matching the Compound node in Neo4j.

### 3. Persist dependency targets as stub nodes

In `persist_design`, when a triple's `object_qualified_name` isn't in
`qname_to_node` (the design's nodes), check if it's a dependency reference.
If so, create a minimal `OntologyNode` stub with:

- `kind = "class"`
- `source_type = "dependency"`
- `qualified_name = <dependency qname>`
- `name = <bare name>`
- `is_intercomponent = True`

This satisfies the SQLite FK constraint (`object_id` → `ontology_nodes.id`)
and provides a join point for the Neo4j sync.

### 4. Skip dependency stubs in `sync_design_node`

When syncing Design nodes to Neo4j, skip nodes with
`source_type = "dependency"`. The real node already exists as a Compound.
`sync_design_triple` already uses `coalesce(o_design, o_compound)`, so the
edge will be created from the Design node directly to the Compound.

### 5. Handle dependency stubs in graph queries

In `fetch_design_graph`, the existing dependency compound fetch already
finds Design→Compound edges. The new `depends_on` triples will also be
Design→Compound edges. The `tag_cross_layer` transform already marks edges
between different layers as `is_cross_layer = "true"`, so dependency
edges will be visually styled in the UI.

### 6. Filter dependency stubs from design-intent views

The `enrich_with_requirement_tags` function and other SQLite-based queries
should exclude `source_type = "dependency"` nodes from design-intent
contexts (they aren't part of the design, they're cross-references).

## Data Flow

```
discover_classes
  └─ dependency_classes: [{qualified_name: "Fl_Button", name: "Fl_Button", source: "fltk", ...}, ...]
      │
      ├─► design_oo (as prompt context) ← already works
      │
      └─► design_hlr builds dependency_lookup: {"Fl_Button": "Fl_Button", "Fl_Window": "Fl_Window", ...}
            │
            └─► map_oo_to_ontology(dependency_lookup=...)
                  │
                  ├─ Association: CalculatorWindow -[aggregates]-> Fl_Button
                  │   resolves to: user_interface::CalculatorWindow -[aggregates]-> Fl_Button
                  │
                  ├─ Inherits: DigitButton inherits Fl_Button  
                  │   resolves to: user_interface::DigitButton -[generalizes]-> Fl_Button
                  │
                  └─ Type reference: attr "clearButton: Fl_Button*"
                      resolves to: user_interface::CalculatorWindow -[depends_on]-> Fl_Button
                  
                  └─► DesignSchema with triples targeting "Fl_Button"
                        │
                        └─► persist_design
                              │
                              ├─ Fl_Button not in qname_to_node
                              │   → create stub OntologyNode(source_type="dependency")
                              │   → triple persists with FK to stub node
                              │
                              └─► sync_design_triple
                                    │
                                    └─ Design node ─[aggregates]→ Compound node (Fl_Button) ✓
```

## Files to Change

| File | Change |
|------|--------|
| `backend/ticketing_agent/design/map_to_ontology.py` | Add `dependency_lookup` param. Use it to resolve dep refs in associations, inheritance, and type signatures. Add `depends_on` triples from type refs. |
| `backend/ticketing_agent/design/design_hlr.py` | Build `dependency_lookup` from `dependency_classes` + `as_built_classes`. Pass to `map_oo_to_ontology`. |
| `backend/requirements/services/persistence.py` | In `persist_design`, create stub nodes for dependency targets not in `qname_to_node`. Track via `DesignResult`. |
| `backend/requirements/services/graph_tags.py` | Exclude `source_type="dependency"` stubs from requirement tag enrichment. |
| `backend/db/neo4j/sync.py` | Skip `source_type="dependency"` nodes in `sync_design_node`. `sync_design_triple` needs no changes. |
| `backend/db/models/ontology.py` | Add `"dependency"` to `SOURCE_TYPES` choices so stubs validate. |
| `backend/codebase/schemas.py` | Add `"dependency"` to `SourceType` literal. |
| `scripts/03_design_requirements.py` | No changes needed — `design_hlr` handles it. |