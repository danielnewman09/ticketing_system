"""Migrated neomodel node types extending CodeGraphNode.

Import this package after configuring neomodel's database connection
(e.g., via backend.db.neo4j.connection).
"""

from backend_migrated.models import Component, Dependency, Language, ProjectMeta

__all__ = [
    "Component",
    "Dependency",
    "Language",
    "ProjectMeta",
]