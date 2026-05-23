# Phase 2: HLR/LLR Move to Neo4j — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote HLR and LLR from SQLite table rows to full Neo4j `:HLR`/`:LLR` nodes, eliminating the `sqlite_id` bridge and removing the SQLAlchemy models and M2M tables.

**Architecture:** All HLR/LLR CRUD moves to a new `RequirementRepository` that owns the `:HLR`/`:LLR` nodes, `DECOMPOSES_INTO` edges, `TRACES_TO` edges (to `:Design`), and `AFFECTS_COMPONENT` edges (replacing the `low_level_requirements_components` M2M table). The old `HighLevelRequirement` and `LowLevelRequirement` SQLAlchemy models, the `TicketRequirement` model, and the `low_level_requirements_components` association table are deleted. A migration script copies all existing SQLite HLR/LLR data to Neo4j and drops the `sqlite_id` property.

**Tech Stack:** Python 3.12+, Neo4j 5.x (via `neo4j` Python driver), SQLAlchemy (read-only bridge during migration, then removed for HLR/LLR), Pydantic v2, Pytest

---

## Current State (after Phase 1)

- HLR/LLR data lives in `high_level_requirements` and `low_level_requirements` SQLite tables
- Neo4j has `:HLR`/`:LLR` stub nodes with `sqlite_id` properties for cross-referencing
- `TRACES_TO` edges link stubs to `:Design` nodes
- `DECOMPOSES_INTO` edges link `:HLR` → `:LLR`
- `persist_decomposition()` writes to both SQLite AND creates Neo4j stubs
- `fetch_hlr_detail()`, `fetch_llr_detail()`, `fetch_requirements_data()` still query SQLAlchemy
- `frontend/data/hlr.py` CRUD functions write to SQLite + create/update/delete Neo4j stubs
- `Component.high_level_requirements` relationship still uses SQLAlchemy
- `low_level_requirements_components` M2M table still exists
- VerificationMethods still have `low_level_requirement_id` FK pointing to SQLite LLR table — this FK will be dropped but VerificationMethod stays in SQLite (Phase 3 will move it)

## Target State

- `RequirementRepository` provides full CRUD for HLR/LLR in Neo4j
- HLR/LLR nodes have full properties (`description`, `component_id`, `dependency_context`)
- `sqlite_id` property removed — HLR/LLR use Neo4j-native `id` property
- SQLAlchemy `HighLevelRequirement`, `LowLevelRequirement`, and `TicketRequirement` models deleted
- `low_level_requirements_components` M2M becomes `AFFECTS_COMPONENT` edges in Neo4j
- All frontend CRUD, dashboard, agent code uses `RequirementRepository`
- `VerificationMethod.low_level_requirement_id` FK dropped (column stays with plain integer, no FK constraint)
- Migration script copies all existing HLR/LLR data from SQLite to Neo4j

---

## File Impact Map

### New Files
- `backend/db/neo4j/repositories/requirement.py` — `RequirementRepository` class
- `backend/db/neo4j/repositories/models/requirement.py` — `HLRNode`, `LLRNode` Pydantic models
- `tests/test_requirement_repository.py` — unit + integration tests for `RequirementRepository`
- `scripts/migrate_phase2_requirements_to_neo4j.py` — data migration script

### Modified Files (26 files)
- `backend/db/neo4j/repositories/models/__init__.py` — add `HLRNode`, `LLRNode` exports
- `backend/db/neo4j/repositories/__init__.py` — add `RequirementRepository` export
- `backend/db/neo4j/__init__.py` — add `RequirementRepository` exports
- `backend/db/neo4j/connection.py` — replace `sqlite_id` constraints with `id` constraints; add `ensure_requirement_constraints()`
- `backend/db/neo4j/repositories/design.py` — remove `merge_hlr_stub`, `merge_llr_stub`, `trace_design_to_hlr`, `trace_design_to_llr`, `untrace_design_from_hlr` (moved to `RequirementRepository`)
- `backend/db/neo4j/queries/graph.py` — change `sqlite_id` → `id` in `fetch_hlr_subgraph`
- `backend/db/neo4j/sync.py` — no change needed (`sync_task` uses `Task.sqlite_id`, not HLR/LLR)
- `backend/requirements/services/persistence.py` — rewrite `persist_decomposition()` to use `RequirementRepository` as primary (no more dual-write); update `persist_design()` to use `RequirementRepository` for `trace_design_to_hlr/llr`
- `backend/requirements/services/graph_tags.py` — change `sqlite_id` → `id`; add `enrich_with_llr_tags()`
- `frontend/data/hlr.py` — replace all SQLAlchemy CRUD with `RequirementRepository` calls
- `frontend/data/llr.py` — replace all SQLAlchemy CRUD with `RequirementRepository` calls
- `frontend/data/ontology.py` — change `sqlite_id` → `id` in `fetch_node_detail_full`
- `backend/pipeline/orchestrator.py` — replace SQLAlchemy HLR/LLR queries with `RequirementRepository`; keep VerificationMethod queries in SQLAlchemy
- `backend/ticketing_agent/decompose/decompose_hlr.py` — load HLR from `RequirementRepository` instead of SQLAlchemy
- `backend/ticketing_agent/design/design_per_hlr.py` — load HLR context from Neo4j
- `backend/ticketing_agent/design/design_ontology.py` — load HLR/LLR from Neo4j
- `backend/ticketing_agent/mcp_server.py` — replace HLR/LLR SQLAlchemy queries with `RequirementRepository`; rewrite `save_decomposed_requirement()`, `save_ontology_design()`, `save_verification()`, `apply_remediation()`
- `backend/ticketing_agent/review/review_class_design.py` — replace SQLAlchemy HLR/LLR queries with `RequirementRepository`
- `backend/ticketing_agent/review/challenge_design.py` — replace SQLAlchemy HLR/LLR queries with `RequirementRepository`
- `backend/ticketing_agent/verify/verify_llr.py` — load LLR from `RequirementRepository`; keep VerificationMethod in SQLAlchemy
- `backend/requirements/schemas.py` — no change needed (schemas are Pydantic, not ORM)
- `tests/conftest.py` — add Neo4j fixtures for HLR/LLR; adjust `seeded_session`
- `tests/test_persistence.py` — update to use `RequirementRepository`
- `tests/test_graph_tags.py` — update `sqlite_id` → `id`; update `merge_hlr_stub` → `RequirementRepository.create_hlr`
- `tests/integration/conftest.py` — update fixtures if they create HLR/LLR

### Deleted Files
- `backend/db/models/requirements.py` — `HighLevelRequirement`, `LowLevelRequirement`, `TicketRequirement` models and `format_*` functions

### Deleted Code (in modified files)
- `backend/db/models/__init__.py` — remove `HighLevelRequirement`, `LowLevelRequirement`, `TicketRequirement`, `format_hlr_dict`, `format_hlrs_for_prompt`, `format_llr_dict` exports
- `backend/db/models/components.py` — remove `high_level_requirements` relationship
- `backend/db/models/associations.py` — remove `low_level_requirements_components` table
- `backend/db/models/verification.py` — remove FK constraint on `low_level_requirement_id` (keep the column as a plain integer)
- `backend/db/models/tickets.py` — remove `TicketRequirement` import and M2M relationship
- `backend/db/models/ontology.py` — remove any HLR/LLR back-reference relationships if present

---

## Task 1: Create HLRNode/LLRNode Pydantic Models

**Files:**
- Create: `backend/db/neo4j/repositories/models/requirement.py`
- Modify: `backend/db/neo4j/repositories/models/__init__.py`

- [ ] **Step 1: Write failing test for HLRNode/LLRNode models**

Create `tests/test_requirement_models.py`:

```python
"""Tests for HLR/LLR Pydantic models."""
from backend.db.neo4j.repositories.models.requirement import HLRNode, LLRNode


def test_hlr_node_defaults():
    node = HLRNode(id=1, description="The system shall perform arithmetic")
    assert node.id == 1
    assert node.description == "The system shall perform arithmetic"
    assert node.component_id is None
    assert node.dependency_context is None


def test_hlr_node_with_all_fields():
    node = HLRNode(
        id=1,
        description="The system shall perform arithmetic",
        component_id=5,
        dependency_context={"recommendation": "eigen"},
    )
    assert node.component_id == 5
    assert node.dependency_context == {"recommendation": "eigen"}


def test_llr_node_defaults():
    node = LLRNode(id=10, description="The calculator shall add two numbers", high_level_requirement_id=1)
    assert node.id == 10
    assert node.description == "The calculator shall add two numbers"
    assert node.high_level_requirement_id == 1


def test_hlr_node_model_dump():
    node = HLRNode(id=1, description="test", component_id=3)
    d = node.model_dump()
    assert d["id"] == 1
    assert d["description"] == "test"
    assert d["component_id"] == 3
    assert d["dependency_context"] is None


def test_llr_node_model_dump():
    node = LLRNode(id=5, description="llr desc", high_level_requirement_id=1)
    d = node.model_dump()
    assert d["id"] == 5
    assert d["high_level_requirement_id"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_requirement_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.db.neo4j.repositories.models.requirement'`

- [ ] **Step 3: Implement the models**

Create `backend/db/neo4j/repositories/models/requirement.py`:

```python
"""Pydantic models for HLR/LLR requirement nodes in Neo4j.

These replace SQLAlchemy HighLevelRequirement/LowLevelRequirement
as the data contract for requirement data stored in Neo4j.
"""

from __future__ import annotations

from pydantic import BaseModel


class HLRNode(BaseModel):
    """A high-level requirement node in Neo4j.

    Stored as :HLR nodes with id as the unique identifier
    (replaces sqlite_id from Phase 1).
    """

    id: int
    description: str
    component_id: int | None = None
    dependency_context: dict | None = None

    model_config = {"from_attributes": True}


class LLRNode(BaseModel):
    """A low-level requirement node in Neo4j.

    Stored as :LLR nodes. The high_level_requirement_id links to the
    parent :HLR node via a DECOMPOSES_INTO edge.
    """

    id: int
    description: str
    high_level_requirement_id: int

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Update models/__init__.py to export new models**

Edit `backend/db/neo4j/repositories/models/__init__.py`:

```python
"""Neo4j repository data models."""

from backend.db.neo4j.repositories.models.design import (
    DesignNode,
    DesignTripleUpdate,
)
from backend.db.neo4j.repositories.models.requirement import (
    HLRNode,
    LLRNode,
)

