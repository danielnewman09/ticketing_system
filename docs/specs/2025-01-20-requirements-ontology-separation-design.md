# Requirements-Ontology Graph Separation

**Date:** 2025-01-20  
**Status:** Approved  

## Problem

Requirements (HLRs, LLRs) currently leak onto the ontology graph as synthetic diamond-shaped nodes connected by `TRACES_TO` dashed edges. This violates the design intent that requirements should tag design metadata, not participate as graph topology.

Specific issues:

1. **`_attach_traced_requirements()`** in `backend/db/neo4j/queries/graph.py` manufactures synthetic HLR/LLR nodes at query time and injects them into Cytoscape output, crossing the SQLite/Neo4j boundary inside a Neo4j query function.
2. **Synthetic node IDs** like `"hlr:3"` break Cytoscape's namespace grouping and collapse logic (they have `qualified_name: ""`).
3. **`_detect_layer()`** in `detail.py` still checks for `HLR`/`LLR` Neo4j labels — dead code that signals an expectation that requirements belong in Neo4j.
4. **`fetch_node_detail()`** extracts requirements from Neo4j incoming relationships — also dead code since requirements are never synced to Neo4j.
5. **The association model** links requirements to *triples* (`high_level_requirements_triples`), which means finding which design nodes an HLR touches requires walking through triple endpoints — an indirect query.
6. **Theme/CSS** has dedicated `layer="requirement"` and `TRACES_TO` styling for nodes that shouldn't exist on the graph.

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Requirements on graph | Tags on design nodes, not separate nodes | Clean topological view; requirements are metadata, not entities |
| Association model | Direct node links + keep triple links (Option B) | Fast path for tagging; triple links preserved for traceability |
| Where tags appear | Cytoscape graph only, not sidebar | Cleaner separation; HLR subgraph highlights are sufficient |
| HLR subgraph scope | Direct nodes + 1-hop neighbourhood | Provides structural context without excessive expansion |
| Which requirement levels tag | HLRs only; LLRs don't appear | LLRs map to unit tests — a separate concern |
| Tag toggle | `requirement_tags="none" \| "hlr"` | User can toggle tags off for pure topology or on for traceability |
| Pipeline separation | Two-stage: bare Neo4j query → SQLite enrichment | Neo4j queries never import SQLAlchemy; clean testability |

## Architecture

### Data Model

Two new M2M association tables alongside the existing triple-based ones:

```python
high_level_requirements_nodes = Table(
    "high_level_requirements_nodes",
    Base.metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("highlevelrequirement_id", Integer,
           ForeignKey("high_level_requirements.id", ondelete="CASCADE"), nullable=False),
    Column("ontologynode_id", Integer,
           ForeignKey("ontology_nodes.id", ondelete="CASCADE"), nullable=False),
)

low_level_requirements_nodes = Table(
    "low_level_requirements_nodes",
    Base.metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("lowlevelrequirement_id", Integer,
           ForeignKey("low_level_requirements.id", ondelete="CASCADE"), nullable=False),
    Column("ontologynode_id", Integer,
           ForeignKey("ontology_nodes.id", ondelete="CASCADE"), nullable=False),
)
```

New relationships:

- `HighLevelRequirement.nodes` → `OntologyNode` (via `high_level_requirements_nodes`)
- `LowLevelRequirement.nodes` → `OntologyNode` (via `low_level_requirements_nodes`)
- `OntologyNode.high_level_requirements` → `HighLevelRequirement` (reverse)
- `OntologyNode.low_level_requirements` → `LowLevelRequirement` (reverse)

The existing `high_level_requirements_triples` and `low_level_requirements_triples` tables remain for traceability (recording *which relationship* satisfied a requirement).

### Pipeline: Two-Stage Graph Enrichment

**Stage 1 — Bare Neo4j query** (`backend/db/neo4j/queries/graph.py`):

Returns pure topology — design nodes, edges, no requirement data. No SQLAlchemy imports.

