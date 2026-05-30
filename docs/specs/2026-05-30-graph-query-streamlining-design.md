# Graph Query Streamlining: Typed Graph Hierarchy & Repository-Centric Reads

**Date:** 2026-05-30
**Status:** Draft
**Author:** Daniel Newman

## Problem

The ontology graph page (`/ontology/graph`) renders empty because the "Design Intent" layer queries `:Design` nodes, which were removed during the graph primitives refactoring. Design-intent data now lives under `:Compound`/`:Member`/`:Namespace` with `layer: "design"`, but the read side was never updated.

Additionally, the read path is scattered across three layers of raw Cypher strings with no type safety — `queries/graph.py`, `queries/detail.py`, `queries/compounds.py`, and `frontend/data/*.py` all write inline Cypher. The repository (`DesignRepository`) already handles writes with typed models; reads should follow the same pattern.

## Goals

1. Fix the empty ontology graph by updating queries to use `:Compound|Member|Namespace` with `layer` filtering
2. Extend `DesignRepository` with typed graph read methods — it becomes the single Cypher entry point
3. Introduce typed graph containers (`CompoundGraph`, `NamespaceGraph`, `OntologyGraph`) that are self-contained (one query fills everything)
4. Remove all raw Cypher from `frontend/data/*.py` and `queries/*.py`
5. Drop `:Design` label, `IMPLEMENTED_BY` relationship, and `CONTAINS`→`COMPOSES` unification

## Design

### 1. Model Changes

#### 1a. MemberNode.kind — add "function"

`backend/db/neo4j/models/nodes/member.py`:

```python
kind: Literal["method", "attribute", "constant", "enum_value", "function"]
```

The Doxygen parser creates `kind="function"` for dependency-layer members (19,322 nodes). This must be a valid kind.

#### 1b. New: Typed Graph Containers

`backend/db/neo4j/models/graph.py`:

```python
@dataclass
class GraphEdge:
    """A directed relationship between two nodes in a subgraph."""
    source_qualified_name: str
    target_qualified_name: str
    predicate: str          # UPPERCASE Neo4j rel type
    mechanism: str = ""
    position: int | None = None
    name: str = ""
    display_name: str = ""

@dataclass
class CompoundGraph:
    """Self-contained payload for one CompoundNode.

    One Cypher query returns the node, all its members (via COMPOSES),
    nested classes (via COMPOSES), and all non-COMPOSES edges in/out.
    No secondary queries needed.
    """
    node: CompoundNode
    members: list[MemberNode]
    nested: list["CompoundGraph"]
    edges_out: list[GraphEdge]
    edges_in: list[GraphEdge]

@dataclass
class NamespaceGraph:
    """Self-contained payload for one NamespaceNode and everything inside it.

    Recursively descends one level. `compounds` includes classes, structs,
    interfaces, and enums owned by this namespace (via COMPOSES from
    Namespace→Compound).
    """
    node: NamespaceNode
    compounds: list[CompoundGraph]
    namespaces: list["NamespaceGraph"]

@dataclass
class OntologyGraph:
    """Top-level graph for the ontology visualization page.

    Contains all namespaces (with their compounds), unparented compounds
    (no owning namespace), and cross-cutting edges (between namespaces
    or between unparented compounds).
    """
    namespaces: list[NamespaceGraph]
    compounds: list[CompoundGraph]
    edges: list[GraphEdge]

    def to_raw(self) -> dict:
        """Flatten to raw dict shape consumed by format_cytoscape_graph().

        Returns {"nodes": [...], "edges": [...]} where each node/edge
        is a flat dict with Neo4j properties.
        """
        ...
```

### 2. Repository Methods

Extend `DesignRepository` in `backend/db/neo4j/repositories/design.py`:

```python
class DesignRepository:
    # --- Existing (unchanged) ---
    # merge_node, get_by_qualified_name, find_nodes, delete_node,
    # merge_triple, clear_design_graph, sync_implementation_status

    # --- New: graph queries ---
    def get_compound_graph(
        self, qualified_name: str, *, layer: str = "design"
    ) -> CompoundGraph | None: ...

    def get_namespace_graph(
        self, qualified_name: str, *, layer: str = "design"
    ) -> NamespaceGraph | None: ...

    def get_ontology_graph(
        self,
        *,
        layer: str = "design",
        kind_filter: str | None = None,
        search: str | None = None,
        component_id: int | None = None,
    ) -> OntologyGraph: ...

    def get_hlr_subgraph(
        self, hlr_id: int, component_id: int | None = None
    ) -> OntologyGraph: ...

    def get_neighbourhood_graph(
        self, qualified_name: str
    ) -> OntologyGraph: ...

    def get_graph_stats(self) -> dict: ...
```