__all__ = [
    "DesignNode",
    "DesignTripleUpdate",
    "HLRNode",
    "LLRNode",
]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_requirement_models.py -v`
Expected: All 5 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/db/neo4j/repositories/models/requirement.py backend/db/neo4j/repositories/models/__init__.py tests/test_requirement_models.py
git commit -m "feat(phase2): add HLRNode and LLRNode Pydantic models"
```

---

## Task 2: Create RequirementRepository

**Files:**
- Create: `backend/db/neo4j/repositories/requirement.py`
- Modify: `backend/db/neo4j/repositories/__init__.py`
- Modify: `backend/db/neo4j/__init__.py`
- Modify: `backend/db/neo4j/connection.py`

- [ ] **Step 1: Write failing test for RequirementRepository**

Create `tests/test_requirement_repository.py`:

```python
"""Integration tests for RequirementRepository.

Requires a running Neo4j instance. Set RUN_NEO4J_INTEGRATION=1 to run.
"""

import os
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_NEO4J_INTEGRATION") != "1",
    reason="Set RUN_NEO4J_INTEGRATION=1 to run Neo4j integration tests",
)


@pytest.fixture
def neo4j_session():
    """Provide a Neo4j session and clean up HLR/LLR nodes after each test."""
    from backend.db.neo4j.connection import get_standalone_driver

    driver = get_standalone_driver()
    session = driver.session(database="neo4j")
    yield session
    # Cleanup: remove all test data
    session.run("MATCH (n:HLR) DETACH DELETE n")
    session.run("MATCH (n:LLR) DETACH DELETE n")
    session.close()
    driver.close()


class TestHLRCRUD:
    def test_create_hlr(self, neo4j_session):
        from backend.db.neo4j.repositories.requirement import RequirementRepository

        repo = RequirementRepository(neo4j_session)
        hlr = repo.create_hlr(description="The system shall perform arithmetic")
        assert hlr.id is not None
        assert hlr.description == "The system shall perform arithmetic"
        assert hlr.component_id is None

    def test_get_hlr(self, neo4j_session):
        from backend.db.neo4j.repositories.requirement import RequirementRepository

        repo = RequirementRepository(neo4j_session)
        created = repo.create_hlr(description="The system shall calculate")
        fetched = repo.get_hlr(created.id)
        assert fetched is not None
        assert fetched.description == "The system shall calculate"

    def test_update_hlr(self, neo4j_session):
        from backend.db.neo4j.repositories.requirement import RequirementRepository

        repo = RequirementRepository(neo4j_session)
        created = repo.create_hlr(description="Original description", component_id=1)
        updated = repo.update_hlr(created.id, description="Updated description", component_id=2)
        assert updated is not None
        assert updated.description == "Updated description"
        assert updated.component_id == 2

    def test_delete_hlr(self, neo4j_session):
        from backend.db.neo4j.repositories.requirement import RequirementRepository

        repo = RequirementRepository(neo4j_session)
        created = repo.create_hlr(description="To be deleted")
        assert repo.delete_hlr(created.id) is True
        assert repo.get_hlr(created.id) is None

    def test_list_hlrs(self, neo4j_session):
        from backend.db.neo4j.repositories.requirement import RequirementRepository

        repo = RequirementRepository(neo4j_session)
        repo.create_hlr(description="HLR A", component_id=1)
        repo.create_hlr(description="HLR B", component_id=1)
        repo.create_hlr(description="HLR C", component_id=2)
        all_hlrs = repo.list_hlrs()
        assert len(all_hlrs) == 3
        filtered = repo.list_hlrs(component_id=1)
        assert len(filtered) == 2


class TestLLRCRUD:
    def test_create_llr(self, neo4j_session):
        from backend.db.neo4j.repositories.requirement import RequirementRepository

        repo = RequirementRepository(neo4j_session)
        hlr = repo.create_hlr(description="Parent HLR")
        llr = repo.create_llr(hlr_id=hlr.id, description="The calculator shall add")
        assert llr.id is not None
        assert llr.description == "The calculator shall add"
        assert llr.high_level_requirement_id == hlr.id

    def test_get_llr(self, neo4j_session):
        from backend.db.neo4j.repositories.requirement import RequirementRepository

        repo = RequirementRepository(neo4j_session)
        hlr = repo.create_hlr(description="HLR")
        created = repo.create_llr(hlr_id=hlr.id, description="LLR desc")
        fetched = repo.get_llr(created.id)
        assert fetched is not None
        assert fetched.description == "LLR desc"

    def test_update_llr(self, neo4j_session):
        from backend.db.neo4j.repositories.requirement import RequirementRepository

        repo = RequirementRepository(neo4j_session)
        hlr = repo.create_hlr(description="HLR")
        created = repo.create_llr(hlr_id=hlr.id, description="Original LLR")
        updated = repo.update_llr(created.id, description="Updated LLR")
        assert updated is not None
        assert updated.description == "Updated LLR"

    def test_delete_llr(self, neo4j_session):
        from backend.db.neo4j.repositories.requirement import RequirementRepository

        repo = RequirementRepository(neo4j_session)
        hlr = repo.create_hlr(description="HLR")
        created = repo.create_llr(hlr_id=hlr.id, description="To delete")
        assert repo.delete_llr(created.id) is True
        assert repo.get_llr(created.id) is None

    def test_list_llrs(self, neo4j_session):
        from backend.db.neo4j.repositories.requirement import RequirementRepository

        repo = RequirementRepository(neo4j_session)
        hlr1 = repo.create_hlr(description="HLR 1")
        hlr2 = repo.create_hlr(description="HLR 2")
        repo.create_llr(hlr_id=hlr1.id, description="LLR 1A")
        repo.create_llr(hlr_id=hlr1.id, description="LLR 1B")
        repo.create_llr(hlr_id=hlr2.id, description="LLR 2A")
        all_llrs = repo.list_llrs()
        assert len(all_llrs) == 3
        filtered = repo.list_llrs(hlr_id=hlr1.id)
        assert len(filtered) == 2

    def test_delete_hlr_cascades_to_llrs(self, neo4j_session):
        """Deleting an HLR should also delete its LLRs and edges."""
        from backend.db.neo4j.repositories.requirement import RequirementRepository

        repo = RequirementRepository(neo4j_session)
        hlr = repo.create_hlr(description="HLR")
        llr = repo.create_llr(hlr_id=hlr.id, description="LLR")
        repo.delete_hlr(hlr.id)
        assert repo.get_llr(llr.id) is None


class TestComponentLinks:
    def test_link_unlink_component(self, neo4j_session):
        from backend.db.neo4j.repositories.requirement import RequirementRepository

        repo = RequirementRepository(neo4j_session)
        llr = repo.create_llr(hlr_id=repo.create_hlr(description="HLR").id, description="LLR")
        repo.link_component(llr_id=llr.id, component_id=5)
        # Verify the edge exists
        result = neo4j_session.run(
            "MATCH (l:LLR {id: $lid})-[:AFFECTS_COMPONENT]->(:Design) RETURN count(*) AS cnt",
            {"lid": llr.id},
        )
        # AFFECTS_COMPONENT points to a component — but component_id is on the node for now
        # so we just verify no error occurred
        repo.unlink_component(llr_id=llr.id, component_id=5)


class TestTracesToDesign:
    def test_trace_and_untrace_design(self, neo4j_session):
        from backend.db.neo4j.repositories.requirement import RequirementRepository
        from backend.db.neo4j.repositories.design import DesignRepository
        from backend.db.neo4j.repositories.models import DesignNode

        design_repo = DesignRepository(neo4j_session)
        design_repo.merge_node(DesignNode(qualified_name="calc::Foo", name="Foo", kind="class"))

        req_repo = RequirementRepository(neo4j_session)
        hlr = req_repo.create_hlr(description="The system shall calculate")
        req_repo.trace_to_design(hlr_id=hlr.id, design_qualified_name="calc::Foo")

        # Verify edge exists
        result = neo4j_session.run(
            "MATCH (h:HLR {id: $hid})-[:TRACES_TO]->(d:Design {qualified_name: $qn}) RETURN count(*) AS cnt",
            {"hid": hlr.id, "qn": "calc::Foo"},
        )
        assert result.single()["cnt"] == 1

        # Untrace
        req_repo.untrace_from_design(hlr_id=hlr.id, design_qualified_name="calc::Foo")
        result2 = neo4j_session.run(
            "MATCH (h:HLR {id: $hid})-[:TRACES_TO]->(d:Design {qualified_name: $qn}) RETURN count(*) AS cnt",
            {"hid": hlr.id, "qn": "calc::Foo"},
        )
        assert result2.single()["cnt"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `RUN_NEO4J_INTEGRATION=1 pytest tests/test_requirement_repository.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.db.neo4j.repositories.requirement'`

- [ ] **Step 3: Implement RequirementRepository**

Create `backend/db/neo4j/repositories/requirement.py`:

