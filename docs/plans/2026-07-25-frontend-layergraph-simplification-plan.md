# Implementation Plan: Frontend LayerGraph Simplification

**Spec:** `docs/specs/2026-07-25-frontend-layergraph-simplification-design.md`

## Overview

Replace the `DesignRepository` → `OntologyGraph` → `format_ontology_graph()` pipeline in the frontend with `GraphRepository` → `LayerGraph` → `layer_graph_to_cytoscape()`. Six tasks, ordered by dependency.

---

## Task 1: Create `frontend/graph/labels.py` — UML label builders

**Why first:** The label formatters are self-contained with no dependencies on new code. Extracting them first means `format.py` can import them immediately.

**Steps:**

1. Create `frontend/graph/__init__.py` (empty for now)
2. Create `frontend/graph/labels.py`
3. Copy the following from `backend/graph/transforms.py` into `labels.py`:
   - Constants: `_COLLAPSIBLE_KINDS`, `_OWNER_KINDS`, `_VISIBILITY_PREFIX`, `_VISIBILITY_ORDER`, `_KIND_ORDER`, `_MEMBER_COLORS`, `_STATUS_COLORS_HTML`, `KIND_BORDER_COLORS`, `STATUS_BORDER_COLORS`, `_BUILTIN_TYPES`, `_TEMPLATE_PREFIXES`
   - Functions: `_is_builtin_type()`, `_type_origin_marker()`, `_dedup_by_name()`, `_format_member_html()`, `_build_uml_html()`, `_format_member_line()`, `_build_uml_label()`
4. Copy from `backend/graph/__init__.py` into `labels.py`:
   - `_CODEGRAPH_KIND_GROUP` dict
   - `_CODEGRAPH_STEREOTYPE_MAP` dict
5. Add `_ENTITY_KINDS = {"class", "interface", "enum", "struct"}` — needed by format.py to skip entity-kind children in member grouping
6. Ensure all imports are stdlib + typing only (no `backend.*` or `codegraph.*` imports)
7. Keep `_STEREOTYPES` dicts inside `_build_uml_label` and `_build_uml_html` as-is (they are local to those functions)

**Files created:**
- `frontend/graph/__init__.py`
- `frontend/graph/labels.py`

**Files unchanged:** `backend/graph/transforms.py` (cleaned up in Task 5)

**Verify:** `python -c "from frontend.graph.labels import _build_uml_label, _build_uml_html, _ENTITY_KINDS"`

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
   - Recurse into `entry.children` (grouped by type_key); namespace/module/package nodes become `parent_id` for children
   - Collect `entry.references` as Cy edges via `_build_edge()`
4. Implement `_build_node(entry, parent_id) -> dict`:
   - Unified handler for all node types (namespace, compound, member)
   - Reads `entry.node` attributes for fields: `qualified_name`, `name`, `kind`, `layer`, `source`, `component_id`, `visibility` (mapped from `protection`), `brief_description`/`description`, `type_signature`, `argsstring`
   - For compound nodes with children: build UML label via `_build_uml_label()` / `_build_uml_html()` from `labels.py`, set `has_members`, `html_label`, `member_count`
   - For namespace nodes: set `is_namespace: "true"`, no UML label
   - Set `parent` field from `parent_id` parameter (Cytoscape compound node parent)
   - Set `change_status: "new"` for design-layer nodes (matching current behavior)
5. Implement `_build_edge(source_qname, target_key, relation_type) -> dict`:
   - Produce `{"data": {"id": f"e_{source_qname}_{target_key}_{relation_type}", "source": source_qname, "target": target_key, "label": relation_type}}`
   - Note: `target_key` in `CompositeEntry.references` is a local key that equals `qualified_name` for compounds/members/namespaces
6. Implement `_is_namespace(node) -> bool`:
   - Return True if `getattr(node, 'kind', '') in ('namespace', 'module', 'package')`
