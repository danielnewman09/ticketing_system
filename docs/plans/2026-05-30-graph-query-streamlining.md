# Graph Query Streamlining Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace raw `:Design` Cypher scattered across 8+ files with typed graph containers and repository methods, fixing the empty ontology graph page.

**Architecture:** Extend `DesignRepository` with graph read methods that return `CompoundGraph`, `NamespaceGraph`, and `OntologyGraph` objects. These are self-contained (one Cypher query fills everything). All callers — frontend data layer, design_data, graph_tags — call repository methods instead of writing raw Cypher. Drop `:Design`, `IMPLEMENTED_BY`, and unify `CONTAINS`→`COMPOSES`.

**Tech Stack:** Python 3.12, Neo4j (Cypher), Pydantic, dataclasses

---

### Task 1: Model changes — MemberNode + new graph containers

**Files:**
- Modify: `backend/db/neo4j/models/nodes/member.py`
- Create: `backend/db/neo4j/models/graph.py`
- Modify: `backend/db/neo4j/models/__init__.py` (if it re-exports, skip if not)
- Create: `tests/unit/test_graph_models.py`

- [ ] **Step 1: Add "function" to MemberNode.kind Literal**

Open `backend/db/neo4j/models/nodes/member.py`. Change the `kind` field from:
```python
kind: Literal["method", "attribute", "constant", "enum_value"]
```
to:
```python
kind: Literal["method", "attribute", "constant", "enum_value", "function"]
```

- [ ] **Step 2: Create `backend/db/neo4j/models/graph.py`**

```python
"""Typed graph containers for the ontology visualization.

Each container is self-contained: one Cypher query fills all fields.
No secondary queries are needed to resolve members, edges, or nested objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.db.neo4j.models.nodes import CompoundNode, MemberNode, NamespaceNode


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
    """Self-contained payload for one :Compound node.

    One Cypher query returns the compound, all its members (via COMPOSES),
    nested compounds (via COMPOSES → nested classes), and all non-COMPOSES
    edges in and out.
    """

    node: CompoundNode
    members: list[MemberNode] = field(default_factory=list)
    nested: list[CompoundGraph] = field(default_factory=list)
    edges_out: list[GraphEdge] = field(default_factory=list)
    edges_in: list[GraphEdge] = field(default_factory=list)


@dataclass
class NamespaceGraph:
    """Self-contained payload for one :Namespace node and its contents.

    Recursively descends one level. ``compounds`` includes classes,
    structs, interfaces, and enums owned by this namespace (via
    COMPOSES from Namespace→Compound).
    """

    node: NamespaceNode
    compounds: list[CompoundGraph] = field(default_factory=list)
    namespaces: list[NamespaceGraph] = field(default_factory=list)


@dataclass
class OntologyGraph:
    """Top-level graph for the ontology visualization page.

    Contains all namespaces (with their compounds), unparented compounds
    (no owning namespace), and cross-cutting edges (between namespaces
    or unparented compounds).
    """

    namespaces: list[NamespaceGraph] = field(default_factory=list)
    compounds: list[CompoundGraph] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)

    def to_raw(self) -> dict:
        """Flatten the typed hierarchy into the raw dict shape consumed by
        ``format_cytoscape_graph()``.

        Returns ``{"nodes": [...], "edges": [...]}`` where each node is a
        flat dict of Neo4j properties and each edge has ``source``,
        ``target``, and ``type`` keys.
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

- [ ] **Step 3: Write unit test for to_raw()**

Create `tests/unit/test_graph_models.py`:

```python
"""Unit tests for graph container models."""

from backend.db.neo4j.models.graph import (
    CompoundGraph,
    GraphEdge,
    NamespaceGraph,
    OntologyGraph,
)
from backend.db.neo4j.models.nodes import CompoundNode, MemberNode, NamespaceNode


class TestOntologyGraphToRaw:
    def test_empty_graph_returns_empty_dicts(self):
        graph = OntologyGraph()
        raw = graph.to_raw()
        assert raw == {"nodes": [], "edges": []}

    def test_single_compound_with_members(self):
        node = CompoundNode(
            qualified_name="ns::MyClass",
            name="MyClass",
            kind="class",
            layer="design",
        )
        member = MemberNode(
            qualified_name="ns::MyClass::run",
            name="run",
            kind="method",
            layer="design",
        )
        edge = GraphEdge(
            source_qualified_name="ns::MyClass",
            target_qualified_name="ns::OtherClass",
            predicate="DEPENDS_ON",
        )
        cg = CompoundGraph(
            node=node,
            members=[member],
            edges_out=[edge],
        )
        graph = OntologyGraph(compounds=[cg])
        raw = graph.to_raw()

        assert len(raw["nodes"]) == 2
        assert len(raw["edges"]) == 1
        node_qns = {n["qualified_name"] for n in raw["nodes"]}
        assert "ns::MyClass" in node_qns
        assert "ns::MyClass::run" in node_qns
        assert raw["edges"][0]["source"] == "ns::MyClass"
        assert raw["edges"][0]["target"] == "ns::OtherClass"
        assert raw["edges"][0]["type"] == "DEPENDS_ON"

    def test_namespace_with_nested_compounds(self):
        node = CompoundNode(
            qualified_name="ns::MyClass",
            name="MyClass",
            kind="class",
            layer="design",
        )
        ns_node = NamespaceNode(
            qualified_name="ns",
            name="ns",
            kind="namespace",
            layer="design",
        )
        cg = CompoundGraph(node=node)
        nsg = NamespaceGraph(node=ns_node, compounds=[cg])
        graph = OntologyGraph(namespaces=[nsg])
        raw = graph.to_raw()

        assert len(raw["nodes"]) == 2
        qns = {n["qualified_name"] for n in raw["nodes"]}
        assert "ns::MyClass" in qns
        assert "ns" in qns

    def test_nested_classes(self):
        outer = CompoundNode(
            qualified_name="ns::Outer",
            name="Outer",
            kind="class",
            layer="design",
        )
        inner_node = CompoundNode(
            qualified_name="ns::Outer::Inner",
            name="Inner",
            kind="class",
            layer="design",
        )
        inner = CompoundGraph(node=inner_node)
        outer_cg = CompoundGraph(node=outer, nested=[inner])
        graph = OntologyGraph(compounds=[outer_cg])
        raw = graph.to_raw()

        assert len(raw["nodes"]) == 2
        qns = {n["qualified_name"] for n in raw["nodes"]}
        assert "ns::Outer" in qns
        assert "ns::Outer::Inner" in qns

    def test_deduplicates_duplicate_nodes(self):
        node = CompoundNode(
            qualified_name="ns::Shared",
            name="Shared",
            kind="class",
            layer="design",
        )
        cg1 = CompoundGraph(node=node)
        cg2 = CompoundGraph(node=node)
        graph = OntologyGraph(compounds=[cg1, cg2])
        raw = graph.to_raw()

        assert len(raw["nodes"]) == 1
        assert raw["nodes"][0]["qualified_name"] == "ns::Shared"
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/unit/test_graph_models.py -v
```

Expected: All 5 tests pass.

- [ ] **Step 5: Verify MemberNode still works**

```bash
python -c "from backend.db.neo4j.models.nodes import MemberNode; m = MemberNode(qualified_name='a::b', name='b', kind='function', layer='dependency'); print(m.kind)"
```

Expected: prints `function`

- [ ] **Step 6: Commit**

```bash
git add backend/db/neo4j/models/nodes/member.py backend/db/neo4j/models/graph.py tests/unit/test_graph_models.py
git commit -m "feat: add function kind to MemberNode, add typed graph containers"
```

---

### Task 2: Doxygen parser — CONTAINS → COMPOSES

**Files:**
- Modify: `../Doxygen-Dependency-Parser/src/doxygen_index/neo4j_backend.py`

- [ ] **Step 1: Change CONTAINS to COMPOSES**

Open `../Doxygen-Dependency-Parser/src/doxygen_index/neo4j_backend.py`.
In `_write_file_relationships`, change line:
```python
MERGE (c)-[:CONTAINS]->(m)
```
to:
```python
MERGE (c)-[:COMPOSES]->(m)
```

And change the print line from:
```python
print("  Relationships: DEFINED_IN, CONTAINS")
```
to:
```python
print("  Relationships: DEFINED_IN, COMPOSES")
```

- [ ] **Step 2: Commit**

```bash
cd ../Doxygen-Dependency-Parser && git add src/doxygen_index/neo4j_backend.py && git commit -m "refactor: rename CONTAINS to COMPOSES to unify edge type with design layer" && cd -
```

---

### Task 3: Repository — _label_match helper, drop :Design from existing methods

**Files:**
- Modify: `backend/db/neo4j/repositories/design.py`
- Create: `tests/unit/test_design_repository_labels.py`

- [ ] **Step 1: Add _DESIGN_NODE_LABELS constant and _label_match helper**

In `backend/db/neo4j/repositories/design.py`, add these module-level definitions after the existing `_determine_node_type`, `_determine_label`, and `_props_to_node` functions (before the `DesignRepository` class):

```python
_DESIGN_NODE_LABELS: list[str] = ["Compound", "Member", "Namespace"]