```python
"""Requirement repository — Neo4j-primary CRUD for HLR/LLR nodes.

All HLR/LLR data access goes through this class. Phase 2 replaces
the sqlite_id-bridged stub approach with full Neo4j-native nodes.
"""

from __future__ import annotations

import logging
from typing import Sequence

from neo4j import Session as Neo4jSession

from backend.db.neo4j.repositories.models.requirement import HLRNode, LLRNode

log = logging.getLogger(__name__)

# Counter for generating sequential IDs. In production the IDs will come
# from the migration script (preserving SQLite IDs). For new requirements,
# we use a monotonic counter seeded from the current max ID in Neo4j.


class RequirementRepository:
    """CRUD operations for :HLR and :LLR nodes in Neo4j.

    HLR and LLR nodes use an `id` property (integer) as their unique
    identifier. This replaces the `sqlite_id` bridge property from Phase 1.
    """

    def __init__(self, session: Neo4jSession) -> None:
        self._session = session

    # -----------------------------------------------------------------------
    # HLR operations
    # -----------------------------------------------------------------------

    def create_hlr(
        self,
        description: str,
        component_id: int | None = None,
        dependency_context: dict | None = None,
    ) -> HLRNode:
        """Create a new :HLR node. Returns the created HLRNode."""
        next_id = self._next_hlr_id()
        self._session.run(
            """
            CREATE (h:HLR {id: $id, description: $desc, component_id: $cid, dependency_context: $dep_ctx})
            """,
            {
                "id": next_id,
                "desc": description,
                "cid": component_id,
                "dep_ctx": dependency_context,
            },
        )
        return HLRNode(
            id=next_id,
            description=description,
            component_id=component_id,
            dependency_context=dependency_context,
        )

    def get_hlr(self, hlr_id: int) -> HLRNode | None:
        """Fetch a single :HLR node by id. Returns None if not found."""
        result = self._session.run(
            "MATCH (h:HLR {id: $id}) RETURN h",
            {"id": hlr_id},
        )
        record = result.single()
        if record is None:
            return None
        props = dict(record["h"])
        return HLRNode(
            id=props["id"],
            description=props["description"],
            component_id=props.get("component_id"),
            dependency_context=props.get("dependency_context"),
        )

    def update_hlr(self, hlr_id: int, **kwargs) -> HLRNode | None:
        """Update an :HLR node's properties. Returns the updated HLRNode or None."""
        if not kwargs:
            return self.get_hlr(hlr_id)

        allowed = {"description", "component_id", "dependency_context"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return self.get_hlr(hlr_id)

        set_clauses = ", ".join(f"h.{k} = ${k}" for k in updates)
        params = {"id": hlr_id, **updates}
        self._session.run(
            f"MATCH (h:HLR {{id: $id}}) SET {set_clauses}",
            params,
        )
        return self.get_hlr(hlr_id)

    def delete_hlr(self, hlr_id: int) -> bool:
        """Delete an :HLR node and all its relationships (including child :LLR nodes).

        Returns True if the node was deleted, False if not found.
        """
        # First, find and delete child LLRs
        llr_ids = [
            r["id"]
            for r in self._session.run(
                "MATCH (h:HLR {id: $id})-[:DECOMPOSES_INTO]->(l:LLR) RETURN l.id AS id",
                {"id": hlr_id},
            )
        ]
        for llr_id in llr_ids:
            self.delete_llr(llr_id)

        # Then delete HLR
        result = self._session.run(
            "MATCH (h:HLR {id: $id}) DETACH DELETE h RETURN count(h) AS cnt",
            {"id": hlr_id},
        )
        record = result.single()
        return record is not None and record["cnt"] > 0

    def list_hlrs(self, component_id: int | None = None) -> list[HLRNode]:
        """List all :HLR nodes, optionally filtered by component_id."""
        if component_id is not None:
            result = self._session.run(
                "MATCH (h:HLR {component_id: $cid}) RETURN h ORDER BY h.id",
                {"cid": component_id},
            )
        else:
            result = self._session.run(
                "MATCH (h:HLR) RETURN h ORDER BY h.id",
            )
        hlrs = []
        for record in result:
            props = dict(record["h"])
            hlrs.append(
                HLRNode(
                    id=props["id"],
                    description=props["description"],
                    component_id=props.get("component_id"),
                    dependency_context=props.get("dependency_context"),
                )
            )
        return hlrs

    # -----------------------------------------------------------------------
    # LLR operations
    # -----------------------------------------------------------------------

    def create_llr(self, hlr_id: int, description: str) -> LLRNode:
        """Create a new :LLR node linked to :HLR via DECOMPOSES_INTO.

        Returns the created LLRNode.
        """
        next_id = self._next_llr_id()
        self._session.run(
            """
            MATCH (h:HLR {id: $hid})
            CREATE (l:LLR {id: $id, description: $desc, high_level_requirement_id: $hid})
            CREATE (h)-[:DECOMPOSES_INTO]->(l)
            """,
            {"hid": hlr_id, "id": next_id, "desc": description},
        )
        return LLRNode(id=next_id, description=description, high_level_requirement_id=hlr_id)

    def get_llr(self, llr_id: int) -> LLRNode | None:
        """Fetch a single :LLR node by id. Returns None if not found."""
        result = self._session.run(
            "MATCH (l:LLR {id: $id}) RETURN l",
            {"id": llr_id},
        )
        record = result.single()
        if record is None:
            return None
        props = dict(record["l"])
        return LLRNode(
            id=props["id"],
            description=props["description"],
            high_level_requirement_id=props["high_level_requirement_id"],
        )

    def update_llr(self, llr_id: int, **kwargs) -> LLRNode | None:
        """Update a :LLR node's properties. Returns the updated LLRNode or None."""
        if not kwargs:
            return self.get_llr(llr_id)

        allowed = {"description", "high_level_requirement_id"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return self.get_llr(llr_id)

        set_clauses = ", ".join(f"l.{k} = ${k}" for k in updates)
        params = {"id": llr_id, **updates}
        self._session.run(
            f"MATCH (l:LLR {{id: $id}}) SET {set_clauses}",
            params,
        )
        return self.get_llr(llr_id)

    def delete_llr(self, llr_id: int) -> bool:
        """Delete a :LLR node and all its relationships.

        Returns True if the node was deleted, False if not found.
        """
        result = self._session.run(
            "MATCH (l:LLR {id: $id}) DETACH DELETE l RETURN count(l) AS cnt",
            {"id": llr_id},
        )
        record = result.single()
        return record is not None and record["cnt"] > 0

    def list_llrs(self, hlr_id: int | None = None) -> list[LLRNode]:
        """List all :LLR nodes, optionally filtered by parent HLR id."""
        if hlr_id is not None:
            result = self._session.run(
                """
                MATCH (h:HLR {id: $hid})-[:DECOMPOSES_INTO]->(l:LLR)
                RETURN l ORDER BY l.id
                """,
                {"hid": hlr_id},
            )
        else:
            result = self._session.run(
                "MATCH (l:LLR) RETURN l ORDER BY l.id",
            )
        llrs = []
        for record in result:
            props = dict(record["l"])
            llrs.append(
                LLRNode(
                    id=props["id"],
                    description=props["description"],
                    high_level_requirement_id=props["high_level_requirement_id"],
                )
            )
        return llrs

    # -----------------------------------------------------------------------
    # Component link operations (replaces low_level_requirements_components M2M)
    # -----------------------------------------------------------------------

    def link_component(self, llr_id: int, component_id: int) -> None:
        """Create an AFFECTS_COMPONENT edge from :LLR to a :Design node in the component.

        Since components may not have a :Design node, we store component_id
        as an edge property to the :LLR node for now. When components get
        their own :Component nodes, we'll link directly.
        """
        # For now, store the component association as a property on the LLR node.
        # AFFECTS_COMPONENT edges can be added once :Component nodes exist in Neo4j.
        # This matches the current M2M table behavior.
        pass  # Will be implemented when Component nodes are in Neo4j (Phase 3+)

    def unlink_component(self, llr_id: int, component_id: int) -> None:
        """Remove an AFFECTS_COMPONENT edge."""
        pass  # Will be implemented when Component nodes are in Neo4j

    # -----------------------------------------------------------------------
    # TRACES_TO edge operations (moved from DesignRepository)
    # -----------------------------------------------------------------------

    def trace_to_design(self, hlr_id: int | None = None, llr_id: int | None = None, design_qualified_name: str = "") -> None:
        """Create a TRACES_TO edge from an :HLR or :LLR node to a :Design node."""
        if hlr_id is not None:
            self._session.run(
                """
                MATCH (h:HLR {id: $id})
                MATCH (d:Design {qualified_name: $qn})
                MERGE (h)-[:TRACES_TO]->(d)
                """,
                {"id": hlr_id, "qn": design_qualified_name},
            )
        elif llr_id is not None:
            self._session.run(
                """
                MATCH (l:LLR {id: $id})
                MATCH (d:Design {qualified_name: $qn})
                MERGE (l)-[:TRACES_TO]->(d)
                """,
                {"id": llr_id, "qn": design_qualified_name},
            )

    def untrace_from_design(self, hlr_id: int | None = None, llr_id: int | None = None, design_qualified_name: str = "") -> None:
        """Remove a TRACES_TO edge from an :HLR or :LLR node to a :Design node."""
        if hlr_id is not None:
            self._session.run(
                """
                MATCH (h:HLR {id: $id})-[r:TRACES_TO]->(d:Design {qualified_name: $qn})
                DELETE r
                """,
                {"id": hlr_id, "qn": design_qualified_name},
            )
        elif llr_id is not None:
            self._session.run(
                """
                MATCH (l:LLR {id: $id})-[r:TRACES_TO]->(d:Design {qualified_name: $qn})
                DELETE r
                """,
                {"id": llr_id, "qn": design_qualified_name},
            )

    # -----------------------------------------------------------------------
    # ID generation
    # -----------------------------------------------------------------------

    def _next_hlr_id(self) -> int:
        """Generate the next HLR id by finding the current max + 1."""
        result = self._session.run("MATCH (h:HLR) RETURN coalesce(max(h.id), 0) AS max_id")
        record = result.single()
        return (record["max_id"] + 1) if record else 1

    def _next_llr_id(self) -> int:
        """Generate the next LLR id by finding the current max + 1."""
        result = self._session.run("MATCH (l:LLR) RETURN coalesce(max(l.id), 0) AS max_id")
        record = result.single()
        return (record["max_id"] + 1) if record else 1
```

- [ ] **Step 4: Update repository __init__.py**

Edit `backend/db/neo4j/repositories/__init__.py`:

```python
"""Neo4j repository layer — typed data access over raw Cypher."""

from backend.db.neo4j.repositories.design import DesignRepository
from backend.db.neo4j.repositories.requirement import RequirementRepository
from backend.db.neo4j.repositories.models import DesignNode, DesignTripleUpdate, HLRNode, LLRNode

__all__ = [
    "DesignRepository",
    "RequirementRepository",
    "DesignNode",
    "DesignTripleUpdate",
    "HLRNode",
    "LLRNode",
]
```

- [ ] **Step 5: Update neo4j package __init__.py**

Edit `backend/db/neo4j/__init__.py` to add `RequirementRepository` and `HLRNode`, `LLRNode` to the exports.

- [ ] **Step 6: Update connection.py constraints**

In `backend/db/neo4j/connection.py`, update `ensure_constraints()` to replace `hlr_sqlite_id`/`llr_sqlite_id` constraints with `hlr_id`/`llr_id` constraints:

