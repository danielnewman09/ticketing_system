# Robust Test Coverage for Ticketing System

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build comprehensive test coverage for the ticketing_system codebase, starting with test infrastructure and highest-ROI targets (persistence layer, ORM models, Pydantic schemas), then agent helpers, then MCP server integration.

**Architecture:** Tests use an in-memory SQLite database (no Neo4j, no external LLM calls). Each test gets a fresh schema-created session via pytest fixtures. Persistence functions are tested against real SQLAlchemy models. Agent functions are tested by mocking only the LLM call boundary.

**Tech Stack:** pytest ≥8.0, pytest-cov ≥5.0, pytest-mock ≥3.14, SQLAlchemy 2.0 (in-memory SQLite), Pydantic v2

---

## Current State

- **15 tests total** — all in `tests/test_oo_design_schema.py`, covering 1 Pydantic schema
- **0 tests** for: persistence layer, ORM models, agent functions, MCP server, frontend data layer, requirement schemas
- **No test infrastructure** — no `conftest.py`, no DB fixtures, no mock LLM fixtures

---

## Phase 1 — Test Infrastructure & Foundation

### Task 1: Add test dependencies to pyproject.toml

**Objective:** Ensure all test tooling is available

**Files:**
- Modify: `pyproject.toml:23-26`

**Step 1: Write failing test** (N/A — this is config)

**Step 2: Update pyproject.toml**

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "pytest-mock>=3.14",
]
```

**Step 3: Verify**

Run: `cd /home/dnewman/ticketing_system && pip install -e ".[dev]" 2>&1 | tail -5`
Expected: Successfully installed pytest-cov pytest-mock

**Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add pytest-cov and pytest-mock to dev dependencies"
```

---

### Task 2: Create conftest.py with in-memory DB fixture

**Objective:** Provide a reusable test database session that creates/drops all tables per test, without requiring sqlite-vec or Neo4j

**Files:**
- Create: `tests/conftest.py`
- Read: `backend/db/__init__.py` (for `get_or_create`, `Base`)
- Read: `backend/db/base.py` (for `Base` import path)

**Step 1: Write conftest.py**

```python
"""Shared test fixtures — in-memory SQLite with all ORM tables."""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from backend.db.base import Base

# Import all models so Base.metadata knows about every table
import backend.db.models  # noqa: F401


@pytest.fixture()
def engine():
    """Create a fresh in-memory SQLite engine per test.

    Does NOT load sqlite-vec extension — tests that need vector
    search should be integration tests, not unit tests.
    """
    eng = create_engine("sqlite:///:memory:")
    # Enable WAL mode for better concurrent access in tests
    @event.listens_for(eng, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    return eng


@pytest.fixture()
def tables(engine):
    """Create all tables before the test, drop after.

    Use this when you need tables but NOT a session.
    """
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture()
def session(engine, tables):
    """Provide a transactional session that rolls back after each test.

    This is the main fixture for persistence & ORM tests:
    - All tables are created before the test
    - The session is in a transaction that rolls back on teardown
    - No data leaks between tests
    """
    connection = engine.connect()
    transaction = connection.begin()
    sess = Session(bind=connection, expire_on_commit=False)

    yield sess

    sess.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def seeded_session(session):
    """Session pre-populated with minimal seed data:

    - 1 Language (C++)
    - 1 Component (Calculator) with language
    - 1 HighLevelRequirement ("The system shall perform arithmetic")
    - 3 Predicates (associates, composes, depends_on)
    """
    from backend.db.models.components import Component, Language
    from backend.db.models.requirements import HighLevelRequirement
    from backend.db.models.ontology import Predicate

    lang = Language(name="C++", version="17")
    session.add(lang)
    session.flush()

    comp = Component(name="Calculator", namespace="calc", language=lang)
    session.add(comp)
    session.flush()

    hlr = HighLevelRequirement(
        description="The system shall perform arithmetic operations",
        component=comp,
    )
    session.add(hlr)
    session.flush()

    # Seed predicates that persistence functions depend on
    Predicate.ensure_defaults(session)
    session.flush()

    # Stash IDs for convenience
    session._seed = {
        "language_id": lang.id,
        "component_id": comp.id,
        "hlr_id": hlr.id,
    }

    yield session
```

**Step 2: Verify conftest loads**

Run: `cd /home/dnewman/ticketing_system && python -m pytest --co -q 2>&1 | tail -5`
Expected: Still collects 15 tests (the existing ones) — conftest itself has no tests but must not break collection

**Step 3: Write a smoke test to prove the fixture works**

Create: `tests/test_conftest_smoke.py`

```python
"""Smoke test — proves conftest fixtures work end-to-end."""

from backend.db.models.requirements import HighLevelRequirement


def test_session_can_create_hlr(session):
    """The bare session fixture lets us create and query an HLR."""
    hlr = HighLevelRequirement(description="Test HLR")
    session.add(hlr)
    session.flush()
    assert hlr.id is not None
    found = session.query(HighLevelRequirement).filter_by(id=hlr.id).first()
    assert found is not None
    assert found.description == "Test HLR"


def test_seeded_session_has_defaults(seeded_session):
    """The seeded_session fixture pre-populates language, component, HLR, predicates."""
    from backend.db.models.components import Component, Language
    from backend.db.models.ontology import Predicate

    assert session.query(Language).count() == 1
    assert session.query(Component).count() == 1
    assert session.query(HighLevelRequirement).count() == 1
    assert session.query(Predicate).count() >= 3


def test_session_rolls_back_between_tests(session):
    """Each test starts with a clean DB — no data leaks."""
    assert session.query(HighLevelRequirement).count() == 0
```

**Step 4: Run the smoke tests**

Run: `cd /home/dnewman/ticketing_system && python -m pytest tests/test_conftest_smoke.py -v`
Expected: 3 passed

**Step 5: Run ALL tests to check for regressions**

Run: `cd /home/dnewman/ticketing_system && python -m pytest tests/ -q`
Expected: 18 passed (15 original + 3 smoke)

**Step 6: Commit**

```bash
git add tests/conftest.py tests/test_conftest_smoke.py
git commit -m "test: add conftest with in-memory DB fixtures and smoke tests"
```

---

## Phase 2 — ORM Model Tests

### Task 3: Test HighLevelRequirement model

**Objective:** Verify HLR CRUD, relationships, to_prompt_text, format helpers

**Files:**
- Create: `tests/test_requirements_models.py`

**Step 1: Write failing tests**

