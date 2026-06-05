"""TODO(2026-06): Remove this shim — import from codegraph directly.

All models now live in codegraph. This file re-exports them for
backward compatibility during the transition.
"""

from codegraph.diagram import ClassDiagram, Association
from codegraph.models import (
    ClassNode,
    InterfaceNode,
    EnumNode,
    UnionNode,
    ModuleNode,
    MethodNode,
    AttributeNode,
    EnumValueNode,
    FunctionNode,
    DefineNode,
)

__all__ = [
    "Association",
    "AttributeNode",
    "ClassDiagram",
    "ClassNode",
    "InterfaceNode",
    "EnumNode",
    "UnionNode",
    "ModuleNode",
    "MethodNode",
    "AttributeNode",
    "EnumValueNode",
    "FunctionNode",
    "DefineNode",
]
