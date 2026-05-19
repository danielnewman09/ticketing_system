"""Shared test fixtures — in-memory SQLite with all ORM tables.

Every test gets a fresh database that is created from scratch and
torn down afterwards.  No sqlite-vec extension, no Neo4j, no disk
artifacts.
"""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from backend.db.base import Base

# Import all models so Base.metadata knows about every table.
import backend.db.models  # noqa: F401


@pytest.fixture()
def engine():
    """Create a fresh in-memory SQLite engine per test.

    Does NOT load sqlite-vec — tests that need vector search
    should be integration tests, not unit tests.
    """
    eng = create_engine("sqlite:///:memory:")

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
    - 1 Component (Calculator) with that language
    - 1 HighLevelRequirement ("The system shall perform arithmetic")
    - 7 default Predicates (associates, composes, depends_on, …)
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

    yield session