```python
"""Tests for HighLevelRequirement, LowLevelRequirement, and TicketRequirement models."""

import pytest
from backend.db.models.requirements import (
    HighLevelRequirement,
    LowLevelRequirement,
    TicketRequirement,
    format_hlr_dict,
    format_hlrs_for_prompt,
    format_llr_dict,
)
from backend.db.models.tickets import Ticket


class TestHighLevelRequirement:
    def test_create_hlr(self, seeded_session):
        hlr = HighLevelRequirement(description="New HLR")
        seeded_session.add(hlr)
        seeded_session.flush()
        assert hlr.id is not None
        assert hlr.description == "New HLR"

    def test_hlr_repr_truncates_long_description(self):
        hlr = HighLevelRequirement(description="x" * 200)
        assert len(repr(hlr)) <= 80

    def test_hlr_repr_short_description(self):
        hlr = HighLevelRequirement(description="Short")
        assert repr(hlr) == "Short"

    def test_hlr_to_prompt_text_without_llrs(self, seeded_session):
        hlr = seeded_session.query(HighLevelRequirement).first()
        text = hlr.to_prompt_text()
        assert "HLR" in text
        assert str(hlr.id) in text
        assert hlr.description in text

    def test_hlr_to_prompt_text_with_component(self, seeded_session):
        hlr = seeded_session.query(HighLevelRequirement).first()
        text = hlr.to_prompt_text(include_component=True)
        assert "Component" in text
        assert "Calculator" in text

    def test_hlr_to_prompt_text_with_llrs(self, seeded_session):
        hlr = seeded_session.query(HighLevelRequirement).first()
        llr = LowLevelRequirement(high_level_requirement=hlr, description="Sub-requirement")
        seeded_session.add(llr)
        seeded_session.flush()
        text = hlr.to_prompt_text(include_llrs=True)
        assert "LLR" in text
        assert "Sub-requirement" in text

    def test_hlr_component_relationship(self, seeded_session):
        from backend.db.models.components import Component
        hlr = seeded_session.query(HighLevelRequirement).first()
        comp = seeded_session.query(Component).first()
        assert hlr.component == comp
        assert hlr.component_id == comp.id


class TestLowLevelRequirement:
    def test_create_llr_under_hlr(self, seeded_session):
        hlr = seeded_session.query(HighLevelRequirement).first()
        llr = LowLevelRequirement(high_level_requirement=hlr, description="LLR 1")
        seeded_session.add(llr)
        seeded_session.flush()
        assert llr.id is not None
        assert llr.high_level_requirement_id == hlr.id
        assert hlr.low_level_requirements[0] == llr

    def test_llr_to_prompt_text(self, seeded_session):
        hlr = seeded_session.query(HighLevelRequirement).first()
        llr = LowLevelRequirement(high_level_requirement=hlr, description="Test LLR")
        seeded_session.add(llr)
        seeded_session.flush()
        text = llr.to_prompt_text()
        assert "LLR" in text
        assert "Test LLR" in text

    def test_llr_verifications_relationship(self, seeded_session):
        from backend.db.models.verification import VerificationMethod
        hlr = seeded_session.query(HighLevelRequirement).first()
        llr = LowLevelRequirement(high_level_requirement=hlr, description="LLR with vmethod")
        seeded_session.add(llr)
        seeded_session.flush()
        vm = VerificationMethod(low_level_requirement=llr, method="automated")
        seeded_session.add(vm)
        seeded_session.flush()
        assert len(llr.verifications) == 1


class TestFormatHelpers:
    def test_format_hlr_dict_without_component(self):
        hlr = {"id": 1, "description": "Test HLR"}
        result = format_hlr_dict(hlr)
        assert result == "HLR 1: Test HLR"

    def test_format_hlr_dict_with_component(self):
        hlr = {"id": 1, "description": "Test HLR", "component_name": "Engine"}
        result = format_hlr_dict(hlr, include_component=True)
        assert "[Component: Engine]" in result

    def test_format_hlr_dict_with_component_alt_key(self):
        hlr = {"id": 1, "description": "Test HLR", "component__name": "Engine"}
        result = format_hlr_dict(hlr, include_component=True)
        assert "[Component: Engine]" in result

    def test_format_hlrs_for_prompt_basic(self):
        hlrs = [{"id": 1, "description": "HLR one"}, {"id": 2, "description": "HLR two"}]
        result = format_hlrs_for_prompt(hlrs)
        assert "HLR 1: HLR one" in result
        assert "HLR 2: HLR two" in result

    def test_format_hlrs_for_prompt_with_llrs(self):
        hlrs = [{"id": 1, "description": "HLR one"}]
        llrs = [{"id": 10, "description": "LLR sub", "hlr_id": 1}]
        result = format_hlrs_for_prompt(hlrs, llrs)
        assert "LLR 10" in result

    def test_format_hlrs_for_prompt_unlinked_llrs(self):
        hlrs = [{"id": 1, "description": "HLR one"}]
        llrs = [{"id": 10, "description": "Orphan LLR", "hlr_id": None}]
        result = format_hlrs_for_prompt(hlrs, llrs)
        assert "Unlinked LLRs" in result

    def test_format_llr_dict(self):
        llr = {"id": 5, "description": "Sub req"}
        result = format_llr_dict(llr)
        assert result == "LLR 5: Sub req"
```

**Step 2: Run tests to verify failure**

Run: `cd /home/dnewman/ticketing_system && python -m pytest tests/test_requirements_models.py -v`
Expected: FAIL — tests need the seeded_session fixture and model imports to work

**Step 3: Verify after implementation (tests should pass on first run since models already exist)**

Run: `cd /home/dnewman/ticketing_system && python -m pytest tests/test_requirements_models.py -v`
Expected: All tests pass (these test existing code, not new features)

**Step 4: Commit**

```bash
git add tests/test_requirements_models.py
git commit -m "test: add ORM tests for requirements models and format helpers"
```

---

### Task 4: Test Ontology models (OntologyNode, Predicate, OntologyTriple)

**Objective:** Verify ontology CRUD, unique constraints, default predicates, node kinds validation

**Files:**
- Create: `tests/test_ontology_models.py`

**Step 1: Write failing tests**

