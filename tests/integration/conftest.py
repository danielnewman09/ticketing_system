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
    # OntologyNodes/Triples/Predicates removed in Phase 4 — skip loading into SQLite
    # Verification data is now in Neo4j (Phase 3) — skip loading into SQLite

