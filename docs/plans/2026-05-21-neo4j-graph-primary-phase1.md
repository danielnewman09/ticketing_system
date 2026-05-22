# Neo4j Graph-Primary: Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Neo4j the sole authority for design nodes, triples, and predicates — eliminating the SQLAlchemy OntologyNode/OntologyTriple/Predicate models, the neo4j sync layer, and four M2M association tables.

**Architecture:** New `DesignRepository` class writes/reads Design nodes and relationships directly to/from Neo4j via Cypher MERGE/MATCH. Pydantic models replace SQLAlchemy ORM objects as the data contract. HLR/LLR temporarily get `:HLR`/`:LLR` stub nodes in Neo4j (with `sqlite_id` property) to enable Cypher-traversal-based requirement tagging, replacing the M2M bridge tables. All design-node CRUD, graph queries, and requirement-tag enrichment use Neo4j exclusively.

**Tech Stack:** Python, Neo4j Python driver, Pydantic, existing NiceGUI frontend

**Spec:** `docs/specs/2026-05-21-neo4j-graph-primary-design.md` (Phase 1)

---

## File Structure

**New files:**
- `backend/db/neo4j/repositories/__init__.py` — re-exports
- `backend/db/neo4j/repositories/design.py` — DesignRepository class
- `backend/db/neo4j/repositories/models/__init__.py` — re-exports
- `backend/db/neo4j/repositories/models/design.py` — DesignNode, DesignTripleUpdate Pydantic models
- `backend/db/neo4j/repositories/constants.py` — PREDICATE_TO_REL_TYPE, DEFAULT_PREDICATES, NODE_KIND_VALUES, etc.
- `tests/test_design_repository.py` — DesignRepository tests

**Modified files:**
- `backend/db/neo4j/connection.py` — add `ensure_design_constraints()`
- `backend/db/neo4j/__init__.py` — update exports
- `backend/db/neo4j/queries/graph.py` — use DesignRepository + Cypher for HLR traversal
- `backend/db/neo4j/queries/detail.py` — use DesignRepository
- `backend/requirements/services/graph_tags.py` — rewrite to use Cypher TRACES_TO traversal
- `backend/requirements/services/persistence.py` — rewrite `persist_design()` to use DesignRepository; add `sync_hlr_llr_stubs()`
- `backend/pipeline/orchestrator.py` — remove Neo4j sync phase
- `frontend/data/ontology.py` — update to use repository and Cypher enrichment
- `frontend/data/hlr.py` — update HLR graph queries
- `backend/db/models/ontology.py` — remove (constants moved, model deleted)
- `backend/db/models/associations.py` — remove 4 M2M tables (keep dependency_components and tickets tables for later phases)
- `backend/db/models/__init__.py` — remove OntologyNode/OntologyTriple/Predicate re-exports
- `services/dependencies.py` — minor updates if needed
- `tests/conftest.py` — adjust fixtures for new architecture
- `tests/test_ontology_models.py` — remove (tests for deleted models)
- `tests/test_persistence.py` — rewrite to use DesignRepository
- `tests/test_graph_tags.py` — rewrite to use Cypher-based enrichment

**Deleted files:**
- `backend/db/neo4j/sync.py` — entire sync module replaced by repository

---

### Task 1: Create Pydantic Models and Constants

**Files:**
- Create: `backend/db/neo4j/repositories/__init__.py`
- Create: `backend/db/neo4j/repositories/models/__init__.py`
- Create: `backend/db/neo4j/repositories/models/design.py`
- Create: `backend/db/neo4j/repositories/constants.py`
- Test: `tests/test_design_repository.py`

- [ ] **Step 1: Write the test for DesignNode Pydantic model**

Create `tests/test_design_repository.py`:

```python
"""Tests for DesignRepository and design Pydantic models."""

import pytest
from pydantic import ValidationError


class TestDesignNodeModel:
    """Tests for the DesignNode Pydantic model."""

    def test_create_minimal(self):
        from backend.db.neo4j.repositories.models.design import DesignNode

        node = DesignNode(qualified_name="ns::Foo", name="Foo", kind="class")
        assert node.qualified_name == "ns::Foo"
        assert node.name == "Foo"
        assert node.kind == "class"
        assert node.specialization == ""
        assert node.visibility == ""
        assert node.description == ""
        assert node.implementation_status == "designed"

    def test_create_all_fields(self):
        from backend.db.neo4j.repositories.models.design import DesignNode

        node = DesignNode(
            qualified_name="ns::Foo",
            name="Foo",
            kind="method",
            specialization="staticmethod",
            visibility="public",
            description="A method",
            refid="classns_1_1Foo_1a123",
            source_type="member",
            type_signature="int(int, int)",
            argsstring="(int x, int y)",
            definition="int Foo::calculate(int x, int y)",
            file_path="src/foo.py",
            line_number=42,
            is_static=True,
            is_const=False,
            is_virtual=False,
            is_abstract=False,
            is_final=False,
            component_id=1,
            is_intercomponent=False,
            implementation_status="implemented",
            source_file="src/foo.py",
            test_file="test_foo.py",
        )
        assert node.file_path == "src/foo.py"
        assert node.line_number == 42
        assert node.is_static is True
        assert node.component_id == 1
        assert node.implementation_status == "implemented"

    def test_defaults_populated(self):
        from backend.db.neo4j.repositories.models.design import DesignNode

        node = DesignNode(qualified_name="X", name="X", kind="class")
        assert node.specialization == ""
        assert node.source_type == ""
        assert node.type_signature == ""
        assert node.file_path == ""
        assert node.line_number is None
        assert node.component_id is None
        assert node.is_static is False
        assert node.implementation_status == "designed"
        assert node.source_file == ""
        assert node.test_file == ""


class TestDesignConstants:
    """Tests for constants moved from ontology models."""

    def test_predicate_mapping(self):
        from backend.db.neo4j.repositories.constants import PREDICATE_TO_REL_TYPE

        assert PREDICATE_TO_REL_TYPE["composes"] == "COMPOSES"
        assert PREDICATE_TO_REL_TYPE["depends_on"] == "DEPENDS_ON"
        assert len(PREDICATE_TO_REL_TYPE) == 7

    def test_default_predicates(self):
        from backend.db.neo4j.repositories.constants import DEFAULT_PREDICATES

        names = {name for name, _ in DEFAULT_PREDICATES}
        assert "composes" in names
        assert "depends_on" in names

    def test_node_kind_values(self):
        from backend.db.neo4j.repositories.constants import NODE_KIND_VALUES

        assert "class" in NODE_KIND_VALUES
        assert "method" in NODE_KIND_VALUES
        assert len(NODE_KIND_VALUES) == 11
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /Users/danielnewman/dev/ticketing_system && python -m pytest tests/test_design_repository.py::TestDesignNodeModel::test_create_minimal -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.db.neo4j.repositories.models.design'`

- [ ] **Step 3: Create the directory structure and `__init__.py` files**

```bash
mkdir -p backend/db/neo4j/repositories/models
touch backend/db/neo4j/repositories/__init__.py
touch backend/db/neo4j/repositories/models/__init__.py
```

- [ ] **Step 4: Create `backend/db/neo4j/repositories/constants.py`**