7. Implement `_build_member_data(entry) -> dict[str, list[dict]]` — helper to extract member dicts from `entry.children` for UML label building:
   - Skip entity-kind children (`_ENTITY_KINDS`)
   - Group by canonical kind using `_CODEGRAPH_KIND_GROUP`
   - Each member dict: `{"name": ..., "type_signature": ..., "argsstring": ..., "visibility": ..., "qualified_name": ..., "layer": ...}`
8. Implement three filter helpers that mutate `LayerGraph` in-place:
   - `_filter_by_kind(graph, kind)`: remove entries from `graph.entries` whose `node.kind != kind`; prune resulting orphan subtrees; also remove `entry.references` edges whose target is no longer in the graph
   - `_filter_by_search(graph, text)`: mark entries where `text` appears in `node.name` or `node.qualified_name`; preserve ancestor chain; walk bottom-up, keep any entry with a matching descendant; prune unmarked entries from `graph.entries`
   - `_filter_by_component(graph, component_id)`: keep entries where `node.component_id == component_id`; preserve ancestor chain by same bottom-up strategy
9. Update `frontend/graph/__init__.py`: re-export `layer_graph_to_cytoscape` and filter helpers

**Key design decisions for filters:**

All three filters preserve the `CompositeEntry` tree. When an entry is kept because a descendant matches, its ancestors must also be kept. Implementation: walk all entries via `_all_entries()`, mark entries that match or have a matching descendant, then rebuild `graph.entries` keeping only marked root entries. Since `_all_entries()` returns a generator, materialize with `list()` when needed for double-pass algorithms.

After filtering, also prune references: for each remaining entry, remove `(rel_type, target_key, target_type)` tuples where `target_key` is not in the surviving entry set.

**Files created:**
- `frontend/graph/format.py`

**Files modified:**
- `frontend/graph/__init__.py` (add re-exports)

**Verify:** Write a small test that constructs a `LayerGraph` with a namespace → class → method hierarchy, converts to Cytoscape, and asserts:
- Namespace node has `is_namespace: "true"` and is parent of class
- Class node has `has_members: "true"` and UML label containing method names
- Edges reference qualified names correctly

---

## Task 3: Rewrite `frontend/data/ontology.py` — replace DesignRepository reads with GraphRepository

**Why third:** Depends on `frontend/graph/format.py` being importable.

**Steps:**

1. Remove `from backend.db.neo4j.repositories.design import DesignRepository` from all read-path functions (keep in `update_member_type` and `fetch_hlr_graph_data`)
2. Remove `from backend.graph import format_ontology_graph` from all functions
3. Keep `_label_match_direct()` — still needed by `fetch_node_detail_full()` for the TRACES_TO raw Cypher query
4. Rewrite `fetch_ontology_data()`:
   ```python
   from codegraph.repository import GraphRepository
   repo = GraphRepository()
   graph = repo.get_by_layer("design")
   ```
   - Walk `list(graph._all_entries())` to build `nodes`, `kind_counts`, `total_nodes`
   - Count `total_predicates` from `entry.references` across all entries
   - Keep the SQLite `Component` lookup for component names (unchanged)
   - Note: `total_triples` in the old code maps to `total_references` (sum of reference counts); adapt the return key if needed
5. Rewrite `fetch_ontology_graph_data()`:
   ```python
   from codegraph.repository import GraphRepository
   from frontend.graph.format import layer_graph_to_cytoscape, _filter_by_kind, _filter_by_search, _filter_by_component
   
   repo = GraphRepository()
   graph = repo.get_by_layer(layer)
   
   if kind_filter:
       _filter_by_kind(graph, kind_filter)
   if search:
       _filter_by_search(graph, search)
   if component_id:
       _filter_by_component(graph, component_id)
   
   formatted = layer_graph_to_cytoscape(graph)
   ```
   - Apply `filter_cross_layer_elements()` if `include_dependencies` is False
   - Apply `enrich_with_requirement_tags()` if layer is "design" and tags are enabled