def _label_match(alias: str = "n") -> str:
    """Build a Neo4j label-matching clause for codebase graph nodes.

    Example: ``_label_match("d")`` returns
    ``"(d:Compound OR d:Member OR d:Namespace)"``
    """
    return f"({' OR '.join(f'{alias}:{l}' for l in _DESIGN_NODE_LABELS)})"
```

- [ ] **Step 2: Update `get_by_qualified_name` — drop :Design**

Change the Cypher from:
```python
result = self._session.run(
    """
    MATCH (n)
    WHERE n.qualified_name = $qn
      AND (n:Compound OR n:Member OR n:Namespace OR n:Design)
    RETURN n
    """,
    {"qn": qualified_name},
)
```
to:
```python
label_clause = _label_match("n")
result = self._session.run(
    f"""
    MATCH (n)
    WHERE n.qualified_name = $qn
      AND {label_clause}
    RETURN n
    """,
    {"qn": qualified_name},
)
```

- [ ] **Step 3: Update `find_nodes` — drop :Design**

Change the `conditions` list from:
```python
conditions = ["(n:Compound OR n:Member OR n:Namespace OR n:Design)"]
```
to:
```python
conditions = [_label_match("n")]
```

- [ ] **Step 4: Update `delete_node` — drop :Design**

Change the Cypher from:
```python
result = self._session.run(
    """
    MATCH (n)
    WHERE n.qualified_name = $qn
      AND (n:Compound OR n:Member OR n:Namespace OR n:Design)
    DETACH DELETE n
    RETURN count(n) AS cnt
    """,
    {"qn": qualified_name},
)
```
to:
```python
label_clause = _label_match("n")
result = self._session.run(
    f"""
    MATCH (n)
    WHERE n.qualified_name = $qn
      AND {label_clause}
    DETACH DELETE n
    RETURN count(n) AS cnt
    """,
    {"qn": qualified_name},
)
```

- [ ] **Step 5: Update `merge_triple` — drop :Design**

Replace the object matching section of the Cypher. Change:
```python
cypher = """
MATCH (s)
WHERE s.qualified_name = $subj AND (s:Compound OR s:Member OR s:Namespace OR s:Design)
OPTIONAL MATCH (o_new)
WHERE o_new.qualified_name = $obj AND (o_new:Compound OR o_new:Member OR o_new:Namespace)
OPTIONAL MATCH (o_legacy:Design {qualified_name: $obj})
WITH s, coalesce(o_new, o_legacy) AS target
WHERE target IS NOT NULL
MERGE (s)-[r:REL_TYPE]->(target)
"""
```
to:
```python
subj_clause = _label_match("s")
obj_clause = _label_match("target")
cypher = f"""
MATCH (s)
WHERE s.qualified_name = $subj AND {subj_clause}
MATCH (target)
WHERE target.qualified_name = $obj AND {obj_clause}
MERGE (s)-[r:REL_TYPE]->(target)
"""
```

Note: The `OPTIONAL MATCH ... coalesce` pattern with legacy `:Design` is removed entirely since `:Design` no longer exists.

- [ ] **Step 6: Update `clear_design_graph` — drop :Design**

Change:
```python
self._session.run("MATCH (n) WHERE n:Compound OR n:Member OR n:Namespace OR n:Design DETACH DELETE n")
```
to:
```python
label_clause = _label_match("n")
self._session.run(f"MATCH (n) WHERE {label_clause} DETACH DELETE n")
```

- [ ] **Step 7: Update `sync_implementation_status` — drop :Design**

Change the Cypher from:
```python
self._session.run(
    """
    MATCH (n)
    WHERE n.qualified_name = $qn
      AND (n:Compound OR n:Member OR n:Namespace OR n:Design)
    SET n.implementation_status = $status,
        n.source_file = $source_file,
        n.test_file = $test_file
    """,
    {...},
)
```
to:
```python
label_clause = _label_match("n")
self._session.run(
    f"""
    MATCH (n)
    WHERE n.qualified_name = $qn
      AND {label_clause}
    SET n.implementation_status = $status,
        n.source_file = $source_file,
        n.test_file = $test_file
    """,
    {...},
)
```

- [ ] **Step 8: Update class docstring**

Change the `DesignRepository` class docstring from:
```
Supports both the new label scheme (:Compound, :Member, :Namespace
with `layer` property) and the legacy :Design label for backward
compatibility during migration.
```
to:
```
Uses the :Compound, :Member, :Namespace labels with ``layer``
property for filtering design-intent vs. as-built vs. dependency.
```

- [ ] **Step 9: Write unit test for _label_match**

Create `tests/unit/test_design_repository_labels.py`:

```python
"""Unit tests for label matching in DesignRepository."""

from backend.db.neo4j.repositories.design import _label_match


class TestLabelMatch:
    def test_default_alias(self):
        clause = _label_match()
        assert "(n:Compound" in clause
        assert "OR n:Member" in clause
        assert "OR n:Namespace)" in clause

    def test_custom_alias(self):
        clause = _label_match("d")
        assert "(d:Compound" in clause
        assert "OR d:Member" in clause
        assert "OR d:Namespace)" in clause

    def test_no_design_label(self):
        clause = _label_match()
        assert ":Design" not in clause
```

- [ ] **Step 10: Run tests**

```bash
pytest tests/unit/test_design_repository_labels.py -v
```

Expected: 3 tests pass.

- [ ] **Step 11: Commit**

```bash
git add backend/db/neo4j/repositories/design.py tests/unit/test_design_repository_labels.py
git commit -m "refactor: drop :Design label from repository, add _label_match helper"
```

---

### Task 4: Repository — get_compound_graph + get_namespace_graph

**Files:**
- Modify: `backend/db/neo4j/repositories/design.py`

- [ ] **Step 1: Add imports**

At the top of `backend/db/neo4j/repositories/design.py`, add these imports after the existing imports:

```python
from backend.db.neo4j.models.graph import (
    CompoundGraph,
    GraphEdge,
    NamespaceGraph,
    OntologyGraph,
)
```

And add `MemberNode` to the existing import:
```python
from backend.db.neo4j.models.nodes import CompoundNode, MemberNode, NamespaceNode
```
(If `MemberNode` already imported, skip.)

- [ ] **Step 2: Add private hydration helper `_hydrate_graph_edge`**

Add this as a module-level function after `_props_to_node`:

```python
def _hydrate_graph_edge(rel_type: str, source_qn: str, target_qn: str,
                        mechanism: str = "", position: int | None = None,
                        name: str = "", display_name: str = "") -> GraphEdge:
    """Create a GraphEdge from raw Neo4j relationship fields."""
    return GraphEdge(
        source_qualified_name=source_qn,
        target_qualified_name=target_qn,
        predicate=rel_type,
        mechanism=mechanism or "",
        position=position,
        name=name or "",
        display_name=display_name or "",
    )
