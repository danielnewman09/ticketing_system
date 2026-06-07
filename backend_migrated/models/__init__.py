"""Neomodel node types that extend CodeGraphNode for project-management metadata.

Provides ProjectMeta, Component, Language, and Dependency node models for the
ticketing system's project-management layer. These extend CodeGraphNode
from codegraph to share serialization, registry, and relationship
introspection infrastructure, while living in the same Neo4j database
as code-level nodes (ClassNode, NamespaceNode, etc.).

NOTE: Before creating or querying nodes, neomodel's database connection
must be configured. This is done by importing backend.db.neo4j.connection
or by setting NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD environment variables.
"""

from backend_migrated.models.component import Component
from backend_migrated.models.dependency import Dependency
from backend_migrated.models.language import Language
from backend_migrated.models.project import ProjectMeta

__all__ = [
    "Component",
    "Dependency",
    "Language",
    "ProjectMeta",
]