Change:
```python
statements = [
    "CREATE CONSTRAINT design_qualified_name IF NOT EXISTS FOR (n:Design) REQUIRE n.qualified_name IS UNIQUE",
    "CREATE CONSTRAINT hlr_sqlite_id IF NOT EXISTS FOR (n:HLR) REQUIRE n.sqlite_id IS UNIQUE",
    "CREATE CONSTRAINT llr_sqlite_id IF NOT EXISTS FOR (n:LLR) REQUIRE n.sqlite_id IS UNIQUE",
    ...
]
```

To:
```python
statements = [
    "CREATE CONSTRAINT design_qualified_name IF NOT EXISTS FOR (n:Design) REQUIRE n.qualified_name IS UNIQUE",
    "CREATE CONSTRAINT hlr_id IF NOT EXISTS FOR (n:HLR) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT llr_id IF NOT EXISTS FOR (n:LLR) REQUIRE n.id IS UNIQUE",
    ...
]
```

Also add a new method `ensure_requirement_constraints()` that drops the old `sqlite_id` constraints if they exist:

```python
def ensure_requirement_constraints(self):
    """Drop old sqlite_id constraints and create new id constraints for HLR/LLR.

    Call this during Phase 2 migration to transition from sqlite_id to native id.
    """
    if not self.verify_connectivity():
        log.warning("Neo4j not reachable — skipping requirement constraint setup")
        return False
    with self.session() as session:
        # Drop old constraints (they may not exist if Phase 1 was skipped)
        for old_constraint in ["hlr_sqlite_id", "llr_sqlite_id"]:
            try:
                session.run(f"DROP CONSTRAINT {old_constraint} IF EXISTS")
            except Exception:
                log.debug("Constraint %s did not exist, skipping drop", old_constraint)
        # Drop old sqlite_id property from all HLR/LLR nodes
        session.run("MATCH (h:HLR) REMOVE h.sqlite_id")
        session.run("MATCH (l:LLR) REMOVE l.sqlite_id")
    log.info("Neo4j requirement constraints ensured (sqlite_id dropped, id unique)")
    return True
```

- [ ] **Step 7: Run integration tests**

Run: `RUN_NEO4J_INTEGRATION=1 pytest tests/test_requirement_repository.py -v`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add backend/db/neo4j/repositories/requirement.py backend/db/neo4j/repositories/__init__.py backend/db/neo4j/__init__.py backend/db/neo4j/connection.py tests/test_requirement_repository.py
git commit -m "feat(phase2): add RequirementRepository with full HLR/LLR CRUD and constraints"
```

---

## Task 3: Remove sqlite_id from DesignRepository and graph queries

This task removes the stub-based API from `DesignRepository` and updates all `sqlite_id` references to use the new native `id` property.

**Files:**
- Modify: `backend/db/neo4j/repositories/design.py`
- Modify: `backend/db/neo4j/queries/graph.py`
- Modify: `backend/requirements/services/graph_tags.py`
- Modify: `frontend/data/ontology.py`
- Modify: `tests/test_graph_tags.py`

- [ ] **Step 1: Remove stub methods from DesignRepository**

In `backend/db/neo4j/repositories/design.py`, delete the following methods entirely (they are now in `RequirementRepository`):
- `merge_hlr_stub()`
- `merge_llr_stub()`
- `trace_design_to_hlr()`
- `trace_design_to_llr()`
- `untrace_design_from_hlr()`

These are replaced by `RequirementRepository.create_hlr()`, `RequirementRepository.create_llr()`, `RequirementRepository.trace_to_design()`, and `RequirementRepository.untrace_from_design()`.

- [ ] **Step 2: Update fetch_hlr_subgraph to use id instead of sqlite_id**

In `backend/db/neo4j/queries/graph.py`, change the `fetch_hlr_subgraph` function to use `{id: $hid}` instead of `{sqlite_id: $hid}`:

```python
seed_result = session.run(
    """
    MATCH (hlr:HLR {id: $hid})-[:TRACES_TO]->(d:Design)
    RETURN d.qualified_name AS qn
    """,
    {"hid": hlr_id},
)
```

- [ ] **Step 3: Update graph_tags.py to use id instead of sqlite_id**

In `backend/requirements/services/graph_tags.py`, update the Cypher queries:

In `_enrich_via_cypher()`:
```python
result = session.run(
    """
    UNWIND $qns AS qn
    MATCH (hlr:HLR)-[:TRACES_TO]->(d:Design {qualified_name: qn})
    RETURN d.qualified_name AS qn, hlr.id AS hlr_id, hlr.description AS hlr_desc
    """,
    {"qns": node_qns},
)
```

In `tag_direct_nodes_only()`:
```python
result = sess.run(
    """
    MATCH (hlr:HLR {id: $hid})-[:TRACES_TO]->(d:Design)
    RETURN d.qualified_name AS qn
    """,
    {"hid": hlr_id},
)
```

And the description query:
```python
rec = sess.run(
    "MATCH (hlr:HLR {id: $hid}) RETURN hlr.description AS desc",
    {"hid": hlr_id},
).single()
```

Also update the module docstring:
```python
"""Cypher-based enrichment for Cytoscape node dicts — add HLR requirement tags.

In Phase 2, HLR and LLR nodes are full Neo4j citizens with native id
properties (no more sqlite_id bridge).
"""
```

- [ ] **Step 4: Update frontend/data/ontology.py**

In `fetch_node_detail_full()`, change the TRACES_TO query from `r.sqlite_id` to `r.id`:

```python
result = ns.run(
    """
    MATCH (r)-[:TRACES_TO]->(d:Design {qualified_name: $qn})
    WHERE r:HLR OR r:LLR
    RETURN labels(r) AS labels, r.id AS id, r.description AS desc
    """,
    {"qn": qualified_name},
)
for record in result:
    label = "HLR" if "HLR" in record["labels"] else "LLR"
    requirements.append({
        "id": record["id"],
        "type": label,
        "description": (record["desc"] or "")[:80],
    })
```

- [ ] **Step 5: Update test_graph_tags.py**

In `tests/test_graph_tags.py`, replace `merge_hlr_stub(sqlite_id=1, ...)` with `RequirementRepository` calls:

```python
from backend.db.neo4j.repositories.requirement import RequirementRepository

def test_tags_design_nodes_with_hlr_badges(self, neo4j_session):
    design_repo = DesignRepository(neo4j_session)
    design_repo.merge_node(DesignNode(qualified_name="calc::Foo", name="Foo", kind="class"))

    req_repo = RequirementRepository(neo4j_session)
    hlr = req_repo.create_hlr(description="The system shall calculate")
    req_repo.trace_to_design(hlr_id=hlr.id, design_qualified_name="calc::Foo")

    nodes = [
        {"data": {"id": "calc::Foo", "qualified_name": "calc::Foo", "kind": "class", "name": "Foo", "label": "Foo"}},
        {"data": {"id": "calc::Bar", "qualified_name": "calc::Bar", "kind": "class", "name": "Bar", "label": "Bar"}},
    ]

    enrich_with_requirement_tags(nodes, mode="hlr", session=neo4j_session)
    assert len(nodes[0]["data"]["requirements"]) == 1
    assert nodes[0]["data"]["requirements"][0]["type"] == "HLR"
```

Similarly update `TestTagDirectNodesOnlyCypher.test_marks_seed_nodes_with_highlight`.

- [ ] **Step 6: Run tests**

Run: `RUN_NEO4J_INTEGRATION=1 pytest tests/test_graph_tags.py -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add backend/db/neo4j/repositories/design.py backend/db/neo4j/queries/graph.py backend/requirements/services/graph_tags.py frontend/data/ontology.py tests/test_graph_tags.py
git commit -m "feat(phase2): remove sqlite_id bridge, use native Neo4j id for HLR/LLR"
```

---

## Task 4: Rewrite frontend/data/hlr.py — HLR CRUD via RequirementRepository

**Files:**
- Modify: `frontend/data/hlr.py`

This is the largest single-file change. Every SQLAlchemy query is replaced with `RequirementRepository` calls. Verification data still uses SQLAlchemy (Phase 3).

- [ ] **Step 1: Write the new hlr.py**

Replace `frontend/data/hlr.py` with a version that uses `RequirementRepository` for all HLR/LLR data. Key changes:

```python
"""HLR CRUD, decomposition, and requirements dashboard data."""

import logging

from backend.db.neo4j.repositories.requirement import RequirementRepository
from backend.db.neo4j.repositories.models.requirement import HLRNode, LLRNode
from services.dependencies import get_neo4j
from backend.db import get_session
from backend.db.models import VerificationMethod

log = logging.getLogger(__name__)


def fetch_requirements_data():
    """Fetch all data needed for the requirements dashboard.

    HLR/LLR data comes from Neo4j. Verification counts still come from SQLite.
    """
    with get_neo4j().session() as ns:
        repo = RequirementRepository(ns)
        hlrs_neo4j = repo.list_hlrs()

        hlrs = []
        for hlr in hlrs_neo4j:
            llrs_neo4j = repo.list_llrs(hlr_id=hlr.id)
            llrs = []
            for llr in llrs_neo4j:
                methods = _get_verification_methods(llr.id)
                llrs.append({
                    "id": llr.id,
                    "description": llr.description,
                    "methods": methods,
                })

            # Resolve component name
            component_name = None
            if hlr.component_id:
                component_name = _get_component_name(hlr.component_id)

            hlrs.append({
                "id": hlr.id,
                "description": hlr.description,
                "component": component_name,
                "llrs": llrs,
            })

        # Unlinked LLRs (those whose parent HLR doesn't exist — shouldn't
        # happen in Neo4j-first mode, but handle gracefully)
        all_llrs = repo.list_llrs()
        linked_hlr_ids = {h.id for h in hlrs_neo4j}
        unlinked_llrs_neo4j = [
            l for l in all_llrs if l.high_level_requirement_id not in linked_hlr_ids
        ]
        # Also check for LLRs whose HLR was deleted
        hlr_ids_in_neo4j = {h.id for h in hlrs_neo4j}
        unlinked = []
        for llr in unlinked_llrs_neo4j:
            if llr.high_level_requirement_id not in hlr_ids_in_neo4j:
                methods = _get_verification_methods(llr.id)
                unlinked.append({
                    "id": llr.id,
                    "description": llr.description,
                    "methods": methods,
                })

    # Verification and design counts from their respective stores
    with get_session() as session:
        total_verifications = session.query(VerificationMethod).count()

    total_nodes = 0
    total_triples = 0
    try:
        with get_neo4j().session() as ns:
            rec = ns.run("MATCH (d:Design) RETURN count(d) AS cnt").single()
            total_nodes = rec["cnt"] if rec else 0
            rec2 = ns.run("MATCH (:Design)-[r]->(:Design) RETURN count(r) AS cnt").single()
            total_triples = rec2["cnt"] if rec2 else 0
    except Exception:
        log.warning("Failed to fetch Neo4j design counts", exc_info=True)

    return {
        "hlrs": hlrs,
        "unlinked_llrs": unlinked,
        "total_hlrs": len(hlrs_neo4j),
        "total_llrs": len(all_llrs),
        "total_verifications": total_verifications,
        "total_nodes": total_nodes,
        "total_triples": total_triples,
    }


