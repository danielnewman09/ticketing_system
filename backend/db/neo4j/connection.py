"""Backward-compatible re-exports from :mod:`backend_migrated.connection`.

All connection lifecycle and driver management now lives in
:mod:`backend_migrated.connection`, which delegates to
:mod:`codegraph.connection` and :mod:`codegraph.config` for the modern
neomodel 6.x configuration API.

This module re-exports the public names so that existing imports like::

    from backend.db.neo4j.connection import Neo4jSessionManager, NEO4J_URI

continue to work unchanged.
"""

from __future__ import annotations

# Re-export the canonical Neo4jSessionManager and lifecycle functions.
from backend_migrated.connection import (  # noqa: F401
    Neo4jSessionManager,
    close_neo4j,
    ensure_connection,
    get_neo4j,
    init_neo4j,
)

# Re-export the Neo4j environment variables from codegraph.config.
# These are read once at import time from NEO4J_URI, NEO4J_USER,
# NEO4J_PASSWORD environment variables.
from codegraph.config import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER  # noqa: F401