```python
"""Constants for the Neo4j design layer.

Moved from backend.db.models.ontology during Phase 1 migration.
These constants define the vocabulary of predicates, node kinds,
and specializations used by the design repository and Cypher queries.
"""

# ---------------------------------------------------------------------------
# Predicates — mapping lowercase names to UPPER_SNAKE_CASE Neo4j rel types
# ---------------------------------------------------------------------------

PREDICATE_TO_REL_TYPE = {
    "associates": "ASSOCIATES",
    "aggregates": "AGGREGATES",
    "composes": "COMPOSES",
    "depends_on": "DEPENDS_ON",
    "generalizes": "GENERALIZES",
    "realizes": "REALIZES",
    "invokes": "INVOKES",
}

DEFAULT_PREDICATES = [
    ("associates", "General association between two entities"),
    ("aggregates", "Whole-part relationship where the part can exist independently"),
    ("composes", "Strong whole-part relationship where the part is owned by the whole"),
    ("depends_on", "One entity depends on another"),
    ("generalizes", "Inheritance / is-a relationship"),
    ("realizes", "A class implements/realizes an interface or contract"),
    ("invokes", "Weak association, signifying a caller-callee relationship"),
]

# ---------------------------------------------------------------------------
# Node kinds — language-agnostic base kinds
# ---------------------------------------------------------------------------

NODE_KINDS = [
    ("attribute", "Attribute"),
    ("class", "Class"),
    ("constant", "Constant"),
    ("enum", "Enum"),
    ("enum_value", "Enum Value"),
    ("function", "Function"),
    ("interface", "Interface"),
    ("method", "Method"),
    ("module", "Module"),
    ("primitive", "Primitive Type"),
    ("type_alias", "Type Alias"),
]

NODE_KIND_VALUES = {k for k, _ in NODE_KINDS}

# ---------------------------------------------------------------------------
# Visibility / access specifiers
# ---------------------------------------------------------------------------

VISIBILITY_CHOICES = [
    ("public", "Public"),
    ("private", "Private"),
    ("protected", "Protected"),
]

# ---------------------------------------------------------------------------
# Semantic groupings
# ---------------------------------------------------------------------------

TYPE_KINDS = {"class", "interface", "enum", "type_alias"}
VALUE_KINDS = {"enum_value", "function", "method", "attribute", "constant"}

# ---------------------------------------------------------------------------
# Codebase source types
# ---------------------------------------------------------------------------

SOURCE_TYPES = [
    ("namespace", "Namespace"),
    ("compound", "Compound"),
    ("member", "Member"),
    ("dependency", "Dependency Reference"),
]

SOURCE_TYPE_VALUES = {k for k, _ in SOURCE_TYPES}

# ---------------------------------------------------------------------------
# Language-specific specializations
# ---------------------------------------------------------------------------

LANGUAGE_SPECIALIZATIONS = {
    "cpp": {
        "class": [
            "struct",
            "template_class",
            "abstract_class",
        ],
        "method": [
            "virtual_method",
            "pure_virtual_method",
            "template_method",
            "static_method",
            "const_method",
            "operator_overload",
        ],
        "function": [
            "template_function",
        ],
        "constant": [
            "constexpr",
            "const",
        ],
        "enum": [
            "enum_class",
        ],
        "type_alias": [
            "using",
            "typedef",
        ],
        "module": [
            "namespace",
        ],
    },
    "python": {
        "class": [
            "dataclass",
            "namedtuple",
        ],
        "method": [
            "classmethod",
            "staticmethod",
            "property",
            "abstractmethod",
            "async_method",
        ],
        "function": [
            "async_function",
            "generator",
            "decorator",
        ],
        "interface": [
            "protocol",
            "abc",
        ],
        "constant": [
            "final",
        ],
        "module": [
            "package",
        ],
    },
    "javascript": {
        "class": [],
        "method": [
            "getter",
            "setter",
            "static_method",
            "async_method",
        ],
        "function": [
            "arrow_function",
            "async_function",
            "generator",
        ],
        "module": [
            "es_module",
            "commonjs_module",
        ],
    },
}

SUPPORTED_LANGUAGES = set(LANGUAGE_SPECIALIZATIONS.keys())


def valid_specializations(language, kind):
    """Return the set of valid specializations for a language + kind."""
    lang_spec = LANGUAGE_SPECIALIZATIONS.get(language, {})
    return set(lang_spec.get(kind, []))
```

- [ ] **Step 5: Create `backend/db/neo4j/repositories/models/design.py`**

```python
"""Pydantic models for Neo4j Design nodes and triple updates.

These replace SQLAlchemy OntologyNode/OntologyTriple as the
data contract between Neo4j and the application layer.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DesignNode(BaseModel):
    """A design-intent node in the ontology graph.

    Mirrors the properties stored on :Design nodes in Neo4j.
    qualified_name is the unique identifier and MERGE key.
    """

    qualified_name: str
    name: str
    kind: str
    specialization: str = ""
    visibility: str = ""
    description: str = ""
    refid: str = ""
    source_type: str = ""
    type_signature: str = ""
    argsstring: str = ""
    definition: str = ""
    file_path: str = ""
    line_number: int | None = None
    is_static: bool = False
    is_const: bool = False
    is_virtual: bool = False
    is_abstract: bool = False
    is_final: bool = False
    component_id: int | None = None
    is_intercomponent: bool = False
    implementation_status: str = "designed"
    source_file: str = ""
    test_file: str = ""

    model_config = {"from_attributes": True}


class DesignTripleUpdate(BaseModel):
    """A request to create or update a relationship between two Design nodes.

    subject and object are identified by qualified_name.
    predicate is the lowercase predicate name (e.g. "composes").
    """

    subject_qualified_name: str
    predicate: str
    object_qualified_name: str
```

- [ ] **Step 6: Update `backend/db/neo4j/repositories/models/__init__.py`**

```python
"""Design layer data models for Neo4j repositories."""

from backend.db.neo4j.repositories.models.design import (
    DesignNode,
    DesignTripleUpdate,
)

__all__ = [
    "DesignNode",
    "DesignTripleUpdate",
]
```

- [ ] **Step 7: Update `backend/db/neo4j/repositories/__init__.py`**

```python
"""Neo4j repository layer — typed data access over raw Cypher."""

from backend.db.neo4j.repositories.design import DesignRepository
from backend.db.neo4j.repositories.models import DesignNode, DesignTripleUpdate

__all__ = [
    "DesignRepository",
    "DesignNode",
    "DesignTripleUpdate",
]
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `cd /Users/danielnewman/dev/ticketing_system && python -m pytest tests/test_design_repository.py -v`
Expected: All tests PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/db/neo4j/repositories/ tests/test_design_repository.py
git commit -m "feat: add DesignNode Pydantic model and constants for Neo4j repositories"
```

---

### Task 2: Create DesignRepository

**Files:**
- Create: `backend/db/neo4j/repositories/design.py`
- Test: `tests/test_design_repository.py`

- [ ] **Step 1: Write failing tests for DesignRepository**

Add to `tests/test_design_repository.py`:

```python
import os
import pytest

# Skip if Neo4j is not available
pytestmark = pytest.mark.skipif(
    os.environ.get("NEO4J_URI") is None and True,  # Set to False for integration runs
    reason="Neo4j not available (set NEO4J_URI to enable)"
)


class TestDesignRepositoryIntegration:
    """Integration tests for DesignRepository against a live Neo4j.

    These tests require a running Neo4j instance. Set the environment
    variable SKIP_NEO4J_INTEGRATION=1 to skip.
    """

    @pytest.fixture(autouse=True)
    def cleanup(self):
        """Remove all :Design and :HLR nodes after each test."""
        from backend.db.neo4j.connection import get_standalone_driver
        driver = get_standalone_driver()
        with driver.session(database="neo4j") as session:
            yield
            session.run("MATCH (n:Design) DETACH DELETE n")
            session.run("MATCH (n:HLR) DETACH DELETE n")
            session.run("MATCH (n:LLR) DETACH DELETE n")
        driver.close()

    def test_merge_node_creates_new(self):
        from backend.db.neo4j.repositories.design import DesignRepository
        from backend.db.neo4j.repositories.models import DesignNode
        from backend.db.neo4j.connection import get_standalone_driver

        driver = get_standalone_driver()
        with driver.session(database="neo4j") as session:
            repo = DesignRepository(session)
            node = DesignNode(qualified_name="calc::Calculator", name="Calculator", kind="class")
            result = repo.merge_node(node)
            assert result.qualified_name == "calc::Calculator"

        # Verify node exists in Neo4j
        with driver.session(database="neo4j") as session:
            record = session.run(
                "MATCH (d:Design {qualified_name: $qn}) RETURN d",
                {"qn": "calc::Calculator"},
            ).single()
            assert record is not None
            assert dict(record["d"])["kind"] == "class"

    def test_merge_node_updates_existing(self):
        from backend.db.neo4j.repositories.design import DesignRepository
        from backend.db.neo4j.repositories.models import DesignNode
        from backend.db.neo4j.connection import get_standalone_driver

        driver = get_standalone_driver()
        with driver.session(database="neo4j") as session:
            repo = DesignRepository(session)
            node = DesignNode(qualified_name="calc::Calculator", name="Calculator", kind="class")
            repo.merge_node(node)

            # Update description
            node.description = "Updated description"
            repo.merge_node(node)

        with driver.session(database="neo4j") as session:
            record = session.run(
                "MATCH (d:Design {qualified_name: $qn}) RETURN d.description AS desc",
                {"qn": "calc::Calculator"},
            ).single()
            assert record["desc"] == "Updated description"

    def test_merge_triple_creates_relationship(self):
        from backend.db.neo4j.repositories.design import DesignRepository
        from backend.db.neo4j.repositories.models import DesignNode
        from backend.db.neo4j.connection import get_standalone_driver

        driver = get_standalone_driver()
        with driver.session(database="neo4j") as session:
            repo = DesignRepository(session)
            parent = DesignNode(qualified_name="calc::Calculator", name="Calculator", kind="class")
            child = DesignNode(qualified_name="calc::Calculator.display", name="display", kind="attribute")
            repo.merge_node(parent)
            repo.merge_node(child)
            repo.merge_triple("calc::Calculator", "composes", "calc::Calculator.display")

        with driver.session(database="neo4j") as session:
            record = session.run(
                "MATCH (s:Design {qualified_name: $sqn})-[r:COMPOSES]->(o:Design {qualified_name: $oqn}) RETURN type(r) AS rel_type",
                {"sqn": "calc::Calculator", "oqn": "calc::Calculator.display"},
            ).single()
            assert record is not None
            assert record["rel_type"] == "COMPOSES"

    def test_get_by_qualified_name(self):
        from backend.db.neo4j.repositories.design import DesignRepository
        from backend.db.neo4j.repositories.models import DesignNode
        from backend.db.neo4j.connection import get_standalone_driver

        driver = get_standalone_driver()
        with driver.session(database="neo4j") as session:
            repo = DesignRepository(session)
            node = DesignNode(qualified_name="calc::Calculator", name="Calculator", kind="class", description="A calculator")
            repo.merge_node(node)
            result = repo.get_by_qualified_name("calc::Calculator")
            assert result is not None
            assert result.name == "Calculator"
            assert result.description == "A calculator"

    def test_get_by_qualified_name_not_found(self):
        from backend.db.neo4j.repositories.design import DesignRepository
        from backend.db.neo4j.connection import get_standalone_driver

        driver = get_standalone_driver()
        with driver.session(database="neo4j") as session:
            repo = DesignRepository(session)
            result = repo.get_by_qualified_name("nonexistent::Node")
            assert result is None

    def test_find_nodes_by_kind(self):
        from backend.db.neo4j.repositories.design import DesignRepository
        from backend.db.neo4j.repositories.models import DesignNode
        from backend.db.neo4j.connection import get_standalone_driver

        driver = get_standalone_driver()
        with driver.session(database="neo4j") as session:
            repo = DesignRepository(session)
            repo.merge_node(DesignNode(qualified_name="ns::Foo", name="Foo", kind="class"))
            repo.merge_node(DesignNode(qualified_name="ns::bar", name="bar", kind="method"))
            repo.merge_node(DesignNode(qualified_name="ns::Baz", name="Baz", kind="class"))

            classes = repo.find_nodes(kind="class")
            assert len(classes) == 2
            assert all(n.kind == "class" for n in classes)

    def test_delete_node(self):
        from backend.db.neo4j.repositories.design import DesignRepository
        from backend.db.neo4j.repositories.models import DesignNode
        from backend.db.neo4j.connection import get_standalone_driver

        driver = get_standalone_driver()
        with driver.session(database="neo4j") as session:
            repo = DesignRepository(session)
            repo.merge_node(DesignNode(qualified_name="ns::ToDelete", name="ToDelete", kind="class"))
            result = repo.delete_node("ns::ToDelete")
            assert result is True

            verify = repo.get_by_qualified_name("ns::ToDelete")
            assert verify is None

    def test_skips_dependency_stub_in_merge(self):
        from backend.db.neo4j.repositories.design import DesignRepository
        from backend.db.neo4j.repositories.models import DesignNode
        from backend.db.neo4j.connection import get_standalone_driver

        driver = get_standalone_driver()
        with driver.session(database="neo4j") as session:
            repo = DesignRepository(session)
            node = DesignNode(
                qualified_name="Fl_Button",
                name="Fl_Button",
                kind="class",
                source_type="dependency",
            )
            result = repo.merge_node(node)
            # Dependency stubs should be skipped — they exist as :Compound nodes
            # in Neo4j already, not as :Design nodes

        with driver.session(database="neo4j") as session:
            record = session.run(
                "MATCH (d:Design {qualified_name: $qn}) RETURN d",
                {"qn": "Fl_Button"},
            ).single()
            assert record is None, "Dependency stub should not be created as Design node"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/danielnewman/dev/ticketing_system && python -m pytest tests/test_design_repository.py::TestDesignRepositoryIntegration -v 2>&1 | head -20`
Expected: Tests skip or fail because `DesignRepository` doesn't exist yet.

- [ ] **Step 3: Implement `DesignRepository`**

Create `backend/db/neo4j/repositories/design.py`:

```python
"""Design node and triple repository — Neo4j-primary data access.

All design graph CRUD goes through this class. No SQLAlchemy models
are used for design data.
"""

from __future__ import annotations

import logging
from typing import Sequence

from neo4j import Session as Neo4jSession

from backend.db.neo4j.repositories.constants import PREDICATE_TO_REL_TYPE
from backend.db.neo4j.repositories.models.design import (
    DesignNode,
    DesignTripleUpdate,
)

log = logging.getLogger(__name__)


class DesignRepository:
    """CRUD operations for :Design nodes and their relationships.

    Each method accepts a Neo4j session and performs Cypher queries
    directly. The caller is responsible for transaction management
    (the session context manager handles commit/rollback).
    """

    def __init__(self, session: Neo4jSession) -> None:
        self._session = session

    # -----------------------------------------------------------------------
    # Node operations
    # -----------------------------------------------------------------------

    def merge_node(self, node: DesignNode) -> DesignNode:
        """Create or update a :Design node by qualified_name.

        Dependency-reference stubs (source_type='dependency') are skipped
        because their real nodes exist as :Compound in Neo4j. Edges to
        them are created via merge_triple, which routes to Compounds.
        """
        if node.source_type == "dependency":
            log.debug("Skipping dependency stub %s in Neo4j merge", node.qualified_name)
            return node

        kind_label = node.kind.capitalize() if node.kind else "Unknown"

        cypher = f"""
        MERGE (d:Design {{qualified_name: $qn}})
        SET d:{kind_label},
            d.name = $name,
            d.kind = $kind,
            d.specialization = $specialization,
            d.visibility = $visibility,
            d.description = $description,
            d.refid = $refid,
            d.source_type = $source_type,
            d.component_id = $component_id,
            d.is_intercomponent = $is_intercomponent,
            d.file_path = $file_path,
            d.line_number = $line_number,
            d.type_signature = $type_signature,
            d.argsstring = $argsstring,
            d.definition = $definition,
            d.is_static = $is_static,
            d.is_const = $is_const,
            d.is_virtual = $is_virtual,
            d.is_abstract = $is_abstract,
            d.is_final = $is_final,
            d.implementation_status = $implementation_status,
            d.source_file = $source_file,
            d.test_file = $test_file
        """
        self._session.run(cypher, node.model_dump())
        return node

    def get_by_qualified_name(self, qualified_name: str) -> DesignNode | None:
        """Fetch a :Design node by qualified_name. Returns None if not found."""
        result = self._session.run(
            "MATCH (d:Design {qualified_name: $qn}) RETURN d",
            {"qn": qualified_name},
        )
        record = result.single()
        if record is None:
            return None
        props = dict(record["d"])
        return DesignNode(**props)

    def find_nodes(
        self,
        kind: str | None = None,
        search: str | None = None,
        component_id: int | None = None,
    ) -> list[DesignNode]:
        """Find :Design nodes matching optional filters."""
        conditions = ["d:Design"]
        params: dict = {}

        if kind:
            conditions.append("d.kind = $kind")
            params["kind"] = kind
        if component_id is not None:
            conditions.append("d.component_id = $comp_id")
            params["comp_id"] = component_id
        if search:
            conditions.append("(d.name CONTAINS $search OR d.qualified_name CONTAINS $search)")
            params["search"] = search

        where = " AND ".join(conditions)
        cypher = f"MATCH (d) WHERE {where} RETURN d"

        result = self._session.run(cypher, params)
        nodes = []
        for record in result:
            props = dict(record["d"])
            try:
                nodes.append(DesignNode(**props))
            except Exception:
                log.warning("Skipping Design node with invalid props: %s", props)
        return nodes

    def delete_node(self, qualified_name: str) -> bool:
        """Delete a :Design node and all its relationships. Returns True if deleted."""
        result = self._session.run(
            "MATCH (d:Design {qualified_name: $qn}) DETACH DELETE d RETURN count(d) AS cnt",
            {"qn": qualified_name},
        )
        record = result.single()
        return record is not None and record["cnt"] > 0

    # -----------------------------------------------------------------------
    # Triple / relationship operations
    # -----------------------------------------------------------------------

    def merge_triple(
        self,
        subject_qualified_name: str,
        predicate: str,
        object_qualified_name: str,
    ) -> None:
        """MERGE a typed relationship between two Design nodes.

        For dependency targets (object is a dependency stub), falls back
        to matching :Compound nodes.
        """
        rel_type = PREDICATE_TO_REL_TYPE.get(predicate)
        if not rel_type:
            log.warning("Unknown predicate %r — skipping triple", predicate)
            return

        cypher = f"""
        MATCH (s:Design {{qualified_name: $subj}})
        OPTIONAL MATCH (o_design:Design {{qualified_name: $obj}})
        OPTIONAL MATCH (o_compound:Compound {{qualified_name: $obj}})
        WITH s, coalesce(o_design, o_compound) AS target
        WHERE target IS NOT NULL
        MERGE (s)-[r:{rel_type}]->(target)
        """
        self._session.run(
            cypher,
            {"subj": subject_qualified_name, "obj": object_qualified_name},
        )

    # -----------------------------------------------------------------------
    # HLR/LLR stub operations (temporary bridge — Phase 1 only)
    # -----------------------------------------------------------------------

    def merge_hlr_stub(self, sqlite_id: int, description: str, component_id: int | None = None) -> None:
        """Create or update an :HLR stub node. Phase 1 bridge to SQLite HLRs.

        These stubs enable Cypher traversal from HLR→Design for requirement
        tagging while HLRs still live in SQLite. Phase 2 makes HLRs full
        Neo4j citizens and removes sqlite_id.
        """
        self._session.run(
            """
            MERGE (h:HLR {sqlite_id: $sid})
            SET h.description = $desc,
                h.component_id = $cid
            """,
            {"sid": sqlite_id, "desc": description, "cid": component_id},
        )

    def merge_llr_stub(self, sqlite_id: int, description: str) -> None:
        """Create or update an :LLR stub node. Phase 1 bridge."""
        self._session.run(
            """
            MERGE (l:LLR {sqlite_id: $sid})
            SET l.description = $desc
            """,
            {"sid": sqlite_id, "desc": description},
        )

    def trace_design_to_hlr(self, hlr_sqlite_id: int, design_qualified_name: str) -> None:
        """Create a TRACES_TO edge from an HLR stub to a Design node."""
        self._session.run(
            """
            MATCH (h:HLR {sqlite_id: $hid})
            MATCH (d:Design {qualified_name: $qn})
            MERGE (h)-[:TRACES_TO]->(d)
            """,
            {"hid": hlr_sqlite_id, "qn": design_qualified_name},
        )

    def trace_design_to_llr(self, llr_sqlite_id: int, design_qualified_name: str) -> None:
        """Create a TRACES_TO edge from an LLR stub to a Design node."""
        self._session.run(
            """
            MATCH (l:LLR {sqlite_id: $lid})
            MATCH (d:Design {qualified_name: $qn})
            MERGE (l)-[:TRACES_TO]->(d)
            """,
            {"lid": llr_sqlite_id, "qn": design_qualified_name},
        )

    def untrace_design_from_hlr(self, hlr_sqlite_id: int, design_qualified_name: str) -> None:
        """Remove a TRACES_TO edge from an HLR stub to a Design node."""
        self._session.run(
            """
            MATCH (h:HLR {sqlite_id: $hid})-[r:TRACES_TO]->(d:Design {qualified_name: $qn})
            DELETE r
            """,
            {"hid": hlr_sqlite_id, "qn": design_qualified_name},
        )

    # -----------------------------------------------------------------------
    # Bulk operations
    # -----------------------------------------------------------------------

    def clear_design_graph(self) -> bool:
        """Delete all :Design nodes and their relationships."""
        try:
            self._session.run("MATCH (n:Design) DETACH DELETE n")
            log.info("Cleared design graph from Neo4j")
            return True
        except Exception:
            log.warning("Neo4j clear failed", exc_info=True)
            return False

    def sync_implementation_status(self, qualified_name: str, status: str, source_file: str = "", test_file: str = "") -> None:
        """Update implementation_status on a :Design node."""
        self._session.run(
            """
            MATCH (d:Design {qualified_name: $qn})
            SET d.implementation_status = $status,
                d.source_file = $source_file,
                d.test_file = $test_file
            """,
            {
                "qn": qualified_name,
                "status": status,
                "source_file": source_file,
                "test_file": test_file,
            },
        )
```

- [ ] **Step 4: Add `ensure_design_constraints()` to `backend/db/neo4j/connection.py`**

Add this method to the `Neo4jConnection` class, after the existing `ensure_constraints()` method:

```python
    def ensure_design_constraints(self):
        """Create constraints and indexes for the design layer.

        Called once at application startup (or when the design repository
        is first used). Extends the base Neo4j constraints.
        """
        if not self.verify_connectivity():
            log.warning("Neo4j not reachable — skipping design constraint setup")
            return False
        statements = [
            "CREATE CONSTRAINT design_qualified_name IF NOT EXISTS FOR (n:Design) REQUIRE n.qualified_name IS UNIQUE",
            "CREATE CONSTRAINT hlr_sqlite_id IF NOT EXISTS FOR (n:HLR) REQUIRE n.sqlite_id IS UNIQUE",
            "CREATE CONSTRAINT llr_sqlite_id IF NOT EXISTS FOR (n:LLR) REQUIRE n.sqlite_id IS UNIQUE",
            "CREATE INDEX design_kind IF NOT EXISTS FOR (n:Design) ON (n.kind)",
            "CREATE INDEX design_component_id IF NOT EXISTS FOR (n:Design) ON (n.component_id)",
        ]
        with self.session() as session:
            for stmt in statements:
                session.run(stmt)
        log.info("Neo4j design constraints and indexes ensured")
        return True
```

- [ ] **Step 5: Run the integration tests (skipped by default, enable manually)**

The integration tests are skipped unless `NEO4J_URI` is set and the skipif is disabled. For now, verify the unit tests (Pydantic model + constants) pass:

Run: `cd /Users/danielnewman/dev/ticketing_system && python -m pytest tests/test_design_repository.py::TestDesignNodeModel -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/db/neo4j/repositories/ backend/db/neo4j/connection.py tests/test_design_repository.py
git commit -m "feat: add DesignRepository with MERGE/MATCH/DELETE Cypher operations"
```

---

### Task 3: Rewrite `graph_tags.py` to Use Cypher Traversal

**Files:**
- Modify: `backend/requirements/services/graph_tags.py`
- Test: `tests/test_graph_tags.py`

This is the first consumer to switch from the two-stage pipeline (Neo4j topology → SQLite enrichment) to pure Cypher.

- [ ] **Step 1: Write the test for Cypher-based enrichment**

Replace `tests/test_graph_tags.py` with tests that use the `:HLR`/`:LLR` stub nodes and `TRACES_TO` edges instead of SQLite M2M tables. These tests need Neo4j, so they are integration tests marked with a skipif:

```python
"""Tests for Cypher-based requirement tag enrichment."""

import os
import pytest
from backend.db.neo4j.repositories.design import DesignRepository
from backend.db.neo4j.repositories.models import DesignNode

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_NEO4J_INTEGRATION") != "1",
    reason="Set RUN_NEO4J_INTEGRATION=1 to run Neo4j integration tests"
)


@pytest.fixture
def neo4j_session():
    from backend.db.neo4j.connection import get_standalone_driver
    driver = get_standalone_driver()
    session = driver.session(database="neo4j")
    yield session
    session.run("MATCH (n:Design) DETACH DELETE n")
    session.run("MATCH (n:HLR) DETACH DELETE n")
    session.run("MATCH (n:LLR) DETACH DELETE n")
    session.close()
    driver.close()


class TestEnrichWithRequirementTagsCypher:
    def test_tags_design_nodes_with_hlr_badges(self, neo4j_session):
        from backend.requirements.services.graph_tags import enrich_with_requirement_tags

        repo = DesignRepository(neo4j_session)
        repo.merge_node(DesignNode(qualified_name="calc::Foo", name="Foo", kind="class"))
        repo.merge_hlr_stub(sqlite_id=1, description="The system shall calculate")
        repo.trace_design_to_hlr(hlr_sqlite_id=1, design_qualified_name="calc::Foo")

        nodes = [
            {"data": {"id": "calc::Foo", "qualified_name": "calc::Foo", "kind": "class", "name": "Foo"}},
            {"data": {"id": "calc::Bar", "qualified_name": "calc::Bar", "kind": "class", "name": "Bar"}},
        ]

        enrich_with_requirement_tags(nodes, mode="hlr", session=neo4j_session)

        assert len(nodes[0]["data"]["requirements"]) == 1
        assert nodes[0]["data"]["requirements"][0]["type"] == "HLR"
        assert "requirements" not in nodes[1]["data"]

    def test_mode_none_returns_unchanged(self):
        from backend.requirements.services.graph_tags import enrich_with_requirement_tags

        nodes = [{"data": {"id": "n1", "qualified_name": "ns::Foo"}}]
        result = enrich_with_requirement_tags(nodes, mode="none")
        assert result == nodes
        assert "requirements" not in result[0]["data"]


class TestTagDirectNodesOnlyCypher:
    def test_marks_seed_nodes_with_highlight(self, neo4j_session):
        from backend.requirements.services.graph_tags import tag_direct_nodes_only

        repo = DesignRepository(neo4j_session)
        repo.merge_node(DesignNode(qualified_name="calc::Direct", name="Direct", kind="class"))
        repo.merge_node(DesignNode(qualified_name="calc::Neighbour", name="Neighbour", kind="class"))
        repo.merge_hlr_stub(sqlite_id=1, description="A requirement")
        repo.trace_design_to_hlr(hlr_sqlite_id=1, design_qualified_name="calc::Direct")

        nodes = [
            {"data": {"id": "calc::Direct", "qualified_name": "calc::Direct", "kind": "class", "name": "Direct", "label": "Direct"}},
            {"data": {"id": "calc::Neighbour", "qualified_name": "calc::Neighbour", "kind": "class", "name": "Neighbour", "label": "Neighbour"}},
        ]
        tag_direct_nodes_only(nodes, hlr_id=1, session=neo4j_session)

        assert nodes[0]["data"]["is_hlr_highlight"] == "true"
        assert len(nodes[0]["data"]["requirements"]) == 1
        assert nodes[1]["data"].get("is_hlr_highlight", "") == ""
```

- [ ] **Step 2: Run tests to verify they are properly skipped**

Run: `cd /Users/danielnewman/dev/ticketing_system && python -m pytest tests/test_graph_tags.py -v`
Expected: Tests are skipped (SKIP message about `RUN_NEO4J_INTEGRATION`).

- [ ] **Step 3: Rewrite `backend/requirements/services/graph_tags.py`**

Replace the entire file with Cypher-based implementations:

```python
"""Cypher-based enrichment for Cytoscape node dicts — add HLR requirement tags.

Stage 1 (Neo4j) now produces bare topology AND traces HLR→Design edges.
Stage 2 enriches nodes with requirement metadata from :HLR stub nodes.

In Phase 1, :HLR and :LLR stubs carry a sqlite_id property for
cross-referencing. After Phase 2, they become full nodes with
native IDs and this code simplifies further.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from neo4j import Session as Neo4jSession

log = logging.getLogger(__name__)


def enrich_with_requirement_tags(
    nodes: list[dict],
    mode: str = "none",
    session: "Neo4jSession | None" = None,
) -> list[dict]:
    """Tag design nodes with HLR badges from Neo4j :HLR stub nodes.

    Modifies nodes in-place, adding a 'requirements' key to each node
    that is traced by one or more HLRs.

    Args:
        nodes: Cytoscape-format node dicts (from Stage 1).
        mode: "none" = no tags, "hlr" = add HLR tags.
        session: Neo4j session for Cypher queries.

    Returns:
        The same list (modified in-place).
    """
    if mode == "none":
        return nodes

    node_qns = [
        n["data"].get("qualified_name")
        for n in nodes
        if n["data"].get("qualified_name") and n["data"].get("source_type") != "dependency"
    ]
    if not node_qns:
        return nodes

    if session is None:
        from backend.db.neo4j.connection import get_neo4j
        neo4j_conn = get_neo4j()
        with neo4j_conn.session() as sess:
            _enrich_via_cypher(sess, node_qns, nodes)
    else:
        _enrich_via_cypher(session, node_qns, nodes)

    return nodes


def _enrich_via_cypher(
    session: "Neo4jSession",
    node_qns: list[str],
    nodes: list[dict],
) -> None:
    """Run Cypher to find HLR→Design traces and tag matching nodes."""
    qn_to_reqs: dict[str, list[dict]] = {}

    result = session.run(
        """
        UNWIND $qns AS qn
        MATCH (hlr:HLR)-[:TRACES_TO]->(d:Design {qualified_name: qn})
        RETURN d.qualified_name AS qn, hlr.sqlite_id AS hlr_id, hlr.description AS hlr_desc
        """,
        {"qns": node_qns},
    )
    for record in result:
        qn = record["qn"]
        qn_to_reqs.setdefault(qn, []).append({
            "id": record["hlr_id"],
            "type": "HLR",
            "description": (record["hlr_desc"] or "")[:80],
        })

    for node in nodes:
        d = node["data"]
        qn = d.get("qualified_name", "")
        if qn in qn_to_reqs:
            d["requirements"] = qn_to_reqs[qn]
            badges = " ".join(f"[{r['type']} {r['id']}]" for r in qn_to_reqs[qn])
            d["label"] = d.get("label", "") + "\n" + badges
            d["has_requirements"] = "true"


def tag_direct_nodes_only(
    nodes: list[dict],
    hlr_id: int,
    session: "Neo4jSession | None" = None,
) -> None:
    """Mark seed nodes in an HLR subgraph with is_hlr_highlight and requirements tag.

    Args:
        nodes: Cytoscape-format node dicts.
        hlr_id: SQLite ID of the HLR to tag for (Phase 1 bridge).
        session: Neo4j session.
    """
    seed_qns: set[str] = set()

    def _query(sess: "Neo4jSession") -> None:
        nonlocal seed_qns
        result = sess.run(
            """
            MATCH (hlr:HLR {sqlite_id: $hid})-[:TRACES_TO]->(d:Design)
            RETURN d.qualified_name AS qn, hlr.description AS hlr_desc
            """,
            {"hid": hlr_id},
        )
        for record in result:
            seed_qns.add(record["qn"])
            # Capture description for badge text
            hlr_desc = (record["hlr_desc"] or "")[:80]

    if session is not None:
        _query(session)
    else:
        from backend.db.neo4j.connection import get_neo4j
        with get_neo4j().session() as sess:
            _query(sess)

    if not seed_qns:
        return

    # Fetch HLR description for badge
    hlr_desc = ""
    if session is not None:
        rec = session.run(
            "MATCH (hlr:HLR {sqlite_id: $hid}) RETURN hlr.description AS desc",
            {"hid": hlr_id},
        ).single()
        if rec:
            hlr_desc = (rec["desc"] or "")[:80]

    for node in nodes:
        d = node["data"]
        qn = d.get("qualified_name", "")
        if qn in seed_qns:
            d["is_hlr_highlight"] = "true"
            d.setdefault("requirements", []).append({
                "id": hlr_id,
                "type": "HLR",
                "description": hlr_desc,
            })
            badge = f"[HLR {hlr_id}]"
            d["label"] = d.get("label", "") + "\n" + badge
            d["has_requirements"] = "true"
```