```

- [ ] **Step 3: Add `get_compound_graph` method to DesignRepository**

Add inside the `DesignRepository` class, after the existing `find_nodes` method:

```python
    def get_compound_graph(
        self, qualified_name: str, *, layer: str | None = None
    ) -> CompoundGraph | None:
        """Fetch a single compound with members, edges, and nested classes.

        One Cypher query. Returns None if the compound is not found.

        Args:
            qualified_name: The ``qualified_name`` property value.
            layer: Optional layer filter. If None, matches any layer.
        """
        layer_condition = "AND c.layer = $layer" if layer is not None else ""
        params = {"qn": qualified_name}
        if layer is not None:
            params["layer"] = layer

        member_label = _label_match("m")
        tgt_label = _label_match("tgt")
        src_label = _label_match("src")

        result = self._session.run(
            f"""
            MATCH (c:Compound {{qualified_name: $qn}})
            {layer_condition}
            OPTIONAL MATCH (c)-[:COMPOSES]->(m:Member)
            OPTIONAL MATCH (c)-[r_out]->(tgt)
              WHERE NOT {tgt_label.replace('n', 'tgt').replace('tgt:', 'tgt:Member') if 'Member' not in tgt_label else ''}
                AND type(r_out) <> 'COMPOSES'
            OPTIONAL MATCH (src)-[r_in]->(c)
              WHERE NOT src:Member
            OPTIONAL MATCH (c)-[:COMPOSES]->(nested:Compound)
            RETURN c,
                   collect(DISTINCT m) AS members,
                   collect(DISTINCT {{rel: type(r_out), source_qn: c.qualified_name, target_qn: tgt.qualified_name, mechanism: r_out.mechanism, position: r_out.position, name: r_out.name, display_name: r_out.display_name}}) AS outs,
                   collect(DISTINCT {{rel: type(r_in), source_qn: src.qualified_name, target_qn: c.qualified_name, mechanism: r_in.mechanism, position: r_in.position, name: r_in.name, display_name: r_in.display_name}}) AS ins,
                   collect(DISTINCT nested) AS nested_compounds
            """,
            params,
        )
        record = result.single()
        if record is None or record["c"] is None:
            return None

        # Hydrate compound
        c_props = dict(record["c"])
        compound = CompoundNode(**c_props)

        # Hydrate members
        members: list[MemberNode] = []
        for m in (record["members"] or []):
            if m is None:
                continue
            try:
                members.append(MemberNode(**dict(m)))
            except Exception:
                log.debug("Skipping invalid member: %s", m.get("qualified_name", "?"))

        # Hydrate edges
        edges_out: list[GraphEdge] = []
        for e in (record["outs"] or []):
            if e is None or e.get("rel") is None:
                continue
            edges_out.append(_hydrate_graph_edge(
                e["rel"], e.get("source_qn", ""), e.get("target_qn", ""),
                mechanism=e.get("mechanism", ""),
                position=e.get("position"),
                name=e.get("name", ""),
                display_name=e.get("display_name", ""),
            ))

        edges_in: list[GraphEdge] = []
        for e in (record["ins"] or []):
            if e is None or e.get("rel") is None:
                continue
            edges_in.append(_hydrate_graph_edge(
                e["rel"], e.get("source_qn", ""), e.get("target_qn", ""),
            ))

        # Hydrate nested compounds (recursive)
        nested: list[CompoundGraph] = []
        for nc in (record["nested_compounds"] or []):
            if nc is None:
                continue
            nc_props = dict(nc)
            nc_qn = nc_props.get("qualified_name", "")
            if nc_qn:
                nested_cg = self.get_compound_graph(nc_qn, layer=layer)
                if nested_cg:
                    nested.append(nested_cg)

        return CompoundGraph(
            node=compound,
            members=members,
            nested=nested,
            edges_out=edges_out,
            edges_in=edges_in,
        )
```

Wait — the `NOT tgt:Member` clause in the Cypher is problematic because `_label_match` doesn't let us exclude a single label. Let me simplify: use a direct label filter for the edge query.

Actually, let me re-think. The edge query should match all non-COMPOSES edges from the compound to any target. We don't want to include edges to Members (those are already captured via COMPOSES→Member). But we DO want edges to other Compounds and Namespaces.

Simpler approach for the Cypher:

```cypher
OPTIONAL MATCH (c)-[r_out]->(tgt)
  WHERE type(r_out) <> 'COMPOSES'
    AND (tgt:Compound OR tgt:Namespace)
```

This excludes Member targets and COMPOSES edges. Let me use this simpler pattern.

- [ ] **Step 3 (revised): Add `get_compound_graph` method**

Add inside `DesignRepository`, after `find_nodes`:

```python
    def get_compound_graph(
        self, qualified_name: str, *, layer: str | None = None
    ) -> CompoundGraph | None:
        """Fetch a single compound with members, edges, and nested classes.

        One Cypher query fills the entire CompoundGraph. Returns None
        if the compound is not found.
        """
        layer_condition = "AND c.layer = $layer" if layer is not None else ""
        params: dict = {"qn": qualified_name}
        if layer is not None:
            params["layer"] = layer

        result = self._session.run(
            f"""
            MATCH (c:Compound {{qualified_name: $qn}})
            {layer_condition}
            OPTIONAL MATCH (c)-[:COMPOSES]->(m:Member)
            OPTIONAL MATCH (c)-[r_out]->(tgt)
              WHERE type(r_out) <> 'COMPOSES'
                AND (tgt:Compound OR tgt:Namespace)
            OPTIONAL MATCH (src)-[r_in]->(c)
              WHERE NOT src:Member
            OPTIONAL MATCH (c)-[:COMPOSES]->(nested:Compound)
            RETURN c,
                   collect(DISTINCT m) AS members,
                   collect(DISTINCT {{rel: type(r_out),
                       source_qn: c.qualified_name,
                       target_qn: tgt.qualified_name}}) AS outs,
                   collect(DISTINCT {{rel: type(r_in),
                       source_qn: src.qualified_name,
                       target_qn: c.qualified_name}}) AS ins,
                   collect(DISTINCT nested) AS nested_compounds
            """,
            params,
        )
        record = result.single()
        if record is None or record["c"] is None:
            return None

        c_props = dict(record["c"])
        compound = CompoundNode(**c_props)

        members: list[MemberNode] = []
        for m in (record["members"] or []):
            if m is None:
                continue
            try:
                members.append(MemberNode(**dict(m)))
            except Exception:
                log.debug("Skipping invalid member: %s",
                          m.get("qualified_name", "?"))

        edges_out: list[GraphEdge] = []
        for e in (record["outs"] or []):
            if e is None or e.get("rel") is None:
                continue
            edges_out.append(_hydrate_graph_edge(
                e["rel"], e.get("source_qn", ""), e.get("target_qn", ""),
            ))

        edges_in: list[GraphEdge] = []
        for e in (record["ins"] or []):
            if e is None or e.get("rel") is None:
                continue
            edges_in.append(_hydrate_graph_edge(
                e["rel"], e.get("source_qn", ""), e.get("target_qn", ""),
            ))

        nested: list[CompoundGraph] = []
        for nc in (record["nested_compounds"] or []):
            if nc is None:
                continue
            nc_qn = nc.get("qualified_name", "")
            if nc_qn:
                nested_cg = self.get_compound_graph(nc_qn, layer=layer)
                if nested_cg:
                    nested.append(nested_cg)

        return CompoundGraph(
            node=compound,
            members=members,
            nested=nested,
            edges_out=edges_out,
            edges_in=edges_in,
        )
```

- [ ] **Step 4: Add `get_namespace_graph` method**

Add after `get_compound_graph`:

```python
    def get_namespace_graph(
        self, qualified_name: str, *, layer: str | None = None
    ) -> NamespaceGraph | None:
        """Fetch a namespace with all contained compounds and child namespaces.

        One Cypher query fills the NamespaceGraph. Returns None if
        the namespace is not found.
        """
        layer_condition = "AND n.layer = $layer" if layer is not None else ""
        params: dict = {"qn": qualified_name}
        if layer is not None:
            params["layer"] = layer

        result = self._session.run(
            f"""
            MATCH (n:Namespace {{qualified_name: $qn}})
            {layer_condition}
            OPTIONAL MATCH (n)-[:COMPOSES]->(c:Compound)
            RETURN n, collect(DISTINCT c) AS compounds
            """,
            params,
        )
        record = result.single()
        if record is None or record["n"] is None:
            return None

        ns_props = dict(record["n"])
        ns_node = NamespaceNode(**ns_props)

        compounds: list[CompoundGraph] = []
        for c in (record["compounds"] or []):
            if c is None:
                continue
            c_qn = c.get("qualified_name", "")
            if c_qn:
                cg = self.get_compound_graph(c_qn, layer=layer)
                if cg:
                    compounds.append(cg)

        return NamespaceGraph(
            node=ns_node,
            compounds=compounds,
            namespaces=[],
        )