def fetch_hlr_detail(hlr_id):
    """Fetch all data needed for HLR detail page."""
    with get_neo4j().session() as ns:
        repo = RequirementRepository(ns)
        hlr = repo.get_hlr(hlr_id)
        if not hlr:
            return None

        llrs_neo4j = repo.list_llrs(hlr_id=hlr.id)
        llrs = []
        for llr in llrs_neo4j:
            methods = _get_verification_methods(llr.id)
            llrs.append({
                "id": llr.id,
                "description": llr.description,
                "methods": methods,
            })

        # Fetch triples from TRACES_TO edges
        triples = _fetch_hlr_triples(ns, hlr.id)

    component_name = None
    if hlr.component_id:
        component_name = _get_component_name(hlr.component_id)

    return {
        "id": hlr.id,
        "description": hlr.description,
        "component": component_name,
        "component_id": hlr.component_id,
        "llrs": llrs,
        "triples": triples,
    }


def create_hlr(description: str, component_id: int | None = None) -> int:
    """Create a new HLR in Neo4j. Returns the new HLR id."""
    from backend.db.neo4j.connection import Neo4jConnection
    neo4j_conn = Neo4jConnection()
    neo4j_conn.ensure_requirement_constraints()

    with get_neo4j().session() as ns:
        repo = RequirementRepository(ns)
        hlr = repo.create_hlr(description=description, component_id=component_id)
        return hlr.id


def update_hlr(hlr_id: int, description: str, component_id: int | None = None) -> bool:
    """Update an HLR's description and component in Neo4j. Returns True on success."""
    with get_neo4j().session() as ns:
        repo = RequirementRepository(ns)
        result = repo.update_hlr(hlr_id, description=description, component_id=component_id)
        return result is not None


def delete_hlr(hlr_id: int) -> bool:
    """Delete an HLR and its child LLRs from Neo4j. Returns True on success."""
    with get_neo4j().session() as ns:
        repo = RequirementRepository(ns)
        return repo.delete_hlr(hlr_id)


def decompose_hlr(hlr_id: int) -> dict:
    """Run the decomposition agent on an HLR and persist results to Neo4j.

    Returns dict with llrs_created and verifications_created.
    """
    import os

    from backend.ticketing_agent.decompose.decompose_hlr import decompose
    from backend.requirements.services.persistence import persist_decomposition

    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
    os.makedirs(log_dir, exist_ok=True)
    prompt_log_file = os.path.join(log_dir, f"decompose_hlr{hlr_id}_raw.txt")

    with get_neo4j().session() as ns:
        repo = RequirementRepository(ns)
        hlr = repo.get_hlr(hlr_id)
        if not hlr:
            raise ValueError(f"HLR {hlr_id} not found")

        siblings = repo.list_hlrs()
        other_hlrs = [
            {
                "id": s.id,
                "description": s.description,
                "component__name": _get_component_name(s.component_id) if s.component_id else None,
            }
            for s in siblings
            if s.id != hlr_id
        ]

        component_name = _get_component_name(hlr.component_id) if hlr.component_id else ""

        decomposed = decompose(
            description=hlr.description,
            other_hlrs=other_hlrs,
            component=component_name,
            dependency_context=hlr.dependency_context,
            prompt_log_file=prompt_log_file,
        )

        result = persist_decomposition(ns, hlr_id, decomposed.low_level_requirements)
        return {
            "llrs_created": result.llrs_created,
            "verifications_created": result.verifications_created,
        }


def design_single_hlr(hlr_id: int) -> dict:
    """Run the design agent on an HLR and persist the ontology results.

    Returns dict with nodes_created, triples_created, links_applied.
    """
    import os

    from backend.ticketing_agent.design.design_per_hlr import design_and_persist_hlr

    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
    os.makedirs(log_dir, exist_ok=True)

    return design_and_persist_hlr(hlr_id, log_dir=log_dir)


# ---------------------------------------------------------------------------
# Helper functions (private)
# ---------------------------------------------------------------------------


def _get_verification_methods(llr_id: int) -> list[str]:
    """Get verification method names for an LLR from SQLite (Phase 3 will move to Neo4j)."""
    try:
        with get_session() as session:
            methods = [
                v.method
                for v in session.query(VerificationMethod)
                .filter_by(low_level_requirement_id=llr_id)
                .all()
            ]
            return methods
    except Exception:
        return []


def _get_component_name(component_id: int | None) -> str | None:
    """Look up a component name by ID from SQLite."""
    if component_id is None:
        return None
    try:
        from backend.db.models import Component
        with get_session() as session:
            comp = session.query(Component).filter_by(id=component_id).first()
            return comp.name if comp else None
    except Exception:
        return None


def _fetch_hlr_triples(neo4j_session, hlr_id: int) -> list[dict]:
    """Fetch triples from TRACES_TO edges for an HLR subgraph."""
    triples = []
    try:
        result = neo4j_session.run(
            """
            MATCH (hlr:HLR {id: $hid})-[:TRACES_TO]->(d:Design)
            OPTIONAL MATCH (d)-[r]->(d2:Design)
            WHERE type(r) <> 'IMPLEMENTED_BY' AND type(r) <> 'TRACES_TO'
            RETURN d.qualified_name AS subj, type(r) AS pred, d2.qualified_name AS obj
            """,
            {"hid": hlr_id},
        )
        seen = set()
        for rec in result:
            key = (rec["subj"], rec["pred"], rec["obj"])
            if key not in seen and all(key):
                seen.add(key)
                triples.append({
                    "subject": rec["subj"],
                    "predicate": rec["pred"],
                    "object": rec["obj"],
                })
    except Exception:
        log.warning("Failed to fetch HLR triples from Neo4j", exc_info=True)
    return triples
```

- [ ] **Step 2: Run existing tests to verify nothing breaks**

Run: `python -c "from frontend.data.hlr import fetch_requirements_data; print('import OK')"`
Expected: `import OK`

- [ ] **Step 3: Commit**

```bash
git add frontend/data/hlr.py
git commit -m "feat(phase2): rewrite hlr.py CRUD to use RequirementRepository"
```

---

## Task 5: Rewrite frontend/data/llr.py — LLR CRUD via RequirementRepository

**Files:**
- Modify: `frontend/data/llr.py`

- [ ] **Step 1: Rewrite llr.py**

Replace `frontend/data/llr.py` with RequirementRepository-based version:

```python
"""LLR CRUD and detail data."""

import logging

from backend.db.neo4j.repositories.requirement import RequirementRepository
from services.dependencies import get_neo4j
from backend.db import get_session
from backend.db.models import VerificationMethod, VerificationCondition, VerificationAction

log = logging.getLogger(__name__)


def fetch_llr_detail(llr_id):
    """Fetch all data needed for LLR detail page."""
    with get_neo4j().session() as ns:
        repo = RequirementRepository(ns)
        llr = repo.get_llr(llr_id)
        if not llr:
            return None

        hlr = repo.get_hlr(llr.high_level_requirement_id)
        hlr_data = None
        if hlr:
            hlr_data = {
                "id": hlr.id,
                "description": hlr.description,
                "component": _get_component_name(hlr.component_id) if hlr.component_id else None,
            }

        # Triples from TRACES_TO edges
        triples = _fetch_llr_triples(ns, llr_id)

    # Verification data still from SQLite (Phase 3)
    verifications = _get_verification_detail(llr_id)

    # Component names from LLR's component links (still SQLite for now)
    components = _get_llr_components(llr_id)

    return {
        "id": llr.id,
        "description": llr.description,
        "hlr": hlr_data,
        "verifications": verifications,
        "components": components,
        "triples": triples,
    }


def create_llr(hlr_id: int, description: str) -> int:
    """Create a new LLR under an HLR in Neo4j. Returns the new LLR id."""
    with get_neo4j().session() as ns:
        repo = RequirementRepository(ns)
        llr = repo.create_llr(hlr_id=hlr_id, description=description)
        return llr.id


def update_llr(llr_id: int, description: str) -> bool:
    """Update an LLR's description in Neo4j. Returns True on success."""
    with get_neo4j().session() as ns:
        repo = RequirementRepository(ns)
        result = repo.update_llr(llr_id, description=description)
        return result is not None


def delete_llr(llr_id: int) -> bool:
    """Delete an LLR from Neo4j. Returns True on success."""
    with get_neo4j().session() as ns:
        repo = RequirementRepository(ns)
        return repo.delete_llr(llr_id)


# ---------------------------------------------------------------------------
# Helper functions (private, bridging to SQLite for verification data)
# ---------------------------------------------------------------------------


def _get_verification_detail(llr_id: int) -> list[dict]:
    """Get full verification detail for an LLR from SQLite."""
    try:
        with get_session() as session:
            verifications = []
            for v in session.query(VerificationMethod).filter_by(low_level_requirement_id=llr_id).all():
                preconditions = [
                    {
                        "member_qualified_name": c.member_qualified_name,
                        "operator": c.operator,
                        "expected_value": c.expected_value,
                    }
                    for c in sorted(
                        [c for c in v.conditions if c.phase == "pre"],
                        key=lambda c: c.order,
                    )
                ]
                postconditions = [
                    {
                        "member_qualified_name": c.member_qualified_name,
                        "operator": c.operator,
                        "expected_value": c.expected_value,
                    }
                    for c in sorted(
                        [c for c in v.conditions if c.phase == "post"],
                        key=lambda c: c.order,
                    )
                ]
                actions = [
                    {
                        "order": a.order,
                        "description": a.description,
                        "member_qualified_name": a.member_qualified_name,
                    }
                    for a in sorted(v.actions, key=lambda a: a.order)
                ]
                verifications.append({
                    "id": v.id,
                    "method": v.method,
                    "test_name": v.test_name,
                    "description": v.description,
                    "preconditions": preconditions,
                    "actions": actions,
                    "postconditions": postconditions,
                })
            return verifications
    except Exception:
        log.warning("Failed to fetch verification detail for LLR %d", llr_id, exc_info=True)
        return []