```python
"""Tests for OntologyNode, Predicate, OntologyTriple models."""

import pytest
from sqlalchemy.exc import IntegrityError

from backend.db.models.ontology import (
    OntologyNode,
    OntologyTriple,
    Predicate,
    NODE_KIND_VALUES,
    VISIBILITY_CHOICES,
    valid_specializations,
    LANGUAGE_SPECIALIZATIONS,
    TYPE_KINDS,
    VALUE_KINDS,
)


class TestOntologyNode:
    def test_create_minimal_node(self, session):
        node = OntologyNode(kind="class", name="Foo", qualified_name="ns::Foo")
        session.add(node)
        session.flush()
        assert node.id is not None
        assert node.kind == "class"
        assert node.name == "Foo"

    def test_node_defaults(self, session):
        node = OntologyNode(kind="class", name="Bar", qualified_name="ns::Bar")
        session.add(node)
        session.flush()
        assert node.specialization == ""
        assert node.visibility == ""
        assert node.is_static is False
        assert node.is_const is False
        assert node.is_virtual is False
        assert node.is_abstract is False
        assert node.is_final is False
        assert node.is_intercomponent is False

    def test_node_repr_uses_qualified_name(self):
        node = OntologyNode(kind="class", name="Foo", qualified_name="ns::Foo")
        assert repr(node) == "ns::Foo"

    def test_node_repr_falls_back_to_name(self):
        node = OntologyNode(kind="class", name="Foo")
        assert repr(node) == "Foo"  # qualified_name defaults to ""

    def test_node_kind_values_are_comprehensive(self):
        """NODE_KIND_VALUES should cover all base kinds."""
        expected = {"attribute", "class", "constant", "enum", "enum_value",
                    "function", "interface", "method", "module", "primitive", "type_alias"}
        assert NODE_KIND_VALUES == expected

    def test_type_kinds_and_value_kinds_partition(self):
        """TYPE_KINDS and VALUE_KINDS should not overlap and together cover most kinds."""
        assert TYPE_KINDS & VALUE_KINDS == set()
        # Together they should cover everything except module and primitive
        union = TYPE_KINDS | VALUE_KINDS
        assert "class" in union
        assert "attribute" in union


class TestPredicate:
    def test_create_predicate(self, session):
        pred = Predicate(name="test_predicate", description="A test")
        session.add(pred)
        session.flush()
        assert pred.id is not None

    def test_predicate_name_unique(self, session):
        pred1 = Predicate(name="unique_pred")
        session.add(pred1)
        session.flush()
        pred2 = Predicate(name="unique_pred")
        session.add(pred2)
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()

    def test_ensure_defaults_creates_all(self, session):
        Predicate.ensure_defaults(session)
        session.flush()
        names = {p.name for p in session.query(Predicate).all()}
        for name, _ in Predicate.DEFAULT_PREDICATES:
            assert name in names

    def test_ensure_defaults_idempotent(self, session):
        Predicate.ensure_defaults(session)
        session.flush()
        count_after_first = session.query(Predicate).count()
        Predicate.ensure_defaults(session)
        session.flush()
        count_after_second = session.query(Predicate).count()
        assert count_after_first == count_after_second

    def test_predicate_repr(self):
        pred = Predicate(name="associates")
        assert repr(pred) == "associates"


class TestOntologyTriple:
    def test_create_triple(self, seeded_session):
        sub = OntologyNode(kind="class", name="A", qualified_name="A")
        obj = OntologyNode(kind="class", name="B", qualified_name="B")
        seeded_session.add_all([sub, obj])
        seeded_session.flush()
        pred = seeded_session.query(Predicate).filter_by(name="associates").first()
        triple = OntologyTriple(subject=sub, predicate=pred, object=obj)
        seeded_session.add(triple)
        seeded_session.flush()
        assert triple.id is not None
        assert triple.subject.qualified_name == "A"
        assert triple.object.qualified_name == "B"

    def test_triple_unique_constraint(self, seeded_session):
        sub = OntologyNode(kind="class", name="X", qualified_name="X")
        obj = OntologyNode(kind="class", name="Y", qualified_name="Y")
        seeded_session.add_all([sub, obj])
        seeded_session.flush()
        pred = seeded_session.query(Predicate).first()
        t1 = OntologyTriple(subject=sub, predicate=pred, object=obj)
        seeded_session.add(t1)
        seeded_session.flush()
        t2 = OntologyTriple(subject=sub, predicate=pred, object=obj)
        seeded_session.add(t2)
        with pytest.raises(IntegrityError):
            seeded_session.flush()

    def test_triple_cascade_deletes_with_subject(self, seeded_session):
        sub = OntologyNode(kind="class", name="Del", qualified_name="Del")
        obj = OntologyNode(kind="class", name="Keep", qualified_name="Keep")
        seeded_session.add_all([sub, obj])
        seeded_session.flush()
        pred = seeded_session.query(Predicate).first()
        t = OntologyTriple(subject=sub, predicate=pred, object=obj)
        seeded_session.add(t)
        seeded_session.flush()
        triple_id = t.id
        seeded_session.delete(sub)
        seeded_session.flush()
        assert seeded_session.query(OntologyTriple).filter_by(id=triple_id).first() is None

    def test_triple_repr(self, seeded_session):
        sub = OntologyNode(kind="class", name="R", qualified_name="R")
        obj = OntologyNode(kind="class", name="S", qualified_name="S")
        seeded_session.add_all([sub, obj])
        seeded_session.flush()
        pred = seeded_session.query(Predicate).filter_by(name="associates").first()
        t = OntologyTriple(subject=sub, predicate=pred, object=obj)
        seeded_session.add(t)
        seeded_session.flush()
        text = repr(t)
        assert "R" in text
        assert "associates" in text
        assert "S" in text


class TestValidSpecializations:
    def test_cpp_class_specializations(self):
        result = valid_specializations("cpp", "class")
        assert "struct" in result
        assert "abstract_class" in result

    def test_python_class_specializations(self):
        result = valid_specializations("python", "class")
        assert "dataclass" in result

    def test_unknown_language_returns_empty(self):
        result = valid_specializations("rust", "class")
        assert result == set()

    def test_unknown_kind_returns_empty(self):
        result = valid_specializations("cpp", "unknown_kind")
        assert result == set()
```

**Step 2: Run tests**

Run: `cd /home/dnewman/ticketing_system && python -m pytest tests/test_ontology_models.py -v`
Expected: All pass (testing existing model code)

**Step 3: Commit**

```bash
git add tests/test_ontology_models.py
git commit -m "test: add ORM tests for ontology models and specialty helpers"
```

---

### Task 5: Test Component and Dependency models

**Objective:** Verify Component tree structure, Language relationships, Dependency uniqueness

**Files:**
- Create: `tests/test_component_models.py`

**Step 1: Write failing tests**

