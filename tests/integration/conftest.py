"""Pytest fixtures for integration tests that need a fully-loaded database.

Provides a `loaded_session` fixture that loads the exported SQLite fixtures
into a fresh in-memory database, giving tests a realistic dataset with
requirements, ontology, dependencies, and verifications.

Usage in tests::

    from tests.integration.conftest import loaded_session

    def test_something(loaded_session):
        nodes = loaded_session.query(OntologyNode).all()
        assert len(nodes) == 47
"""

import json
import os

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from backend.db.base import Base
from backend.db.models import (
    Component,
    Dependency,
    DependencyManager,
    HighLevelRequirement,
    Language,
    LowLevelRequirement,
    OntologyNode,
    OntologyTriple,
    Predicate,
    VerificationAction,
    VerificationCondition,
    VerificationMethod,
)

import backend.db.models  # noqa: F401 — ensure all tables are registered
from backend.db.models.components import dependency_components

FIXTURES_DIR = os.path.dirname(__file__)
SQLITE_FIXTURE = os.path.join(FIXTURES_DIR, "sqlite_fixtures.json")


@pytest.fixture
def loaded_session():
    """Yield a session with the full exported dataset loaded.

    Uses an in-memory SQLite database that is discarded after the test.
    """
    with open(SQLITE_FIXTURE) as f:
        data = json.load(f)

    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, expire_on_commit=False)

    _load_fixture_data(session, data)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


def _load_fixture_data(session, data):
    """Load fixture data dict into the given session."""
    # Reference data
    for row in data.get("predicates", []):
        session.add(Predicate(id=row["id"], name=row["name"], description=row.get("description")))

    for row in data.get("languages", []):
        session.add(Language(id=row["id"], name=row["name"], version=row.get("version")))

    for row in data.get("dependency_managers", []):
        session.add(DependencyManager(
            id=row["id"], name=row["name"],
            language_id=row.get("language_id"),
            version=row.get("version", ""),
            lock_file=row.get("lock_file", ""),
        ))

    for row in data.get("components", []):
        session.add(Component(
            id=row["id"], name=row["name"],
            description=row.get("description", ""),
            language_id=row.get("language_id"),
            parent_id=row.get("parent_id"),
            namespace=row.get("namespace", ""),
        ))

    for row in data.get("dependencies", []):
        session.add(Dependency(
            id=row["id"], name=row["name"],
            version=row.get("version", ""),
            manager_id=row.get("manager_id"),
        ))

    session.flush()

    for row in data.get("dependency_components", []):
        session.execute(
            dependency_components.insert().values(
                component_id=row["component_id"],
                dependency_id=row["dependency_id"],
            )
        )

    # Requirements
    for row in data.get("high_level_requirements", []):
        hlr = HighLevelRequirement(
            id=row["id"],
            description=row["description"],
            component_id=row.get("component_id"),
        )
        dep_ctx = next(
            (d for d in data.get("hlr_dependency_contexts", []) if d["hlr_id"] == row["id"]),
            None,
        )
        if dep_ctx:
            hlr.dependency_context = dep_ctx["dependency_context"]
        session.add(hlr)

    for row in data.get("low_level_requirements", []):
        session.add(LowLevelRequirement(
            id=row["id"],
            description=row["description"],
            high_level_requirement_id=row["high_level_requirement_id"],
        ))

    session.flush()

    # Ontology
    for row in data.get("ontology_nodes", []):
        session.add(OntologyNode(
            id=row["id"],
            qualified_name=row["qualified_name"],
            name=row.get("name", ""),
            kind=row.get("kind", ""),
            specialization=row.get("specialization", ""),
            visibility=row.get("visibility", ""),
            description=row.get("description", ""),
            refid=row.get("refid", ""),
            component_id=row.get("component_id"),
            is_intercomponent=row.get("is_intercomponent", False),
            source_type=row.get("source_type", ""),
            type_signature=row.get("type_signature", ""),
            argsstring=row.get("argsstring", ""),
            definition=row.get("definition", ""),
            file_path=row.get("file_path", ""),
            line_number=row.get("line_number"),
            is_static=row.get("is_static", False),
            is_const=row.get("is_const", False),
            is_virtual=row.get("is_virtual", False),
            is_abstract=row.get("is_abstract", False),
            is_final=row.get("is_final", False),
        ))

    session.flush()

    for row in data.get("ontology_triples", []):
        session.add(OntologyTriple(
            id=row["id"],
            subject_id=row["subject_id"],
            predicate_id=row["predicate_id"],
            object_id=row["object_id"],
        ))

    session.flush()

    # M2M relationships
    for row in data.get("hlr_triples", []):
        hlr = session.get(HighLevelRequirement, row["hlr_id"])
        triple = session.get(OntologyTriple, row["triple_id"])
        if hlr and triple:
            hlr.triples.append(triple)

    for row in data.get("hlr_nodes", []):
        hlr = session.get(HighLevelRequirement, row["hlr_id"])
        node = session.get(OntologyNode, row["node_id"])
        if hlr and node:
            hlr.nodes.append(node)

    for row in data.get("llr_nodes", []):
        llr = session.get(LowLevelRequirement, row["llr_id"])
        node = session.get(OntologyNode, row["node_id"])
        if llr and node:
            llr.nodes.append(node)

    # Verifications
    for row in data.get("verification_methods", []):
        session.add(VerificationMethod(
            id=row["id"],
            method=row["method"],
            test_name=row.get("test_name", ""),
            description=row.get("description", ""),
            low_level_requirement_id=row["low_level_requirement_id"],
        ))

    session.flush()

    for row in data.get("verification_conditions", []):
        session.add(VerificationCondition(
            id=row["id"],
            verification_id=row["verification_id"],
            phase=row.get("phase", "pre"),
            order=row.get("order", 0),
            member_qualified_name=row.get("member_qualified_name", ""),
            operator=row.get("operator", ""),
            expected_value=row.get("expected_value", ""),
            ontology_node_id=row.get("ontology_node_id"),
        ))

    for row in data.get("verification_actions", []):
        session.add(VerificationAction(
            id=row["id"],
            verification_id=row["verification_id"],
            order=row.get("order", 0),
            description=row.get("description", ""),
            member_qualified_name=row.get("member_qualified_name", ""),
            ontology_node_id=row.get("ontology_node_id"),
        ))

    session.flush()