6. Rewrite `fetch_neighbourhood_graph_data(qualified_name)`:
   ```python
   from codegraph.repository import GraphRepository
   from frontend.graph.format import layer_graph_to_cytoscape
   
   repo = GraphRepository()
   graph = repo.get_by_neighbourhood(qualified_name)
   return layer_graph_to_cytoscape(graph)
   ```
   - Wrap in try/except returning `{"nodes": [], "edges": []}` on failure
7. Rewrite `fetch_graph_node_detail(qualified_name)`:
   ```python
   repo = GraphRepository()
   graph = repo.get_by_compound(qualified_name)
   flat = graph._flat_index()
   entry = flat.get(qualified_name)
   if entry is None:
       return None
   ```
   - Build `outgoing` from `entry.references` — each `(rel_type, target_key, target_type)` becomes `{"rel": rel_type, "target_qn": target_key, "target_name": "", "target_labels": [target_type]}`
   - Build `incoming` by scanning all entries in `flat.items()`: for each other entry's references, if `target_key == qualified_name`, add to incoming
   - Build `members` by flattening `entry.children` (iterate all type groups)
   - Build `properties` from node attributes (use `vars(entry.node)` or similar, filtering to serializable fields; the current code uses `cg.node.model_dump()` which is Pydantic — for CodeGraphNode use `node.__dict__` filtering out neomodel internals, or build a field-by-field dict)
   - **Important:** The old code uses `CompoundGraph.node.model_dump()` and `CompoundGraph.edges_out/in`. The new code uses `CompositeEntry.node` (a `CodeGraphNode` neomodel instance). Build the properties dict by reading known attributes: `qualified_name`, `name`, `kind`, `layer`, `source`, `component_id`, `protection` (→ visibility), `description`, `brief_description`, `type_signature`, `argsstring`, `definition`, `file_path`, `line_number`, `source_type`, `is_static`, `is_const`, `is_virtual`, `is_abstract`, `is_final`, `specialization`. Use `getattr(node, attr, default)` with a known field list.
8. Rewrite `fetch_node_detail_full(qualified_name)`:
   - Delegate to the new `fetch_graph_node_detail(qualified_name)` for the base data
   - Keep the existing TRACES_TO raw Cypher query for requirement tags (unchanged)
   - Keep the SQLite Component name lookup (unchanged)
9. Remove all unused imports: `Neo4j session`, `DesignRepository` from read paths, raw Cypher strings used only by removed code
10. Keep `filter_cross_layer_elements()` — still operates on Cytoscape dicts
11. Keep `enrich_with_requirement_tags()` import — still called as post-processing
12. Keep `fetch_hlr_graph_data()` — still uses DesignRepository (TRACES_TO)
13. Keep `update_member_type()` — still uses raw Cypher (write operation)
14. Keep `resolve_node_id_by_qualified_name()` — hash-based, unchanged

**Files modified:**
- `frontend/data/ontology.py`

**Verify:**
- `from frontend.data.ontology import fetch_ontology_graph_data, fetch_neighbourhood_graph_data, fetch_graph_node_detail, fetch_ontology_data` all succeed
- No remaining `DesignRepository` import in read-path functions
- `_label_match_direct` still present for `fetch_node_detail_full`

---

## Task 4: Rewrite `frontend/data/dependencies.py` — `fetch_design_dependency_links_data`

**Why fourth:** Depends on `frontend/graph/format.py`.

**Steps:**