```python
"""Tests for Component, Language, BuildSystem, TestFramework, DependencyManager, Dependency."""

import pytest
from sqlalchemy.exc import IntegrityError

from backend.db.models.components import (
    Component,
    Language,
    BuildSystem,
    TestFramework,
    DependencyManager,
    Dependency,
    DependencyRecommendation,
)


class TestComponent:
    def test_create_component(self, session):
        comp = Component(name="Engine")
        session.add(comp)
        session.flush()
        assert comp.id is not None

    def test_component_unique_name_per_parent(self, session):
        parent = Component(name="Parent")
        session.add(parent)
        session.flush()
        c1 = Component(name="Dup", parent=parent)
        c2 = Component(name="Dup", parent=parent)
        session.add_all([c1, c2])
        with pytest.raises(IntegrityError):
            session.flush()

    def test_component_same_name_different_parent_ok(self, session):
        p1 = Component(name="P1")
        p2 = Component(name="P2")
        session.add_all([p1, p2])
        session.flush()
        c1 = Component(name="Shared", parent=p1)
        c2 = Component(name="Shared", parent=p2)
        session.add_all([c1, c2])
        session.flush()  # Should NOT raise

    def test_component_tree_parent_child(self, session):
        parent = Component(name="Root")
        child = Component(name="Child", parent=parent)
        session.add_all([parent, child])
        session.flush()
        assert child.parent == parent
        assert child in parent.children

    def test_component_full_namespace_with_namespace(self):
        comp = Component(name="X", namespace="my::ns")
        assert comp.full_namespace == "my::ns"

    def test_component_full_namespace_without_namespace(self):
        comp = Component(name="X")
        assert comp.full_namespace == ""

    def test_component_to_prompt_text(self, session):
        lang = Language(name="Python")
        session.add(lang)
        session.flush()
        comp = Component(name="Backend", namespace="app.core", language=lang,
                        description="Core backend")
        session.add(comp)
        session.flush()
        text = comp.to_prompt_text()
        assert "Backend" in text
        assert "app.core" in text
        assert "Core backend" in text
        assert "Python" in text

    def test_component_cascade_deletes_children(self, session):
        parent = Component(name="Del")
        child = Component(name="DelChild", parent=parent)
        session.add_all([parent, child])
        session.flush()
        child_id = child.id
        session.delete(parent)
        session.flush()
        assert session.query(Component).filter_by(id=child_id).first() is None


class TestLanguage:
    def test_create_language(self, session):
        lang = Language(name="Rust", version="1.75")
        session.add(lang)
        session.flush()
        assert repr(lang) == "Rust 1.75"

    def test_language_repr_no_version(self):
        lang = Language(name="Go")
        assert repr(lang) == "Go"

    def test_language_name_unique(self, session):
        l1 = Language(name="UniqueLang")
        l2 = Language(name="UniqueLang")
        session.add_all([l1, l2])
        with pytest.raises(IntegrityError):
            session.flush()


class TestDependency:
    def test_create_dependency(self, session):
        lang = Language(name="DepLang")
        dm = DependencyManager(name="pip", language=lang, manifest_file="requirements.txt")
        session.add_all([lang, dm])
        session.flush()
        dep = Dependency(manager=dm, name="flask", version="3.0")
        session.add(dep)
        session.flush()
        assert dep.id is not None
        assert repr(dep) == "flask==3.0"

    def test_dependency_unique_per_manager(self, session):
        lang = Language(name="DepLang2")
        dm = DependencyManager(name="npm", language=lang, manifest_file="package.json")
        session.add_all([lang, dm])
        session.flush()
        d1 = Dependency(manager=dm, name="react")
        d2 = Dependency(manager=dm, name="react")
        session.add_all([d1, d2])
        with pytest.raises(IntegrityError):
            session.flush()


class TestDependencyRecommendation:
    def test_create_recommendation(self, seeded_session):
        from backend.db.models.components import Component, DependencyRecommendation
        comp = seeded_session.query(Component).first()
        rec = DependencyRecommendation(
            component=comp, name="boost", github_url="https://github.com/boostorg/boost",
            status="pending",
        )
        seeded_session.add(rec)
        seeded_session.flush()
        assert rec.id is not None
        assert "pending" in repr(rec)
```

**Step 2: Run tests**

Run: `cd /home/dnewman/ticketing_system && python -m pytest tests/test_component_models.py -v`
Expected: All pass

**Step 3: Commit**

```bash
git add tests/test_component_models.py
git commit -m "test: add ORM tests for component, language, and dependency models"
```

---

### Task 6: Test Verification models

**Objective:** Verify CRUD, cascade deletes, preconditions/postconditions property, to_prompt_text

**Files:**
- Create: `tests/test_verification_models.py`

**Step 1: Write failing tests**

```python
"""Tests for VerificationMethod, VerificationCondition, VerificationAction."""

import pytest

from backend.db.models.requirements import HighLevelRequirement, LowLevelRequirement
from backend.db.models.verification import (
    VERIFICATION_METHODS,
    VerificationMethod,
    VerificationCondition,
    VerificationAction,
)


class TestVerificationMethod:
    def test_create_verification_method(self, seeded_session):
        hlr = seeded_session.query(HighLevelRequirement).first()
        llr = LowLevelRequirement(high_level_requirement=hlr, description="LLR")
        seeded_session.add(llr)
        seeded_session.flush()
        vm = VerificationMethod(
            low_level_requirement=llr,
            method="automated",
            test_name="test_add",
            description="Test addition",
        )
        seeded_session.add(vm)
        seeded_session.flush()
        assert vm.id is not None
        assert vm.method == "automated"

    def test_verification_method_types_constant(self):
        assert set(VERIFICATION_METHODS) == {"automated", "review", "inspection"}

    def test_preconditions_postconditions_properties(self, seeded_session):
        hlr = seeded_session.query(HighLevelRequirement).first()
        llr = LowLevelRequirement(high_level_requirement=hlr, description="LLR 2")
        seeded_session.add(llr)
        seeded_session.flush()
        vm = VerificationMethod(low_level_requirement=llr, method="automated")
        seeded_session.add(vm)
        seeded_session.flush()
        pre = VerificationCondition(
            verification=vm, phase="pre", order=0,
            member_qualified_name="x", expected_value="1",
        )
        post = VerificationCondition(
            verification=vm, phase="post", order=0,
            member_qualified_name="y", expected_value="2",
        )
        seeded_session.add_all([pre, post])
        seeded_session.flush()
        assert len(vm.preconditions) == 1
        assert len(vm.postconditions) == 1
        assert vm.preconditions[0].member_qualified_name == "x"

    def test_cascade_delete_llr_deletes_vm(self, seeded_session):
        hlr = seeded_session.query(HighLevelRequirement).first()
        llr = LowLevelRequirement(high_level_requirement=hlr, description="ToDelete")
        seeded_session.add(llr)
        seeded_session.flush()
        vm = VerificationMethod(low_level_requirement=llr, method="review")
        seeded_session.add(vm)
        seeded_session.flush()
        vm_id = vm.id
        seeded_session.delete(llr)
        seeded_session.flush()
        assert seeded_session.query(VerificationMethod).filter_by(id=vm_id).first() is None

    def test_to_prompt_text_with_test_name(self):
        vm = VerificationMethod(method="automated", test_name="test_x", description="Test X")
        text = vm.to_prompt_text()
        assert "automated" in text
        assert "test_x" in text

    def test_to_prompt_text_without_test_name(self):
        vm = VerificationMethod(method="review", description="A review")
        text = vm.to_prompt_text()
        assert text.startswith("review")


class TestVerificationCondition:
    def test_create_condition(self, seeded_session):
        hlr = seeded_session.query(HighLevelRequirement).first()
        llr = LowLevelRequirement(high_level_requirement=hlr, description="LLR")
        seeded_session.add(llr)
        seeded_session.flush()
        vm = VerificationMethod(low_level_requirement=llr, method="automated")
        seeded_session.add(vm)
        seeded_session.flush()
        vc = VerificationCondition(
            verification=vm, phase="pre", order=0,
            member_qualified_name="calc::Engine::add", operator="==", expected_value="0",
        )
        seeded_session.add(vc)
        seeded_session.flush()
        assert vc.id is not None
        assert "calc::Engine::add" in repr(vc)


class TestVerificationAction:
    def test_create_action(self, seeded_session):
        hlr = seeded_session.query(HighLevelRequirement).first()
        llr = LowLevelRequirement(high_level_requirement=hlr, description="LLR")
        seeded_session.add(llr)
        seeded_session.flush()
        vm = VerificationMethod(low_level_requirement=llr, method="automated")
        seeded_session.add(vm)
        seeded_session.flush()
        va = VerificationAction(
            verification=vm, order=0,
            description="Call add()", member_qualified_name="calc::Engine::add",
        )
        seeded_session.add(va)
        seeded_session.flush()
        assert va.id is not None
```

