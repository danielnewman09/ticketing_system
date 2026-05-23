"""Pytest fixtures for integration tests that need a fully-loaded database.

Provides a `loaded_session` fixture that loads the exported SQLite fixtures
into a fresh in-memory database, giving tests a realistic dataset with
ontology, dependencies, and verifications.

Phase 2 note: HLR/LLR data now lives in Neo4j, not SQLite. The fixture
no longer loads high_level_requirements or low_level_requirements tables.
Verification methods still use SQLite with a plain low_level_requirement_id
column (no FK constraint).
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
    Language,
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
    HLR/LLR data is no longer loaded into SQLite (Phase 2: in Neo4j).
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

    # HLR/LLR data is now in Neo4j (Phase 2) — skip loading into SQLite

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

    # HLR/LLR M2M relationships with OntologyNode removed (Phase 2)

    # Verifications — low_level_requirement_id is a plain integer (no FK)
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