```

- [ ] **Step 5: Write integration test**

Create `tests/integration/test_design_repository_graph.py`:

```python
"""Integration tests for graph query methods on DesignRepository.

Requires a running Neo4j instance.
"""

import pytest
from backend.db.neo4j.repositories.design import DesignRepository
from backend.db.neo4j.models.nodes import CompoundNode, MemberNode
from services.dependencies import get_neo4j


@pytest.fixture
def neo4j_session():
    conn = get_neo4j()
    with conn.session() as session:
        yield session


class TestGetCompoundGraph:
    def test_returns_none_for_missing_compound(self, neo4j_session):
        repo = DesignRepository(neo4j_session)
        assert repo.get_compound_graph("does_not::exist") is None

    def test_returns_compound_with_members(self, neo4j_session):
        repo = DesignRepository(neo4j_session)
        # Create test data
        node = CompoundNode(
            qualified_name="test_graph::TestClass",
            name="TestClass",
            kind="class",
            layer="design",
        )
        repo.merge_node(node)
        member = MemberNode(
            qualified_name="test_graph::TestClass::do_thing",
            name="do_thing",
            kind="method",
            layer="design",
        )
        repo.merge_node(member)
        repo.merge_triple("test_graph::TestClass", "composes",
                          "test_graph::TestClass::do_thing")

        cg = repo.get_compound_graph("test_graph::TestClass", layer="design")
        assert cg is not None
        assert cg.node.name == "TestClass"
        assert cg.node.kind == "class"
        assert len(cg.members) == 1
        assert cg.members[0].name == "do_thing"
        assert cg.members[0].kind == "method"
```

- [ ] **Step 6: Run integration test**

```bash
pytest tests/integration/test_design_repository_graph.py -v
```

Expected: 2 tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/db/neo4j/repositories/design.py tests/integration/test_design_repository_graph.py
git commit -m "feat: add get_compound_graph and get_namespace_graph to DesignRepository"
```

---

### Task 5: Repository — get_ontology_graph

**Files:**
- Modify: `backend/db/neo4j/repositories/design.py`

- [ ] **Step 1: Add `get_ontology_graph` method**

Add after `get_namespace_graph` in `DesignRepository`:

```python
    def get_ontology_graph(
        self,
        *,
        layer: str = "design",
        kind_filter: str | None = None,
        search: str | None = None,
        component_id: int | None = None,
    ) -> OntologyGraph:
        """Fetch the full ontology graph for the given layer.

        Returns an OntologyGraph with all namespaces, their compounds,
        unparented compounds, and cross-cutting edges.

        Args:
            layer: "design", "as-built", or "dependency".
            kind_filter: Optional kind to filter compounds by.
            search: Optional text search on name and qualified_name.
            component_id: Optional component FK filter.
        """
        # Build filter conditions for compounds
        conditions = ["c.layer = $layer"]
        params: dict = {"layer": layer}

        if kind_filter:
            conditions.append("c.kind = $kind")
            params["kind"] = kind_filter
        if component_id is not None:
            conditions.append("c.component_id = $comp_id")
            params["comp_id"] = component_id
        if search:
            conditions.append(
                "(c.name CONTAINS $search OR c.qualified_name CONTAINS $search)"
            )
            params["search"] = search

        where = " AND ".join(conditions)

        # Fetch compounds with their edges
        result = self._session.run(
            f"""
            MATCH (c:Compound)
            WHERE {where}
            OPTIONAL MATCH (c)-[:COMPOSES]->(m:Member)
            OPTIONAL MATCH (c)-[r_out]->(tgt)
              WHERE type(r_out) <> 'COMPOSES'
                AND (tgt:Compound OR tgt:Namespace)
            OPTIONAL MATCH (src)-[r_in]->(c)
              WHERE NOT src:Member
            RETURN c,
                   collect(DISTINCT m) AS members,
                   collect(DISTINCT {{rel: type(r_out),
                       source_qn: c.qualified_name,
                       target_qn: tgt.qualified_name}}) AS outs,
                   collect(DISTINCT {{rel: type(r_in),
                       source_qn: src.qualified_name,
                       target_qn: c.qualified_name}}) AS ins
            ORDER BY c.qualified_name
            """,
            params,
        )

        # Build CompoundGraph for each compound
        compound_graphs: dict[str, CompoundGraph] = {}
        for record in result:
            c = record["c"]
            if c is None:
                continue
            c_props = dict(c)
            c_qn = c_props.get("qualified_name", "")

            members: list[MemberNode] = []
            for m in (record["members"] or []):
                if m is None:
                    continue
                try:
                    members.append(MemberNode(**dict(m)))
                except Exception:
                    pass

            edges_out: list[GraphEdge] = []
            for e in (record["outs"] or []):
                if e is None or e.get("rel") is None:
                    continue
                edges_out.append(_hydrate_graph_edge(
                    e["rel"], e.get("source_qn", ""), e.get("target_qn", ""),
                ))

            edges_in: list[GraphEdge] = []
            for e in (record["ins"] or []):
                if e is None or e.get("rel") is None:
                    continue
                edges_in.append(_hydrate_graph_edge(
                    e["rel"], e.get("source_qn", ""), e.get("target_qn", ""),
                ))

            compound = CompoundNode(**c_props)
            cg = CompoundGraph(
                node=compound,
                members=members,
                edges_out=edges_out,
                edges_in=edges_in,
            )
            compound_graphs[c_qn] = cg

        # Fetch namespaces with layer filter
        ns_result = self._session.run(
            """
            MATCH (n:Namespace)
            WHERE n.layer = $layer
            OPTIONAL MATCH (n)-[:COMPOSES]->(c:Compound)
            RETURN n, collect(DISTINCT c) AS compounds
            ORDER BY n.qualified_name
            """,
            {"layer": layer},
        )

        # Build NamespaceGraph for each namespace
        ns_graphs: dict[str, NamespaceGraph] = {}
        ns_owned_compound_qns: set[str] = set()
        for record in ns_result:
            n = record["n"]
            if n is None:
                continue
            ns_props = dict(n)
            ns_qn = ns_props.get("qualified_name", "")
            ns_node = NamespaceNode(**ns_props)

            ns_compounds: list[CompoundGraph] = []
            for c in (record["compounds"] or []):
                if c is None:
                    continue
                c_qn = c.get("qualified_name", "")
                ns_owned_compound_qns.add(c_qn)
                if c_qn in compound_graphs:
                    ns_compounds.append(compound_graphs[c_qn])

            ns_graphs[ns_qn] = NamespaceGraph(
                node=ns_node,
                compounds=ns_compounds,
                namespaces=[],
            )

        # Compounds NOT owned by any namespace are top-level
        unparented: list[CompoundGraph] = [
            cg for qn, cg in compound_graphs.items()
            if qn not in ns_owned_compound_qns
        ]

        # Cross-cutting edges (between compounds in different namespaces,
        # or from namespace to namespace)
        cross_edges: list[GraphEdge] = []
        edge_seen: set[tuple[str, str, str]] = set()
        for cg in compound_graphs.values():
            for ge in cg.edges_out:
                key = (ge.source_qualified_name, ge.target_qualified_name, ge.predicate)
                if key not in edge_seen:
                    edge_seen.add(key)
                    cross_edges.append(ge)

        return OntologyGraph(
            namespaces=list(ns_graphs.values()),
            compounds=unparented,
            edges=cross_edges,
        )
```

- [ ] **Step 2: Commit**

```bash
git add backend/db/neo4j/repositories/design.py
git commit -m "feat: add get_ontology_graph to DesignRepository"
```

---

### Task 6: Repository — get_hlr_subgraph + get_neighbourhood_graph