**Step 2: Run tests**

Run: `cd /home/dnewman/ticketing_system && python -m pytest tests/test_verification_models.py -v`
Expected: All pass

**Step 3: Commit**

```bash
git add tests/test_verification_models.py
git commit -m "test: add ORM tests for verification models"
```

---

## Phase 3 — Pydantic Schema Tests

### Task 7: Test requirements schemas (DecomposedRequirementSchema, LowLevelRequirementSchema, VerificationSchema)

**Objective:** Verify schema validation, defaults, round-trip serialization, VerificationMethodType sync

**Files:**
- Create: `tests/test_requirements_schemas.py`

**Step 1: Write failing tests**

```python
"""Tests for requirements Pydantic schemas."""

import pytest
from pydantic import ValidationError

from backend.requirements.schemas import (
    DecomposedRequirementSchema,
    LowLevelRequirementSchema,
    VerificationConditionSchema,
    VerificationActionSchema,
    VerificationSchema,
    VerificationMethodType,
)
from backend.db.models.verification import VERIFICATION_METHODS


class TestVerificationSchema:
    def test_create_minimal_verification(self):
        v = VerificationSchema(method="automated")
        assert v.method == "automated"
        assert v.test_name == ""
        assert v.preconditions == []
        assert v.actions == []
        assert v.postconditions == []

    def test_create_full_verification(self):
        v = VerificationSchema(
            method="review",
            test_name="test_div",
            description="Review division",
            preconditions=[
                VerificationConditionSchema(
                    member_qualified_name="Calc::status",
                    operator="==",
                    expected_value="OK",
                ),
            ],
            actions=[
                VerificationActionSchema(
                    description="Call divide",
                    member_qualified_name="Calc::divide",
                ),
            ],
            postconditions=[
                VerificationConditionSchema(
                    member_qualified_name="Calc::result",
                    operator="==",
                    expected_value="42",
                ),
            ],
        )
        assert len(v.preconditions) == 1
        assert len(v.actions) == 1
        assert len(v.postconditions) == 1

    def test_invalid_method_rejected(self):
        with pytest.raises(ValidationError):
            VerificationSchema(method="invalid_method")

    def test_method_type_literals_match_model(self):
        """VerificationMethodType Literal must stay in sync with VERIFICATION_METHODS."""
        literal_methods = set(VerificationMethodType.__args__)
        model_methods = set(VERIFICATION_METHODS)
        assert literal_methods == model_methods


class TestLowLevelRequirementSchema:
    def test_create_llr(self):
        llr = LowLevelRequirementSchema(
            description="The system shall add two numbers",
            verifications=[VerificationSchema(method="automated", test_name="test_add")],
        )
        assert llr.description == "The system shall add two numbers"
        assert len(llr.verifications) == 1

    def test_llr_requires_description(self):
        with pytest.raises(ValidationError):
            LowLevelRequirementSchema(verifications=[])


class TestDecomposedRequirementSchema:
    def test_create_decomposed(self):
        d = DecomposedRequirementSchema(
            description="HLR text",
            low_level_requirements=[
                LowLevelRequirementSchema(description="LLR 1", verifications=[]),
                LowLevelRequirementSchema(description="LLR 2", verifications=[]),
            ],
        )
        assert len(d.low_level_requirements) == 2

    def test_round_trip_json(self):
        d = DecomposedRequirementSchema(
            description="Test HLR",
            low_level_requirements=[
                LowLevelRequirementSchema(
                    description="LLR",
                    verifications=[VerificationSchema(method="automated", test_name="t1")],
                ),
            ],
        )
        json_str = d.model_dump_json()
        restored = DecomposedRequirementSchema.model_validate_json(json_str)
        assert restored.description == "Test HLR"
        assert len(restored.low_level_requirements) == 1
        assert restored.low_level_requirements[0].verifications[0].test_name == "t1"


class TestVerificationConditionSchema:
    def test_default_operator(self):
        c = VerificationConditionSchema(
            member_qualified_name="x", expected_value="1",
        )
        assert c.operator == "=="

    def test_custom_operator(self):
        c = VerificationConditionSchema(
            member_qualified_name="x", operator="!=", expected_value="0",
        )
        assert c.operator == "!="


class TestVerificationActionSchema:
    def test_default_member_qname(self):
        a = VerificationActionSchema(description="Do something")
        assert a.member_qualified_name == ""

    def test_with_member_qname(self):
        a = VerificationActionSchema(
            description="Call foo",
            member_qualified_name="ns::Bar::foo",
        )
        assert a.member_qualified_name == "ns::Bar::foo"
```

**Step 2: Run tests**

Run: `cd /home/dnewman/ticketing_system && python -m pytest tests/test_requirements_schemas.py -v`
Expected: All pass

**Step 3: Commit**

```bash
git add tests/test_requirements_schemas.py
git commit -m "test: add Pydantic schema tests for requirements"
```

---

## Phase 4 — Persistence Layer Tests (Highest Value)

### Task 8: Test persist_decomposition

**Objective:** Verify that persist_decomposition creates LLRs and verification stubs, returns correct counts

**Files:**
- Create: `tests/test_persistence.py`

**Step 1: Write failing tests for persist_decomposition**

```python
"""Tests for the persistence service layer.

These are the most critical tests in the codebase — the persistence
layer is called by the MCP server, NiceGUI views, and demo scripts.
"""

import pytest
from unittest.mock import patch

from backend.db.models.requirements import HighLevelRequirement, LowLevelRequirement
from backend.db.models.verification import VerificationMethod
from backend.requirements.schemas import (
    LowLevelRequirementSchema,
    VerificationSchema,
)
from backend.requirements.services.persistence import (
    persist_decomposition,
    persist_design,
    persist_verification,
    resolve_ontology_node,
    validate_verification_references,
    augment_design_for_unresolved,
    build_verification_context,
    DecompositionResult,
)


class TestPersistDecomposition:
    """Test persist_decomposition — creates LLRs + verification stubs under an HLR."""

    def test_creates_llrs_with_verification_stubs(self, seeded_session):
        hlr = seeded_session.query(HighLevelRequirement).first()
        llrs_data = [
            LowLevelRequirementSchema(
                description="LLR 1: Add numbers",
                verifications=[
                    VerificationSchema(method="automated", test_name="test_add"),
                    VerificationSchema(method="review"),
                ],
            ),
            LowLevelRequirementSchema(
                description="LLR 2: Subtract numbers",
                verifications=[
                    VerificationSchema(method="inspection"),
                ],
            ),
        ]

        # Patch Neo4j sync so we don't need a running Neo4j
        with patch("backend.requirements.services.persistence.try_sync_requirement"):
            result = persist_decomposition(seeded_session, hlr, llrs_data)

        assert result.llrs_created == 2
        assert result.verifications_created == 3

        # Verify DB state
        db_llrs = seeded_session.query(LowLevelRequirement).filter(
            LowLevelRequirement.high_level_requirement_id == hlr.id
        ).all()
        assert len(db_llrs) == 2

        # First LLR should have 2 verification methods
        vm_count = seeded_session.query(VerificationMethod).filter(
            VerificationMethod.low_level_requirement_id == db_llrs[0].id
        ).count()
        assert vm_count == 2

    def test_empty_llrs_list(self, seeded_session):
        hlr = seeded_session.query(HighLevelRequirement).first()
        with patch("backend.requirements.services.persistence.try_sync_requirement"):
            result = persist_decomposition(seeded_session, hlr, [])
        assert result.llrs_created == 0
        assert result.verifications_created == 0

    def test_neo4j_sync_failure_does_not_crash(self, seeded_session):
        hlr = seeded_session.query(HighLevelRequirement).first()
        llrs_data = [
            LowLevelRequirementSchema(description="LLR", verifications=[]),
        ]
        with patch(
            "backend.requirements.services.persistence.try_sync_requirement",
            side_effect=Exception("Neo4j down"),
        ):
            result = persist_decomposition(seeded_session, hlr, llrs_data)
        # Should still succeed — Neo4j is best-effort
        assert result.llrs_created == 1
```

