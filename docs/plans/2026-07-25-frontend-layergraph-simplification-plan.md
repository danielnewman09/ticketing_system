# Implementation Plan: Frontend LayerGraph Simplification

**Spec:** `docs/specs/2026-07-25-frontend-layergraph-simplification-design.md`

## Overview

Replace the `DesignRepository` → `OntologyGraph` → `format_ontology_graph()` pipeline in the frontend with `GraphRepository` → `LayerGraph` → `layer_graph_to_cytoscape()`. Six tasks, ordered by dependency.

---

## Task 1: Create `frontend/graph/labels.py` — UML label builders

**Why first:** The formatters are self-contained and have no dependencies on the new code. Extracting them first means `format.py` can import them immediately.

**Steps:**

1. Create `frontend/graph/__init__.py` (empty for now)
2. Create `frontend/graph/labels.py`
3. Copy the following from `backend/graph/transforms.py` into `labels.py`:
   - `_COLLAPSIBLE_KINDS`, `_OWNER_KINDS`, `_VISIBILITY_PREFIX`, `_VISIBILITY_ORDER`, `_KIND_ORDER`
   - `_MEMBER_COLORS`, `_STATUS_COLORS_HTML`, `KIND_BORDER_COLORS`, `STATUS_BORDER_COLORS`
   - `_BUILTIN_TYPES`, `_is_builtin_type()`, `_type_origin_marker()`
   - `_dedup_by_name()`
   - `_format_member_html()`, `_build_uml_html()`
   - `_format_member_line()`, `_build_uml_label()`
   - `_CODEGRAPH_KIND_GROUP`, `_CODEGRAPH_STEREOTYPE_MAP` (move from `backend/graph/__init__.py`)
4. Add a `_ENTITY_KINDS` set containing `{"class", "interface", "enum", "struct"}` — needed by format.py to skip entity-kind children in member grouping
5. Update all internal references within the copied functions to be relative imports within `frontend.graph.labels`
6. Verify `labels.py` has no import on `backend.graph` or `codegraph.graph` (it should only use stdlib + typing)

**Files created:**
- `frontend/graph/__init__.py`
- `frontend/graph/labels.py`

**Files unchanged:** `backend/graph/transforms.py` (will be cleaned up in Task 5)

**Verify:** `python -c "from frontend.graph.labels import _build_uml_label, _build_uml_html"` succeeds

---

## Task 2: Create `frontend/graph/format.py` — Cytoscape transform + filters

**Why second:** This is the core new module. It depends on `labels.py` for UML formatting and on `codegraph.graph.LayerGraph` / `codegraph.graph.CompositeEntry` for the data structure.

**Steps:**

1. Create `frontend/graph/format.py`
2. Implement `layer_graph_to_cytoscape(graph: LayerGraph) -> dict`:
   - Walk `graph.entries` recursively via `_walk_entry()`
   - Deduplicate nodes by `qualified_name` (seen set)
   - Produce `{"nodes": [...], "edges": [...]}` in Cytoscape shape
3. Implement `_walk_entry(entry, parent_id, nodes, edges, seen)`:
   - Build Cy node via `_build_node(entry, parent_id)`
   - Recurse into `entry.children` (grouped by type_key); namespace nodes become `parent_id` for children
   - Collect `entry.references` as Cy edges via `_build_edge()`
4. Implement `_build_node(entry, parent_id) -> dict`:
   - Unified handler for all node types (namespace, compound, member)
   - Reads `entry.node.__properties__` for fields: `qualified_name`, `name`, `kind`, `layer`, `source`, `component_id`, `visibility`, `brief_description`/`description`, `type_signature`, `argsstring`
   - For compound nodes with children: build UML label via `_build_uml_label()` / `_build_uml_html()` from `labels.py`, set `has_members`, `html_label`, `member_count`
   - For namespace nodes: set `is_namespace: "true"`, no UML label
   - Set `parent` field from `parent_id` parameter (Cytoscape compound node parent)
   - Set `change_status: "new"` for design layer (matching current behavior)
5. Implement `_build_edge(source_qname, target_key, relation_type) -> dict`:
   - Produce `{"data": {"id": f"e_{source}_{target}_{rel}", "source": source, "target": target, "label": rel}}`
6. Implement `_is_namespace(node) -> bool`:
   - Return True if `getattr(node, 'kind', '') in ('namespace', 'module', 'package')`