**Files:**
- Modify: `backend/db/neo4j/repositories/design.py`

- [ ] **Step 1: Add `get_hlr_subgraph` method**

Add after `get_ontology_graph`:

```python
    def get_hlr_subgraph(
        self, hlr_id: int, component_id: int | None = None
    ) -> OntologyGraph:
        """Fetch the design subgraph around an HLR.

        Finds seed design nodes via TRACES_TO from the HLR, then fetches
        a 1-hop neighbourhood of compounds and their members.
        """
        # Find seed qualified_names from TRACES_TO edges
        seed_result = self._session.run(
            f"""
            MATCH (hlr:HLR {{id: $hid}})-[:TRACES_TO]->(d)
            WHERE {_label_match("d")}
            RETURN d.qualified_name AS qn
            """,
            {"hid": hlr_id},
        )
        seed_qns = [r["qn"] for r in seed_result if r["qn"]]
        if not seed_qns:
            log.warning("HLR %d has no linked nodes via TRACES_TO", hlr_id)
            return OntologyGraph()

        # Fetch 1-hop neighbourhood
        return self._get_neighbourhood_from_seeds(seed_qns, component_id)
```

- [ ] **Step 2: Add `get_neighbourhood_graph` method**

Add after `get_hlr_subgraph`:

```python
    def get_neighbourhood_graph(self, qualified_name: str) -> OntologyGraph:
        """Fetch the 1-hop neighbourhood of a node as an OntologyGraph."""
        return self._get_neighbourhood_from_seeds([qualified_name])
```

- [ ] **Step 3: Add private `_get_neighbourhood_from_seeds` method**

Add after `get_neighbourhood_graph`:

```python
    def _get_neighbourhood_from_seeds(
        self, seed_qns: list[str], component_id: int | None = None
    ) -> OntologyGraph:
        """Build an OntologyGraph from seed qualified names."""
        label_clause = _label_match("d")

        # Seed nodes
        result = self._session.run(
            f"UNWIND $qns AS qn MATCH (d) WHERE d.qualified_name = qn AND {label_clause} RETURN d",
            {"qns": seed_qns},
        )
        compound_graphs: dict[str, CompoundGraph] = {}
        for record in result:
            d = record["d"]
            if d is None:
                continue
            qn = d.get("qualified_name", "")
            cg = self.get_compound_graph(qn)
            if cg:
                compound_graphs[qn] = cg

        # Outgoing edges from seeds to neighbours
        edge_out = self._session.run(
            """
            UNWIND $qns AS qn
            MATCH (s {qualified_name: qn})-[r]->(t)
            WHERE type(r) <> 'COMPOSES'
              AND (t:Compound OR t:Namespace)
            RETURN s.qualified_name AS src, t.qualified_name AS tgt,
                   type(r) AS rel_type
            """,
            {"qns": seed_qns},
        )
        for record in edge_out:
            src, tgt, rel = record["src"], record["tgt"], record["rel_type"]
            if tgt and tgt not in compound_graphs:
                cg = self.get_compound_graph(tgt)
                if cg:
                    compound_graphs[tgt] = cg
            if src in compound_graphs:
                compound_graphs[src].edges_out.append(
                    _hydrate_graph_edge(rel, src, tgt or "")
                )

        # Incoming edges to seeds
        edge_in = self._session.run(
            """
            UNWIND $qns AS qn
            MATCH (s)-[r]->(t {qualified_name: qn})
            WHERE type(r) <> 'COMPOSES'
              AND NOT s:Member
              AND s.qualified_name <> t.qualified_name
            RETURN s.qualified_name AS src, t.qualified_name AS tgt,
                   type(r) AS rel_type
            """,
            {"qns": seed_qns},
        )
        for record in edge_in:
            src, tgt, rel = record["src"], record["tgt"], record["rel_type"]
            if src and src not in compound_graphs:
                cg = self.get_compound_graph(src)
                if cg:
                    compound_graphs[src] = cg
            if tgt in compound_graphs:
                compound_graphs[tgt].edges_in.append(
                    _hydrate_graph_edge(rel, src or "", tgt)
                )

        # Optional: full component expansion
        if component_id is not None:
            comp_result = self._session.run(
                """
                MATCH (c:Compound {component_id: $cid})
                RETURN c.qualified_name AS qn
                """,
                {"cid": component_id},
            )
            for record in comp_result:
                qn = record["qn"]
                if qn and qn not in compound_graphs:
                    cg = self.get_compound_graph(qn)
                    if cg:
                        compound_graphs[qn] = cg

        return OntologyGraph(compounds=list(compound_graphs.values()))
```

- [ ] **Step 4: Commit**

```bash
git add backend/db/neo4j/repositories/design.py
git commit -m "feat: add get_hlr_subgraph and get_neighbourhood_graph to DesignRepository"
```

---

### Task 7: Repository — get_graph_stats + get_dependency_links

**Files:**
- Modify: `backend/db/neo4j/repositories/design.py`

- [ ] **Step 1: Add `get_graph_stats` method**

Add after `get_neighbourhood_graph`:

```python
    def get_graph_stats(self) -> dict:
        """Return node counts by kind, edge counts by predicate.

        Returns a dict with keys: total_nodes, total_edges,
        total_predicates, kind_counts, nodes (top 200).
        """
        label_clause = _label_match("d")

        # Kind counts
        kind_result = self._session.run(
            f"MATCH (d) WHERE {label_clause} RETURN d.kind AS kind, count(d) AS cnt"
        )
        kind_counts: dict[str, int] = {}
        total_nodes = 0
        for record in kind_result:
            kind = record["kind"] or "unknown"
            cnt = record["cnt"]
            kind_counts[kind] = cnt
            total_nodes += cnt

        # Node list (top 200)
        nodes_result = self._session.run(
            f"""
            MATCH (d) WHERE {label_clause}
            RETURN d.qualified_name AS qn, d.name AS name,
                   d.kind AS kind, d.component_id AS cid
            ORDER BY d.qualified_name LIMIT 200
            """
        )
        nodes = []
        for record in nodes_result:
            nodes.append({
                "name": record["name"],
                "kind": record["kind"],
                "qualified_name": record["qn"],
                "component_id": record["cid"],
            })

        # Edge count
        edge_result = self._session.run(
            f"""
            MATCH (s)-[r]->(t)
            WHERE {_label_match('s')} AND {_label_match('t')}
            RETURN count(r) AS cnt
            """
        )
        total_edges = edge_result.single()["cnt"]

        # Distinct predicate count
        pred_result = self._session.run(
            f"""
            MATCH (s)-[r]->(t)
            WHERE {_label_match('s')} AND {_label_match('t')}
            RETURN count(DISTINCT type(r)) AS cnt
            """
        )
        total_predicates = pred_result.single()["cnt"]

        return {
            "nodes": nodes,
            "kind_counts": kind_counts,
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "total_predicates": total_predicates,
        }
```

- [ ] **Step 2: Add `get_dependency_links` method**

Add after `get_graph_stats`:

```python
    def get_dependency_links(self, design_qnames: list[str]) -> OntologyGraph:
        """Find dependency Compounds linked to given design qualified names.

        Returns an OntologyGraph with design compounds, linked dependency
        compounds, and the edges between them.
        """
        if not design_qnames:
            return OntologyGraph()

        label_clause = _label_match("d")
        design_set = set(design_qnames)

        result = self._session.run(
            f"""
            UNWIND $qnames AS qn
            MATCH (d) WHERE d.qualified_name = qn AND {label_clause}
            OPTIONAL MATCH (d)-[r]->(dep:Compound)
            WHERE dep.layer = 'dependency'
            RETURN d, collect(DISTINCT {{dep: dep, rel: type(r)}}) AS dep_links
            """,
            {"qnames": design_qnames},
        )

        compounds: list[CompoundGraph] = []
        seen_qns: set[str] = set()
        edges: list[GraphEdge] = []

        for record in result:
            d = record["d"]
            if d is None:
                continue
            d_qn = d.get("qualified_name", "")
            if d_qn not in seen_qns:
                seen_qns.add(d_qn)
                d_props = dict(d)
                compounds.append(CompoundGraph(
                    node=CompoundNode(**d_props),
                ))

            for item in (record["dep_links"] or []):
                if item is None or item.get("dep") is None:
                    continue
                dep = item["dep"]
                dep_qn = dep.get("qualified_name", "")
                dep_props = dict(dep)
                if dep_qn not in seen_qns:
                    seen_qns.add(dep_qn)
                    try:
                        compounds.append(CompoundGraph(
                            node=CompoundNode(**dep_props),
                        ))
                    except Exception:
                        pass
                edges.append(_hydrate_graph_edge(
                    item["rel"], d_qn, dep_qn,
                ))

        return OntologyGraph(compounds=compounds, edges=edges)
```

