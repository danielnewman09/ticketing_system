# Collapse Thin Data-Layer Wrappers — Frontend → Codegraph Direct

**Date:** 2026-06-06
**Status:** Draft

## Summary

Eliminate thin pass-through functions in the frontend data layer that do nothing but delegate to codegraph. Pages that call these wrappers will instead import `GraphRepository` and `layer_graph_to_cytoscape()` directly. Functions that contain real frontend-specific logic (filtering, tag enrichment, stats aggregation, node detail assembly) are kept. Requirements-related code (HLR/LLR triples, TRACES_TO queries) is moved out of `ontology.py` into `hlr.py` or left for a separate pass.

## Scope

**In scope:**

- `frontend/data/ontology.py` — remove `fetch_neighbourhood_graph_data()`; remove HLR/requirements imports; trim `fetch_node_detail_full()` to drop the TRACES_TO Cypher query
- `frontend/data/dependencies.py` — skipped for this pass
- `frontend/data/__init__.py` — remove re-exports of collapsed functions
- Page handlers that call `fetch_neighbourhood_graph_data()` — import codegraph directly
- Page handlers that call `fetch_node_detail_full()` — handle requirement tags separately via hlr.py

**Out of scope:**

- `frontend/data/dependencies.py` — deferred
- `frontend/data/hlr.py` / `frontend/data/llr.py` — handled separately (requirements pass)
- `update_member_type()` — kept as-is (write function)
- All write paths — unchanged

## Functions: Keep vs. Collapse

| Function | Action | Rationale |
|---|---|---|
| `fetch_ontology_graph_data()` | **Keep** | Real logic: in-memory filters + Cytoscape transform + tag enrichment + cross-layer prune |
| `fetch_neighbourhood_graph_data()` | **Collapse** | 3-line wrapper: `get_by_neighbourhood(qn)` → `layer_graph_to_cytoscape()` |
| `fetch_graph_node_detail()` | **Keep** | Real logic: flat index assembly, ref inversion, member extraction, property mapping |
| `fetch_node_detail_full()` | **Keep, but split** | Keeps node detail assembly; TRACES_TO Cypher query moves to hlr.py; SQL component lookup stays |
| `fetch_ontology_data()` | **Keep** | Real logic: stats walk (kind counts, predicate set, node list) + SQL component map |
| `fetch_hlr_graph_data()` | **Out of scope** | Requirements pass (uses DesignRepository) |

## Import Changes in `ontology.py`

**Removed:**

```python
from codegraph.connection import get_session as get_neo4j_session
from backend.db.neo4j.repositories.design import DesignRepository
from backend.graph import format_ontology_graph
```

**Kept:**

```python
from codegraph.repository import GraphRepository
from frontend.graph.format import layer_graph_to_cytoscape, _filter_by_kind, _filter_by_search, _filter_by_component
from backend.requirements.services.graph_tags import enrich_with_requirement_tags, tag_direct_nodes_only
from backend.db import get_session  # for SQL component name lookups
```

## `fetch_node_detail_full()` — Split

The TRACES_TO Cypher query inside `fetch_node_detail_full()` (which builds the `requirements` list) moves out. The function retains:

- calls `fetch_graph_node_detail()` for node properties + relationships
- formats the `node_data` dict (property mapping)
- looks up `Component` name from SQLite

The requirements array (`["requirements"]` key) becomes the page handler's responsibility — it calls `fetch_node_detail_full()` plus a separate requirements-specific function (in `hlr.py`, deferred to the requirements pass). For this pass, `fetch_node_detail_full()` returns an empty `["requirements"]: []` and the TRACES_TO Cypher query block is removed. The node detail page already handles an empty requirements list gracefully.

## Page Handler Changes

### `frontend/pages/ontology_graph.py`

**Before:**

```python
from frontend.data.ontology import fetch_neighbourhood_graph_data

# ...
graph_data = await asyncio.to_thread(fetch_neighbourhood_graph_data, qn)
```

**After:**

```python
from codegraph.repository import GraphRepository
from frontend.graph.format import layer_graph_to_cytoscape

# ...
graph_data = await asyncio.to_thread(
    lambda: layer_graph_to_cytoscape(GraphRepository().get_by_neighbourhood(qn))
)
```

### `frontend/pages/node_detail.py`

The page currently calls `fetch_node_detail_full()`. The `requirements` list in the return value is maintained via a local helper until the requirements pass moves the TRACES_TO logic to `hlr.py`. The import path to `fetch_node_detail_full` does not change.

## `frontend/data/__init__.py` Changes

Remove from the re-export list and `__all__`:

```python
"fetch_neighbourhood_graph_data",
```

All other exports remain.

## What Stays Unchanged

- `frontend/graph/format.py` — unchanged
- `frontend/graph/labels.py` — unchanged
- `frontend/pages/*.py` — all pages except `ontology_graph.py` are unchanged
- `frontend/data/hlr.py`, `frontend/data/llr.py` — unchanged (requirements pass is separate)
- `frontend/data/components.py` — unchanged
- `codegraph` — unchanged (consumed, not modified)
- All backend files — unchanged

## File Manifest

| File | Action |
|---|---|
| `frontend/data/ontology.py` | **Modified.** Remove `fetch_neighbourhood_graph_data()`, trim HLR imports, split TRACES_TO out of `fetch_node_detail_full()` |
| `frontend/data/__init__.py` | **Modified.** Remove `fetch_neighbourhood_graph_data` from exports |
| `frontend/pages/ontology_graph.py` | **Modified.** Import `GraphRepository` + `layer_graph_to_cytoscape` directly |

## Verification

- Existing tests in `frontend/data/` import paths remain valid
- `fetch_ontology_graph_data()` still returns its `{nodes, edges}` dict unchanged
- `fetch_graph_node_detail()` still returns its detail dict unchanged
- `fetch_ontology_data()` still returns its stats dict unchanged
- Category graph on ontology page still renders correctly
- Node detail page still shows properties, relationships, and members
- Component name lookups in detail views still resolve