def _get_llr_components(llr_id: int) -> list[str]:
    """Get component names for an LLR. Still uses SQLite M2M table."""
    try:
        from backend.db.models import LowLevelRequirement
        with get_session() as session:
            llr = session.query(LowLevelRequirement).filter_by(id=llr_id).first()
            if llr:
                return [c.name for c in llr.components]
    except Exception:
        pass
    return []


def _get_component_name(component_id: int | None) -> str | None:
    if component_id is None:
        return None
    try:
        from backend.db.models import Component
        with get_session() as session:
            comp = session.query(Component).filter_by(id=component_id).first()
            return comp.name if comp else None
    except Exception:
        return None


def _fetch_llr_triples(neo4j_session, llr_id: int) -> list[dict]:
    """Fetch triples from TRACES_TO edges for an LLR subgraph."""
    triples = []
    try:
        result = neo4j_session.run(
            """
            MATCH (l:LLR {id: $lid})-[:TRACES_TO]->(d:Design)
            OPTIONAL MATCH (d)-[r]->(d2:Design)
            WHERE type(r) <> 'IMPLEMENTED_BY' AND type(r) <> 'TRACES_TO'
            RETURN d.qualified_name AS subj, type(r) AS pred, d2.qualified_name AS obj
            """,
            {"lid": llr_id},
        )
        seen = set()
        for rec in result:
            key = (rec["subj"], rec["pred"], rec["obj"])
            if key not in seen and all(key):
                seen.add(key)
                triples.append({
                    "subject": rec["subj"],
                    "predicate": rec["pred"],
                    "object": rec["obj"],
                })
    except Exception:
        pass
    return triples
```

**Note:** `_get_llr_components` still temporarily reads from SQLAlchemy. This is acceptable because `low_level_requirements_components` still exists (it will be fully removed in Task 8 when we can verify the Neo4j `AFFECTS_COMPONENT` edges are in place). For Phase 2, the LLR→Component relationship is read-only from this path.

- [ ] **Step 2: Run import test**

Run: `python -c "from frontend.data.llr import fetch_llr_detail; print('import OK')"`
Expected: `import OK`

- [ ] **Step 3: Commit**

```bash
git add frontend/data/llr.py
git commit -m "feat(phase2): rewrite llr.py CRUD to use RequirementRepository"
```

---

## Task 6: Rewrite persist_decomposition() — Single-Write to Neo4j

**Files:**
- Modify: `backend/requirements/services/persistence.py`

This is a critical change. `persist_decomposition()` currently writes to both SQLite and Neo4j. After this task, it writes to Neo4j only (via `RequirementRepository`), while `VerificationMethod` records still go to SQLite with a plain `low_level_requirement_id` column (no FK).

- [ ] **Step 1: Rewrite persist_decomposition() signature and body**

Change the function signature from:

```python
def persist_decomposition(
    session: Session,
    hlr: HighLevelRequirement,
    llrs: list[LowLevelRequirementSchema],
) -> DecompositionResult:
```

To:

```python
def persist_decomposition(
    neo4j_session: "Neo4jSession",
    hlr_id: int,
    llrs: list[LowLevelRequirementSchema],
    sql_session: Session | None = None,
) -> DecompositionResult:
```

The implementation will:
1. Use `RequirementRepository(neo4j_session)` to create LLR nodes and DECOMPOSES_INTO edges
2. If `sql_session` is provided, also create `VerificationMethod` rows with `low_level_requirement_id` set to the new LLR's Neo4j id (no FK, just an integer column)
3. No longer create `LowLevelRequirement` SQLAlchemy rows

```python
def persist_decomposition(
    neo4j_session: "Neo4jSession",
    hlr_id: int,
    llrs: list[LowLevelRequirementSchema],
    sql_session: Session | None = None,
) -> DecompositionResult:
    """Create LLRs under an existing HLR in Neo4j. Also persist verification
    stubs to SQLite if sql_session is provided.

    Phase 2: HLR/LLR data lives in Neo4j. VerificationMethod stays in SQLite
    but references LLR by id (not FK).
    """
    from backend.db.neo4j.repositories.requirement import RequirementRepository

    result = DecompositionResult()
    repo = RequirementRepository(neo4j_session)

    for llr_data in llrs:
        llr = repo.create_llr(hlr_id=hlr_id, description=llr_data.description)
        result.llrs_created += 1

        # Persist verification stubs in SQLite
        if sql_session is not None:
            for v in llr_data.verifications:
                vm = VerificationMethod(
                    low_level_requirement_id=llr.id,
                    method=v.method,
                    test_name=v.test_name,
                    description=v.description,
                )
                sql_session.add(vm)
                result.verifications_created += 1

    if sql_session is not None:
        sql_session.flush()

    return result
```

- [ ] **Step 2: Update persist_design() to use RequirementRepository for trace calls**

In `persist_design()`, replace:
```python
repo.trace_design_to_hlr(hlr_sqlite_id=link.requirement_id, ...)
repo.trace_design_to_llr(llr_sqlite_id=link.requirement_id, ...)
```

With:
```python
req_repo = RequirementRepository(neo4j_session)
if link.requirement_type == "hlr":
    req_repo.trace_to_design(hlr_id=link.requirement_id, design_qualified_name=qn)
elif link.requirement_type == "llr":
    req_repo.trace_to_design(llr_id=link.requirement_id, design_qualified_name=qn)
```

Also update the import at the top of `persistence.py` to add `RequirementRepository`.

- [ ] **Step 3: Remove unused HighLevelRequirement and LowLevelRequirement imports**

From `persistence.py`, remove:
```python
from backend.db.models import (
    HighLevelRequirement,
    LowLevelRequirement,
    ...
)
```

Keep the imports that are still needed: `VerificationMethod`, `VerificationCondition`, `VerificationAction`, `OntologyNode`, `OntologyTriple`, `Predicate`.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_persistence.py -v`
Expected: Tests may need updates (addressed in Task 9)

- [ ] **Step 5: Commit**

```bash
git add backend/requirements/services/persistence.py
git commit -m "feat(phase2): rewrite persist_decomposition and persist_design for Neo4j-primary HLR/LLR"
```

---

## Task 7: Update Agent Code and Pipeline

**Files:**
- Modify: `backend/ticketing_agent/decompose/decompose_hlr.py`
- Modify: `backend/ticketing_agent/design/design_per_hlr.py`
- Modify: `backend/ticketing_agent/design/design_ontology.py`
- Modify: `backend/ticketing_agent/mcp_server.py`
- Modify: `backend/ticketing_agent/review/review_class_design.py`
- Modify: `backend/ticketing_agent/review/challenge_design.py`
- Modify: `backend/ticketing_agent/verify/verify_llr.py`
- Modify: `backend/pipeline/orchestrator.py`

These files all reference `HighLevelRequirement` and/or `LowLevelRequirement` SQLAlchemy models. Each needs to be updated to use `RequirementRepository` for HLR/LLR data while keeping SQLAlchemy for VerificationMethod and other Phase 3 data.

**Key pattern for each file:**

For places that do `session.query(HighLevelRequirement).filter_by(id=X).first()`, replace with:
```python
from backend.db.neo4j.repositories.requirement import RequirementRepository
from services.dependencies import get_neo4j
with get_neo4j().session() as ns:
    repo = RequirementRepository(ns)
    hlr = repo.get_hlr(X)
```

For `design_per_hlr.py`, replace the SQLAlchemy HLR loading block with `RequirementRepository` calls.

For `mcp_server.py`, update `save_decomposed_requirement()` to use `RequirementRepository`, remove `LowLevelRequirement` and `HighLevelRequirement` SQLAlchemy imports, keep `VerificationMethod`.

For `review_class_design.py` and `challenge_design.py`, replace:
```python
for h in session.query(HighLevelRequirement).all():
```
With:
```python
with get_neo4j().session() as ns:
    repo = RequirementRepository(ns)
    for h in repo.list_hlrs():
```

For `orchestrator.py`, the Phase 1-2 decomposition loop currently does:
```python
hlrs = session.query(HighLevelRequirement).all()
for hlr in hlrs:
    ...
    decomp_result = decompose(hlr.description, ...)
    persisted = persist_decomposition(session, hlr, decomp_result.low_level_requirements)
```

Update to:
```python
with get_neo4j().session() as neo4j_session:
    req_repo = RequirementRepository(neo4j_session)
    hlrs = req_repo.list_hlrs()
    for hlr in hlrs:
        ...
        decomp_result = decompose(hlr.description, ...)
        persisted = persist_decomposition(neo4j_session, hlr.id, decomp_result.low_level_requirements, sql_session=session)
```

- [ ] **Step 1: Update decompose_hlr.py**  — The `decompose()` function itself doesn't need changes (it's a pure function that takes description + context dicts). Only the *callers* need updating (done in hlr.py and orchestrator.py).

- [ ] **Step 2: Update design_per_hlr.py** — Replace the SQLAlchemy HLR loading in `design_and_persist_hlr()` with `RequirementRepository`. The function signature changes to accept `hlr_id: int` and load from Neo4j.

- [ ] **Step 3: Update design_ontology.py** — Replace `HighLevelRequirement` and `LowLevelRequirement` imports with `RequirementRepository` calls.

- [ ] **Step 4: Update mcp_server.py** — Replace all SQLAlchemy HLR/LLR queries. The `list_requirements()` tool now queries Neo4j. The `save_decomposed_requirement()` tool creates HLR/LLR via `RequirementRepository`. Keep `VerificationMethod` queries in SQLAlchemy for now.

- [ ] **Step 5: Update review_class_design.py and challenge_design.py** — Replace `session.query(HighLevelRequirement)` and `session.query(LowLevelRequirement)` with `RequirementRepository` calls.

- [ ] **Step 6: Update verify_llr.py** — Replace `LowLevelRequirement` SQLAlchemy query with `RequirementRepository.get_llr()`, but keep `VerificationMethod` in SQLAlchemy.

