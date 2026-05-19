# Requirements-Ontology Graph Separation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove synthetic HLR/LLR requirement nodes from the ontology graph and replace them with tag-based metadata on design nodes, persisted via new M2M association tables in SQLite.

**Architecture:** Two-stage data pipeline — bare Neo4j topology query followed by optional SQLite enrichment. Requirements tag design nodes as metadata badges; they never appear as graph entities. New `high_level_requirements_nodes` and `low_level_requirements_nodes` M2M tables provide direct HLR→Node links alongside the existing HLR→Triple links.

**Tech Stack:** SQLAlchemy 2.0 (ORM + Alembic migrations), Neo4j (Cypher queries), NiceGUI (Cytoscape.js), pytest

**Spec:** `docs/specs/2025-01-20-requirements-ontology-separation-design.md`

---

## File Structure

### New files

| File | Responsibility |
|---|---|
| `backend/requirements/services/graph_tags.py` | `enrich_with_requirement_tags()` and `tag_direct_nodes_only()` — SQLite enrichment for Cytoscape nodes |
| `tests/test_graph_tags.py` | Unit tests for graph tag enrichment |
| `scripts/backfill_requirement_nodes.py` | One-time data migration to populate M2M from existing triple associations |
| `alembic/versions/xxxx_add_requirement_nodes_tables.py` | Alembic migration for two new M2M tables |

### Modified files

| File | Changes |
|---|---|
| `backend/db/models/associations.py` | Add `high_level_requirements_nodes` and `low_level_requirements_nodes` tables |
| `backend/db/models/__init__.py` | Re-export new association tables |
| `backend/db/models/requirements.py` | Add `nodes` M2M relationship on HLR and LLR |
| `backend/db/models/ontology.py` | Add `high_level_requirements` and `low_level_requirements` reverse relationships on `OntologyNode` |
| `backend/db/neo4j/queries/graph.py` | Delete `_attach_traced_requirements()`, remove its call from `fetch_design_graph()`, rewrite `fetch_hlr_subgraph()` |
| `backend/db/neo4j/queries/detail.py` | Remove HLR/LLR from `_detect_layer()`, remove requirements from `fetch_node_detail()` |
| `backend/graph/builders.py` | Pass `requirements` and `is_hlr_highlight` through in `_build_design_node()` |
| `backend/requirements/services/persistence.py` | Add node-link derivation in `persist_design()`, extend `DesignResult` |
| `frontend/data/ontology.py` | Two-stage pipeline composition, add `requirement_tags` param |
| `frontend/theme.py` | Remove requirement layer/edge styles, add highlight/badge styles |
| `frontend/pages/ontology_graph.py` | Add HLR tags toggle, JavaScript badge rendering |
| `frontend/pages/hlr_detail.py` | Use new `fetch_hlr_graph_data()` with `requirement_tags` |
| `frontend/pages/node_detail.py` | Remove "Traced Requirements" card |
| `frontend/widgets.py` | Add `show_requirement_tags` to `GraphState` |
| `tests/test_requirements_models.py` | Add tests for new M2M node relationships |
| `tests/test_ontology_models.py` | Add tests for reverse relationships on `OntologyNode` |

---

### Task 1: Add M2M Association Tables and ORM Relationships

**Files:**
- Modify: `backend/db/models/associations.py`
- Modify: `backend/db/models/__init__.py`
- Modify: `backend/db/models/requirements.py`
- Modify: `backend/db/models/ontology.py`
- Test: `tests/test_requirements_models.py`
- Test: `tests/test_ontology_models.py`

- [ ] **Step 1: Write the failing tests for HLR.nodes and LLR.nodes relationships**

Add to `tests/test_requirements_models.py`:

```python
class TestHLRNodesRelationship:
    """Tests for the HLR → OntologyNode M2M relationship."""

    def test_hlr_has_empty_nodes_by_default(self, seeded_session):
        hlr = seeded_session.query(HighLevelRequirement).first()
        assert hlr.nodes == []

    def test_add_node_to_hlr(self, seeded_session):
        from backend.db.models.ontology import OntologyNode
        hlr = seeded_session.query(HighLevelRequirement).first()
        node = OntologyNode(kind="class", name="Calculator", qualified_name="calc::Calculator")
        seeded_session.add(node)
        seeded_session.flush()
        hlr.nodes.append(node)
        seeded_session.flush()
        assert node in hlr.nodes
        assert hlr in node.high_level_requirements

    def test_remove_node_from_hlr(self, seeded_session):
        from backend.db.models.ontology import OntologyNode
        hlr = seeded_session.query(HighLevelRequirement).first()
        node = OntologyNode(kind="class", name="Widget", qualified_name="calc::Widget")
        seeded_session.add(node)
        seeded_session.flush()
        hlr.nodes.append(node)
        seeded_session.flush()
        hlr.nodes.remove(node)
        seeded_session.flush()
        assert node not in hlr.nodes

    def test_hlr_nodes_distinct_from_triples(self, seeded_session):
        """HLR.nodes and HLR.triples are independent collections."""
        from backend.db.models.ontology import OntologyNode, OntologyTriple, Predicate
        hlr = seeded_session.query(HighLevelRequirement).first()

        sub = OntologyNode(kind="class", name="Sub", qualified_name="ns::Sub")
        obj = OntologyNode(kind="class", name="Obj", qualified_name="ns::Obj")
        seeded_session.add_all([sub, obj])
        seeded_session.flush()

        pred = seeded_session.query(Predicate).filter_by(name="composes").first()
        triple = OntologyTriple(subject_id=sub.id, predicate_id=pred.id, object_id=obj.id)
        seeded_session.add(triple)
        seeded_session.flush()

        # Link the triple
        hlr.triples.append(triple)
        # Also link both nodes directly
        hlr.nodes.extend([sub, obj])
        seeded_session.flush()

        assert triple in hlr.triples
        assert sub in hlr.nodes
        assert obj in hlr.nodes
        # They are independent: removing a node doesn't remove a triple
        hlr.nodes.remove(sub)
        seeded_session.flush()
        assert triple in hlr.triples
        assert sub not in hlr.nodes


class TestLLRNodesRelationship:
    """Tests for the LLR → OntologyNode M2M relationship."""

    def test_llr_has_empty_nodes_by_default(self, seeded_session):
        hlr = seeded_session.query(HighLevelRequirement).first()
        llr = LowLevelRequirement(description="LLR test", high_level_requirement=hlr)
        seeded_session.add(llr)
        seeded_session.flush()
        assert llr.nodes == []

    def test_add_node_to_llr(self, seeded_session):
        from backend.db.models.ontology import OntologyNode
        hlr = seeded_session.query(HighLevelRequirement).first()
        llr = LowLevelRequirement(description="LLR", high_level_requirement=hlr)
        seeded_session.add(llr)
        seeded_session.flush()

        node = OntologyNode(kind="method", name="doThing", qualified_name="calc::doThing")
        seeded_session.add(node)
        seeded_session.flush()
        llr.nodes.append(node)
        seeded_session.flush()
        assert node in llr.nodes
        assert llr in node.low_level_requirements
```

Add to `tests/test_ontology_models.py`:

```python
class TestOntologyNodeRequirementRelationships:
    """Tests for reverse requirement relationships on OntologyNode."""

    def test_node_high_level_requirements(self, seeded_session):
        from backend.db.models.requirements import HighLevelRequirement
        hlr = seeded_session.query(HighLevelRequirement).first()
        node = OntologyNode(kind="class", name="X", qualified_name="ns::X")
        seeded_session.add(node)
        seeded_session.flush()
        hlr.nodes.append(node)
        seeded_session.flush()
        assert hlr in node.high_level_requirements

    def test_node_low_level_requirements(self, seeded_session):
        from backend.db.models.requirements import LowLevelRequirement, HighLevelRequirement
        hlr = seeded_session.query(HighLevelRequirement).first()
        llr = LowLevelRequirement(description="LLR", high_level_requirement=hlr)
        seeded_session.add(llr)
        seeded_session.flush()
        node = OntologyNode(kind="class", name="Y", qualified_name="ns::Y")
        seeded_session.add(node)
        seeded_session.flush()
        llr.nodes.append(node)
        seeded_session.flush()
        assert llr in node.low_level_requirements
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_requirements_models.py::TestHLRNodesRelationship tests/test_requirements_models.py::TestLLRNodesRelationship tests/test_ontology_models.py::TestOntologyNodeRequirementRelationships -v`
Expected: FAIL — `nodes` attribute doesn't exist on `HighLevelRequirement` yet.

- [ ] **Step 3: Add the M2M association tables**

In `backend/db/models/associations.py`, add after the existing `high_level_requirements_triples` table:

```python
# HLR ↔ OntologyNode
high_level_requirements_nodes = Table(
    "high_level_requirements_nodes",
    Base.metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "highlevelrequirement_id",
        Integer,
        ForeignKey("high_level_requirements.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "ontologynode_id",
        Integer,
        ForeignKey("ontology_nodes.id", ondelete="CASCADE"),
        nullable=False,
    ),
)

# LLR ↔ OntologyNode
low_level_requirements_nodes = Table(
    "low_level_requirements_nodes",
    Base.metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "lowlevelrequirement_id",
        Integer,
        ForeignKey("low_level_requirements.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "ontologynode_id",
        Integer,
        ForeignKey("ontology_nodes.id", ondelete="CASCADE"),
        nullable=False,
    ),
)
```

- [ ] **Step 4: Add relationships to the ORM models**

In `backend/db/models/requirements.py`, add to `HighLevelRequirement`:

```python
from backend.db.models.associations import (
    high_level_requirements_triples,
    low_level_requirements_components,
    low_level_requirements_triples,
    high_level_requirements_nodes,
    low_level_requirements_nodes,
)

# Inside HighLevelRequirement class:
nodes: Mapped[list[OntologyNode]] = relationship(
    "OntologyNode", secondary=high_level_requirements_nodes
)
```

In `backend/db/models/requirements.py`, add to `LowLevelRequirement`:

```python
# Inside LowLevelRequirement class:
nodes: Mapped[list[OntologyNode]] = relationship(
    "OntologyNode", secondary=low_level_requirements_nodes
)
```

In `backend/db/models/ontology.py`, add to `OntologyNode`:

```python
from backend.db.models.associations import (
    high_level_requirements_nodes,
    low_level_requirements_nodes,
)

# Inside OntologyNode class, after task_links:
high_level_requirements: Mapped[list["HighLevelRequirement"]] = relationship(
    "HighLevelRequirement", secondary=high_level_requirements_nodes, back_populates="nodes"
)
low_level_requirements: Mapped[list["LowLevelRequirement"]] = relationship(
    "LowLevelRequirement", secondary=low_level_requirements_nodes, back_populates="nodes"
)
```