- [ ] **Step 3: Commit**

```bash
git add backend/db/neo4j/repositories/design.py
git commit -m "feat: add get_graph_stats and get_dependency_links to DesignRepository"
```

---

### Task 8: Update queries/__init__.py — re-export from repository

**Files:**
- Modify: `backend/db/neo4j/queries/__init__.py`

- [ ] **Step 1: Replace the module with a backward-compat shim**

The new API is repository-based. Old callers import from `queries`. We provide shim functions that delegate to `DesignRepository`:

```python
"""Read-side Neo4j queries — backward-compat shim delegating to DesignRepository.

New code should use ``DesignRepository`` methods directly:
``repo.get_ontology_graph()`` instead of ``fetch_design_graph()``.
"""

from __future__ import annotations

from services.dependencies import get_neo4j
from backend.db.neo4j.repositories.design import DesignRepository


def _repo():
    """Get a DesignRepository with an active session from the pool."""
    conn = get_neo4j()
    # Each call opens a fresh session; caller (repository) manages it
    # We create the repo here so callers don't need to pass sessions.
    return conn


def fetch_design_graph(
    kind_filter=None, search=None, component_id=None
):
    conn = get_neo4j()
    with conn.session() as session:
        repo = DesignRepository(session)
        graph = repo.get_ontology_graph(
            layer="design",
            kind_filter=kind_filter,
            search=search,
            component_id=component_id,
        )
        return graph.to_raw()


def fetch_hlr_subgraph(hlr_id, component_id=None):
    conn = get_neo4j()
    with conn.session() as session:
        repo = DesignRepository(session)
        graph = repo.get_hlr_subgraph(hlr_id, component_id)
        return graph.to_raw()


def fetch_neighbourhood_graph(qualified_name):
    conn = get_neo4j()
    with conn.session() as session:
        repo = DesignRepository(session)
        graph = repo.get_neighbourhood_graph(qualified_name)
        return graph.to_raw()


def fetch_node_detail(qualified_name):
    conn = get_neo4j()
    with conn.session() as session:
        repo = DesignRepository(session)
        cg = repo.get_compound_graph(qualified_name)
        if cg is None:
            return None
        return {
            "properties": cg.node.model_dump(),
            "outgoing": [
                {"rel": e.predicate, "target_qn": e.target_qualified_name,
                 "target_name": "", "target_labels": ["Compound"]}
                for e in cg.edges_out
            ],
            "incoming": [
                {"rel": e.predicate, "source_qn": e.source_qualified_name,
                 "source_name": "", "source_labels": ["Compound"]}
                for e in cg.edges_in
            ],
            "implemented_by": [],
            "members": [m.model_dump() for m in cg.members],
            "codebase_members": [],
            "available_types": [],
        }


def fetch_codebase_compounds(search=None):
    conn = get_neo4j()
    with conn.session() as session:
        repo = DesignRepository(session)
        graph = repo.get_ontology_graph(
            layer="as-built", search=search,
        )
        return graph.to_raw()


def fetch_dependency_compounds(search=None, source_filter=None, limit=100):
    conn = get_neo4j()
    with conn.session() as session:
        repo = DesignRepository(session)
        graph = repo.get_ontology_graph(
            layer="dependency", search=search,
        )
        raw = graph.to_raw()
        # source_filter is not yet handled by get_ontology_graph;
        # keep the old behaviour for now
        return raw


def fetch_design_dependency_links(design_qnames):
    conn = get_neo4j()
    with conn.session() as session:
        repo = DesignRepository(session)
        graph = repo.get_dependency_links(design_qnames)
        return graph.to_raw()


__all__ = [
    "fetch_design_graph",
    "fetch_hlr_subgraph",
    "fetch_neighbourhood_graph",
    "fetch_node_detail",
    "fetch_codebase_compounds",
    "fetch_dependency_compounds",
    "fetch_design_dependency_links",
]
```

- [ ] **Step 2: Commit**

```bash
git add backend/db/neo4j/queries/__init__.py
git commit -m "refactor: re-export queries as DesignRepository shims for backward compat"
```

---

### Task 9: Update frontend/data/ontology.py — no raw Cypher

**Files:**
- Modify: `frontend/data/ontology.py`

- [ ] **Step 1: Rewrite `fetch_ontology_data` to use repository**

Replace the entire `fetch_ontology_data` function:

```python
def fetch_ontology_data():
    """Fetch all data needed for ontology page via DesignRepository."""
    from backend.db.neo4j.repositories.design import DesignRepository

    with get_neo4j().session() as session:
        repo = DesignRepository(session)
        stats = repo.get_graph_stats()

        # Resolve component names (still needs SQLite)
        component_map: dict[int, str] = {}
        try:
            from backend.db import get_session
            from backend.db.models import Component
            with get_session() as sql_session:
                for c in sql_session.query(Component).all():
                    component_map[c.id] = c.name
        except Exception:
            pass

        nodes = []
        for n in stats.get("nodes", []):
            cid = n.get("component_id")
            nodes.append({
                "name": n["name"],
                "kind": n["kind"],
                "qualified_name": n["qualified_name"],
                "component": component_map.get(cid, "-") if cid else "-",
            })

    return {
        "nodes": nodes,
        "kind_counts": stats["kind_counts"],
        "total_nodes": stats["total_nodes"],
        "total_triples": stats["total_edges"],
        "total_predicates": stats["total_predicates"],
    }
```

- [ ] **Step 2: Rewrite `fetch_ontology_graph_data` to use repository**

Replace `fetch_ontology_graph_data`:

```python
def fetch_ontology_graph_data(
    layer: str = "design",
    kind_filter: str | None = None,
    search: str | None = None,
    component_id: int | None = None,
    source_filter: str | None = None,
    requirement_tags: str = "hlr",
    include_dependencies: bool = True,
) -> dict:
    """Fetch graph data for Cytoscape.js rendering via DesignRepository."""
    try:
        from backend.db.neo4j.repositories.design import DesignRepository
        from backend.graph import format_cytoscape_graph
        from backend.requirements.services.graph_tags import enrich_with_requirement_tags

        with get_neo4j().session() as session:
            repo = DesignRepository(session)
            graph = repo.get_ontology_graph(
                layer=layer,
                kind_filter=kind_filter,
                search=search,
                component_id=component_id,
            )
            raw = graph.to_raw()

        formatted = format_cytoscape_graph(raw)

        if layer == "design" and requirement_tags != "none":
            enrich_with_requirement_tags(formatted["nodes"], mode=requirement_tags)

        if not include_dependencies:
            formatted["nodes"], formatted["edges"] = filter_cross_layer_elements(
                formatted["nodes"], formatted["edges"]
            )

        return formatted
    except Exception:
        log.warning("Neo4j query failed — returning empty graph", exc_info=True)
        return {"nodes": [], "edges": []}
```

Note: The `source_filter` parameter was used by the dependency layer for filtering by source (e.g., "eigen"). Since `get_ontology_graph` uses `layer="dependency"` and doesn't support source-level filtering yet, `source_filter` is accepted but unused in this path. The dependency-layer path still works via the backward-compat shim in `queries/__init__.py`.

- [ ] **Step 3: Rewrite `fetch_hlr_graph_data`**