1. Remove `from backend.db.neo4j.repositories.design import DesignRepository` from `fetch_design_dependency_links_data`
2. Remove `from backend.graph import format_ontology_graph` from that function
3. Rewrite `fetch_design_dependency_links_data()`:
   ```python
   from codegraph.repository import GraphRepository
   from codegraph.graph import LayerGraph
   from frontend.graph.format import layer_graph_to_cytoscape

   repo = GraphRepository()
   merged_entries: dict[str, CompositeEntry] = {}
   
   for qn in design_qnames:
       sub = repo.get_by_neighbourhood(qn)
       for key, entry in sub._flat_index().items():
           if key not in merged_entries:
               merged_entries[key] = entry
   
   if not merged_entries:
       return {"nodes": [], "edges": []}
   
   # Rebuild a LayerGraph from collected root entries
   graph = LayerGraph(layer="design", entries=merged_entries)
   return layer_graph_to_cytoscape(graph)
   ```
   
   **Note on merging:** Simply collecting all entries into a flat dict and re-wrapping in a `LayerGraph` may lose the tree structure (children that are root entries would be orphaned). Better approach: for each `get_by_neighbourhood` result, merge `sub.entries` into a combined entries dict. If a key already exists, skip it (first write wins for root entries).

4. Wrap in try/except returning `{"nodes": [], "edges": []}` on failure

**Important merge subtlety:** When merging multiple neighbourhood graphs, we need to preserve the tree structure. Each `LayerGraph.entries` contains root entries. To merge:
- Collect all root entries from all subgraphs
- For duplicates, keep the first one encountered
- The `layer_graph_to_cytoscape` walk will follow children recursively, so we only need root entries in the merged dict

**Files modified:**
- `frontend/data/dependencies.py`

**Verify:** No remaining `DesignRepository` or `format_ontology_graph` import in `fetch_design_dependency_links_data`

---

## Task 5: Clean up `backend/graph/`

**Why fifth:** Only after the frontend no longer calls `format_ontology_graph()`.

**Steps:**

1. In `backend/graph/__init__.py`:
   - Remove `format_ontology_graph` from module (it was the main `_build_compound_cytoscape_node` etc. pipeline)
   - Remove `_CODEGRAPH_KIND_GROUP` and `_CODEGRAPH_STEREOTYPE_MAP` (moved to `frontend/graph/labels.py`)
   - Remove `_ENTITY_KINDS` import from transforms (moved to `frontend/graph/labels.py`)
   - Keep `tag_cross_layer` — still used as post-processing by `frontend/data/ontology.py`
   - Remove all `TYPE_CHECKING` imports that were only needed by `format_ontology_graph` (`CompoundGraph`, `GraphEdge`, `NamespaceGraph`, `OntologyGraph`) — **only if** no other backend code imports them. Check first with `grep -rn "from backend.graph import" backend/ frontend/`
   - Remove `_build_compound_cytoscape_node`, `_build_namespace_cytoscape_node`, `_build_graph_edge` from `__init__.py` (they were re-exports from transforms)

2. In `backend/graph/transforms.py`:
   - Remove `format_ontology_graph()` function
   - Remove `_build_compound_cytoscape_node()`, `_build_namespace_cytoscape_node()`, `_build_graph_edge()`
   - Remove `_assign_component_parents()`, `_assign_inferred_parents()` and all their helpers: `_resolve_parent_ns`, `_find_existing_module`, `_ensure_namespace_node`, `_match_namespace`, `_fetch_component_namespaces`, `_CONTAINABLE`
   - Remove UML label functions moved to `frontend/graph/labels.py`: `_build_uml_label()`, `_build_uml_html()`, `_format_member_html()`, `_format_member_line()`
   - Remove constants moved to `frontend/graph/labels.py`: `_COLLAPSIBLE_KINDS`, `_OWNER_KINDS`, `_VISIBILITY_PREFIX`, `_VISIBILITY_ORDER`, `_KIND_ORDER`, `_MEMBER_COLORS`, `_STATUS_COLORS_HTML`, `KIND_BORDER_COLORS`, `STATUS_BORDER_COLORS`, `_BUILTIN_TYPES`, `_TEMPLATE_PREFIXES`, `_is_builtin_type()`, `_type_origin_marker()`, `_dedup_by_name()`
   - Remove `_ENTITY_KINDS` (moved to frontend)
   - **Keep** `tag_cross_layer()` — still used

