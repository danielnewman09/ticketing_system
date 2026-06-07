The plan has been written to `docs/plans/2026-07-25-frontend-layergraph-simplification-plan.md`. Here's a summary of what was produced:

**6 tasks, ordered by dependency:**

1. **Create `frontend/graph/labels.py`** — Extract ~18 UML formatting constants and functions from `backend/graph/transforms.py` and `backend/graph/__init__.py` into a new self-contained module with no backend imports.

2. **Create `frontend/graph/format.py`** — Build the new `layer_graph_to_cytoscape()` transform that walks `CompositeEntry` trees (no more manual namespace/compound reconstruction), plus three in-place filter helpers (`_filter_by_kind`, `_filter_by_search`, `_filter_by_component`) that preserve ancestor chains.

3. **Rewrite `frontend/data/ontology.py`** — Replace all `DesignRepository` read paths with `GraphRepository` calls. Four functions rewritten (`fetch_ontology_data`, `fetch_ontology_graph_data`, `fetch_neighbourhood_graph_data`, `fetch_graph_node_detail`). Three functions kept unchanged (`fetch_hlr_graph_data`, `update_member_type`, `resolve_node_id_by_qualified_name`). Key detail: `_all_entries()` returns a generator so we materialize with `list()` when needed.

4. **Rewrite `frontend/data/dependencies.py`** — Replace `DesignRepository` + `format_ontology_graph` with `GraphRepository.get_by_neighbourhood()` + merge + `layer_graph_to_cytoscape()`. Uses `_flat_index()` for merging.

5. **Clean up `backend/graph/`** — Remove `format_ontology_graph`, all moved label functions, `_assign_component_parents`, `_assign_inferred_parents`, moved constants. Keep only `tag_cross_layer` and its helpers.

6. **End-to-end verification** — Import audits, shape compatibility checks, test runs, manual app verification.

**Key differences from the original stale plan:**
- Corrected `_all_entries()` behavior: it returns an Iterator, so we materialize with `list()` when double-iteration is needed
- Corrected `_flat_index()` usage in merge: use `.items()` iteration, not `._all_entries()` key-value pairs
- Noted that `_label_match_direct()` must be kept for the TRACES_TO query in `fetch_node_detail_full`
- Made explicit that `target_key` in `CompositeEntry.references` tuples is a local key that equals `qualified_name` for all relevant node types
- Added clear guidance on what stays in `backend/graph/transforms.py` (only `tag_cross_layer`)