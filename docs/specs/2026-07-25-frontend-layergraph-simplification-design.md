# Frontend LayerGraph Simplification

**Date:** 2026-07-25
**Status:** Approved

## Summary

Replace the `DesignRepository` → `OntologyGraph` → `format_ontology_graph()` read
pipeline in the frontend with `GraphRepository` → `LayerGraph` →
`layer_graph_to_cytoscape()`. The `LayerGraph`/`CompositeEntry` structure
already captures the namespace → compound → member hierarchy that the
current `format_ontology_graph()` manually reconstructs. This eliminates
raw Cypher queries from most frontend read paths and removes the
intermediate `OntologyGraph`/`CompoundGraph`/`NamespaceGraph` types from
the frontend entirely.

## Scope

**In scope:**
- Frontend read paths in `frontend/data/ontology.py` and
  `frontend/data/dependencies.py`
- New `frontend/graph/format.py` and `frontend/graph/labels.py`
- Retirement of `format_ontology_graph()` from the frontend call chain
- In-memory filtering of `LayerGraph` (kind, search, component)

**Out of scope:**
- `DesignRepository` write operations (`merge_node`, `save_associations`,
  `delete_node`, `sync_implementation_status`) — left untouched
- `DesignRepository.get_hlr_subgraph()` — uses TRACES_TO edges outside the
  codegraph model; stays as-is
- Backend agent pipeline (`backend/ticketing_agent/`) — continues using
  `DesignRepository` and/or `ClassDiagram` independently
- `ClassDiagram` / `OntologyGraph` / `CompoundGraph` / `NamespaceGraph` /
  `GraphEdge` types in codegraph — retained for backend use; retired only
  from frontend imports

## Data Flow

### Current (retired)

```
frontend/data/ontology.py
  → DesignRepository (raw Cypher via Neo4j session)
  → OntologyGraph / NamespaceGraph / CompoundGraph / GraphEdge
  → format_ontology_graph() (backend/graph/transforms.py)
  → Cytoscape {nodes, edges}
```

### New

```
frontend/data/ontology.py
  → GraphRepository.get_by_layer() / get_by_neighbourhood() / get_by_compound()
  → LayerGraph (CompositeEntry tree)
  → frontend/graph/format.py → layer_graph_to_cytoscape()
  → Cytoscape {nodes, edges}
```

`GraphRepository` uses neomodel's global connection — no Neo4j session
management needed in the frontend.

## Cytoscape Transform — `frontend/graph/format.py`

Core entry point:

```python
def layer_graph_to_cytoscape(graph: LayerGraph) -> dict:
    """Walk CompositeEntry tree → Cytoscape {nodes, edges}."""
    nodes = []
    edges = []
    seen_qnames = set()

    for entry in graph.entries.values():
        _walk_entry(entry, parent_id=None, nodes=nodes, edges=edges, seen=seen_qnames)

    return {"nodes": nodes, "edges": edges}
```

Walk logic:

```python
def _walk_entry(entry, parent_id, nodes, edges, seen):
    node = entry.node
    qname = node.qualified_name
    if qname in seen:
        return
    seen.add(qname)

    # Build Cytoscape node dict
    cy_node = _build_node(entry, parent_id=parent_id)
    nodes.append(cy_node)

    # Recurse into composed children (members, nested compounds, etc.)
    for type_key, children in entry.children.items():
        for child_key, child_entry in children.items():
            child_parent = qname if _is_namespace(node) else parent_id
            _walk_entry(child_entry, parent_id=child_parent, nodes=nodes, edges=edges, seen=seen)

    # Collect non-COMPOSES edges (references)
    for relation_type, target_key, target_type in entry.references:
        edges.append(_build_edge(qname, target_key, relation_type))
```

**Simplifications over current `format_ontology_graph()`:**

- One `_build_node()` handles all node types (no separate
  `_build_namespace_cytoscape_node` vs `_build_compound_cytoscape_node`)
- Namespace parent assignment comes from `CompositeEntry` tree structure
  (`parent_id` parameter), not from qualified-name heuristics like
  `_assign_component_parents` / `_assign_inferred_parents`
- Member collapsing is inherent in the tree walk: members appear as
  children of their compound in `CompositeEntry.children`, so the UML
  label is built directly
- Cross-layer edge tagging (`tag_cross_layer`) stays as a post-processing
  step over the Cytoscape dicts

**File structure:**