3. Search for remaining imports of removed symbols:
   ```bash
   grep -rn "format_ontology_graph\|_build_uml_label\|_build_uml_html\|_build_compound_cytoscape_node\|_CODEGRAPH_KIND_GROUP\|_CODEGRAPH_STEREOTYPE_MAP" backend/ frontend/ --include='*.py'
   ```
   If references remain, audit case-by-case but do NOT migrate in this task.

**Files modified:**
- `backend/graph/__init__.py`
- `backend/graph/transforms.py`

**Verify:**
- `python -c "from backend.graph import tag_cross_layer"` succeeds
- No remaining frontend code imports `format_ontology_graph`
- `python -c "from frontend.graph.format import layer_graph_to_cytoscape"` succeeds

---

## Task 6: End-to-end verification

**Why last:** Ensures all import paths are correct and nothing is broken.

**Steps:**

1. **Import audit:**
   ```bash
   grep -rn "from backend.graph import format_ontology_graph" frontend/
   grep -rn "from backend.db.neo4j.repositories.design import DesignRepository" frontend/data/ontology.py frontend/data/dependencies.py
   ```
   Expected: `format_ontology_graph` has zero hits in frontend/. `DesignRepository` hits only in `fetch_hlr_graph_data` and `update_member_type` within `ontology.py`, and zero hits in `dependencies.py`.

2. **No-op import test:**
   ```bash
   python -c "from frontend.graph.format import layer_graph_to_cytoscape"
   python -c "from frontend.graph.labels import _build_uml_label, _build_uml_html, _ENTITY_KINDS, _CODEGRAPH_KIND_GROUP, _CODEGRAPH_STEREOTYPE_MAP"
   python -c "from backend.graph import tag_cross_layer"
   ```

3. **Shape compatibility check:** Verify that `layer_graph_to_cytoscape()` output matches the existing `format_ontology_graph()` output shape:
   ```python
   {"nodes": [{"data": {"id": ..., "label": ..., ...}}, ...], 
    "edges": [{"data": {"id": ..., "source": ..., "target": ..., "label": ..., ...}}, ...]}
   ```

4. **Run existing tests:** `pytest tests/ -x`

5. **Manual verification** (requires running app with Neo4j):
   - Ontology overview page (`/ontology`): stats render correctly
   - Ontology graph page (`/ontology/graph`): graph renders, filters work (kind, search, component), layer switching works, requirement tags toggle works, dependency toggle works
   - Node detail page (`/node/{id}`): properties, members, relationships, neighbourhood graph
   - Dependency review page: dependency links load
   - HLR detail page: ontology graph renders (still uses `DesignRepository` for TRACES_TO)

---

## Risk Mitigation

| Risk | Mitigation |
|---|---|
| `GraphRepository` requires live Neo4j | The existing `DesignRepository` fallback remains for `fetch_hlr_graph_data()` and `update_member_type()`. Both paths return the same Cytoscape dict shape. If needed, a feature flag can switch back. |
| Performance on large graphs | `GraphRepository.get_by_layer()` does many small neomodel queries. If slow, batch Cypher can be re-introduced as an optimization without changing the transform layer. |
| `CompositeEntry.references` stores `(relation_type, target_key, target_type)` tuples, not rich `GraphEdge` objects | `_build_edge()` builds edges from tuple fields only. The current frontend only uses `label` (= relation_type) for display, so `mechanism`, `position`, `name`, `display_name` from `GraphEdge` are not needed. If needed later, extend the tuple or add a separate edge-property map. |
| `_all_entries()` returns a generator, not a list | Materialize with `list()` when multiple passes are needed (e.g., filter helpers that scan then prune). |
| `fetch_ontology_data()` previously used `DesignRepository.get_graph_stats()` which returns `total_edges` | The new version computes `total_triples` from `entry.references` counts. The key name may differ — verify the return dict matches what the frontend page expects. |
| Member attribute name differences | `CompoundGraph.members` used `protection` for visibility; `CodeGraphNode` also uses `protection`. Ensure `_build_node` maps `protection → visibility` in the Cytoscape output. |