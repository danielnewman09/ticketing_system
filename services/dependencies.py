"""Shared dependency accessors for Neo4j — re-exports from backend_migrated.

All connection lifecycle and driver management now lives in
:mod:`backend_migrated.connection`.  This module re-exports the public
names so that existing imports like::

    from services.dependencies import init_neo4j, close_neo4j, get_neo4j

continue to work unchanged.
"""

from backend_migrated.connection import (  # noqa: F401
    Neo4jSessionManager,
    close_neo4j,
    ensure_connection,
    get_neo4j,
    init_neo4j,
)