**Step 2: Run tests**

Run: `cd /home/dnewman/ticketing_system && python -m pytest tests/test_persistence.py::TestPersistDecomposition -v`
Expected: All pass

---

### Task 9: Test resolve_ontology_node and validate_verification_references

**Objective:** Test the node resolution algorithm (longest prefix match) and validation report

**Files:**
- Modify: `tests/test_persistence.py` (append classes)

**Step 1: Write tests for resolve_ontology_node**

```python
class TestResolveOntologyNode:
    """Test the longest-prefix-match resolution algorithm."""

    def test_exact_match(self, seeded_session):
        from backend.db.models.ontology import OntologyNode
        node = OntologyNode(kind="class", name="Engine", qualified_name="calc::Engine")
        seeded_session.add(node)
        seeded_session.flush()
        result = resolve_ontology_node(seeded_session, "calc::Engine")
        assert result is not None
        assert result.qualified_name == "calc::Engine"

    def test_prefix_match(self, seeded_session):
        from backend.db.models.ontology import OntologyNode
        cls = OntologyNode(kind="class", name="Engine", qualified_name="calc::Engine")
        seeded_session.add(cls)
        seeded_session.flush()
        # Member qname extends class qname
        result = resolve_ontology_node(seeded_session, "calc::Engine::add")
        assert result is not None
        assert result.qualified_name == "calc::Engine"

    def test_longest_prefix_wins(self, seeded_session):
        from backend.db.models.ontology import OntologyNode
        ns = OntologyNode(kind="module", name="calc", qualified_name="calc")
        cls = OntologyNode(kind="class", name="Engine", qualified_name="calc::Engine")
        seeded_session.add_all([ns, cls])
        seeded_session.flush()
        # "calc::Engine::add" should match "calc::Engine" not "calc"
        result = resolve_ontology_node(seeded_session, "calc::Engine::add")
        assert result is not None
        assert result.qualified_name == "calc::Engine"

    def test_no_match_returns_none(self, seeded_session):
        result = resolve_ontology_node(seeded_session, "nonexistent::Node")
        assert result is None

    def test_empty_string_returns_none(self, seeded_session):
        result = resolve_ontology_node(seeded_session, "")
        assert result is None

    def test_with_preloaded_node_list(self, seeded_session):
        from backend.db.models.ontology import OntologyNode
        cls = OntologyNode(kind="class", name="X", qualified_name="ns::X")
        seeded_session.add(cls)
        seeded_session.flush()
        node_list = [{"qualified_name": "ns::X", "pk": cls.id}]
        result = resolve_ontology_node(seeded_session, "ns::X::method", node_list)
        assert result is not None
        assert result.qualified_name == "ns::X"
```

**Step 2: Write tests for validate_verification_references**

```python
class TestValidateVerificationReferences:
    """Test validation of member_qualified_name against ontology nodes."""

    def test_all_resolved_exact_match(self):
        ontology_nodes = [
            {"qualified_name": "calc::Engine"},
            {"qualified_name": "calc::Engine::add"},
        ]
        v = VerificationSchema(
            method="automated",
            actions=[
                VerificationActionSchema(
                    description="Call add",
                    member_qualified_name="calc::Engine::add",
                ),
            ],
        )
        report = validate_verification_references([v], ontology_nodes)
        assert report.all_resolved is True
        assert len(report.resolved) == 1
        assert len(report.unresolved) == 0

    def test_prefix_match_resolved(self):
        ontology_nodes = [{"qualified_name": "calc::Engine"}]
        v = VerificationSchema(
            method="automated",
            actions=[
                VerificationActionSchema(
                    description="Call add",
                    member_qualified_name="calc::Engine::add",
                ),
            ],
        )
        report = validate_verification_references([v], ontology_nodes)
        assert report.all_resolved is True
        assert report.resolved[0] == ("calc::Engine::add", "calc::Engine")

    def test_unresolved_reference(self):
        v = VerificationSchema(
            method="automated",
            preconditions=[
                VerificationConditionSchema(
                    member_qualified_name="unknown::method",
                    expected_value="1",
                ),
            ],
        )
        report = validate_verification_references([v], [])
        assert report.all_resolved is False
        assert len(report.unresolved) == 1

    def test_empty_member_qname_skipped(self):
        v = VerificationSchema(
            method="review",
            actions=[
                VerificationActionSchema(description="Manual step", member_qualified_name=""),
            ],
        )
        report = validate_verification_references([v], [])
        assert report.all_resolved is True  # empty qnames are skipped
```

**Step 3: Run tests**

Run: `cd /home/dnewman/ticketing_system && python -m pytest tests/test_persistence.py -v`
Expected: All pass

**Step 4: Commit**

```bash
git add tests/test_persistence.py
git commit -m "test: add persistence layer tests — decompose, resolve, validate"
```

---

### Task 10: Test persist_design and persist_verification

**Objective:** Verify design persistence creates nodes/triples/links, verification persistence replaces methods and resolves ontology nodes

**Files:**
- Modify: `tests/test_persistence.py` (append classes)

**Step 1: Write tests for persist_design**