- `fetch_design_graph()`: returns `{"nodes": [...], "edges": [...]}` with no `TRACES_TO` edges or synthetic requirement nodes.
- `fetch_hlr_subgraph()`: uses SQLite M2M table to collect seed qualified names, then fetches seed nodes + 1-hop neighbourhood from Neo4j.

**Stage 2 — SQLite enrichment** (`backend/requirements/services/graph_tags.py`):

Pure SQLAlchemy lookup that tags design node dicts with requirement metadata.

```python
def enrich_with_requirement_tags(nodes: list[dict], mode: str = "none") -> list[dict]:
    """Tag design nodes with HLR badges from SQLite.
    mode: "none" = no tags, "hlr" = add HLR tags.
    Modifies nodes in-place.
    """
    if mode == "none":
        return nodes
    # Query HLR → node associations via M2M table
    # Each matching node gets: node["requirements"] = [{"id": 3, "type": "HLR", "description": "..."}, ...]

def tag_direct_nodes_only(nodes: list[dict], hlr_id: int) -> None:
    """Mark seed nodes in an HLR subgraph with is_hlr_highlight and requirements tag."""
    # Directly-linked nodes get: node["is_hlr_highlight"] = "true"
    # Plus the requirements tag for the specific HLR.
```

**Composition** (`frontend/data/ontology.py`):

```python
def fetch_ontology_graph_data(
    layer="design", ..., requirement_tags="hlr",
) -> dict:
    raw = fetch_design_graph(...)       # Stage 1: Neo4j
    formatted = format_cytoscape_graph(raw)
    if layer == "design" and requirement_tags != "none":
        enrich_with_requirement_tags(formatted["nodes"], mode=requirement_tags)  # Stage 2
    return formatted
```

### Design Persistence

In `persist_design()`, after triple links are saved, node links are derived from them:

```python
for link in design.requirement_links:
    triple = saved_triples[link.triple_index]
    req = ... # HLR or LLR
    for node in [triple.subject, triple.object]:
        if node not in req.nodes:
            req.nodes.append(node)
```

`DesignResult` gains `node_links_applied` and `node_links_skipped` counters.

### HLR Subgraph

`fetch_hlr_subgraph()` flow:

1. SQLite: collect seed qualified names from `hlr.nodes` (new M2M)
2. Neo4j: fetch seed Design nodes
3. Neo4j: fetch 1-hop Design edges (both outgoing and incoming, excluding `IMPLEMENTED_BY`)
4. Neo4j: fetch neighbour Design nodes for edges
5. Optional: expand to full component if `component_id` provided
6. Frontend: call `tag_direct_nodes_only()` to mark seeds with `is_hlr_highlight`

### Frontend Changes

**Cytoscape node badges:** After the graph renders, JavaScript adds badge text to node labels for nodes with `requirements` data. Nodes with `is_hlr_highlight` get an orange border.

```javascript
cy.nodes().forEach(node => {
    const reqs = node.data('requirements');
    if (reqs && reqs.length > 0) {
        node.data('label', node.data('name') + '\n' +
            reqs.map(r => `[${r.type} ${r.id}]`).join(' '));
        node.addClass('has-requirements');
    }
});
```

**Theme updates:**
- Remove: `node[layer="requirement"]` style block, `edge[label="TRACES_TO"]` style, `TRACES_TO` from `EDGE_COLORS`, `requirement`/`requirement_border` from `STATUS_COLORS`, `requirement` from `LAYER_STYLES`
- Add: `node[is_hlr_highlight="true"]` style (3px orange border), `node.has-requirements` style (slightly larger font)

**Graph page:** Add an "HLR Tags" toggle switch. Passes `requirement_tags="hlr"` or `"none"` to the data layer.

**HLR detail page:** Uses new `fetch_hlr_graph_data(hlr_id, component_id, requirement_tags="hlr")`. No HLR diamond node appears. Directly-linked design nodes highlighted with orange border.