- [ ] **Step 4: Commit**

```bash
git add backend/requirements/services/graph_tags.py tests/test_graph_tags.py
git commit -m "refactor: rewrite graph_tags.py to use Cypher TRACES_TO traversal instead of SQLite M2M"
```

---

### Task 4: Rewrite `persistence.py` `persist_design()` to Use DesignRepository

**Files:**
- Modify: `backend/requirements/services/persistence.py`
- Test: `tests/test_persistence.py`

- [ ] **Step 1: Rewrite `persist_design()` to use DesignRepository**

In `backend/requirements/services/persistence.py`, replace the SQLAlchemy-based `persist_design()` with one that writes directly to Neo4j via `DesignRepository`. The function still creates HLR/LLR link stubs in Neo4j (Phase 1 bridge). The `OntologyNode` and `OntologyTriple` imports are removed. Key changes:

- Import `DesignRepository` and `DesignNode` from the new repository
- Replace `get_or_create(OntologyNode, ...)` calls with `repo.merge_node(DesignNode(...))`
- Replace `get_or_create(OntologyTriple, ...)` with `repo.merge_triple()`
- Replace SQLAlchemy HLR↔node M2M append with `repo.trace_design_to_hlr()`
- Remove `try_sync_design_nodes_and_triples()` call (no more dual-write)
- Keep `persist_decomposition()` and `persist_verification()` unchanged (they don't touch design data)
- Keep `build_verification_context()`, `resolve_ontology_node()`, `validate_verification_references()`, and `augment_design_for_unresolved()` unchanged for now (they're used by verification which migrates in Phase 3)

The key signature change: `persist_design()` now takes a Neo4j session instead of a SQLAlchemy session. The caller must provide both if HLR links are needed (Phase 1 bridge).

- [ ] **Step 2: Update callers of `persist_design()`**

Search for all callers of `persist_design` and update them:
- `backend/ticketing_agent/design/design_per_hlr.py` — pass Neo4j session
- `backend/pipeline/orchestrator.py` — remove sync phase, use DesignRepository directly
- `scripts/03_design_requirements.py` — update script

For each caller, the pattern is:
```python
with get_session() as sql_session:
    # Still need SQLite for HLR/LLR (Phase 1)
    ...
with get_neo4j().session() as neo4j_session:
    repo = DesignRepository(neo4j_session)
    result = persist_design(neo4j_session, design, qname_to_node=qname_to_node)
```

- [ ] **Step 3: Rewrite `test_persistence.py`**

The test needs to create a real Neo4j session instead of a SQLAlchemy session. Mark as integration test with skipif. Test that `persist_design()` creates :Design nodes and :HLR stubs with TRACES_TO edges in Neo4j.

- [ ] **Step 4: Commit**

```bash
git add backend/requirements/services/persistence.py backend/ticketing_agent/design/ backend/pipeline/orchestrator.py scripts/ tests/test_persistence.py
git commit -m "refactor: rewrite persist_design() to use DesignRepository instead of SQLAlchemy"
```

---

### Task 5: Update Frontend Data Layer and Query Modules

**Files:**
- Modify: `frontend/data/ontology.py`
- Modify: `frontend/data/hlr.py`
- Modify: `backend/db/neo4j/queries/graph.py`
- Modify: `backend/db/neo4j/queries/detail.py`
- Modify: `backend/db/neo4j/__init__.py`

- [ ] **Step 1: Update `backend/db/neo4j/queries/graph.py`**

The `fetch_hlr_subgraph()` function currently does a two-step: SQLite query for seed qualified_names, then Neo4j for the graph. Rewrite to use Cypher directly starting from `:HLR` stub nodes:

```python
def fetch_hlr_subgraph(hlr_id: int, component_id: int | None = None) -> dict:
    """Fetch design subgraph around an HLR using Cypher traversal.

    In Phase 1, hlr_id is the sqlite_id property on :HLR stub nodes.
    """
    log.info("fetch_hlr_subgraph(hlr_id=%d, component_id=%s)", hlr_id, component_id)
    with get_neo4j().session() as session:
        # Find seed nodes traced by this HLR
        seed_result = session.run(
            """
            MATCH (hlr:HLR {sqlite_id: $hid})-[:TRACES_TO]->(d:Design)
            RETURN d
            """,
            {"hid": hlr_id},
        )
        seed_qns = []
        for record in seed_result:
            qn = dict(record["d"]).get("qualified_name", "")
            if qn:
                seed_qns.append(qn)

        if not seed_qns:
            return {"nodes": [], "edges": []}

        # Fetch seed nodes + 1-hop neighbours (same logic as before but
        # using UNWIND on seed_qns instead of a separate SQLite query)
        return _fetch_neighbourhood_from_seeds(session, seed_qns, component_id)
```

Also update `fetch_design_graph()` and `fetch_node_detail()` to remove the SQLite enrichment comments and note that requirement data comes from Cypher TRACES_TO edges.

- [ ] **Step 2: Update `frontend/data/ontology.py`**

- `fetch_ontology_data()`: Replace SQLAlchemy queries for node counts with Cypher queries or DesignRepository calls
- `fetch_ontology_graph_data()`: Remove the `enrich_with_requirement_tags()` call that uses a SQLAlchemy session parameter; the enrichment now uses the Neo4j-only `enrich_with_requirement_tags()`
- `fetch_hlr_graph_data()`: Update to use the new `fetch_hlr_subgraph()` which no longer needs SQLite
- `fetch_node_detail_full()`: Replace SQLAlchemy OntologyNode query with DesignRepository call for basic properties, then Neo4j for relationships and HLR traces
- `update_member_type()`: Update both the Neo4j property AND remove the SQLAlchemy update

- [ ] **Step 3: Update `frontend/data/hlr.py`**

- `decompose_hlr()`: Still uses SQLite for HLR creation (Phase 1 bridge), but also creates the `:HLR` stub in Neo4j via `DesignRepository.merge_hlr_stub()`
- `design_single_hlr()`: Calls `persist_design()` with Neo4j session

- [ ] **Step 4: Update `backend/db/neo4j/__init__.py`**

Add new repository and model re-exports. Remove sync function re-exports:

```python
"""Neo4j data access — connection, repositories, and raw queries."""

from backend.db.neo4j.connection import (
    NEO4J_PASSWORD,
    NEO4J_URI,
    NEO4J_USER,
    Neo4jConnection,
    close_standalone_driver,
    get_standalone_driver,
    get_standalone_session,
)
from backend.db.neo4j.queries import (
    fetch_codebase_compounds,
    fetch_dependency_compounds,
    fetch_design_dependency_links,
    fetch_design_graph,
    fetch_hlr_subgraph,
    fetch_neighbourhood_graph,
    fetch_node_detail,
)
from backend.db.neo4j.repositories import DesignRepository
from backend.db.neo4j.repositories.models import DesignNode, DesignTripleUpdate

__all__ = [
    "Neo4jConnection",
    "NEO4J_URI",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
    "get_standalone_driver",
    "get_standalone_session",
    "close_standalone_driver",
    # Repositories
    "DesignRepository",
    "DesignNode",
    "DesignTripleUpdate",
    # Queries
    "fetch_codebase_compounds",
    "fetch_dependency_compounds",
    "fetch_design_dependency_links",
    "fetch_design_graph",
    "fetch_hlr_subgraph",
    "fetch_neighbourhood_graph",
    "fetch_node_detail",
]
```

- [ ] **Step 5: Commit**

```bash
git add frontend/data/ backend/db/neo4j/__init__.py backend/db/neo4j/queries/
git commit -m "refactor: update frontend data layer and Neo4j queries to use DesignRepository"
```

---

### Task 6: Remove Old SQLAlchemy Design Models and Sync Code

**Files:**
- Modify: `backend/db/models/associations.py` — remove 4 M2M tables
- Modify: `backend/db/models/requirements.py` — remove M2M relationships
- Modify: `backend/db/models/ontology.py` — remove M2M reverse relationships and imports
- Modify: `backend/db/models/tasks.py` — add ontology_node_qualified_name column
- Modify: `backend/db/models/verification.py` — add ontology_node_qualified_name columns
- Modify: `backend/db/neo4j/sync.py` — remove design node/triple sync, keep task/implementation sync
- Modify: `backend/db/models/__init__.py` — remove M2M table exports
- Modify: `backend/pipeline/services.py` — remove build_qname_to_node, update persist_tasks
- Modify: `backend/pipeline/orchestrator.py` — remove qname_to_node dict
- Modify: `tests/` — update tests for new schema

**⚠️ Deviations from original plan — items kept as Phase 1 bridge:**

The original plan called for deleting `ontology.py` and `sync.py` entirely, and removing
`OntologyNode`/`OntologyTriple`/`Predicate` exports from `__init__.py`. These were kept because
many consumers still reference them:

1. **`ontology.py` NOT deleted** — Still imported by:
   - `persistence.py`: `resolve_ontology_node`, `build_verification_context`, `augment_design_for_unresolved`
   - `pipeline/services.py`: `persist_tasks` (via `TaskDesignNode.ontology_node` FK)
   - `pipeline/orchestrator.py`: Phase 3 verification context, Phase 10 implementation status sync
   - `review/review_class_design.py`: heavy usage for review agent
   - `review/challenge_design.py`: challenge agent
   - `mcp_server.py`: node/triple list and delete operations
   - `design_ontology.py`, `design_oo_prompt.py`: constants (`NODE_KIND_VALUES`, `LANGUAGE_SPECIALIZATIONS`)
   - `codebase/schemas.py`: constant imports (`NODE_KINDS`, `SOURCE_TYPES`, `VISIBILITY_CHOICES`)
   - `components.py`: `Component.ontology_nodes` relationship
   - `verification.py`: FK references to `ontology_nodes` table
   - `tasks.py`: FK reference to `ontology_nodes` table
   - Various tests and scripts

   Full removal is deferred to Phase 3 (verification migration).

2. **`sync.py` NOT deleted** — Trimmed to only non-design-sync functions:
   - `clear_design_graph()` — still used by `scripts/01_flush_db.py`
   - `link_implemented_nodes()` — called by `sync_full_design`
   - `sync_full_design()` — called by orchestrator Phase 10 (now only does IMPLEMENTED_BY links)
   - `sync_task()` — called by orchestrator Phase 10 (updated to use `ontology_node_qualified_name`)
   - `sync_implementation_status()` — called by orchestrator Phase 10
   - Removed: `sync_design_node`, `sync_design_triple`, `try_sync_design_nodes_and_triples`

3. **`OntologyNode`/`OntologyTriple`/`Predicate` exports kept in `__init__.py`** — Still referenced by
   consumers listed above. Removal deferred to Phase 3.

4. **`TaskDesignNode.ontology_node_id` FK kept** — Now nullable (was NOT NULL) with a new
   `ontology_node_qualified_name` column as the preferred reference. The FK will be removed
   in Phase 3 when `ontology_nodes` table is dropped.

5. **`VerificationCondition.ontology_node_id` and `VerificationAction.ontology_node_id` FKs kept** —
   New `ontology_node_qualified_name` string columns added alongside. FK removal deferred to Phase 3.

- [ ] **Step 1: Remove OntologyNode, OntologyTriple, and Predicate from `backend/db/models/__init__.py`**

Remove these lines from `__init__.py`:
```python
from backend.db.models.ontology import (
    LANGUAGE_SPECIALIZATIONS,
    NODE_KIND_VALUES,
    NODE_KINDS,
    SOURCE_TYPE_VALUES,
    SOURCE_TYPES,
    SUPPORTED_LANGUAGES,
    TYPE_KINDS,
    VALUE_KINDS,
    VISIBILITY_CHOICES,
    OntologyNode,
    OntologyTriple,
    Predicate,
    valid_specializations,
)
```

And remove their entries from `__all__`.

- [ ] **Step 2: Remove 4 M2M tables from `backend/db/models/associations.py`**

Remove these tables:
- `high_level_requirements_triples`
- `low_level_requirements_triples`
- `high_level_requirements_nodes`
- `low_level_requirements_nodes`

Keep: `low_level_requirements_components`, `tickets_components`, `tickets_languages`, `dependency_components` (these are for Phase 2+).

- [ ] **Step 3: Update `backend/db/models/requirements.py`**

Remove imports and relationships referencing `OntologyNode` and `OntologyTriple`:
- Remove `ontology_nodes` relationship on `HighLevelRequirement`
- Remove `ontology_nodes` relationship on `LowLevelRequirement`
- Remove `triples` relationship on both
- Remove the M2M imports from associations
- Keep the `component` relationship and `low_level_requirements` relationship

- [ ] **Step 4: Update `backend/db/models/tasks.py`**

Replace the `ontology_node` relationship on `TaskDesignNode` with a `qualified_name` string property referencing the Design node:

```python
class TaskDesignNode(Base):
    __tablename__ = "task_design_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    ontology_node_qualified_name: Mapped[str] = mapped_column(String(500), nullable=False)
    # FK to ontology_nodes removed — now references Design node by qualified_name

    task: Mapped[Task] = relationship("Task", back_populates="design_nodes")
```

- [ ] **Step 5: Update `backend/db/models/verification.py`**

Replace `ontology_node_id` FK on `VerificationCondition` and `VerificationAction` with `ontology_node_qualified_name` string property:

```python
class VerificationCondition(Base):
    __tablename__ = "verification_conditions"
    # ... existing fields ...
    ontology_node_qualified_name: Mapped[str] = mapped_column(String(500), default="", server_default="")
    # FK to ontology_nodes removed — now references by qualified_name
```

Same for `VerificationAction`.

- [ ] **Step 6: Create Alembic migration for schema changes**

Run: `cd /Users/danielnewman/dev/ticketing_system && alembic revision --autogenerate -m "remove_ontology_sqlalchemy_tables"`

Review the generated migration. It should:
- Drop the 4 M2M tables
- Change `task_design_nodes.ontology_node_id` to `task_design_nodes.ontology_node_qualified_name`
- Change `verification_conditions.ontology_node_id` to `verification_conditions.ontology_node_qualified_name`
- Change `verification_actions.ontology_node_id` to `verification_actions.ontology_node_qualified_name`

Edit the migration to also drop the `ontology_nodes`, `ontology_triples`, and `ontology_predicates` tables.

- [ ] **Step 7: Delete `backend/db/models/ontology.py`**

This file is no longer imported anywhere. Delete it.

- [ ] **Step 8: Delete `backend/db/neo4j/sync.py`**

All sync functionality is replaced by DesignRepository. Delete the file.

- [ ] **Step 9: Update `tests/conftest.py`**

Remove `Predicate` import and `Predicate.ensure_defaults()` from the fixture. Remove `OntologyNode` if present. The seeded_session fixture should still work for HLR/LLR/Component creation.

- [ ] **Step 10: Delete `tests/test_ontology_models.py`**

These tests are for the deleted SQLAlchemy models. They are replaced by `tests/test_design_repository.py`.

- [ ] **Step 11: Run remaining tests to verify nothing is broken**

Run: `cd /Users/danielnewman/dev/ticketing_system && python -m pytest tests/ -v --ignore=tests/test_ontology_models.py --ignore=tests/test_design_repository.py/TestDesignRepositoryIntegration -x`
Expected: All non-integration tests PASS.

- [ ] **Step 12: Commit**

```bash
git add -A
git commit -m "refactor: remove SQLAlchemy OntologyNode/OntologyTriple/Predicate models, M2M tables, and sync layer"
```

---

### Task 7: Data Migration Script

**Files:**
- Create: `scripts/migrate_phase1_design_to_neo4j.py`

This script migrates all existing design data from SQLite to Neo4j, including:
- All `ontology_nodes` rows → `:Design` nodes
- All `ontology_triples` rows → typed relationships
- All `high_level_requirements_nodes` M2M links → `TRACES_TO` edges from `:HLR` stubs
- All `high_level_requirements_triples` M2M links → `COVERED_BY` edges from `:HLR` stubs
- Same for LLR equivalents

- [ ] **Step 1: Write the migration script**

```bash
mkdir -p scripts
```

Create `scripts/migrate_phase1_design_to_neo4j.py`:

```python
#!/usr/bin/env python
"""Migrate Phase 1 design data from SQLite to Neo4j.

Reads ontology_nodes, ontology_triples, and HLR/LLR association tables
from SQLite and MERGEs them into Neo4j as :Design nodes, typed
relationships, and :HLR/:LLR stub nodes with TRACES_TO edges.

Usage:
    python scripts/migrate_phase1_design_to_neo4j.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.db import init_db, get_session
from backend.db.neo4j.connection import get_standalone_driver, Neo4jConnection
from backend.db.neo4j.repositories.design import DesignRepository
from backend.db.neo4j.repositories.models import DesignNode


def main():
    init_db()
    driver = get_standalone_driver()

    # Ensure constraints
    neo4j_conn = Neo4jConnection()
    neo4j_conn.ensure_constraints()
    neo4j_conn.ensure_design_constraints()

    with driver.session(database="neo4j") as neo4j_session:
        repo = DesignRepository(neo4j_session)

        # --- Migrate Design nodes ---
        with get_session() as sql_session:
            from backend.db.models import OntologyNode
            nodes = sql_session.query(OntologyNode).all()
            print(f"Migrating {len(nodes)} design nodes...")
            for node in nodes:
                dn = DesignNode(
                    qualified_name=node.qualified_name or node.name,
                    name=node.name,
                    kind=node.kind,
                    specialization=node.specialization or "",
                    visibility=node.visibility or "",
                    description=node.description or "",
                    refid=node.refid or "",
                    source_type=node.source_type or "",
                    type_signature=node.type_signature or "",
                    argsstring=node.argsstring or "",
                    definition=node.definition or "",
                    file_path=node.file_path or "",
                    line_number=node.line_number,
                    is_static=node.is_static or False,
                    is_const=node.is_const or False,
                    is_virtual=node.is_virtual or False,
                    is_abstract=node.is_abstract or False,
                    is_final=node.is_final or False,
                    component_id=node.component_id,
                    is_intercomponent=node.is_intercomponent or False,
                    implementation_status=node.implementation_status or "designed",
                    source_file=node.source_file or "",
                    test_file=node.test_file or "",
                )
                repo.merge_node(dn)
            print(f"  Migrated {len(nodes)} design nodes")

            # --- Migrate triples ---
            from backend.db.models import OntologyTriple, Predicate
            triples = sql_session.query(OntologyTriple).all()
            print(f"Migrating {len(triples)} triples...")
            predicate_cache = {}
            for pred in sql_session.query(Predicate).all():
                predicate_cache[pred.id] = pred.name
            for triple in triples:
                pred_name = predicate_cache.get(triple.predicate_id)
                if pred_name and triple.subject and triple.object:
                    subj_qn = triple.subject.qualified_name
                    obj_qn = triple.object.qualified_name
                    if subj_qn and obj_qn:
                        repo.merge_triple(subj_qn, pred_name, obj_qn)
            print(f"  Migrated {len(triples)} triples")

            # --- Migrate HLR stubs and TRACES_TO edges ---
            from backend.db.models import HighLevelRequirement
            hlrs = sql_session.query(HighLevelRequirement).all()
            print(f"Migrating {len(hlrs)} HLR stubs...")
            for hlr in hlrs:
                neo4j_session.run(
                    """
                    MERGE (h:HLR {sqlite_id: $sid})
                    SET h.description = $desc,
                        h.component_id = $cid
                    """,
                    {"sid": hlr.id, "desc": hlr.description, "cid": hlr.component_id},
                )
                for node in hlr.nodes:
                    if node.qualified_name:
                        repo.trace_design_to_hlr(hlr.id, node.qualified_name)
            print(f"  Migrated {len(hlrs)} HLR stubs")

            # --- Migrate LLR stubs and TRACES_TO edges ---
            from backend.db.models import LowLevelRequirement
            llrs = sql_session.query(LowLevelRequirement).all()
            print(f"Migrating {len(llrs)} LLR stubs...")
            for llr in llrs:
                neo4j_session.run(
                    """
                    MERGE (l:LLR {sqlite_id: $sid})
                    SET l.description = $desc
                    """,
                    {"sid": llr.id, "desc": llr.description},
                )
                for node in llr.nodes:
                    if node.qualified_name:
                        repo.trace_design_to_llr(llr.id, node.qualified_name)
            print(f"  Migrated {len(llrs)} LLR stubs")

    driver.close()
    print("Migration complete!")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test the migration script**

Run: `cd /Users/danielnewman/dev/ticketing_system && python scripts/migrate_phase1_design_to_neo4j.py`
Expected: Script prints progress messages and completes without errors.

- [ ] **Step 3: Verify migration by querying Neo4j**

Open Neo4j Browser and run:
```cypher
MATCH (d:Design) RETURN count(d) AS design_nodes
MATCH ()-[r:COMPOSES]->() RETURN count(r) AS composes_triples
MATCH (h:HLR)-[:TRACES_TO]->(d:Design) RETURN h.sqlite_id, count(d) AS traced_nodes
```

Expected: Counts match the SQLite data.

- [ ] **Step 4: Commit**

```bash
git add scripts/migrate_phase1_design_to_neo4j.py
git commit -m "feat: add Phase 1 data migration script from SQLite to Neo4j"
```

---

### Task 8: Final Integration Testing and Cleanup

**Files:**
- Test all remaining tests
- Clean up any remaining imports of deleted modules
- Update README or docs if needed

- [ ] **Step 1: Search for remaining references to deleted modules**

Run: `grep -rn "from backend.db.models.ontology import" --include="*.py" | grep -v ".venv" | grep -v __pycache__`
Run: `grep -rn "from backend.db.neo4j.sync import" --include="*.py" | grep -v ".venv" | grep -v __pycache__`
Run: `grep -rn "OntologyNode\|OntologyTriple\|Predicate" --include="*.py" backend/ | grep -v ".venv" | grep -v __pycache__ | grep -v "repositories/" | grep -v "test_design_repository.py"`

For each hit, either:
- Replace with the new repository/model import
- Remove the import if no longer needed
- Add a comment that the functionality moved to Phase 2+ (for requirements/task references that still use SQLAlchemy)

- [ ] **Step 2: Update `backend/codebase/schemas.py` if it imports from ontology**

Check if `backend/codebase/schemas.py` references `NODE_KINDS`, `SOURCE_TYPES`, etc. If so, update the import to point to `backend.db.neo4j.repositories.constants`.

- [ ] **Step 3: Update agent prompts that import from ontology**

Check `backend/ticketing_agent/design/design_ontology.py`, `design_ontology_prompt.py`, and other agent files for imports of `NODE_KIND_VALUES`, `LANGUAGE_SPECIALIZATIONS`, etc. Update imports to `backend.db.neo4j.repositories.constants`.

- [ ] **Step 4: Run the full test suite**

Run: `cd /Users/danielnewman/dev/ticketing_system && python -m pytest tests/ -v --ignore=tests/test_ontology_models.py -x`
Expected: All tests PASS (integration tests skipped if Neo4j not available).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: clean up remaining references to deleted ontology models and sync layer"
```

---

## Phase 1 Summary

After completing these 8 tasks:

- ✅ All design node, triple, and predicate data lives in Neo4j
- ✅ `DesignRepository` is the data access layer for design CRUD
- ✅ HLR/LLR stubs in Neo4j enable Cypher-based requirement tagging
- ✅ The two-stage pipeline (Neo4j → SQLite enrichment) is replaced by single Cypher queries
- ✅ `sync.py` is deleted — no more dual-write
- ✅ `OntologyNode`, `OntologyTriple`, `Predicate` SQLAlchemy models are deleted
- ✅ 4 M2M association tables are deleted
- ✅ `task_design_nodes.ontology_node_id` → `.ontology_node_qualified_name`
- ✅ Data migration script created and validated

The system is fully functional after Phase 1, with HLR/LLR still in SQLite but linked to Neo4j Design nodes via TRACES_TO edges. Phase 2 will promote HLR/LLR to full Neo4j citizens.