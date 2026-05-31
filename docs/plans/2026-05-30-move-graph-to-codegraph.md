# Move graph.py to codegraph library — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Relocate `GraphEdge`, `CompoundGraph`, `NamespaceGraph`, `OntologyGraph` from `backend/db/neo4j/models/graph.py` into `codegraph/graph/__init__.py` and update all imports.

**Architecture:** Pure file relocation with import path updates. The ticketing_system's node subclasses remain compatible since they inherit from codegraph base models.

**Tech Stack:** Python 3.12+, Pydantic, dataclasses

---

### Task 1: Move graph.py to codegraph and update imports

**Files:**
- Create: `/Users/danielnewman/dev/codegraph/src/codegraph/graph/__init__.py`
- Modify: `/Users/danielnewman/dev/codegraph/src/codegraph/__init__.py`
- Modify: `backend/graph/__init__.py`
- Modify: `backend/db/neo4j/repositories/design.py`
- Delete: `backend/db/neo4j/models/graph.py`

- [ ] **Step 1: Create `src/codegraph/graph/__init__.py` in the codegraph repo**

```python
"""Typed graph containers for the ontology visualization.

Each container is self-contained: one Cypher query fills all fields.
No secondary queries are needed to resolve members, edges, or nested objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from codegraph.nodes import CompoundNode, MemberNode, NamespaceNode


@dataclass
class GraphEdge:
    """A directed relationship between two nodes in a subgraph."""

    source_qualified_name: str
    target_qualified_name: str
    predicate: str  # UPPERCASE Neo4j rel type
    mechanism: str = ""
    position: int | None = None
    name: str = ""
    display_name: str = ""


@dataclass
class CompoundGraph:
    """Self-contained payload for one :Compound node."""

    node: CompoundNode
    members: list[MemberNode] = field(default_factory=list)
    nested: list[CompoundGraph] = field(default_factory=list)
    edges_out: list[GraphEdge] = field(default_factory=list)
    edges_in: list[GraphEdge] = field(default_factory=list)


@dataclass
class NamespaceGraph:
    """Self-contained payload for one :Namespace node and its contents."""

    node: NamespaceNode
    compounds: list[CompoundGraph] = field(default_factory=list)
    namespaces: list[NamespaceGraph] = field(default_factory=list)


@dataclass
class OntologyGraph:
    """Top-level graph for the ontology visualization page."""

    namespaces: list[NamespaceGraph] = field(default_factory=list)
    compounds: list[CompoundGraph] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)

    def to_raw(self) -> dict:
        """Flatten the typed hierarchy into the raw dict shape consumed by
        ``format_ontology_graph()``.
        """
        nodes: list[dict] = []
        edges: list[dict] = []
        seen_qns: set[str] = set()

        def _add_node(model) -> None:
            d = model.model_dump()
            qn = d.get("qualified_name", "")
            if qn and qn not in seen_qns:
                seen_qns.add(qn)
                nodes.append(d)

        def _add_edge(ge: GraphEdge) -> None:
            edges.append(
                {
                    "source": ge.source_qualified_name,
                    "target": ge.target_qualified_name,
                    "type": ge.predicate,
                    "mechanism": ge.mechanism,
                    "position": ge.position,
                    "name": ge.name,
                    "display_name": ge.display_name,
                }
            )

        def _walk_namespace(nsg: NamespaceGraph) -> None:
            _add_node(nsg.node)
            for cg in nsg.compounds:
                _walk_compound(cg)
            for child_ns in nsg.namespaces:
                _walk_namespace(child_ns)

        def _walk_compound(cg: CompoundGraph) -> None:
            _add_node(cg.node)
            for m in cg.members:
                _add_node(m)
            for nested in cg.nested:
                _walk_compound(nested)
            for ge in cg.edges_out:
                _add_edge(ge)
            for ge in cg.edges_in:
                _add_edge(ge)

        for nsg in self.namespaces:
            _walk_namespace(nsg)
        for cg in self.compounds:
            _walk_compound(cg)
        for ge in self.edges:
            _add_edge(ge)

        return {"nodes": nodes, "edges": edges}
```

- [ ] **Step 2: Add graph exports to `src/codegraph/__init__.py`**

Insert after the existing `from codegraph.edges import CodebaseEdge` line:

```python
from codegraph.graph import CompoundGraph, GraphEdge, NamespaceGraph, OntologyGraph
```

And add to `__all__`:

```python
    # Graph containers
    "CompoundGraph",
    "GraphEdge",
    "NamespaceGraph",
    "OntologyGraph",
```

- [ ] **Step 3: Verify codegraph imports resolve**

```bash
cd /Users/danielnewman/dev/codegraph && python -c "from codegraph.graph import GraphEdge, CompoundGraph, NamespaceGraph, OntologyGraph; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Update `backend/graph/__init__.py` import**

Change the TYPE_CHECKING import from:
```python
from backend.db.neo4j.models.graph import (
    CompoundGraph,
    GraphEdge,
    NamespaceGraph,
    OntologyGraph,
)
```
to:
```python
from codegraph.graph import (
    CompoundGraph,
    GraphEdge,
    NamespaceGraph,
    OntologyGraph,
)
```

Note: also remove the `if TYPE_CHECKING:` guard since these are dataclasses, not heavyweight imports — the existing `format_ontology_graph(ontograph: "OntologyGraph")` annotation can become `format_ontology_graph(ontograph: OntologyGraph)` with a direct import. Keep the `from __future__ import annotations` so forward refs work either way.

- [ ] **Step 5: Update `backend/db/neo4j/repositories/design.py` import**

Change:
```python
from backend.db.neo4j.models.graph import (
    CompoundGraph,
    GraphEdge,
    NamespaceGraph,
    OntologyGraph,
)
```
to:
```python
from codegraph.graph import (
    CompoundGraph,
    GraphEdge,
    NamespaceGraph,
    OntologyGraph,
)
```

- [ ] **Step 6: Delete old file**

```bash
rm backend/db/neo4j/models/graph.py
```

- [ ] **Step 7: Run tests**

```bash
cd /Users/danielnewman/dev/ticketing_system && python -m pytest tests/ -x -q
```

Expected: all tests pass

- [ ] **Step 8: Commit**

```bash
cd /Users/danielnewman/dev/ticketing_system && git add -A && git commit -m "refactor: move graph containers to codegraph.graph"
```

Also commit in codegraph repo:

```bash
cd /Users/danielnewman/dev/codegraph && git add -A && git commit -m "feat: add graph submodule with GraphEdge, CompoundGraph, NamespaceGraph, OntologyGraph"
```