```python
class TestPersistDesign:
    """Test persist_design — creates ontology nodes, triples, requirement links."""

    def test_creates_nodes_and_triples(self, seeded_session):
        from backend.codebase.schemas import (
            DesignSchema, DesignNodeSchema, DesignTripleSchema, RequirementLinkSchema,
        )
        design = DesignSchema(
            nodes=[
                DesignNodeSchema(
                    kind="class", name="Calc", qualified_name="calc::Calc",
                    component_id=seeded_session._seed["component_id"],
                ),
                DesignNodeSchema(
                    kind="enum", name="Status", qualified_name="calc::Status",
                ),
            ],
            triples=[
                DesignTripleSchema(
                    subject_qualified_name="calc::Calc",
                    predicate="associates",
                    object_qualified_name="calc::Status",
                ),
            ],
            requirement_links=[
                RequirementLinkSchema(
                    triple_index=0,
                    requirement_type="hlr",
                    requirement_id=seeded_session._seed["hlr_id"],
                ),
            ],
        )

        with patch("backend.requirements.services.persistence.try_sync_design_nodes_and_triples"):
            result = persist_design(seeded_session, design)

        assert result.nodes_created == 2
        assert result.triples_created == 1
        assert result.links_applied == 1

    def test_idempotent_design_persist(self, seeded_session):
        from backend.codebase.schemas import DesignSchema, DesignNodeSchema
        design = DesignSchema(
            nodes=[
                DesignNodeSchema(kind="class", name="X", qualified_name="x::X"),
            ],
            triples=[],
            requirement_links=[],
        )
        with patch("backend.requirements.services.persistence.try_sync_design_nodes_and_triples"):
            r1 = persist_design(seeded_session, design)
            r2 = persist_design(seeded_session, design, qname_to_node=r1.qname_to_node)
        assert r1.nodes_created == 1
        assert r2.nodes_existing == 1
        assert r2.nodes_created == 0


class TestPersistVerification:
    """Test persist_verification — replaces LLR verification methods."""

    def _setup_llr_with_stub(self, seeded_session):
        """Create an LLR with a stub verification (as decompose would)."""
        hlr = seeded_session.query(HighLevelRequirement).first()
        llr = LowLevelRequirement(
            high_level_requirement=hlr, description="Test LLR"
        )
        seeded_session.add(llr)
        seeded_session.flush()
        stub = VerificationMethod(low_level_requirement=llr, method="automated")
        seeded_session.add(stub)
        seeded_session.flush()
        return llr

    def test_replaces_stub_with_fleshed_verification(self, seeded_session):
        llr = self._setup_llr_with_stub(seeded_session)
        verifications = [
            VerificationSchema(
                method="automated",
                test_name="test_add",
                description="Test addition",
                preconditions=[
                    VerificationConditionSchema(
                        member_qualified_name="", operator="==", expected_value="init",
                    ),
                ],
                actions=[
                    VerificationActionSchema(
                        description="Call add()",
                        member_qualified_name="",
                    ),
                ],
                postconditions=[
                    VerificationConditionSchema(
                        member_qualified_name="", operator="==", expected_value="result",
                    ),
                ],
            ),
        ]
        result = persist_verification(seeded_session, llr, verifications)
        assert result.verifications_saved == 1
        assert result.conditions_created == 2  # pre + post
        assert result.actions_created == 1

    def test_deletes_old_verifications(self, seeded_session):
        llr = self._setup_llr_with_stub(seeded_session)
        old_vm_id = llr.verifications[0].id
        verifications = [
            VerificationSchema(method="review"),
        ]
        persist_verification(seeded_session, llr, verifications)
        assert seeded_session.query(VerificationMethod).filter_by(id=old_vm_id).first() is None
```

**Step 2: Run tests**

Run: `cd /home/dnewman/ticketing_system && python -m pytest tests/test_persistence.py -v`
Expected: All pass

**Step 3: Commit**

```bash
git add tests/test_persistence.py
git commit -m "test: add persistence tests — design and verification persist"
```

---

### Task 11: Test augment_design_for_unresolved

**Objective:** Verify the closed-loop augmentation creates missing member nodes and COMPOSES triples, re-links verification records

**Files:**
- Modify: `tests/test_persistence.py` (append class)

**Step 1: Write tests**

```python
class TestAugmentDesignForUnresolved:
    """Test closed-loop augmentation — creating missing design nodes from verification refs."""

    def test_creates_member_node_for_unresolved_action(self, seeded_session):
        from backend.db.models.ontology import OntologyNode, OntologyTriple
        # Create a parent class in the ontology
        parent = OntologyNode(
            kind="class", name="Engine", qualified_name="calc::Engine",
            component_id=seeded_session._seed["component_id"],
        )
        seeded_session.add(parent)
        seeded_session.flush()

        unresolved = [("calc::Engine::start", "action")]
        with patch("backend.requirements.services.persistence.try_sync_design_nodes_and_triples"):
            result = augment_design_for_unresolved(seeded_session, unresolved)

        assert result.nodes_created == 1
        assert result.triples_created == 1

        # Verify the node was created correctly
        node = seeded_session.query(OntologyNode).filter_by(
            qualified_name="calc::Engine::start"
        ).first()
        assert node is not None
        assert node.kind == "method"  # action → method

    def test_creates_attribute_node_for_unresolved_condition(self, seeded_session):
        from backend.db.models.ontology import OntologyNode
        parent = OntologyNode(
            kind="class", name="Engine", qualified_name="calc::Engine",
            component_id=seeded_session._seed["component_id"],
        )
        seeded_session.add(parent)
        seeded_session.flush()

        unresolved = [("calc::Engine::count", "precondition")]
        with patch("backend.requirements.services.persistence.try_sync_design_nodes_and_triples"):
            result = augment_design_for_unresolved(seeded_session, unresolved)

        assert result.nodes_created == 1
        node = seeded_session.query(OntologyNode).filter_by(
            qualified_name="calc::Engine::count"
        ).first()
        assert node is not None
        assert node.kind == "attribute"  # condition → attribute

    def test_no_double_creation(self, seeded_session):
        from backend.db.models.ontology import OntologyNode
        parent = OntologyNode(
            kind="class", name="X", qualified_name="ns::X",
        )
        seeded_session.add(parent)
        seeded_session.flush()

        unresolved = [("ns::X::method", "action")]
        with patch("backend.requirements.services.persistence.try_sync_design_nodes_and_triples"):
            r1 = augment_design_for_unresolved(seeded_session, unresolved)
            r2 = augment_design_for_unresolved(seeded_session, unresolved)

        assert r1.nodes_created == 1
        assert r2.nodes_created == 0  # already exists

    def test_skips_unresolved_without_parent_separator(self, seeded_session):
        unresolved = [("NoDoubleColon", "action")]
        with patch("backend.requirements.services.persistence.try_sync_design_nodes_and_triples"):
            result = augment_design_for_unresolved(seeded_session, unresolved)
        assert result.nodes_created == 0

    def test_skips_when_parent_not_found(self, seeded_session):
        unresolved = [("nonexistent::Parent::method", "action")]
        with patch("backend.requirements.services.persistence.try_sync_design_nodes_and_triples"):
            result = augment_design_for_unresolved(seeded_session, unresolved)
        assert result.nodes_created == 0

    def test_empty_unresolved_list(self, seeded_session):
        with patch("backend.requirements.services.persistence.try_sync_design_nodes_and_triples"):
            result = augment_design_for_unresolved(seeded_session, [])
        assert result.nodes_created == 0
        assert result.triples_created == 0
```

**Step 2: Run all persistence tests**

Run: `cd /home/dnewman/ticketing_system && python -m pytest tests/test_persistence.py -v`
Expected: All pass

**Step 3: Run full test suite**

Run: `cd /home/dnewman/ticketing_system && python -m pytest tests/ -q --tb=short`
Expected: All pass, no regressions