**Label matching:** All Cypher uses a module-level `_DESIGN_NODE_LABELS = ["Compound", "Member", "Namespace"]` constant and a `_label_match(alias)` helper. The `:Design` label is removed from all queries.

**Example — `get_compound_graph` Cypher:**

```cypher
MATCH (c:Compound {qualified_name: $qn})
OPTIONAL MATCH (c)-[:COMPOSES]->(m:Member)
OPTIONAL MATCH (c)-[r_out]->(tgt)
  WHERE NOT tgt:Member AND type(r_out) <> 'COMPOSES'
OPTIONAL MATCH (src)-[r_in]->(c)
  WHERE NOT src:Member
OPTIONAL MATCH (c)-[:COMPOSES]->(nested:Compound)
RETURN c,
       collect(DISTINCT m) AS members,
       collect(DISTINCT {rel: type(r_out), target: tgt}) AS outs,
       collect(DISTINCT {rel: type(r_in), source: src}) AS ins,
       collect(DISTINCT nested) AS nested
```

Hydrates into one `CompoundGraph` — node, members, edges, nested classes. One round-trip.

### 3. File Changes

| File | Action |
|------|--------|
| `backend/db/neo4j/models/nodes/member.py` | Add `"function"` to `kind` Literal |
| `backend/db/neo4j/models/graph.py` | **New.** `GraphEdge`, `CompoundGraph`, `NamespaceGraph`, `OntologyGraph` |
| `backend/db/neo4j/repositories/design.py` | Add graph query methods; drop `:Design` from all Cypher; use `_label_match()` |
| `backend/db/neo4j/queries/graph.py` | **Deleted.** Migrated into repository |
| `backend/db/neo4j/queries/detail.py` | **Deleted.** Migrated into repository |
| `backend/db/neo4j/queries/compounds.py` | **Deleted.** Migrated into repository |
| `backend/db/neo4j/queries/__init__.py` | Updated to import and re-export new repository methods (backward compat shim for callers that import from `queries`) |
| `backend/design_data/repository.py` | Delegates raw fetches to `DesignRepository` |
| `backend/graph/__init__.py` | Calls `graph.to_raw()` instead of raw dicts |
| `backend/graph/transforms.py` | Remove `CONTAINS` from `_CONTAINMENT_RELS` |
| `frontend/data/ontology.py` | Calls `repo.get_ontology_graph().to_raw()`; no raw Cypher |
| `frontend/data/hlr.py` | Calls `repo.get_hlr_subgraph()` |
| `frontend/data/llr.py` | Update `:Design` references |
| `backend/requirements/services/graph_tags.py` | Update TRACES_TO query to match new labels |
| `backend/db/neo4j/connection.py` | Drop `:Design` constraints/indexes; add if missing for new labels |
| `backend/db/neo4j/sync.py` | Update to use repository's `clear_design_graph()` |
| `../Doxygen-Dependency-Parser/src/doxygen_index/neo4j_backend.py` | `CONTAINS` → `COMPOSES` |

### 4. What's Dropped

- **`:Design` Neo4j label** — removed from all label matching, constraints, and indexes
- **`IMPLEMENTED_BY` relationship type** — removed from all queries. Does not exist in the graph and had no model field
- **`CONTAINS` relationship type** — replaced by `COMPOSES` in the Doxygen parser; removed from `_CONTAINMENT_RELS` in transforms

### 5. What's Unchanged

- `format_cytoscape_graph()` pipeline
- `collapse_members()`, `assign_namespace_parents()`
- Frontend rendering (`widgets.py`, `theme.py`, `ontology_graph.py`)
- `KIND_COLORS`, `EDGE_COLORS` in `theme.py`
- Write path (`merge_node`, `merge_triple`, persistence layer)

### 6. Data Flow (After)

```
ontology_graph_page()
  → fetch_ontology_graph_data(layer="design")
    → DesignRepository.get_ontology_graph(layer="design")
      → Cypher: MATCH (c:Compound|Member|Namespace) WHERE layer="design"
      → Hydrates OntologyGraph (typed models)
    → graph.to_raw() → dicts
  → format_cytoscape_graph(raw) → Cytoscape elements
  → render_cytoscape_graph(elements)
```

## Migration Notes

1. Change `CONTAINS`→`COMPOSES` in the Doxygen parser, then re-ingest dependency data (order: change parser → re-ingest)
2. After re-ingestion, run `python scripts/01_flush_db.py --nuke-neo4j && python scripts/02_setup_project.py` to repopulate design-intent nodes under the new labels
3. The `sync.py` migration script that converts `:Design`→`:Compound|Member|Namespace` can be retired after this change