```
frontend/graph/
    __init__.py          # re-export layer_graph_to_cytoscape
    format.py            # main transform, _walk_entry, _build_node, _build_edge, filter helpers
    labels.py            # UML label builders (from backend/graph/transforms.py)
```

`labels.py` contains the ~200 lines of UML formatting logic:
`_build_uml_label()`, `_build_uml_html()`, kind/stereotype maps,
visibility prefixes, type-origin markers, and color constants.

## In-Memory Filtering

All filtering happens in Python after `GraphRepository.get_by_layer()`:

```python
def _filter_by_kind(graph: LayerGraph, kind: str):
    """Remove entries whose node.kind != kind. Prunes orphans."""

def _filter_by_search(graph: LayerGraph, text: str):
    """Keep entries where text appears in name or qualified_name.
    Preserves ancestor chain — if a member matches, its parent
    compound and grandparent namespace are kept."""

def _filter_by_component(graph: LayerGraph, component_id: int):
    """Keep entries whose node.component_id matches. Preserves ancestry."""
```

`_filter_by_search` must preserve the ancestor chain. If
`CalculatorWindow::handleEquals` matches, its parent
`CalculatorWindow` and grandparent `ui` namespace stay. The
`CompositeEntry` tree makes this natural — walk depth-first, keep any
entry with a matching descendant.

## Frontend Data Layer Changes

### `frontend/data/ontology.py`

**`fetch_ontology_graph_data()`** — was DesignRepository + Cypher:

```python
def fetch_ontology_graph_data(
    layer="design", kind_filter=None, search=None,
    component_id=None, source_filter=None,
    requirement_tags="hlr", include_dependencies=True,
):
    from codegraph.repository import GraphRepository
    from frontend.graph.format import layer_graph_to_cytoscape

    repo = GraphRepository()
    graph = repo.get_by_layer(layer)

    if kind_filter:
        _filter_by_kind(graph, kind_filter)
    if search:
        _filter_by_search(graph, search)
    if component_id:
        _filter_by_component(graph, component_id)

    formatted = layer_graph_to_cytoscape(graph)

    if not include_dependencies:
        formatted["nodes"], formatted["edges"] = filter_cross_layer_elements(
            formatted["nodes"], formatted["edges"]
        )
    if layer == "design" and requirement_tags != "none":
        enrich_with_requirement_tags(formatted["nodes"], mode=requirement_tags)

    return formatted
```

**`fetch_neighbourhood_graph_data()`** — was a separate DesignRepository method:

```python
def fetch_neighbourhood_graph_data(qualified_name: str) -> dict:
    from codegraph.repository import GraphRepository
    from frontend.graph.format import layer_graph_to_cytoscape

    repo = GraphRepository()
    graph = repo.get_by_neighbourhood(qualified_name)
    return layer_graph_to_cytoscape(graph)
```

**`fetch_graph_node_detail()`** — was ComplexGraph assembly:

```python
def fetch_graph_node_detail(qualified_name: str) -> dict | None:
    from codegraph.repository import GraphRepository

    repo = GraphRepository()
    graph = repo.get_by_compound(qualified_name)
    flat = graph._flat_index()
    entry = flat.get(qualified_name)
    if entry is None:
        return None

    node = entry.node
    # Build outgoing references from this entry
    outgoing = [
        {"rel": rel_type, "target_qn": target_key, "target_name": "", "target_labels": [target_type]}
        for rel_type, target_key, target_type in entry.references
    ]
    # Build incoming references by scanning other entries' references
    incoming = []
    for other_key, other_entry in flat.items():
        for rel_type, target_key, target_type in other_entry.references:
            if target_key == qualified_name:
                incoming.append({
                    "rel": rel_type,
                    "source_qn": other_key,
                    "source_name": "",
                    "source_labels": [type(other_entry.node).__name__.replace("Node", "")],
                })

    members = [
        dict(child.node.__properties__)
        for type_children in entry.children.values()
        for child in type_children.values()
    ]

    return {
        "properties": dict(node.__properties__),
        "outgoing": outgoing,
        "incoming": incoming,
        "implemented_by": [],
        "members": members,
        "codebase_members": [],
        "available_types": [],
    }
```

**`fetch_node_detail_full()`** — same as above plus TRACES_TO query for requirement tags (retained from current code).

**`fetch_ontology_data()`** — stats, was raw Cypher count queries:

```python
def fetch_ontology_data():
    from codegraph.repository import GraphRepository

    repo = GraphRepository()
    graph = repo.get_by_layer("design")

    kind_counts = {}
    total_nodes = 0
    total_references = 0
    nodes = []
    component_map = _get_component_map()

    for entry in graph._all_entries():
        node = entry.node
        total_nodes += 1
        kind = getattr(node, "kind", "unknown")
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
        total_references += len(entry.references)
        cid = getattr(node, "component_id", None)
        nodes.append({
            "name": node.name,
            "kind": kind,
            "qualified_name": node.qualified_name,
            "component": component_map.get(cid, "-") if cid else "-",
        })

    predicates = set()
    for rel_type, _, _ in entry.references:
        predicates.add(rel_type)

    return {
        "nodes": nodes,
        "kind_counts": kind_counts,
        "total_nodes": total_nodes,
        "total_triples": total_references,
        "total_predicates": len(predicates),
    }
```

### `frontend/data/dependencies.py`

**`fetch_design_dependency_links_data()`** — was DesignRepository + format_ontology_graph:

```python
def fetch_design_dependency_links_data(design_qnames: list[str]) -> dict:
    from codegraph.repository import GraphRepository
    from frontend.graph.format import layer_graph_to_cytoscape

    repo = GraphRepository()
    merged = None
    for qn in design_qnames:
        sub = repo.get_by_neighbourhood(qn)
        if merged is None:
            merged = sub
        else:
            merged_flat = merged._flat_index()
            sub_flat = sub._flat_index()
            for key, entry in sub_flat.items():
                if key not in merged_flat:
                    merged.entries[key] = entry

    if merged is None:
        return {"nodes": [], "edges": []}
    return layer_graph_to_cytoscape(merged)
```

## Files Retired or Modified

| File | Action |
|---|---|
| `frontend/graph/__init__.py` | **New.** Re-export `layer_graph_to_cytoscape` |
| `frontend/graph/format.py` | **New.** Main transform, walk, build, filter helpers |
| `frontend/graph/labels.py` | **New.** UML label builders moved from `backend/graph/transforms.py` |
| `frontend/data/ontology.py` | **Modified.** Replace all `DesignRepository` reads with `GraphRepository` calls |
| `frontend/data/dependencies.py` | **Modified.** Replace `DesignRepository` + `format_ontology_graph` with `GraphRepository` + `layer_graph_to_cytoscape` |
| `backend/graph/__init__.py` | **Modified.** Remove `format_ontology_graph` export (no longer called by frontend) |
| `backend/graph/transforms.py` | **Modified.** Remove `format_ontology_graph`, `_build_compound_cytoscape_node`, `_build_graph_edge`, `_build_namespace_cytoscape_node`, `_assign_component_parents`, `_assign_inferred_parents`. Keep `tag_cross_layer` (still used as post-processing). Keep label-building functions until `frontend/graph/labels.py` is complete, then remove. |

Types retained in codegraph (backend still uses them):

| Type | Reason kept |
|---|---|
| `OntologyGraph` | `DesignRepository.get_hlr_subgraph()` and backend agent pipeline |
| `CompoundGraph` | `DesignRepository.get_compound_graph()` and backend agent pipeline |
| `NamespaceGraph` | Used by `OntologyGraph` |
| `GraphEdge` | Used by `CompoundGraph` / `NamespaceGraph` |

## What Stays Unchanged

- `frontend/pages/*.py` — pages call the same data-layer functions (same return shape), no page-level changes
- `frontend/data/hlr.py` — `fetch_hlr_graph_data()` still uses `DesignRepository` (TRACES_TO)
- `frontend/data/ontology.py` — `update_member_type()` (write), `resolve_node_id_by_qualified_name()` (hash), `filter_cross_layer_elements()` (post-processing), `enrich_with_requirement_tags()` (post-processing)
- `codegraph/graph/__init__.py` — `LayerGraph`, `CompositeEntry` unchanged
- `codegraph/repository.py` — `GraphRepository` unchanged
- `DesignRepository` — kept for write operations, HLR subgraph, node detail fallback

## Performance

`GraphRepository.get_by_layer("design")` fetches all design-layer nodes in one
batch of neomodel queries. For a large graph (10k+ nodes), this is comparable
to the current Cypher approach (both fetch all matching nodes). In-memory
filtering is O(n) and fast. The main cost is the initial fetch, which is
dominated by network round-trips to Neo4j.