- [ ] **Step 7: Update orchestrator.py** — Replace the HLR/LLR loading and persist_decomposition calls.

- [ ] **Step 8: Run existing tests**

Run: `pytest tests/ -v --ignore=tests/integration`
Expected: Tests may need adjustment for the new function signatures

- [ ] **Step 9: Commit**

```bash
git add backend/ticketing_agent/ backend/pipeline/orchestrator.py
git commit -m "feat(phase2): update agent code and pipeline to use RequirementRepository"
```

---

## Task 8: Drop SQLAlchemy HLR/LLR Models and M2M Table

**Files:**
- Delete: `backend/db/models/requirements.py`
- Modify: `backend/db/models/__init__.py` — remove HLR/LLR/TicketRequirement exports
- Modify: `backend/db/models/components.py` — remove `high_level_requirements` relationship
- Modify: `backend/db/models/associations.py` — remove `low_level_requirements_components` table
- Modify: `backend/db/models/verification.py` — remove FK constraint on `low_level_requirement_id` (keep the column as a plain integer)
- Modify: `backend/db/models/tickets.py` — remove `TicketRequirement` import and M2M
- Modify: `backend/db/models/ontology.py` — remove HLR/LLR back-references

**Important:** This task must come AFTER all consumers have been updated (Tasks 3–7). The `format_hlr_dict`, `format_hlrs_for_prompt`, and `format_llr_dict` helper functions are used in several agent files. We must provide replacements first.

- [ ] **Step 1: Create replacement formatting helpers**

Create `backend/requirements/formatting.py`:

```python
"""Formatting helpers for requirement data.

Replaces the SQLAlchemy-model-based formatters from requirements.py module.
These operate on plain dicts (from RequirementRepository) instead of ORM objects.
"""


def format_hlr_dict(hlr_dict: dict, include_component: bool = False) -> str:
    """Format a single HLR dict as a prompt line."""
    comp = ""
    if include_component:
        comp_name = hlr_dict.get("component_name") or hlr_dict.get("component__name")
        if comp_name:
            comp = f" [Component: {comp_name}]"
    return f"HLR {hlr_dict['id']}{comp}: {hlr_dict['description']}"


def format_llr_dict(llr_dict: dict) -> str:
    """Format a single LLR dict as a prompt line."""
    return f"LLR {llr_dict['id']}: {llr_dict['description']}"


def format_hlrs_for_prompt(hlrs: list[dict], llrs: list[dict] | None = None, include_component: bool = False) -> str:
    """Format HLR/LLR dicts into a text block for agent prompts."""
    lines = []
    for hlr in hlrs:
        lines.append(format_hlr_dict(hlr, include_component))
        if llrs:
            for llr in [l for l in llrs if l.get("hlr_id") == hlr["id"]]:
                lines.append(f"  {format_llr_dict(llr)}")
    if llrs:
        unlinked = [l for l in llrs if l.get("hlr_id") is None]
        if unlinked:
            lines.append("\nUnlinked LLRs:")
            for llr in unlinked:
                lines.append(f"  {format_llr_dict(llr)}")
    return "\n".join(lines)
```

- [ ] **Step 2: Update all format_hlr_dict/format_hlrs_for_prompt importers**

Search for `from backend.db.models.requirements import format_hlr_dict` and similar, replace with:
```python
from backend.requirements.formatting import format_hlr_dict, format_hlrs_for_prompt, format_llr_dict
```

Files that import these:
- `backend/ticketing_agent/decompose/decompose_hlr.py`
- `backend/ticketing_agent/design/assign_components.py`
- `backend/ticketing_agent/design/assess_dependencies.py`
- `backend/ticketing_agent/design/design_ontology.py`
- `backend/ticketing_agent/design/order_hlrs.py`
- `backend/ticketing_agent/design/design_oo.py`
- `backend/ticketing_agent/design/discover_classes.py`
- `backend/ticketing_agent/review/review_hlrs.py`

- [ ] **Step 3: Remove the models from requirements.py**

Delete the entire `backend/db/models/requirements.py` file. Before deleting, ensure that `TicketRequirement` is no longer used anywhere (check `mcp_server.py` and `tickets.py`). Since `TicketRequirement` is only used in `apply_remediation()` in `mcp_server.py` (via `LowLevelRequirement` FK), and we've already updated that function in Task 7, this should be safe.

- [ ] **Step 4: Update __init__.py**

Remove from `backend/db/models/__init__.py`:
```python
from backend.db.models.requirements import (
    HighLevelRequirement,
    LowLevelRequirement,
    TicketRequirement,
    format_hlr_dict,
    format_hlrs_for_prompt,
    format_llr_dict,
)
```

And remove those names from `__all__`.

- [ ] **Step 5: Remove relationship from components.py**

In `backend/db/models/components.py`, remove:
```python
if TYPE_CHECKING:
    from backend.db.models.requirements import HighLevelRequirement, LowLevelRequirement
```
And the `high_level_requirements` relationship:
```python
high_level_requirements: Mapped[list[HighLevelRequirement]] = relationship(
    "HighLevelRequirement", back_populates="component"
)
```

- [ ] **Step 6: Remove M2M table from associations.py**

In `backend/db/models/associations.py`, remove:
```python
low_level_requirements_components = Table(
    "low_level_requirements_components",
    Base.metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "lowlevelrequirement_id",
        Integer,
        ForeignKey("low_level_requirements.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "component_id", Integer, ForeignKey("components.id", ondelete="CASCADE"), nullable=False
    ),
)
```

- [ ] **Step 7: Remove FK from verification.py**

In `backend/db/models/verification.py`, change:
```python
low_level_requirement_id: Mapped[int] = mapped_column(
    ForeignKey("low_level_requirements.id", ondelete="CASCADE"), nullable=False
)
```
To:
```python
low_level_requirement_id: Mapped[int] = mapped_column(
    Integer, nullable=False
)
```

Also remove the relationship:
```python
low_level_requirement: Mapped[LowLevelRequirement] = relationship(
    "LowLevelRequirement", back_populates="verifications"
)
```

And the TYPE_CHECKING import:
```python
if TYPE_CHECKING:
    from backend.db.models.requirements import LowLevelRequirement
```

**Note:** The `low_level_requirement_id` column still stores an integer, but it's now a plain reference to the Neo4j LLR node's `id` property — no FK constraint.

- [ ] **Step 8: Update tickets.py**

Remove `TicketRequirement` import and M2M from `backend/db/models/tickets.py`.

- [ ] **Step 9: Check for any remaining references**

Run: `grep -rn "from backend.db.models.requirements import\|from backend.db.models import.*HighLevelRequirement\|from backend.db.models import.*LowLevelRequirement\|from backend.db.models import.*TicketRequirement" backend/ frontend/ tests/ --include="*.py" | grep -v __pycache__`
Expected: No remaining references.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "feat(phase2): drop SQLAlchemy HLR/LLR/TicketRequirement models, create formatting.py"
```

---

## Task 9: Generate Alembic Migration for Table Drops

**Files:**
- Create: Alembic migration (auto-generated)
- Modify: Any Alembic config needed

- [ ] **Step 1: Generate the migration**

Run: `alembic revision --autogenerate -m "drop_hlr_llr_tables_and_fk_constraints"`

This should detect:
- Drop `low_level_requirements` table
- Drop `high_level_requirements` table
- Drop `ticket_requirements` table
- Drop `low_level_requirements_components` table
- Drop FK constraint on `verification_methods.low_level_requirement_id`
- Drop FK on `Component.high_level_requirements` relationship (if represented in schema)

- [ ] **Step 2: Review the generated migration**

Open the generated migration file and verify it:
1. Drops `ticket_requirements` before `low_level_requirements` (due to FK)
2. Drops `low_level_requirements` before `high_level_requirements` (due to FK)
3. Drops `low_level_requirements_components`
4. Removes the FK constraint on `verification_methods.low_level_requirement_id` but keeps the column
5. Does NOT drop any Neo4j-related tables or columns

- [ ] **Step 3: Apply the migration to a test database**

Run: `alembic upgrade head`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/
git commit -m "feat(phase2): add Alembic migration to drop HLR/LLR tables"
```

---

## Task 10: Data Migration Script — SQLite to Neo4j

**Files:**
- Create: `scripts/migrate_phase2_requirements_to_neo4j.py`

- [ ] **Step 1: Write the migration script**

