"""TODO(2026-06): Remove this shim — import from codegraph.designs directly.

All models now live in codegraph/designs/. This file re-exports them for
backward compatibility during the transition.
"""
from codegraph.designs import (
    Association,
    AttributeNode,
    ClassDiagram,
    ClassNode,
    DiagramNode,
    EnumNode,
    EnumValueNode,
    InterfaceNode,
    MethodNode,
    ModuleNode,
)

__all__ = [
    "Association",
    "AttributeNode",
    "ClassDiagram",
    "ClassNode",
    "DiagramNode",
    "EnumNode",
    "EnumValueNode",
    "InterfaceNode",
    "MethodNode",
    "ModuleNode",
]