7. Implement the three filter helpers that mutate the `LayerGraph` in-place:
   - `_filter_by_kind(graph, kind)`: remove entries whose `node.kind != kind`; prune resulting orphans
   - `_filter_by_search(graph, text)`: keep entries where `text` appears in `name` or `qualified_name`; preserve ancestor chain
   - `_filter_by_component(graph, component_id)`: keep entries where `node.component_id == component_id`; preserve ancestor chain
8. Add imports to `frontend/graph/__init__.py`: `from frontend.graph.format import layer_graph_to_cytoscape` and filter helpers

**Key design decisions for filter helpers:**

All three filters must preserve the `CompositeEntry` tree structure. When an entry is kept because a descendant matches, its ancestors must also be kept. Implementation: walk the tree bottom-up, mark entries that match or have a matching descendant, then prune unmarked entries from `graph.entries`.

For `_filter_by_kind`: after filtering, also remove `entry.references` edges whose target is no longer in the graph.

**Verify:** Write a small test that creates a `LayerGraph` with a namespace → class → method hierarchy, converts to Cytoscape, and checks that namespace is parent of class, class has members in its label, and edges are correct.

---

## Task 3: Rewrite `frontend/data/ontology.py` — replace DesignRepository reads with GraphRepository

**Why third:** Depends on `frontend/graph/format.py` being available.

**Steps:**

1. Remove all `from backend.db.neo4j.repositories.design import DesignRepository` imports
2. Remove all `from backend.graph import format_ontology_graph` imports
3. Remove the `_label_match_direct()` helper (only used by raw Cypher)
4. Rewrite `fetch_ontology_data()`:
   - Call `GraphRepository().get_by_layer("design")`
   - Walk `graph._all_entries()` to build `nodes`, `kind_counts`, `total_nodes`, `total_predicates`
   - Keep the SQLite `Component` lookup for component names (unchanged)
5. Rewrite `fetch_ontology_graph_data()`:
   - Call `GraphRepository().get_by_layer(layer)`
   - Apply filter helpers (kind, search, component) on the LayerGraph
   - Call `layer_graph_to_cytoscape(graph)` to get Cytoscape dicts
   - Apply `filter_cross_layer_elements()` if `include_dependencies` is False
   - Apply `enrich_with_requirement_tags()` if layer is "design" and tags are enabled
6. Rewrite `fetch_neighbourhood_graph_data()`:
   - Call `GraphRepository().get_by_neighbourhood(qualified_name)`
   - Return `layer_graph_to_cytoscape(graph)`
   - Wrap in try/except returning `{"nodes": [], "edges": []}` on failure (preserve current error behavior)
7. Rewrite `fetch_graph_node_detail()`:
   - Call `GraphRepository().get_by_compound(qualified_name)`
   - Use `graph._flat_index()` to look up the entry
   - Build `outgoing` from `entry.references`
   - Build `incoming` by scanning other entries' references for the target qualified_name
   - Build `members` from `entry.children` (flatten all type groups)
   - Build `properties` from `entry.node.__properties__`
8. Rewrite `fetch_node_detail_full()`:
   - Same as `fetch_graph_node_detail()` plus the existing TRACES_TO query (unchanged)
   - Keep the component name lookup from SQLite (unchanged)
9. Update `fetch_ontology_data()` to handle the `_get_component_map()` helper (keep the existing SQLite lookup)
10. Remove unused imports: `Neo4j session`, `DesignRepository`, raw Cypher strings

**Functions that stay unchanged:**
- `filter_cross_layer_elements()` — still operates on Cytoscape dicts
- `fetch_hlr_graph_data()` — uses TRACES_TO, stays with DesignRepository
- `update_member_type()` — write operation, stays as raw Cypher
- `resolve_node_id_by_qualified_name()` — hash-based, stays
- `enrich_with_requirement_tags()` — post-processing import, stays

**Verify:** Run the existing NiceGUI app and check:
- Ontology overview page loads with correct stats
- Ontology graph page renders with filter controls working
- Node detail page shows properties, members, relationships
- Neighbourhood graph page works

---

## Task 4: Rewrite `frontend/data/dependencies.py` — `fetch_design_dependency_links_data`

**Why fourth:** Depends on `frontend/graph/format.py`.

**Steps:**

1. Remove `from backend.db.neo4j.repositories.design import DesignRepository` from `fetch_design_dependency_links_data`
2. Remove `from backend.graph import format_ontology_graph` from that function
3. Rewrite `fetch_design_dependency_links_data()`:
   - Call `GraphRepository().get_by_neighbourhood(qn)` for each qualified name
   - Merge results: collect entries from each subgraph, skip duplicates
   - Call `layer_graph_to_cytoscape(merged)` on the merged graph
   - Wrap in try/except returning `{"nodes": [], "edges": []}` on failure

