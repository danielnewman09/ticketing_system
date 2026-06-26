"""Neomodel node types re-exported from codegraph submodules.

All project-management and requirement node models now live in:
- codegraph_project.models: Component, ProjectMeta, Language, Dependency
- codegraph_requirements.models: HLR, LLR
- codegraph.models.test: TestNode, AssertionNode, TestStepNode, TestFixtureNode

The ``get_typed_edge_targets`` helper remains in
``backend_migrated.models.verification``.

All project-management nodes participate in the COMPOSES hierarchy
used by LayerGraph:

  Component \u2192 HLR \u2192 LLR \u2192 TestNode \u2192 AssertionNode / TestStepNode / TestFixtureNode

NOTE: Before creating or querying nodes, neomodel's database connection
must be configured (import codegraph.config or set NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD).
"""

from codegraph_project.models import Component, Dependency, Language, ProjectMeta
from codegraph_requirements.models import HLR, LLR
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