**Node detail page:** Remove "Traced Requirements" card from the sidebar. Requirements are visible on the graph, not in the node detail panel.

### Neo4j Query Cleanup

- **Delete** `_attach_traced_requirements()` entirely (both the function and its two call sites)
- **Simplify** `_detect_layer()` to only check for `Design` and fallback, removing HLR/LLR label detection
- **Remove** the requirements extraction loop from `fetch_node_detail()` (incoming HLR/LLR label check)
- **Rewrite** `fetch_hlr_subgraph()` to use M2M seed qnames + 1-hop Neo4j expansion, no `_attach_traced_requirements` call

## Change Inventory

### Deleted code

| File | What |
|---|---|
| `backend/db/neo4j/queries/graph.py` | `_attach_traced_requirements()` function (~80 lines) |

### Modified files

| File | Changes |
|---|---|
| `backend/db/models/associations.py` | Add `high_level_requirements_nodes` and `low_level_requirements_nodes` tables |
| `backend/db/models/__init__.py` | Re-export new association tables |
| `backend/db/models/requirements.py` | Add `nodes` relationship on `HighLevelRequirement`, `LowLevelRequirement` |
| `backend/db/models/ontology.py` | Add `high_level_requirements` and `low_level_requirements` reverse relationships on `OntologyNode` |
| `backend/db/neo4j/queries/graph.py` | Remove `_attach_traced_requirements()` call; rewrite `fetch_hlr_subgraph()` |
| `backend/db/neo4j/queries/detail.py` | Remove HLR/LLR from `_detect_layer()`; remove requirements from `fetch_node_detail()` |
| `backend/graph/builders.py` | Update docstring; pass `requirements` and `is_hlr_highlight` through in `_build_design_node()` |
| `backend/requirements/services/persistence.py` | Add node-link derivation in `persist_design()`; extend `DesignResult` |
| `frontend/data/ontology.py` | 2-stage pipeline; add `requirement_tags` param; remove HLR/LLR from `fetch_graph_node_detail` |
| `frontend/data/hlr.py` | Update `fetch_hlr_detail()` if needed |
| `frontend/theme.py` | Remove requirement layer/edge styles; add highlight/badge styles |
| `frontend/pages/ontology_graph.py` | Add HLR tags toggle; add JavaScript badge rendering |
| `frontend/pages/hlr_detail.py` | Use new `fetch_hlr_graph_data()` |
| `frontend/pages/node_detail.py` | Remove "Traced Requirements" card |
| `frontend/widgets.py` | Update `GraphState` to include `show_requirement_tags` |

### New files

| File | Purpose |
|---|---|
| `backend/requirements/services/graph_tags.py` | `enrich_with_requirement_tags()` and `tag_direct_nodes_only()` |
| `scripts/backfill_requirement_nodes.py` | One-time migration to populate M2M from existing triple associations |
| `alembic/versions/xxxx_add_requirement_nodes_tables.py` | Alembic migration for the two new M2M tables |

## Migration Plan

1. Create Alembic migration for new M2M tables
2. Run `alembic upgrade head`
3. Run backfill script to populate from existing triple associations
4. Deploy code changes
5. Verify: HLR tags appear on graph, no diamond nodes, HLR subgraph works with highlight

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Backfill misses node-triple links | Script is idempotent; runs in a transaction; logs orphaned cases |
| Cytoscape badge rendering performs poorly on large graphs | Badge enrichment is O(HLRs × nodes_per_hlr); JavaScript class application is O(nodes) |
| 1-hop neighbourhood expansion on large components is slow | `fetch_hlr_subgraph()` already limits by component_id; add a node count cap if needed |
| Existing tests reference `_attach_traced_requirements` | Update tests to verify `enrich_with_requirement_tags` instead |
| `fetch_node_detail` removal breaks node detail page | Requirements were dead code (never in Neo4j); remove the panel from the page |