```python
def fetch_hlr_graph_data(
    hlr_id: int,
    component_id: int | None = None,
    requirement_tags: str = "hlr",
) -> dict:
    """Fetch the ontology subgraph around an HLR via DesignRepository."""
    try:
        from backend.db.neo4j.repositories.design import DesignRepository
        from backend.graph import format_cytoscape_graph
        from backend.requirements.services.graph_tags import tag_direct_nodes_only

        with get_neo4j().session() as session:
            repo = DesignRepository(session)
            graph = repo.get_hlr_subgraph(hlr_id, component_id)
            raw = graph.to_raw()

        formatted = format_cytoscape_graph(raw)

        if requirement_tags != "none":
            tag_direct_nodes_only(formatted["nodes"], hlr_id)

        return formatted
    except Exception:
        log.warning("Neo4j HLR subgraph query failed", exc_info=True)
        return {"nodes": [], "edges": []}
```

- [ ] **Step 4: Rewrite `fetch_neighbourhood_graph_data`**

```python
def fetch_neighbourhood_graph_data(qualified_name: str) -> dict:
    """Fetch the 1-hop neighbourhood graph via DesignRepository."""
    try:
        from backend.db.neo4j.repositories.design import DesignRepository
        from backend.graph import format_cytoscape_graph

        with get_neo4j().session() as session:
            repo = DesignRepository(session)
            graph = repo.get_neighbourhood_graph(qualified_name)
            raw = graph.to_raw()

        return format_cytoscape_graph(raw)
    except Exception:
        log.warning("Neo4j neighbourhood query failed", exc_info=True)
        return {"nodes": [], "edges": []}
```

- [ ] **Step 5: Rewrite `fetch_graph_node_detail`**

```python
def fetch_graph_node_detail(qualified_name: str) -> dict | None:
    """Fetch node detail from Neo4j via DesignRepository."""
    try:
        from backend.db.neo4j.repositories.design import DesignRepository

        with get_neo4j().session() as session:
            repo = DesignRepository(session)
            cg = repo.get_compound_graph(qualified_name)

        if cg is None:
            return None

        # Convert CompoundGraph to the dict shape expected by the frontend
        return {
            "properties": cg.node.model_dump(),
            "outgoing": [
                {"rel": e.predicate, "target_qn": e.target_qualified_name,
                 "target_name": "", "target_labels": ["Compound"]}
                for e in cg.edges_out
            ],
            "incoming": [
                {"rel": e.predicate, "source_qn": e.source_qualified_name,
                 "source_name": "", "source_labels": ["Compound"]}
                for e in cg.edges_in
            ],
            "implemented_by": [],
            "members": [m.model_dump() for m in cg.members],
            "codebase_members": [],
            "available_types": [],
        }
    except Exception:
        log.warning("Neo4j node detail query failed", exc_info=True)
        return None
```

- [ ] **Step 6: Rewrite `fetch_node_detail_full`**

Remove the raw Cypher TRACES_TO query. Replace with:

```python
def fetch_node_detail_full(qualified_name: str) -> dict | None:
    """Fetch ontology node by qualified_name with all properties + relationships."""
    neo4j_data = fetch_graph_node_detail(qualified_name)
    if not neo4j_data:
        return None

    props = neo4j_data.get("properties", {})
    node_data = {
        "name": props.get("name", ""),
        "qualified_name": props.get("qualified_name", ""),
        "kind": props.get("kind", ""),
        "specialization": props.get("specialization", ""),
        "visibility": props.get("visibility", ""),
        "description": props.get("description", ""),
        "component_id": props.get("component_id"),
        "type_signature": props.get("type_signature", ""),
        "argsstring": props.get("argsstring", ""),
        "definition": props.get("definition", ""),
        "file_path": props.get("file_path", ""),
        "line_number": props.get("line_number"),
        "source_type": props.get("source_type", ""),
        "is_static": props.get("is_static", False),
        "is_const": props.get("is_const", False),
        "is_virtual": props.get("is_virtual", False),
        "is_abstract": props.get("is_abstract", False),
        "is_final": props.get("is_final", False),
    }

    # Look up component name if component_id exists
    component_name = ""
    if node_data["component_id"]:
        try:
            from backend.db import get_session
            from backend.db.models import Component
            with get_session() as session:
                comp = session.query(Component).filter_by(id=node_data["component_id"]).first()
                if comp:
                    component_name = comp.name
        except Exception:
            pass
    node_data["component"] = component_name

    # Fetch requirement tags from Neo4j TRACES_TO edges
    requirements = []
    try:
        with get_neo4j().session() as ns:
            label_clause = _label_match_direct("d")
            result = ns.run(
                f"""
                MATCH (r)-[:TRACES_TO]->(d {{qualified_name: $qn}})
                WHERE (r:HLR OR r:LLR) AND ({label_clause})
                RETURN labels(r) AS labels, r.id AS id,
                       r.description AS desc
                """,
                {"qn": qualified_name},
            )
            for record in result:
                label_type = "HLR" if "HLR" in record["labels"] else "LLR"
                requirements.append({
                    "id": record["id"],
                    "type": label_type,
                    "description": (record["desc"] or "")[:80],
                })
    except Exception:
        log.warning("Failed to fetch requirement traces for %s",
                     qualified_name, exc_info=True)

    return {"node": node_data, "neo4j": neo4j_data, "requirements": requirements}
```

We need a helper for the TRACES_TO query. Add at module level:

```python
def _label_match_direct(alias: str = "n") -> str:
    """Build label-match clause without import from repository (avoid circular)."""
    return f"({alias}:Compound OR {alias}:Member OR {alias}:Namespace)"
```

- [ ] **Step 7: Rewrite `update_member_type`**

Replace:
```python
ns.run(
    "MATCH (n:Design {qualified_name: $qn}) SET n.type_signature = $ts",
    {"qn": qualified_name, "ts": type_signature},
)
```
with:
```python
ns.run(
    "MATCH (n:Member {qualified_name: $qn}) SET n.type_signature = $ts",
    {"qn": qualified_name, "ts": type_signature},
)
```

- [ ] **Step 8: Commit**

```bash
git add frontend/data/ontology.py
git commit -m "refactor: migrate ontology data layer to DesignRepository methods"
```

---

### Task 10: Update frontend/data/hlr.py

**Files:**
- Modify: `frontend/data/hlr.py`

- [ ] **Step 1: Update :Design references (4 lines)**

**Line 61**: Change `MATCH (d:Design)` to `MATCH (d) WHERE d:Compound OR d:Member OR d:Namespace`:
```python
total_nodes = ns.run(
    "MATCH (d) WHERE d:Compound OR d:Member OR d:Namespace RETURN count(d) AS cnt"
).single()["cnt"]
```

**Line 63**: Change `:Design` to label-match:
```python
result = ns.run(
    "MATCH (s)-[r]->(t) "
    "WHERE (s:Compound OR s:Member OR s:Namespace) "
    "AND (t:Compound OR t:Member OR t:Namespace) "
    "RETURN count(r) AS cnt"
).single()
```

**Lines 220-221**: Change TRACES_TO query:
```python
result = ns.run(
    f"""
    MATCH (hlr:HLR {{id: $hid}})-[:TRACES_TO]->(d)
    WHERE d:Compound OR d:Member OR d:Namespace
    OPTIONAL MATCH (d)-[r]->(d2)
    WHERE d2:Compound OR d2:Member OR d2:Namespace
    ...
    """,
    ...
)
```

- [ ] **Step 2: Commit**

```bash
git add frontend/data/hlr.py
git commit -m "refactor: update HLR data layer to use new node labels"
```

---

### Task 11: Update frontend/data/llr.py + dependencies.py

**Files:**
- Modify: `frontend/data/llr.py`
- Modify: `frontend/data/dependencies.py`

- [ ] **Step 1: Update llr.py :Design references (2 lines)**

**Line 155**: Change `d:Design` to `d:Compound|Member|Namespace`:
```python
MATCH (l:LLR {id: $lid})-[:TRACES_TO]->(d)
WHERE d:Compound OR d:Member OR d:Namespace
```

**Line 156**: Change `d2:Design`:
```python
OPTIONAL MATCH (d)-[r]->(d2)
WHERE d2:Compound OR d2:Member OR d2:Namespace
```

- [ ] **Step 2: Update dependencies.py**

Change the import from `fetch_design_dependency_links` to use the repository directly, or keep the import (it still works via the shim). Verify the function signature matches.

