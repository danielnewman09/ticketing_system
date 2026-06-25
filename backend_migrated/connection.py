"""Neomodel connection lifecycle and session management.

Canonical module for the migrated backend.  Configuration is handled by
:mod:`codegraph.config` (reads ``NEO4J_URI``, ``NEO4J_USER``,
``NEO4J_PASSWORD`` from environment variables and sets the neomodel
database URL using the modern 6.x API).  Driver initialisation and
session management are delegated to :mod:`codegraph.connection`.

Import this module — or call :func:`ensure_connection` — before any
neomodel model class is imported to guarantee the database driver is
configured.

Usage::

    # Standalone scripts
    from backend_migrated.connection import init_neo4j, close_neo4j
    init_neo4j()
    # ... work ...
    close_neo4j()

    # NiceGUI app
    from backend_migrated.connection import Neo4jSessionManager
    app.neo4j = Neo4jSessionManager()
"""

from __future__ import annotations

import logging

from codegraph import get_session as _cg_get_session, verify_connectivity as _cg_verify_connectivity
from codegraph import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER
from codegraph.persistence.connection import _ensure_driver
from neomodel import db as neomodel_db

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------


def ensure_connection() -> None:
    """Ensure neomodel's database driver is initialised.

    Delegates to :func:`codegraph.connection._ensure_driver`, which
    reads the URL from :mod:`codegraph.config` (set from environment
    variables at import time).  Safe to call multiple times.
    """
    _ensure_driver()


# ---------------------------------------------------------------------------
# Neo4jSessionManager
# ---------------------------------------------------------------------------


class Neo4jSessionManager:
    """Lightweight ``app.neo4j``-compatible wrapper.

    Uses neomodel's globally-configured driver under the hood.
    Configuration and driver initialisation are delegated to
    :mod:`codegraph.connection`.

    Compatible with the NiceGUI pattern::

        from backend_migrated.connection import Neo4jSessionManager
        app.neo4j = Neo4jSessionManager()
    """

    def session(self):
        """Return a Neo4j driver session as a context manager."""
        return _cg_get_session()

    def verify_connectivity(self) -> bool:
        """Check that Neo4j is reachable."""
        return _cg_verify_connectivity()

    def get_driver(self):
        """Return the underlying neomodel driver (for callers that need it)."""
        _ensure_driver()
        return neomodel_db.driver

    def ensure_constraints(self) -> None:
        """Create migrated-node-type constraints and indexes (if needed)."""
        from backend_migrated.constraints import ensure_migrated_constraints
        ensure_migrated_constraints()

    def close(self) -> None:
        """No-op — neomodel manages the driver lifecycle."""
        pass


# ---------------------------------------------------------------------------
# Standalone-script lifecycle
# ---------------------------------------------------------------------------

_standalone_mgr: Neo4jSessionManager | None = None


def init_neo4j() -> Neo4jSessionManager:
    """Configure neomodel and register the standalone session manager.

    Call this at the top of standalone scripts (before any Neo4j
    queries).  Idempotent — returns the existing manager if one was
    already created.
    """
    global _standalone_mgr

    # If the NiceGUI app has already set up a connection, use that.
    try:
        from nicegui import app

        if getattr(app, "neo4j", None) is not None:
            _standalone_mgr = None  # app owns the lifecycle
            return app.neo4j
    except (ImportError, AttributeError):
        pass

    if _standalone_mgr is None:
        ensure_connection()
        _standalone_mgr = Neo4jSessionManager()
        log.info("Standalone Neo4j session manager initialised (backend_migrated)")

    return _standalone_mgr


def get_neo4j() -> Neo4jSessionManager:
    """Return an object with ``.session()`` for getting Neo4j sessions.

    Resolution order:

    1. ``app.neo4j`` — set by the NiceGUI app when the web UI is running.
    2. Standalone session manager — created by a prior :func:`init_neo4j`
       call, or lazily created here.
    """
    # 1. NiceGUI app context
    try:
        from nicegui import app

        conn = getattr(app, "neo4j", None)
        if conn is not None:
            return conn
    except (ImportError, AttributeError):
        pass

    # 2. Standalone session manager
    global _standalone_mgr
    if _standalone_mgr is None:
        ensure_connection()
        _standalone_mgr = Neo4jSessionManager()
        log.info("Lazy standalone Neo4j session manager created (backend_migrated)")

    return _standalone_mgr


def close_neo4j() -> None:
    """Close the standalone Neo4j connection (if one was created).

    Safe to call at script exit — no-op when running inside NiceGUI
    (the app shuts down the connection via ``app.on_shutdown``).
    """
    global _standalone_mgr
    if _standalone_mgr is not None:
        _standalone_mgr.close()
        _standalone_mgr = None
        log.info("Standalone Neo4j session manager closed (backend_migrated)")