**Step 4: Commit**

```bash
git add tests/test_persistence.py
git commit -m "test: add closed-loop augmentation tests for persist layer"
```

---

## Phase 5 — MCP Server Tests

### Task 12: Test MCP server read tools

**Objective:** Verify MCP tool inputs/outputs with mock DB sessions (no actual MCP server startup needed)

**Files:**
- Create: `tests/test_mcp_server.py`

**Step 1: Write tests**

```python
"""Tests for the MCP server tools.

We test the tool functions directly (no MCP protocol overhead)
with real in-memory DB sessions to verify input/output shapes.
"""

import json
import pytest
from unittest.mock import patch

from backend.db.models.requirements import HighLevelRequirement, LowLevelRequirement
from backend.db.models.ontology import OntologyNode, Predicate, OntologyTriple


# We need to mock init_db() which the MCP server calls at import time
# to set up its global session factories.
@pytest.fixture(autouse=True)
def mock_init_db():
    """Prevent the MCP server from calling init_db() on import."""
    with patch("backend.ticketing_agent.mcp_server.init_db"):
        yield


class TestListRequirements:
    def test_empty_database(self, seeded_session):
        # We'll call the tool function directly after patching get_session
        # to use our test session instead of the global one
        from backend.ticketing_agent.mcp_server import list_requirements
        with patch("backend.ticketing_agent.mcp_server.get_session") as mock_gs:
            mock_gs.return_value.__enter__ = lambda s: seeded_session
            mock_gs.return_value.__exit__ = lambda s, *a: None
            result = list_requirements()
        assert "HLR" in result
        assert "arithmetic" in result.lower()

    def test_with_llrs(self, seeded_session):
        hlr = seeded_session.query(HighLevelRequirement).first()
        llr = LowLevelRequirement(
            high_level_requirement=hlr, description="Sub req"
        )
        seeded_session.add(llr)
        seeded_session.flush()
        from backend.ticketing_agent.mcp_server import list_requirements
        with patch("backend.ticketing_agent.mcp_server.get_session") as mock_gs:
            mock_gs.return_value.__enter__ = lambda s: seeded_session
            mock_gs.return_value.__exit__ = lambda s, *a: None
            result = list_requirements()
        assert "LLR" in result


class TestListOntology:
    def test_empty_ontology(self, seeded_session):
        from backend.ticketing_agent.mcp_server import list_ontology
        with patch("backend.ticketing_agent.mcp_server.get_session") as mock_gs:
            mock_gs.return_value.__enter__ = lambda s: seeded_session
            mock_gs.return_value.__exit__ = lambda s, *a: None
            result = list_ontology()
        data = json.loads(result)
        assert "nodes" in data
        assert "triples" in data
        assert "predicates" in data

    def test_with_ontology_data(self, seeded_session):
        node = OntologyNode(kind="class", name="A", qualified_name="ns::A")
        seeded_session.add(node)
        seeded_session.flush()
        from backend.ticketing_agent.mcp_server import list_ontology
        with patch("backend.ticketing_agent.mcp_server.get_session") as mock_gs:
            mock_gs.return_value.__enter__ = lambda s: seeded_session
            mock_gs.return_value.__exit__ = lambda s, *a: None
            result = list_ontology()
        data = json.loads(result)
        assert len(data["nodes"]) == 1
        assert data["nodes"][0]["qualified_name"] == "ns::A"
```

**Step 2: Run tests**

Run: `cd /home/dnewman/ticketing_system && python -m pytest tests/test_mcp_server.py -v`
Expected: All pass

**Step 3: Commit**

```bash
git add tests/test_mcp_server.py
git commit -m "test: add MCP server tool tests"
```

---

## Phase 6 — Agent Helper Tests

### Task 13: Test agent pure-function helpers (no LLM mocking needed)

**Objective:** Test the data-formatting and extraction helpers used by agent functions — these are the easiest agent code to test since they're pure functions

**Files:**
- Create: `tests/test_agent_helpers.py`

**Step 1: Identify and test pure helpers**

*(Discover these by reading the agent source files during implementation — candidate helpers include: format_hlr_dict, format_hlrs_for_prompt in requirements.py, any extraction/formatting helpers in design/*.py, review/*.py, verify/*.py)*

The exact functions will be discovered during TDD implementation. Start by searching for functions that:
- Don't call `call_tool` or `llm_caller`
- Take structured data and return transformed data
- Are currently untested

**Step 2: Write tests for each discovered helper, run, commit**

Run: `cd /home/dnewman/ticketing_system && python -m pytest tests/test_agent_helpers.py -v`

**Step 3: Commit**

```bash
git add tests/test_agent_helpers.py
git commit -m "test: add agent helper function tests"
```

---

## Phase 7 — Coverage & CI Hook

### Task 14: Add coverage reporting and enforce minimum

**Objective:** Get a baseline coverage % and set a minimum threshold so coverage only goes up

**Files:**
- Modify: `pyproject.toml` (add pytest-cov config)
- Create: `tests/__init__.py` (already exists, no change)

**Step 1: Add coverage config to pyproject.toml**

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--tb=short -q"
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
]

[tool.coverage.run]
source = ["backend", "frontend"]
omit = ["*/migrations/*", "*/__pycache__/*"]

[tool.coverage.report]
fail_under = 30  # Start low, increase as we add tests
show_missing = true
```

**Step 2: Run coverage**

Run: `cd /home/dnewman/ticketing_system && python -m pytest --cov --cov-report=term-missing tests/`
Expected: Shows coverage ≥30% (should easily hit this with Phase 1-5 tests)

**Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "ci: add coverage reporting with 30% minimum threshold"
```

---

## Summary

| Phase | Tasks | Tests Added | Coverage Target |
|-------|-------|-------------|-----------------|
| 1 — Infrastructure | 2 | ~3 | Foundation |
| 2 — ORM Models | 4 | ~45 | Core data integrity |
| 3 — Pydantic Schemas | 1 | ~15 | Input validation |
| 4 — Persistence Layer | 4 | ~30 | Business logic |
| 5 — MCP Server | 1 | ~4 | API boundary |
| 6 — Agent Helpers | 1 | ~10-20 | Pure logic |
| 7 — Coverage/CI | 1 | 0 | 30% baseline |
| **Total** | **14** | **~107-137** | **≥30%** |

### Priority rationale

1. **Persistence layer** is the highest-risk code — it's the shared core used by MCP server, NiceGUI, and demo scripts. Dual-writes to Neo4j, longest-prefix resolution, closed-loop augmentation are all complex and untested.
2. **ORM models** define data integrity constraints that the whole system depends on — unique constraints, cascade deletes, relationship cardinality.
3. **Pydantic schemas** are the contract between the AI agent and the persistence layer — if they accept bad data, nothing downstream is safe.
4. **MCP server** is the integration boundary — currently zero tests.
5. **Agent helpers** are low-hanging fruit — pure functions with no external dependencies.
6. **Frontend data layer** and **agent integration tests** (with LLM mocking) are deferred to a future plan — they require more infrastructure (NiceGUI test client, complex mock setup).