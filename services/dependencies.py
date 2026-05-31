"""Shared dependency accessors for Neo4j.

Works both inside the NiceGUI app (``app.neo4j`` is set by
``nicegui_app.py``) and in standalone scripts (auto-creates a
standalone ``Neo4jConnection`` on first access).

Standalone scripts should call :func:`init_neo4j` at startup to
explicitly open the connection (and ``close_neo4j`` at exit), but
this is optional — ``get_neo4j`` will lazily create a connection if
needed.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codegraph.neo4j import Neo4jConnection

log = logging.getLogger(__name__)

# Standalone fallback — created lazily by get_neo4j() or eagerly by
# init_neo4j(), and never set when running inside NiceGUI (which sets
# app.neo4j directly).
_standalone_neo4j: Neo4jConnection | None = None


def init_neo4j() -> Neo4jConnection:
    """Create and register the standalone Neo4j connection.

    Call this at the top of standalone scripts (before any Neo4j
    queries) so the driver is available.  Idempotent — returns the
    existing connection if one was already created.
    """
    global _standalone_neo4j

    # If the NiceGUI app has already set up a connection, use that.
    try:
        from nicegui import app

        if getattr(app, "neo4j", None) is not None:
            _standalone_neo4j = None  # app owns the lifecycle
            return app.neo4j
    except (ImportError, AttributeError):
        pass

    if _standalone_neo4j is None:
        from codegraph.neo4j import Neo4jConnection

        _standalone_neo4j = Neo4jConnection()
        log.info("Standalone Neo4j connection initialized")

    return _standalone_neo4j


def get_neo4j() -> Neo4jConnection:
    """Return the current Neo4j connection.

    Resolution order:
    1. ``app.neo4j`` — set by ``nicegui_app.py`` when the web UI is
       running.
    2. Standalone connection — created by a prior ``init_neo4j()``
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

    # 2. Standalone connection (explicitly initialised or lazily created)
    global _standalone_neo4j
    if _standalone_neo4j is None:
        from codegraph.neo4j import Neo4jConnection

        _standalone_neo4j = Neo4jConnection()
        log.info("Lazy standalone Neo4j connection created")

    return _standalone_neo4j


def close_neo4j() -> None:
    """Close the standalone Neo4j connection (if one was created).

    Safe to call at script exit — no-op when running inside NiceGUI
    (the app shuts down the connection via ``app.on_shutdown``).
    """
    global _standalone_neo4j
    if _standalone_neo4j is not None:
        _standalone_neo4j.close()
        _standalone_neo4j = None
        log.info("Standalone Neo4j connection closed")