In `backend/db/models/__init__.py`, add to the imports and `__all__`:

```python
from backend.db.models.associations import (
    high_level_requirements_triples,
    low_level_requirements_components,
    low_level_requirements_triples,
    tickets_components,
    tickets_languages,
    high_level_requirements_nodes,
    low_level_requirements_nodes,
)
```

Add `"high_level_requirements_nodes"` and `"low_level_requirements_nodes"` to the `__all__` list.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_requirements_models.py::TestHLRNodesRelationship tests/test_requirements_models.py::TestLLRNodesRelationship tests/test_ontology_models.py::TestOntologyNodeRequirementRelationships -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/db/models/associations.py backend/db/models/__init__.py backend/db/models/requirements.py backend/db/models/ontology.py tests/test_requirements_models.py tests/test_ontology_models.py
git commit -m "feat: add HLR/LLR ↔ OntologyNode M2M association tables"
```

---

### Task 2: Create Alembic Migration and Backfill Script

**Files:**
- Create: `alembic/versions/xxxx_add_requirement_nodes_tables.py`
- Create: `scripts/backfill_requirement_nodes.py`

- [ ] **Step 1: Generate Alembic migration**

```bash
alembic revision --autogenerate -m "add requirement nodes association tables"
```

- [ ] **Step 2: Review the generated migration**

Open the file and verify it contains:
- `CREATE TABLE high_level_requirements_nodes` with `highlevelrequirement_id` and `ontologynode_id` columns and foreign keys
- `CREATE TABLE low_level_requirements_nodes` with `lowlevelrequirement_id` and `ontologynode_id` columns and foreign keys

- [ ] **Step 3: Run the migration**

```bash
alembic upgrade head
```

Expected: No errors.

- [ ] **Step 4: Write the backfill script**

Create `scripts/backfill_requirement_nodes.py`:

```python
"""One-time migration: populate high_level_requirements_nodes and
low_level_requirements_nodes from existing triple associations.

For each HLR/LLR with linked triples, derive the subject and object nodes
from each triple and add them to the M2M node association.
"""

from backend.db import get_session
from backend.db.models import (
    HighLevelRequirement,
    LowLevelRequirement,
)


def backfill():
    with get_session() as session:
        hlrs_processed = 0
        nodes_linked = 0

        for hlr in session.query(HighLevelRequirement).all():
            existing_node_ids = {n.id for n in hlr.nodes}
            for triple in hlr.triples:
                for node in [triple.subject, triple.object]:
                    if node.id not in existing_node_ids:
                        hlr.nodes.append(node)
                        existing_node_ids.add(node.id)
                        nodes_linked += 1
            hlrs_processed += 1

        llrs_processed = 0
        for llr in session.query(LowLevelRequirement).all():
            existing_node_ids = {n.id for n in llr.nodes}
            for triple in llr.triples:
                for node in [triple.subject, triple.object]:
                    if node.id not in existing_node_ids:
                        llr.nodes.append(node)
                        existing_node_ids.add(node.id)
                        nodes_linked += 1
            llrs_processed += 1

        session.flush()
        print(f"Backfill complete: {hlrs_processed} HLRs, {llrs_processed} LLRs, {nodes_linked} node links created")


if __name__ == "__main__":
    backfill()
```

- [ ] **Step 5: Run the backfill script**

```bash
python scripts/backfill_requirement_nodes.py
```

Expected: Prints summary of HLRs, LLRs, and node links created. No errors.

- [ ] **Step 6: Verify backfill idempotency — run again**

```bash
python scripts/backfill_requirement_nodes.py
```

Expected: `nodes_linked` should be 0 (no duplicates).

- [ ] **Step 7: Commit**

```bash
git add alembic/versions/ scripts/backfill_requirement_nodes.py
git commit -m "feat: add Alembic migration and backfill for requirement nodes M2M"
```

---

### Task 3: Create graph_tags.py — SQLite Enrichment Module

**Files:**
- Create: `backend/requirements/services/graph_tags.py`
- Test: `tests/test_graph_tags.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_graph_tags.py`:

```python
"""Tests for backend/requirements/services/graph_tags.py"""

import pytest
from backend.requirements.services.graph_tags import (
    enrich_with_requirement_tags,
    tag_direct_nodes_only,
)


