"""Migrated neomodel node types and connection management.

Importing this package triggers :mod:`codegraph.config` which sets up
the neomodel database URL from environment variables. For explicit driver
initialisation, call :func:`backend_migrated.connection.ensure_connection`
or use the :class:`~backend_migrated.connection.Neo4jSessionManager`.
"""

from backend_migrated.connection import (
    Neo4jSessionManager,
    close_neo4j,
    ensure_connection,
    get_neo4j,
    init_neo4j,
)
from backend_migrated.models import Component, Dependency, Language, ProjectMeta

__all__ = [
    # Connection management
    "Neo4jSessionManager",
    "ensure_connection",
    "init_neo4j",
    "get_neo4j",
    "close_neo4j",
    # Models
    "Component",
    "Dependency",
    "Language",
    "ProjectMeta",
]