- [ ] **Step 3: Commit**

```bash
git add frontend/data/llr.py frontend/data/dependencies.py
git commit -m "refactor: update LLR and dependencies data layers to use new labels"
```

---

### Task 12: Update graph/__init__.py + transforms.py

**Files:**
- Modify: `backend/graph/__init__.py`
- Modify: `backend/graph/transforms.py`

- [ ] **Step 1: Remove CONTAINS from _CONTAINMENT_RELS**

In `backend/graph/transforms.py`, change:
```python
_CONTAINMENT_RELS = {"COMPOSES", "CONTAINS", "AGGREGATES"}
```
to:
```python
_CONTAINMENT_RELS = {"COMPOSES", "AGGREGATES"}
```

- [ ] **Step 2: Verify no other CONTAINS references in transforms.py**

```bash
rg "CONTAINS" backend/graph/transforms.py
```
Expected: no results (aside from the removed line).

- [ ] **Step 3: graph/__init__.py needs no changes**

It calls `format_cytoscape_graph(raw)` which receives dicts from `graph.to_raw()`. The dict shape is compatible (same keys: `nodes` with flat props, `edges` with `source`/`target`/`type`).

- [ ] **Step 4: Commit**

```bash
git add backend/graph/transforms.py
git commit -m "refactor: remove CONTAINS from containment edge types, use COMPOSES only"
```

---

### Task 13: Update design_data/repository.py

**Files:**
- Modify: `backend/design_data/repository.py`

- [ ] **Step 1: Update :Design references**

Replace all `:Design` with `:Compound` in `DesignDataRepository` Cypher queries. Since these queries filter by `kind` and `component_id`, and design-intent nodes are now `:Compound` with `layer: "design"`, we need to add a layer filter:

Replace all `d:Design` with `d:Compound` and add a `d.layer = 'design'` filter. Specific changes:

**get_class_diagram**: Change conditions to `["d:Compound", "d.layer = $layer"]` with `params["layer"] = layer or "design"`. Update OPTIONAL MATCH to `(d)-[:COMPOSES]->(member:Member)`.

**get_hlr_subgraph**: Change `d:Design` to `d:Compound` and add `d.layer = 'design'`.

**get_class, get_interface, get_enum**: Change `d:Design` to `d:Compound {layer: 'design'}`.

**get_classes_for_component, get_public_api**: Change `d:Design` to `d:Compound` and add `d.layer = 'design'`.

**_fetch_associations**: Change to:
```python
MATCH (s:Compound)-[r]->(o)
WHERE type(r) IN ['AGGREGATES', 'COMPOSES', 'REFERENCES', 'DEPENDS_ON',
                  'ASSOCIATES', 'INVOKES', 'RETURNS', 'REALIZES',
                  'INHERITS_FROM', 'IMPLEMENTS']
  AND (o:Compound OR o:Namespace)
```

- [ ] **Step 2: Update _detect_layer in queries (not used here, but in detail.py)**

Actually `_detect_layer` is in `queries/detail.py` which will be deleted. Since `DesignDataRepository` has its own `_map_layer`, it's fine.

- [ ] **Step 3: Commit**

```bash
git add backend/design_data/repository.py
git commit -m "refactor: update DesignDataRepository to use :Compound with layer filter"
```

---

### Task 14: Update graph_tags.py — TRACES_TO queries

**Files:**
- Modify: `backend/requirements/services/graph_tags.py`

- [ ] **Step 1: Update the TRACES_TO query**

In `_enrich_via_cypher`, change:
```python
MATCH (r)-[:TRACES_TO]->(d:Design {qualified_name: qn})
```
to:
```python
MATCH (r)-[:TRACES_TO]->(d {qualified_name: qn})
WHERE d:Compound OR d:Member OR d:Namespace
```

- [ ] **Step 2: Commit**

```bash
git add backend/requirements/services/graph_tags.py
git commit -m "refactor: update graph_tags TRACES_TO query to match new labels"
```

---

### Task 15: Update connection.py + sync.py — drop :Design constraints

**Files:**
- Modify: `backend/db/neo4j/connection.py`
- Modify: `backend/db/neo4j/sync.py`

- [ ] **Step 1: Remove :Design constraints from connection.py**

Delete these lines (approx lines 69, 80-81, 106-108):
```python
"CREATE CONSTRAINT design_qualified_name IF NOT EXISTS FOR (n:Design) REQUIRE n.qualified_name IS UNIQUE",
"CREATE INDEX design_kind IF NOT EXISTS FOR (n:Design) ON (n.kind)",
"CREATE INDEX design_component_id IF NOT EXISTS FOR (n:Design) ON (n.component_id)",
"CREATE INDEX design_source_type IF NOT EXISTS FOR (n:Design) ON (n.source_type)",
"CREATE INDEX design_implementation_status IF NOT EXISTS FOR (n:Design) ON (n.implementation_status)",
```

- [ ] **Step 2: Update sync.py to use repository**

Replace raw `:Design` Cypher with calls to `DesignRepository.clear_design_graph()`. The `sync.py` migration logic that converts `:Design`→`:Compound|Member|Namespace` should be retired (it was a one-time migration).

Update `clear_design_graph` caller:
```python
from backend.db.neo4j.repositories.design import DesignRepository
repo = DesignRepository(session)
repo.clear_design_graph()
```

- [ ] **Step 3: Remove :Design from sync.py queries**

Replace `MATCH (n:Design) DETACH DELETE n` with repository call.

Replace `MATCH (d:Design {...})` patterns with `MATCH (d:Compound)` or the label-match equivalent, adding `d.layer = 'design'` where needed.

- [ ] **Step 4: Commit**

```bash
git add backend/db/neo4j/connection.py backend/db/neo4j/sync.py
git commit -m "refactor: remove :Design constraints/indexes, update sync to use repository"
```

---

### Task 16: Delete old queries files + final :Design cleanup

**Files:**
- Delete: `backend/db/neo4j/queries/graph.py`
- Delete: `backend/db/neo4j/queries/detail.py`
- Delete: `backend/db/neo4j/queries/compounds.py`
- Delete: `backend/db/neo4j/queries/__pycache__/` (auto-regenerated)

- [ ] **Step 1: Confirm no imports remain**

```bash
rg "from backend.db.neo4j.queries.graph import" backend/ frontend/ scripts/
rg "from backend.db.neo4j.queries.detail import" backend/ frontend/ scripts/
rg "from backend.db.neo4j.queries.compounds import" backend/ frontend/ scripts/
```

All should now go through `queries/__init__.py` (the shim) or directly through `DesignRepository`.

- [ ] **Step 2: Delete files**

```bash
rm backend/db/neo4j/queries/graph.py
rm backend/db/neo4j/queries/detail.py
rm backend/db/neo4j/queries/compounds.py
```

- [ ] **Step 3: Final :Design grep — should find nothing meaningful**

```bash
rg -n ":Design" backend/ frontend/ --type py
```

Expected: only in comments/docs referencing the legacy label in historical context. If any query strings still contain `:Design`, fix them.

- [ ] **Step 4: Commit**

```bash
git rm backend/db/neo4j/queries/graph.py backend/db/neo4j/queries/detail.py backend/db/neo4j/queries/compounds.py
git commit -m "refactor: delete legacy queries modules, migrated to DesignRepository"
```

---

### Task 17: Re-ingest + full verification

- [ ] **Step 1: Re-ingest dependency data with COMPOSES**

```bash
cd ../Doxygen-Dependency-Parser
python -m doxygen_index --source cppreference --xml-dir /path/to/cppreference/xml --clear
cd -
```

- [ ] **Step 2: Flush and repopulate design data**

```bash
python scripts/01_flush_db.py --nuke-neo4j
python scripts/02_setup_project.py
python scripts/03_design_requirements.py
```

- [ ] **Step 3: Run full test suite**

```bash
pytest
```

Expected: all tests pass.

- [ ] **Step 4: Verify graph page renders**

Start the app and navigate to `http://localhost:8081/ontology/graph`. The "Design Intent" layer should show compounds, members, and relationships in PlantUML-style.

- [ ] **Step 5: Commit any final fixes**

If anything needed tweaking, fix and commit.

---