class TestEnrichWithRequirementTags:
    def test_mode_none_returns_nodes_unchanged(self):
        nodes = [{"id": "n1", "qualified_name": "ns::Foo"}]
        result = enrich_with_requirement_tags(nodes, mode="none")
        assert result == nodes
        assert "requirements" not in result[0]

    def test_mode_hlr_tags_nodes_with_matching_requirements(self, seeded_session):
        from backend.db.models.ontology import OntologyNode
        from backend.db.models.requirements import HighLevelRequirement

        hlr = seeded_session.query(HighLevelRequirement).first()
        node = OntologyNode(kind="class", name="Foo", qualified_name="calc::Foo")
        seeded_session.add(node)
        seeded_session.flush()
        hlr.nodes.append(node)
        seeded_session.flush()

        nodes = [{"id": "calc::Foo", "qualified_name": "calc::Foo", "kind": "class", "name": "Foo"}]
        result = enrich_with_requirement_tags(nodes, mode="hlr")

        assert len(result) == 1
        assert len(result[0]["requirements"]) == 1
        assert result[0]["requirements"][0]["type"] == "HLR"
        assert result[0]["requirements"][0]["id"] == hlr.id

    def test_mode_hlr_skips_nodes_without_requirements(self, seeded_session):
        nodes = [{"id": "n1", "qualified_name": "ns::NoReq", "kind": "class", "name": "NoReq"}]
        result = enrich_with_requirement_tags(nodes, mode="hlr")
        assert "requirements" not in result[0]

    def test_mode_hlr_handles_multiple_hlrs_on_same_node(self, seeded_session):
        from backend.db.models.ontology import OntologyNode
        from backend.db.models.requirements import HighLevelRequirement

        comp = seeded_session.query(HighLevelRequirement).first().component
        hlr1 = HighLevelRequirement(description="First HLR", component=comp)
        hlr2 = HighLevelRequirement(description="Second HLR", component=comp)
        seeded_session.add_all([hlr1, hlr2])
        seeded_session.flush()

        node = OntologyNode(kind="class", name="MultiReq", qualified_name="calc::MultiReq")
        seeded_session.add(node)
        seeded_session.flush()

        hlr1.nodes.append(node)
        hlr2.nodes.append(node)
        seeded_session.flush()

        nodes = [{"id": "calc::MultiReq", "qualified_name": "calc::MultiReq", "kind": "class", "name": "MultiReq"}]
        result = enrich_with_requirement_tags(nodes, mode="hlr")

        assert len(result[0]["requirements"]) == 2

    def test_mode_hlr_empty_graph_returns_empty(self):
        result = enrich_with_requirement_tags([], mode="hlr")
        assert result == []


