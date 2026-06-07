"""Design data module — typed read models and query API for class diagram data."""

from codegraph.models import (
    AttributeNode,
    ClassNode,
    DefineNode,
    EnumNode,
    EnumValueNode,
    FunctionNode,
    InterfaceNode,
    MethodNode,
    ModuleNode,
    UnionNode,
)
from backend.design_data.repository import DesignDataRepository
from backend.design_data.transforms import (
    class_diagram_from_oo_design,
    oo_design_from_class_diagram,
)

__all__ = [
    "DesignDataRepository",
    # Neomodel types (for Neo4j persistence)
    "AttributeNode",
    "ClassNode",
    "EnumNode",
    "EnumValueNode",
    "InterfaceNode",
    "MethodNode",
    "ModuleNode",
    "UnionNode",
    "FunctionNode",
    "DefineNode",
    "class_diagram_from_oo_design",
    "oo_design_from_class_diagram",
]
