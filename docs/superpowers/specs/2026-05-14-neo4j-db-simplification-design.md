# Neo4j Layer Simplification

## Objective

Consolidate the Neo4j read/write code into a single `backend/db/neo4j/` package with clear separation between data access and presentation formatting.

## Current State

The Neo4j layer is split across two locations totaling ~1,719 lines:

```
backend/db/neo4j/__init__.py         (77 lines)  — connection management
backend/db/neo4j_sync.py             (357 lines) — write-side sync
backend/db/neo4j_queries/
  __init__.py                        (34 lines)  — query router
  _node_builders.py                  (65 lines)  — Cytoscape dict builders
  _graph_transforms.py               (389 lines) — UML labels, member collapsing, namespace grouping
  design.py                          (240 lines) — design graph queries
  detail.py                          (261 lines) — node detail queries
  compound.py                        (296 lines) — compound layer queries
```

### Problem

Read queries return Cytoscape-js-shaped dicts, coupling Neo4j data access to frontend presentation. The `_graph_transforms.py` and `_node_builders.py` modules are presentation logic living inside the database layer.

## Target State

```
backend/db/neo4j/
  __init__.py             — Facade re-exporting public API
  connection.py           — Neo4jConnection driver/session management
  sync.py                 — Write-side: SQLite → Neo4j sync
  queries/
    __init__.py           — Facade re-exporting raw query functions
    graph.py              — Design-layer read queries → raw dicts
    compounds.py          — Compound-layer read queries → raw dicts
    detail.py             — Single-node queries → raw dicts

backend/graph/
  __init__.py             — Facade re-exporting formatters
  builders.py             — Cytoscape node/edge dict construction
  transforms.py           — Member collapsing, UML labels, namespace grouping
```

### Import graph

```
frontend/data/ontology.py ──→ backend/db/neo4j/queries/*  (raw data)
                                 │
                                 └──→ backend/graph/*       (format for Cytoscape)
```

### What changes per file

**New/kept files** (data layer, `backend/db/neo4j/`):

| File | Source | Change |
|------|--------|--------|
| `__init__.py` | new | Re-export `Neo4jConnection` from connection.py, sync functions from sync.py, raw queries from queries |
| `connection.py` | `neo4j/__init__.py` | Renamed, content unchanged |
| `sync.py` | `neo4j_sync.py` | Moved, content unchanged |
| `queries/__init__.py` | new | Re-export raw query functions from submodules |
| `queries/graph.py` | `design.py` | Stripped `_make_node_data`, `_collapse_members`, `_assign_namespace_parents`. Returns `{nodes: [{qualified_name, kind, name, ...}], edges: [{source, target, type}]}`. `_fetch_traced_requirements` stays but returns raw dicts. |
| `queries/compounds.py` | `compound.py` | Same treatment: no Cytoscape dicts, no formatting pipeline calls. `_discover_dependency_compounds`, `_discover_codebase_compounds`, `_fetch_compound_layer`, `fetch_design_dependency_links` — all return plain dicts. |
| `queries/detail.py` | `detail.py` | `fetch_node_detail` and `fetch_neighbourhood_graph` return raw dicts. No `_collapse_members` call. |

**New files** (presentation layer, `backend/graph/`):

| File | Source | Content |
|------|--------|--------|
| `__init__.py` | new | Re-export `format_cytoscape_graph`, `build_node_dict`, `build_edge_dict` |
| `builders.py` | `_node_builders.py` | `build_cytoscape_node(raw_node)` and `build_cytoscape_edge(raw_edge)` — takes raw dict, returns Cytoscape `{"data": {...}}` shape. Also contains `make_compound_node`, `make_dependency_node` variants. |
| `transforms.py` | `_graph_transforms.py` | `collapse_members(nodes, edges)`, `assign_namespace_parents(nodes, edges)` — same logic, operates on Cytoscape-formatted data. |

### Flow (design graph example)

```python
# frontend/data/ontology.py
from backend.db.neo4j.queries import fetch_design_nodes
from backend.graph import format_cytoscape_graph

def fetch_ontology_graph_data(layer, kind_filter, search, component_id, source_filter):
    try:
        raw = fetch_design_nodes(kind_filter, search, component_id)
        return format_cytoscape_graph(raw)
    except Exception:
        log.warning("Neo4j query failed", exc_info=True)
        return {"nodes": [], "edges": []}
```

The `format_cytoscape_graph(raw)` function in `backend/graph/__init__.py`:
1. Calls `build_cytoscape_node()` / `build_cytoscape_edge()` per item
2. Runs `collapse_members(nodes, edges)` 
3. Runs `assign_namespace_parents(nodes, edges)`
4. Returns `{"nodes": [...], "edges": [...]}`

### Raw dict contract

Each query function returns a dict with `"nodes"` and `"edges"` lists where:
- Each node is `{"qualified_name": str, "name": str, "kind": str, ...}` (flat properties)
- Each edge is `{"source": str, "target": str, "type": str}` (no element_id from Neo4j — just identifiers)

This decouples the Neo4j internals (element IDs) from the frontend interface. The `builders.py` module is responsible for generating stable IDs for Cytoscape.

## Robust Logging

Every function will have logging appropriate to its operation:

### Queries (`backend/db/neo4j/queries/`)
- **`info`**: Query start with params (search terms, filters, limits)
- **`debug`**: Raw results count per query step
- **`warning`**: Full-text index fallback, known expected failures
- **`error`**: Unexpected Neo4j failures, connection issues

### Sync (`backend/db/neo4j/sync.py`)
- **`info`**: Sync start/complete with counts (nodes, triples, requirements)
- **`warning`**: Neo4j unavailable (deferred sync)
- **`error`**: Sync failures

### Connection (`backend/db/neo4j/connection.py`)
- **`info`**: Driver creation, closure
- **`warning`**: Connection verification failures

### Graph formatting (`backend/graph/`)
- **`debug`**: Collapse/transform operations with counts

### Import path updates

All existing importers must be updated:

| Current import | New import |
|---------------|------------|
| `backend.db.neo4j.Neo4jConnection` | `backend.db.neo4j.connection.Neo4jConnection` (or via facade) |
| `backend.db.neo4j.neo4j.NEO4J_URI` | `backend.db.neo4j.connection.NEO4J_URI` |
| `backend.db.neo4j_sync.*` | `backend.db.neo4j.sync.*` |
| `backend.db.neo4j_queries.fetch_graph` | `backend.db.neo4j.queries.fetch_design_nodes` (specific) |
| `backend.db.neo4j_queries.fetch_hlr_subgraph` | `backend.db.neo4j.queries.fetch_hlr_subgraph` |
| `backend.db.neo4j_queries.fetch_neighbourhood_graph` | `backend.db.neo4j.queries.fetch_neighbourhood` |
| `backend.db.neo4j_queries.fetch_node_detail` | `backend.db.neo4j.queries.fetch_node_detail` |
| `backend.db.neo4j_queries.fetch_design_dependency_links` | `backend.db.neo4j.queries.fetch_design_dependency_links` |

### Files to delete

After migration:
- `backend/db/neo4j_sync.py`
- `backend/db/neo4j_queries/` (entire directory)
- `backend/db/neo4j/__init__.py` (rewritten)

### Non-goals

- No changes to sync logic or Cypher queries
- No changes to `services.dependencies.get_neo4j()` — the connection singleton
- No changes to the `frontend/data/` layer beyond import paths and the format step