**Verify:** Navigate to a component's dependency review page and confirm dependency links load.

---

## Task 5: Clean up `backend/graph/`

**Why fifth:** Only after the frontend no longer calls `format_ontology_graph()`.

**Steps:**

1. In `backend/graph/__init__.py`:
   - Remove `format_ontology_graph` from `__all__`
   - Remove the `OntologyGraph` TYPE_CHECKING import (keep `CompoundGraph`, `NamespaceGraph`, `GraphEdge` — they're still used by `DesignRepository`)
   - Remove `_CODEGRAPH_KIND_GROUP` and `_CODEGRAPH_STEREOTYPE_MAP` (moved to `frontend/graph/labels.py`)
   - Keep `tag_cross_layer` — still used as post-processing
2. In `backend/graph/transforms.py`:
   - Remove `format_ontology_graph()` function
   - Remove `_build_compound_cytoscape_node()`, `_build_namespace_cytoscape_node()`, `_build_graph_edge()`
   - Remove `_assign_component_parents()`, `_assign_inferred_parents()`
   - Remove `_build_uml_label()`, `_build_uml_html()`, `_format_member_html()`, `_format_member_line()`
   - Remove `_COLLAPSIBLE_KINDS`, `_OWNER_KINDS`, `_VISIBILITY_PREFIX`, `_VISIBILITY_ORDER`, `_KIND_ORDER`, `_MEMBER_COLORS`, `_STATUS_COLORS_HTML`, `KIND_BORDER_COLORS`, `_BUILTIN_TYPES`, `_is_builtin_type()`, `_type_origin_marker()`, `_dedup_by_name()`, `_CODEGRAPH_KIND_GROUP`, `_CODEGRAPH_STEREOTYPE_MAP`, `_STATUS_COLORS_HTML`, `STATUS_BORDER_COLORS`
   - Keep `tag_cross_layer()` and `_ENTITY_KINDS` (if still referenced anywhere)
3. Search for remaining imports of `format_ontology_graph` across the codebase: `grep -r "format_ontology_graph" backend/ frontend/`
   - If `DesignRepository.get_dependency_links()` or other backend code still uses it, audit case-by-case but do NOT migrate in this task

**Verify:** `python -c "from backend.graph import tag_cross_layer"` succeeds. No remaining frontend code imports `format_ontology_graph`.

---

## Task 6: Update `frontend/data/__init__.py` and verify end-to-end

**Why last:** Ensures all import paths are correct and nothing is broken.

**Steps:**

1. Verify `frontend/data/__init__.py` — no changes needed since function signatures are unchanged (same names, same return shapes)
2. Run a manual end-to-end verification:
   - Ontology overview page (`/ontology`): stats render correctly
   - Ontology graph page (`/ontology/graph`): graph renders, filters work, layer switching works, requirement tags toggle works, dependency toggle works
   - Node detail page (`/node/{id}`): properties, members, relationships, neighbourhood graph
   - Dependency review page: dependency links load
   - HLR detail page: ontology graph renders (still uses `DesignRepository` for TRACES_TO)
3. Check that no remaining file imports `DesignRepository` from `frontend/data/ontology.py` or `frontend/data/dependencies.py` (except for the retained functions: `update_member_type` which imports `get_neo4j`, and `fetch_hlr_graph_data`)
4. Run any existing tests: `pytest tests/ -x`

---

## Risk Mitigation

| Risk | Mitigation |
|---|---|
| `GraphRepository` requires live Neo4j | The existing `DesignRepository` fallback can be kept behind a feature flag if needed. Both paths return the same Cytoscape dict shape. |
| Performance on large graphs | `GraphRepository.get_by_layer()` does many small neomodel queries. If slow, batch Cypher can be re-introduced as an optimization without changing the transform layer. |
| `CompositeEntry._flat_index()` for incoming edges is O(n²) | For node detail, the flat index is built once and scanned. For large graphs, consider building a reverse-reference index at `LayerGraph` construction time. |
| Missing edge properties | `CompositeEntry.references` stores `(relation_type, target_key, target_type)`. Current `GraphEdge` also has `mechanism`, `position`, `name`, `display_name`. These are not in `CompositeEntry.references` yet. If needed, extend the tuple to include these, or add a separate edge-property map. The current frontend only uses `label` (which maps to `relation_type`). |