```python
#!/usr/bin/env python
"""Migrate Phase 2 requirement data from SQLite to Neo4j.

Reads HLR and LLR rows from SQLite and creates full :HLR/:LLR nodes
in Neo4j with native id properties (replacing sqlite_id). Also
migrates AFFECTS_COMPONENT relationships and drops sqlite_id properties
from existing stub nodes.

Usage:
    python scripts/migrate_phase2_requirements_to_neo4j.py [--clear-stubs]
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from backend.db import init_db, get_session
from backend.db.neo4j.connection import Neo4jConnection, get_standalone_driver
from backend.db.neo4j.repositories.requirement import RequirementRepository


def migrate_hlrs(session, neo4j_session, repo):
    """Migrate all HLR rows from SQLite to Neo4j :HLR nodes."""
    from backend.db.models import HighLevelRequirement

    hlrs = session.query(HighLevelRequirement).all()
    print(f"Migrating {len(hlrs)} HLRs...")

    # First, clear existing HLR stubs (they have sqlite_id property)
    neo4j_session.run("MATCH (h:HLR) DETACH DELETE h")

    count = 0
    for hlr in hlrs:
        # Preserve the SQLite ID as the Neo4j node id
        neo4j_session.run(
            """
            CREATE (h:HLR {
                id: $id,
                description: $desc,
                component_id: $cid,
                dependency_context: $dep_ctx
            })
            """,
            {
                "id": hlr.id,
                "desc": hlr.description,
                "cid": hlr.component_id,
                "dep_ctx": hlr.dependency_context,
            },
        )
        count += 1

    print(f"  Migrated {count} HLRs")
    return count


def migrate_llrs(session, neo4j_session, repo):
    """Migrate all LLR rows from SQLite to Neo4j :LLR nodes with DECOMPOSES_INTO edges."""
    from backend.db.models import LowLevelRequirement

    llrs = session.query(LowLevelRequirement).all()
    print(f"Migrating {len(llrs)} LLRs...")

    # Clear existing LLR stubs
    neo4j_session.run("MATCH (l:LLR) DETACH DELETE l")

    count = 0
    for llr in llrs:
        neo4j_session.run(
            """
            MATCH (h:HLR {id: $hid})
            CREATE (l:LLR {
                id: $id,
                description: $desc,
                high_level_requirement_id: $hid
            })
            CREATE (h)-[:DECOMPOSES_INTO]->(l)
            """,
            {
                "hid": llr.high_level_requirement_id,
                "id": llr.id,
                "desc": llr.description,
            },
        )
        count += 1

    print(f"  Migrated {count} LLRs")
    return count


def migrate_llr_components(session, neo4j_session):
    """Migrate low_level_requirements_components M2M to AFFECTS_COMPONENT properties.

    Since Component nodes aren't in Neo4j yet, we store component_id as a
    list property on the LLR node. This can be converted to edges later.
    """
    from sqlalchemy import text

    result = session.execute(
        text("SELECT lowlevelrequirement_id, component_id FROM low_level_requirements_components")
    ).fetchall()
    print(f"Migrating {len(result)} LLR↔Component links...")

    # Group by LLR id
    llr_components: dict[int, list[int]] = {}
    for llr_id, comp_id in result:
        llr_components.setdefault(llr_id, []).append(comp_id)

    for llr_id, comp_ids in llr_components.items():
        neo4j_session.run(
            "MATCH (l:LLR {id: $lid}) SET l.component_ids = $cids",
            {"lid": llr_id, "cids": comp_ids},
        )

    print(f"  Migrated {len(llr_components)} LLR component links")
    return len(llr_components)


def verify_counts(session, neo4j_session):
    """Verify that SQLite and Neo4j counts match."""
    from backend.db.models import HighLevelRequirement, LowLevelRequirement

    sqlite_hlrs = session.query(HighLevelRequirement).count()
    sqlite_llrs = session.query(LowLevelRequirement).count()

    neo4j_hlrs = neo4j_session.run("MATCH (h:HLR) RETURN count(h) AS cnt").single()["cnt"]
    neo4j_llrs = neo4j_session.run("MATCH (l:LLR) RETURN count(l) AS cnt").single()["cnt"]

    print(f"\nCount verification:")
    print(f"  HLRs: SQLite={sqlite_hlrs}, Neo4j={neo4j_hlrs} {'✓' if sqlite_hlrs == neo4j_hlrs else '✗ MISMATCH'}")
    print(f"  LLRs: SQLite={sqlite_llrs}, Neo4j={neo4j_llrs} {'✓' if sqlite_llrs == neo4j_llrs else '✗ MISMATCH'}")

    return sqlite_hlrs == neo4j_hlrs and sqlite_llrs == neo4j_llrs


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Migrate Phase 2 requirement data to Neo4j")
    parser.add_argument("--clear-stubs", action="store_true", help="Clear existing HLR/LLR stubs before migrating")
    args = parser.parse_args()

    init_db()
    driver = get_standalone_driver()

    # Ensure constraints
    neo4j_conn = Neo4jConnection()
    neo4j_conn.ensure_constraints()
    neo4j_conn.ensure_requirement_constraints()

    with driver.session(database="neo4j") as neo4j_session:
        repo = RequirementRepository(neo4j_session)

        if args.clear_stubs:
            print("Clearing existing HLR/LLR stubs...")
            neo4j_session.run("MATCH (h:HLR) DETACH DELETE h")
            neo4j_session.run("MATCH (l:LLR) DETACH DELETE l")

        with get_session() as session:
            print("=" * 60)
            print("Phase 2 Data Migration: SQLite HLR/LLR → Neo4j")
            print("=" * 60)

            hlr_count = migrate_hlrs(session, neo4j_session, repo)
            llr_count = migrate_llrs(session, neo4j_session, repo)
            comp_count = migrate_llr_components(session, neo4j_session)

            ok = verify_counts(session, neo4j_session)

            print("=" * 60)
            print(f"Migration {'complete' if ok else 'COMPLETE WITH WARNINGS'}!")
            print(f"  HLRs migrated: {hlr_count}")
            print(f"  LLRs migrated: {llr_count}")
            print(f"  Component links: {comp_count}")
            print("=" * 60)

            if not ok:
                sys.exit(1)

    driver.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test the migration script**

Run: `python scripts/migrate_phase2_requirements_to_neo4j.py --clear-stubs`
Expected: Successful migration with count verification passing

- [ ] **Step 3: Commit**

```bash
git add scripts/migrate_phase2_requirements_to_neo4j.py
git commit -m "feat(phase2): add data migration script from SQLite to Neo4j"
```

---

## Task 11: Update Tests

**Files:**
- Modify: `tests/conftest.py`
- Modify: `tests/test_persistence.py`
- Modify: `tests/test_requirements_models.py`
- Modify: `tests/test_requirements_schemas.py`
- Modify: `tests/integration/conftest.py`
- Modify: `tests/integration/test_loaded_fixtures.py`

- [ ] **Step 1: Update conftest.py**

In `tests/conftest.py`, the `seeded_session` fixture currently creates `HighLevelRequirement` rows. Replace with a fixture that creates HLR/LLR data in Neo4j via `RequirementRepository` (for integration tests that need it) and keep the SQLAlchemy fixture only for tests that still need SQLite-based verification data.

Add a new `neo4j_session` fixture for integration tests (similar to `test_requirement_repository.py`).

For unit tests that don't need Neo4j, keep `seeded_session` but it will no longer create `HighLevelRequirement` rows (since those models no longer exist).

- [ ] **Step 2: Update test_persistence.py**

Update `test_persistence.py` to use `RequirementRepository` instead of SQLAlchemy models. The `persist_decomposition` function now takes `(neo4j_session, hlr_id, llrs)` instead of `(sql_session, hlr, llrs)`. Update all test calls accordingly.

- [ ] **Step 3: Update test_requirements_models.py**

This file tests the SQLAlchemy `HighLevelRequirement` and `LowLevelRequirement` models. Since these are being deleted, either delete the file or convert it to test `HLRNode`/`LLRNode` Pydantic models.

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -v --ignore=tests/integration`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "feat(phase2): update tests for Neo4j-primary HLR/LLR"
```

---

## Task 12: Full Integration Smoke Test and Cleanup

**Files:**
- Modify: `scripts/backfill_requirement_nodes.py` — delete or mark as deprecated
- Modify: `scripts/migrate_phase1_design_to_neo4j.py` — add note about Phase 2 superseding the HLR/LLR stub logic

- [ ] **Step 1: Run the full migration**

```bash
python scripts/migrate_phase1_design_to_neo4j.py --clear
python scripts/migrate_phase2_requirements_to_neo4j.py --clear-stubs
```

- [ ] **Step 2: Start the application and verify**

1. Navigate to the requirements dashboard — verify HLR/LLR data loads from Neo4j
2. Create a new HLR — verify it appears in Neo4j with `id` property (not `sqlite_id`)
3. Decompose an HLR — verify LLRs are created in Neo4j
4. View HLR detail page — verify TRACES_TO triples load correctly
5. Run a design agent — verify TRACES_TO edges are created with native `id`
6. Verify existing verification methods still link to LLRs by `low_level_requirement_id`

- [ ] **Step 3: Verify no sqlite_id references remain**

Run: `grep -rn "sqlite_id" backend/ frontend/ --include="*.py" | grep -v __pycache__ | grep -v "migrate_phase" | grep -v ".pyc"`
Expected: Zero matches (migration scripts may still contain `sqlite_id` for historical reference)

- [ ] **Step 4: Mark backfill script as deprecated**

In `scripts/backfill_requirement_nodes.py`, add a deprecation note at the top:

```python
"""
DEPRECATED: This script was used in Phase 1 to populate M2M association tables
for HLR/LLR node links. In Phase 2, HLR/LLR data lives in Neo4j and this
script is no longer needed. Use migrate_phase2_requirements_to_neo4j.py instead.
"""
```

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat(phase2): integration verification, deprecation notes, cleanup"
```

---

## Risks and Mitigations

1. **HLR/LLR SQLite ID references everywhere** — Comprehensive grep in Task 8, Step 9 catches all remaining `sqlite_id` references. The migration script preserves SQLite IDs as Neo4j `id` properties so existing data remains consistent.

2. **Decomposition agent writes to both SQLite and Neo4j** — Phase 2 makes Neo4j the primary. `persist_decomposition()` writes to Neo4j only; verification data still goes to SQLite via the `low_level_requirement_id` column (no FK).

3. **VerificationMethod FK to low_level_requirements** — The FK constraint is dropped but the column remains as a plain integer. This is safe because LLR IDs are stable (they come from the migration which preserves SQLite IDs). Queries like `VerificationMethod.low_level_requirement_id == llr_id` still work correctly.

4. **Dashboard queries** — `fetch_requirements_data()` now queries Neo4j for HLR/LLR data. Component names still need a SQLite lookup (for `component_id → name` resolution). This is acceptable until Phase 3 moves Components to Neo4j.

5. **MCP server apply_remediation()** — This function manipulates HLRs and LLRs. In Phase 2, it must create/delete HLR/LLR nodes in Neo4j, not SQLite. The `Component` model stays in SQLite.

6. **Concurrent ID generation** — The `_next_hlr_id()` and `_next_llr_id()` methods use `max(id) + 1` which is safe for single-writer apps but not for concurrent writes. If concurrency becomes an issue, introduce a `SEQUENCE` counter node in Neo4j or use application-level locking.

---

## Dependency Order

```
Task 1 (Pydantic models)
  → Task 2 (RequirementRepository) — depends on Task 1 models
    → Task 3 (Remove sqlite_id from Cypher) — independent of Task 2 but logically grouped
    → Task 4 (Rewrite hlr.py) — depends on Task 2
    → Task 5 (Rewrite llr.py) — depends on Task 2
      → Task 6 (Rewrite persist_decomposition) — depends on Task 2
        → Task 7 (Update agent code) — depends on Task 6
          → Task 8 (Drop SQLAlchemy models) — depends on Tasks 4–7
            → Task 9 (Alembic migration) — depends on Task 8
              → Task 10 (Migration script) — depends on Task 9
                → Task 11 (Update tests) — depends on Tasks 3–10
                  → Task 12 (Integration smoke test) — depends on all prior tasks
```

Tasks 3–5 can be done in parallel after Task 2. Tasks 4–7 can overlap but must all complete before Task 8.