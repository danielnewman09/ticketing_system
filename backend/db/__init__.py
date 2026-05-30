"""Database initialization and session management.

Engine:
- main: db.sqlite3 (requirements, components, tickets, search, ontology)
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from backend.db.base import Base

_BASE_DIR = Path(__file__).resolve().parent.parent.parent

_main_engine = None
_MainSession: sessionmaker | None = None


def _load_sqlite_vec(dbapi_conn, connection_record):
    """Load sqlite-vec extension on every new SQLite connection."""
    import sqlite_vec

    dbapi_conn.enable_load_extension(True)
    sqlite_vec.load(dbapi_conn)
    dbapi_conn.enable_load_extension(False)


def init_db(
    main_url: str | None = None,
):
    """Create engines and session factories.

    Call once at application startup.
    """
    global _main_engine, _MainSession

    if main_url is None:
        main_url = f"sqlite:///{_BASE_DIR / 'db.sqlite3'}"

    _main_engine = create_engine(main_url)

    # Load sqlite-vec on every connection
    event.listen(_main_engine, "connect", _load_sqlite_vec)

    _MainSession = sessionmaker(bind=_main_engine)
    # Import models to ensure they're registered with Base.metadata
    import backend.db.models  # noqa: F401

    # Register event listeners
    from backend.db import events  # noqa: F401


def get_main_engine():
    """Return the main engine (for raw connections, e.g. search)."""
    if _main_engine is None:
        raise RuntimeError("Call init_db() before using the database.")
    return _main_engine


@contextmanager
def get_session():
    """Yield a main-database Session, committing on success, rolling back on error."""
    if _MainSession is None:
        raise RuntimeError("Call init_db() before using the database.")
    session = _MainSession()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_or_create(session: Session, model, defaults=None, **kwargs):
    """Get an existing instance or create a new one.

    Returns (instance, created) tuple.
    """
    instance = session.query(model).filter_by(**kwargs).first()
    if instance:
        return instance, False
    params = {**kwargs, **(defaults or {})}
    instance = model(**params)
    session.add(instance)
    session.flush()
    return instance, True