class TestTagDirectNodesOnly:
    def test_marks_seed_nodes_with_highlight(self, seeded_session):
        from backend.db.models.ontology import OntologyNode
        from backend.db.models.requirements import HighLevelRequirement

        hlr = seeded_session.query(HighLevelRequirement).first()
        node = OntologyNode(kind="class", name="Foo", qualified_name="calc::Foo")
        seeded_session.add(node)
        seeded_session.flush()
        hlr.nodes.append(node)
        seeded_session.flush()

        nodes = [
            {"id": "calc::Foo", "qualified_name": "calc::Foo", "kind": "class", "name": "Foo"},
            {"id": "calc::Bar", "qualified_name": "calc::Bar", "kind": "class", "name": "Bar"},
        ]
        tag_direct_nodes_only(nodes, hlr.id)

        assert nodes[0].get("is_hlr_highlight") == "true"
        assert len(nodes[0].get("requirements", [])) == 1
        assert nodes[1].get("is_hlr_highlight", "") == ""

    def test_hlr_not_found_does_nothing(self):
        nodes = [{"id": "n1", "qualified_name": "ns::X"}]
        tag_direct_nodes_only(nodes, hlr_id=99999)
        assert nodes[0].get("is_hlr_highlight", "") == ""
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_graph_tags.py -v`
Expected: FAIL — module `graph_tags` doesn't exist.

- [ ] **Step 3: Implement graph_tags.py**

Create `backend/requirements/services/graph_tags.py`:

```python
"""SQLite enrichment for Cytoscape node dicts — add HLR requirement tags.

This module is the Stage 2 of the two-stage graph pipeline:
Stage 1 (Neo4j) produces bare topology; Stage 2 (SQLite) tags nodes
with requirement metadata. The two stages never cross boundaries.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def enrich_with_requirement_tags(
    nodes: list[dict],
    mode: str = "none",
) -> list[dict]:
    """Tag design nodes with HLR badges from SQLite.

    Modifies nodes in-place, adding a 'requirements' key to each node
    that is traced by one or more HLRs.

    Args:
        nodes: Cytoscape-format node dicts (from Stage 1).
        mode: "none" = no tags, "hlr" = add HLR tags.

    Returns:
        The same list (modified in-place).
    """
    if mode == "none":
        return nodes

    node_qns = {n.get("qualified_name") for n in nodes if n.get("qualified_name")}
    if not node_qns:
        return nodes

    from backend.db import get_session
    from backend.db.models import HighLevelRequirement

    qn_to_reqs: dict[str, list[dict]] = {}
    with get_session() as session:
        for hlr in session.query(HighLevelRequirement).all():
            for node in hlr.nodes:
                if node.qualified_name in node_qns:
                    qn_to_reqs.setdefault(node.qualified_name, []).append({
                        "id": hlr.id,
                        "type": "HLR",
                        "description": hlr.description[:80],
                    })

    for node in nodes:
        qn = node.get("qualified_name", "")
        if qn in qn_to_reqs:
            node["requirements"] = qn_to_reqs[qn]

    return nodes


def tag_direct_nodes_only(
    nodes: list[dict],
    hlr_id: int,
) -> None:
    """Mark seed nodes in an HLR subgraph with is_hlr_highlight and requirements tag.

    Only nodes directly linked to the HLR (via the M2M table) get the
    highlight flag and tag. 1-hop neighbours remain untagged.

    Args:
        nodes: Cytoscape-format node dicts.
        hlr_id: Database ID of the HLR to tag for.
    """
    from backend.db import get_session
    from backend.db.models import HighLevelRequirement

    with get_session() as session:
        hlr = session.query(HighLevelRequirement).filter_by(id=hlr_id).first()
        if not hlr:
            log.warning("tag_direct_nodes_only: HLR %d not found", hlr_id)
            return

        seed_qns = {n.qualified_name for n in hlr.nodes}

    for node in nodes:
        qn = node.get("qualified_name", "")
        if qn in seed_qns:
            node["is_hlr_highlight"] = "true"
            node.setdefault("requirements", []).append({
                "id": hlr.id,
                "type": "HLR",
                "description": hlr.description[:80],
            })
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_graph_tags.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/requirements/services/graph_tags.py tests/test_graph_tags.py
git commit -m "feat: add graph_tags module for SQLite requirement enrichment"
```

---

### Task 4: Update persist_design() to Derive Node Links

**Files:**
- Modify: `backend/requirements/services/persistence.py`
- Test: `tests/test_task_persistence.py` (or a new test if more appropriate)

- [ ] **Step 1: Write the failing test for node-link derivation**

Add to the appropriate test file (or create `tests/test_design_persistence.py`):

```python
class TestDesignResultNodeLinks:
    """Tests for DesignResult node_links_applied and node_links_skipped."""

    def test_design_result_has_node_link_fields(self):
        from backend.requirements.services.persistence import DesignResult
        result = DesignResult()
        assert result.node_links_applied == 0
        assert result.node_links_skipped == 0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_design_persistence.py::TestDesignResultNodeLinks -v` (or wherever you put it)
Expected: FAIL — `DesignResult` doesn't have `node_links_applied` yet.

- [ ] **Step 3: Extend DesignResult and update persist_design()**

In `backend/requirements/services/persistence.py`, add to `DesignResult`:

```python
@dataclass
class DesignResult:
    nodes_created: int = 0
    nodes_existing: int = 0
    triples_created: int = 0
    triples_skipped: int = 0
    links_applied: int = 0
    links_skipped: int = 0
    node_links_applied: int = 0      # NEW
    node_links_skipped: int = 0      # NEW
    qname_to_node: dict[str, OntologyNode] = field(default_factory=dict)
```

In `persist_design()`, after the requirement links section, add node derivation:

```python
    # --- Node links (derived from triple links) ---
    for link in design.requirement_links:
        triple = None
        if 0 <= link.triple_index < len(saved_triples):
            triple = saved_triples[link.triple_index]

        if not triple:
            continue

        if link.requirement_type == "hlr":
            req = session.query(HighLevelRequirement).filter_by(id=link.requirement_id).first()
        else:
            req = session.query(LowLevelRequirement).filter_by(id=link.requirement_id).first()

        if not req:
            result.node_links_skipped += 1
            continue

        node_ids_in_req = {n.id for n in req.nodes}
        for node in [triple.subject, triple.object]:
            if node.id not in node_ids_in_req:
                req.nodes.append(node)
                node_ids_in_req.add(node.id)
                result.node_links_applied += 1

    session.flush()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_design_persistence.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/requirements/services/persistence.py tests/
git commit -m "feat: derive node links from triple links in persist_design()"
```

---

### Task 5: Remove _attach_traced_requirements() and Clean Up Neo4j Queries

**Files:**
- Modify: `backend/db/neo4j/queries/graph.py`
- Modify: `backend/db/neo4j/queries/detail.py`

- [ ] **Step 1: Delete _attach_traced_requirements() function**

In `backend/db/neo4j/queries/graph.py`:
- Delete the entire `_attach_traced_requirements()` function (lines ~121-200)
- Remove the call `_attach_traced_requirements(nodes, edges)` from the end of `fetch_design_graph()`
- Update the module docstring to remove the sentence about requirement traces from SQLite

- [ ] **Step 2: Rewrite fetch_hlr_subgraph()**

Replace `fetch_hlr_subgraph()` in `backend/db/neo4j/queries/graph.py` with a version that:
1. Queries SQLite for seed qualified_names using `HighLevelRequirement.nodes` (via M2M)
2. Fetches seed Design nodes from Neo4j
3. Fetches 1-hop Design edges + neighbour nodes from Neo4j
4. Does NOT call `_attach_traced_requirements()`
5. Optionally expands to the full component if `component_id` is provided

```python
def fetch_hlr_subgraph(hlr_id: int, component_id: int | None = None) -> dict:
    """Fetch design subgraph around an HLR: seed nodes + 1-hop neighbourhood.

    Uses SQLite to find seed qualified_names via the
    high_level_requirements_nodes M2M table, then fetches those nodes
    and their 1-hop design neighbours from Neo4j.

    Returns bare topology — no synthetic requirement nodes.
    The caller enriches with requirement tags via tag_direct_nodes_only().
    """
    log.info("fetch_hlr_subgraph(hlr_id=%d, component_id=%s)", hlr_id, component_id)

    from backend.db import get_session
    from backend.db.models import HighLevelRequirement

    with get_session() as session:
        hlr = session.query(HighLevelRequirement).filter_by(id=hlr_id).first()
        if not hlr:
            log.warning("HLR %d not found in SQLite", hlr_id)
            return {"nodes": [], "edges": []}
        seed_qns = {n.qualified_name for n in hlr.nodes}

    if not seed_qns:
        log.warning("HLR %d has no linked nodes in SQLite", hlr_id)
        return {"nodes": [], "edges": []}

    with get_neo4j().session() as session:
        nodes: list[dict] = []
        edges: list[dict] = []
        seen_qns: set[str] = set()

        def _add(d) -> None:
            qn = d.get("qualified_name", d.element_id if hasattr(d, "element_id") else "")
            if qn not in seen_qns:
                seen_qns.add(qn)
                nodes.append(dict(d))

        # Seed nodes
        result = session.run(
            "UNWIND $qns AS qn MATCH (d:Design {qualified_name: qn}) RETURN d",
            {"qns": list(seed_qns)},
        )
        for record in result:
            _add(record["d"])

        # Outgoing edges + neighbour nodes
        edge_out = session.run(
            """
            UNWIND $qns AS qn
            MATCH (s:Design {qualified_name: qn})-[r]->(t:Design)
            WHERE type(r) <> 'IMPLEMENTED_BY'
            RETURN s.qualified_name AS src, t.qualified_name AS tgt, type(r) AS rel_type
            """,
            {"qns": list(seed_qns)},
        )
        for record in edge_out:
            src, tgt, rel = record["src"], record["tgt"], record["rel_type"]
            edges.append({"source": src, "target": tgt, "type": rel})
            if tgt and tgt not in seen_qns:
                nb = session.run(
                    "MATCH (d:Design {qualified_name: $qn}) RETURN d",
                    {"qn": tgt},
                ).single()
                if nb:
                    _add(nb["d"])

        # Incoming edges + source nodes
        edge_in = session.run(
            """
            UNWIND $qns AS qn
            MATCH (s:Design)-[r]->(t:Design {qualified_name: qn})
            WHERE type(r) <> 'IMPLEMENTED_BY'
              AND s.qualified_name <> t.qualified_name
            RETURN s.qualified_name AS src, t.qualified_name AS tgt, type(r) AS rel_type
            """,
            {"qns": list(seed_qns)},
        )
        incoming_seen = set()
        for record in edge_in:
            src, tgt, rel = record["src"], record["tgt"], record["rel_type"]
            edge_key = (src, tgt, rel)
            if edge_key not in incoming_seen:
                incoming_seen.add(edge_key)
                edges.append({"source": src, "target": tgt, "type": rel})
            if src and src not in seen_qns:
                nb = session.run(
                    "MATCH (d:Design {qualified_name: $qn}) RETURN d",
                    {"qn": src},
                ).single()
                if nb:
                    _add(nb["d"])

        # Optional: expand to full component
        if component_id is not None:
            comp_result = session.run(
                """
                MATCH (d:Design {component_id: $cid})
                OPTIONAL MATCH (d)-[r]->(d2:Design {component_id: $cid})
                WHERE type(r) <> 'IMPLEMENTED_BY'
                RETURN d, collect({rel: type(r), target_qn: d2.qualified_name}) AS rels
                """,
                {"cid": component_id},
            )
            for record in comp_result:
                _add(record["d"])
                for item in record["rels"]:
                    if item["rel"] is not None and item["target_qn"]:
                        edges.append({
                            "source": record["d"].get("qualified_name", ""),
                            "target": item["target_qn"],
                            "type": item["rel"],
                        })

    log.debug("fetch_hlr_subgraph: %d nodes, %d edges", len(nodes), len(edges))
    return {"nodes": nodes, "edges": edges}
```

- [ ] **Step 3: Clean up _detect_layer() in detail.py**

In `backend/db/neo4j/queries/detail.py`, simplify `_detect_layer()`:

```python
def _detect_layer(labels: list[str]) -> str:
    if "Design" in labels:
        return "design"
    return "as-built"
```

- [ ] **Step 4: Remove requirements extraction from fetch_node_detail()**

In `fetch_node_detail()` in `backend/db/neo4j/queries/detail.py`:
- Remove the `requirements` list construction that checks for `HLR`/`LLR` labels in incoming relationships
- Remove `requirements` from the return dict

Specifically, remove these lines:

```python
requirements = []
# ... and the loop that checks "HLR" in labels or "LLR" in labels
```

And change the return dict to exclude `requirements`:

```python
return {
    "properties": props,
    "outgoing": relationships_out,
    "incoming": relationships_in,
    # REMOVED: "requirements": requirements,
    "implemented_by": implemented_by,
    "members": members,
    "codebase_members": codebase_members,
    "available_types": available_types,
}
```

- [ ] **Step 5: Commit**

```bash
git add backend/db/neo4j/queries/graph.py backend/db/neo4j/queries/detail.py
git commit -m "refactor: remove _attach_traced_requirements, rewrite fetch_hlr_subgraph, clean detail.py"
```

---

### Task 6: Update Graph Builders and Frontend Data Layer

**Files:**
- Modify: `backend/graph/builders.py`
- Modify: `frontend/data/ontology.py`

- [ ] **Step 1: Update builders.py**

Update the module docstring to remove "requirement nodes":

```python
"""Build Cytoscape.js node/edge dicts from raw Neo4j data."""
```

Update `_build_design_node()` to pass through `requirements` and `is_hlr_highlight`:

```python
def _build_design_node(d: dict) -> dict:
    return {
        "id": d.get("element_id", d.get("qualified_name", "")),
        "label": d.get("name", ""),
        "qualified_name": d.get("qualified_name", ""),
        "kind": d.get("kind", ""),
        "description": d.get("description", ""),
        "component_id": d.get("component_id"),
        "visibility": d.get("visibility", ""),
        "type_signature": d.get("type_signature", ""),
        "layer": "design",
        "requirements": d.get("requirements", []),
        "is_hlr_highlight": d.get("is_hlr_highlight", ""),
    }
```

- [ ] **Step 2: Update frontend/data/ontology.py**

Update `fetch_ontology_graph_data()` to compose the two-stage pipeline:

```python
def fetch_ontology_graph_data(
    layer: str = "design",
    kind_filter: str | None = None,
    search: str | None = None,
    component_id: int | None = None,
    source_filter: str | None = None,
    requirement_tags: str = "hlr",
) -> dict:
    """Fetch graph data for Cytoscape.js rendering.

    Stage 1: Neo4j topology (no requirement data).
    Stage 2: SQLite enrichment (optional HLR tags).
    """
    try:
        from backend.db.neo4j.queries import fetch_design_graph, fetch_dependency_compounds, fetch_codebase_compounds
        from backend.graph import format_cytoscape_graph
        from backend.requirements.services.graph_tags import enrich_with_requirement_tags

        if layer == "design":
            raw = fetch_design_graph(kind_filter, search, component_id)
        elif layer == "dependency":
            raw = fetch_dependency_compounds(search, source_filter)
        else:
            raw = fetch_codebase_compounds(search)

        formatted = format_cytoscape_graph(raw)

        if layer == "design" and requirement_tags != "none":
            enrich_with_requirement_tags(formatted["nodes"], mode=requirement_tags)

        return formatted
    except Exception:
        log.warning("Graph query failed — returning empty graph", exc_info=True)
        return {"nodes": [], "edges": []}
```

Update `fetch_hlr_graph_data()` to use the new pipeline:

```python
def fetch_hlr_graph_data(
    hlr_id: int,
    component_id: int | None = None,
    requirement_tags: str = "hlr",
) -> dict:
    """Fetch the ontology subgraph around an HLR for Cytoscape.js.

    Stage 1: Neo4j fetches seed + 1-hop design nodes.
    Stage 2: SQLite tags the directly-linked seed nodes.
    """
    try:
        from backend.db.neo4j.queries import fetch_hlr_subgraph
        from backend.graph import format_cytoscape_graph
        from backend.requirements.services.graph_tags import tag_direct_nodes_only

        raw = fetch_hlr_subgraph(hlr_id, component_id)
        formatted = format_cytoscape_graph(raw)

        if requirement_tags != "none":
            tag_direct_nodes_only(formatted["nodes"], hlr_id)

        return formatted
    except Exception:
        log.warning("Neo4j HLR subgraph query failed — returning empty graph", exc_info=True)
        return {"nodes": [], "edges": []}
```

- [ ] **Step 3: Commit**

```bash
git add backend/graph/builders.py frontend/data/ontology.py
git commit -m "refactor: two-stage graph pipeline with SQLite enrichment"
```

---

### Task 7: Update Theme, Remove Requirement Layer Styles

**Files:**
- Modify: `frontend/theme.py`

- [ ] **Step 1: Remove requirement-related styles**

In `frontend/theme.py`:
- Remove the `node[layer="requirement"]` style block from `cytoscape_base_styles()`
- Remove the `edge[label="TRACES_TO"]` style block from `cytoscape_base_styles()`
- Remove `"TRACES_TO": "#e67e22"` from `EDGE_COLORS`
- Remove `"requirement": "#e67e22"` and `"requirement_border": "#d35400"` from `STATUS_COLORS`
- Remove `"requirement": {"border_style": "solid", "opacity": 1.0, "shape": "diamond"}` from `LAYER_STYLES`

- [ ] **Step 2: Add HLR highlight and badge styles**

In `frontend/theme.py`, add to `cytoscape_base_styles()`:

Add `"hlr_highlight": "#e67e22"` to `STATUS_COLORS`.

Add two new style blocks in the Cytoscape styles:

```python
# Highlight border for HLR-linked nodes
f"""
{{
    selector: 'node[is_hlr_highlight = "true"]',
    style: {{
        'border-width': 3,
        'border-color': '{sc["hlr_highlight"]}',
        'border-style': 'solid',
    }}
}}""",
# Badge text for nodes with requirements
f"""
{{
    selector: 'node.has-requirements',
    style: {{
        'font-size': '{font_size + 1}px',
    }}
}}""",
```

(Where `sc` is STATUS_COLORS and `font_size` is whatever the current pattern uses.)

- [ ] **Step 3: Commit**

```bash
git add frontend/theme.py
git commit -m "refactor: remove requirement layer styles, add HLR highlight/badge styles"
```

---

### Task 8: Update Frontend Pages

**Files:**
- Modify: `frontend/pages/ontology_graph.py`
- Modify: `frontend/pages/hlr_detail.py`
- Modify: `frontend/pages/node_detail.py`
- Modify: `frontend/widgets.py`

- [ ] **Step 1: Add requirement tags toggle to GraphState and ontology_graph_page**

In `frontend/widgets.py`, add `show_requirement_tags: bool = True` to the `GraphState` dataclass.

In `frontend/pages/ontology_graph.py`:
- Update the `load_graph()` callback to pass `requirement_tags` based on `state.show_requirement_tags`:

```python
requirement_tags = "hlr" if state.show_requirement_tags else "none"
data = await asyncio.to_thread(
    fetch_ontology_graph_data,
    layer=layer,
    kind_filter=state.kind_filter,
    search=search or None,
    source_filter=state.source_filter,
    requirement_tags=requirement_tags,
)
```

- Add a toggle switch in the controls section:

```python
ui.switch("HLR Tags", value=True, on_change=lambda e: setattr(state, 'show_requirement_tags', e.value))
```

- Add JavaScript badge rendering to the `load_graph()` callback (after rendering the graph), or in `render_cytoscape_graph()`:

```python
# After graph rendering:
await ui.run_javascript("""
    if (window._cy) {
        window._cy.nodes().forEach(function(node) {
            const reqs = node.data('requirements');
            if (reqs && reqs.length > 0) {
                const badges = reqs.map(r => '[' + r.type + ' ' + r.id + ']').join(' ');
                node.data('label', node.data('name') + '\\n' + badges);
                node.addClass('has-requirements');
            }
        });
    }
