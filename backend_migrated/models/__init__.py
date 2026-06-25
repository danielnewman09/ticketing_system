"""Neomodel node types that extend CodeGraphNode for project-management metadata.

Provides ProjectMeta, Component, Language, Dependency, HLR, LLR,
and TestNode / AssertionNode / TestStepNode / TestFixtureNode node models
(re-exported from codegraph.models.test) for the project-management layer.
These extend CodeGraphNode from codegraph to share serialization, registry,
and relationship introspection infrastructure, while living in the same
Neo4j database as code-level nodes (ClassNode, NamespaceNode, etc.).

All project-management nodes participate in the COMPOSES hierarchy
used by LayerGraph:

  Component \u2192 HLR \u2192 LLR \u2192 TestNode \u2192 AssertionNode / TestStepNode / TestFixtureNode

NOTE: Before creating or querying nodes, neomodel's database connection
must be configured. This is done by importing backend.db.neo4j.connection
or by setting NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD environment variables.
"""

from backend_migrated.models.component import Component
from backend_migrated.models.dependency import Dependency
from backend_migrated.models.language import Language
from backend_migrated.models.project import ProjectMeta
from backend_migrated.models.requirement import HLR, LLR
from backend_migrated.models.verification import (
    AssertionNode,
    TestFixtureNode,
    TestNode,
    TestStepNode,
    get_typed_edge_targets,
)

__all__ = [
    "AssertionNode",
    "Component",
    "Dependency",
    "HLR",
    "Language",
    "LLR",
    "ProjectMeta",
    "TestFixtureNode",
    "TestNode",
    "TestStepNode",
    "get_typed_edge_targets",
]