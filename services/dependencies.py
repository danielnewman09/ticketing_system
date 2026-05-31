"""Shared dependency accessors for Neo4j.

Works both inside the NiceGUI app (``app.neo4j`` is set by
``nicegui_app.py``) and in standalone scripts (auto-creates a
standalone ``Neo4jSessionManager`` on first access).

Standalone scripts should call :func:`init_neo4j` at startup to
explicitly configure the connection (and ``close_neo4j`` at exit), but
this is optional — ``get_neo4j`` will lazily configure neomodel if
needed.
"""

from __future__ import annotations

import logging

from backend.db.neo4j.connection import Neo4jSessionManager

log = logging.getLogger(__name__)

# Standalone fallback — created lazily by get_neo4j() or eagerly by
# init_neo4j(), and never set when running inside NiceGUI (which sets
# app.neo4j directly).
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
        # Import triggers neomodel config
        import backend.db.neo4j.connection  # noqa: F401
        _standalone_mgr = Neo4jSessionManager()
        log.info("Standalone Neo4j session manager initialized")

    return _standalone_mgr


def get_neo4j() -> Neo4jSessionManager:
    """Return an object with .session() for getting Neo4j sessions.

    Resolution order:
    1. ``app.neo4j`` — set by ``nicegui_app.py`` when the web UI is
       running.
    2. Standalone session manager — created by a prior ``init_neo4j()``
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

    # 2. Standalone session manager (explicitly initialised or lazily created)
    global _standalone_mgr
    if _standalone_mgr is None:
        import backend.db.neo4j.connection  # noqa: F401
        _standalone_mgr = Neo4jSessionManager()
        log.info("Lazy standalone Neo4j session manager created")

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
        log.info("Standalone Neo4j session manager closed")