""")
```

- [ ] **Step 2: Update HLR detail page**

In `frontend/pages/hlr_detail.py`:
- Update `fetch_hlr_graph_data` call to pass `requirement_tags="hlr"`:

```python
graph = await asyncio.to_thread(fetch_hlr_graph_data, hlr_id, hlr["component_id"], requirement_tags="hlr")
```

- The graph will now show cleanly linked design nodes with orange-highlighted borders on directly-linked nodes, no HLR diamond.

- [ ] **Step 3: Remove Traced Requirements card from node detail**

In `frontend/pages/node_detail.py`:
- Remove the entire block that renders the "Traced Requirements" card:

```python
# REMOVE THIS BLOCK:
if neo4j.get("requirements"):
    with ui.card().classes("w-full"):
        ui.label("Traced Requirements").classes(CLS_SECTION_HEADER)
        for req in neo4j["requirements"]:
            with ui.row().classes("items-center gap-2 py-1"):
                req_type = req["type"]
                ui.badge(
                    req_type,
                    color="orange" if req_type == "HLR" else "amber",
                ).classes("text-xs")
                ui.label(req.get("name", "")).classes("text-sm")
```

- [ ] **Step 4: Commit**

```bash
git add frontend/pages/ontology_graph.py frontend/pages/hlr_detail.py frontend/pages/node_detail.py frontend/widgets.py
git commit -m "feat: add HLR tags toggle, badge rendering, remove requirement card from node detail"
```

---

### Task 9: Update Frontend Data Layer — Node Detail

**Files:**
- Modify: `frontend/data/ontology.py`

- [ ] **Step 1: Update fetch_node_detail_full() to source requirements from SQLite**

The `fetch_node_detail_full()` function currently calls `fetch_graph_node_detail()` from Neo4j which used to return a `requirements` key. Since we removed that from the Neo4j query, we need to restore requirements data from SQLite instead.

Update `fetch_node_detail_full()` to add requirements from the M2M table:

```python
def fetch_node_detail_full(node_id: int) -> dict | None:
    """Fetch ontology node by SQLite id with all properties + Neo4j relationships."""
    with get_session() as session:
        node = session.query(OntologyNode).filter_by(id=node_id).first()
        if not node:
            return None

        node_data = {
            "id": node.id,
            "name": node.name,
            "qualified_name": node.qualified_name,
            "kind": node.kind,
            # ... all existing fields ...
        }

        # Fetch requirement tags from SQLite M2M (not Neo4j)
        requirements = [
            {"id": hlr.id, "type": "HLR", "description": hlr.description[:80]}
            for hlr in node.high_level_requirements
        ]

    # Fetch Neo4j relationships if available
    neo4j_data = None
    if node_data["qualified_name"]:
        neo4j_data = fetch_graph_node_detail(node_data["qualified_name"])

    return {"node": node_data, "neo4j": neo4j_data, "requirements": requirements}
```

Note: This puts requirements back in the node detail data, but as a separate field sourced from SQLite, not from Neo4j labels. The frontend page has already had the "Traced Requirements" card removed (Task 8), but this data is available if the detail page is later updated to show it differently (e.g., in a badge or tooltip).

- [ ] **Step 2: Commit**

```bash
git add frontend/data/ontology.py
git commit -m "feat: source node requirements from SQLite M2M instead of Neo4j labels"
```

---

### Task 10: End-to-End Verification

**No new code — manual testing**

- [ ] **Step 1: Run the full test suite**

```bash
pytest -v
```

Expected: All tests pass.

- [ ] **Step 2: Start the application and verify the main graph view**

```bash
source .venv/bin/activate && python nicegui_app.py
```

Visit `http://127.0.0.1:8081/ontology/graph`:
- Verify: No diamond-shaped HLR/LLR nodes appear
- Verify: No `TRACES_TO` dashed edges appear
- Verify: HLR tag badges appear on design nodes (with "HLR Tags" toggle on)
- Verify: Toggling "HLR Tags" off removes badges

- [ ] **Step 3: Verify HLR detail page**

Click into an HLR detail page:
- Verify: Design graph shows only design nodes with orange-highlighted borders on linked nodes
- Verify: No HLR diamond node appears in the subgraph

- [ ] **Step 4: Verify node detail page**

Click into a design node detail page:
- Verify: No "Traced Requirements" card in the sidebar
- Verify: Node properties and relationships display correctly

- [ ] **Step 5: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: end-to-end verification adjustments"
```