"""Design data module — typed read models and query API for class diagram data."""

from backend.design_data.models import (
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
from backend.design_data.repository import DesignDataRepository
from backend.design_data.transforms import (
    class_diagram_from_oo_design,
    oo_design_from_class_diagram,
)

__all__ = [
    "Association",
    "AttributeNode",
    "ClassDiagram",
    "ClassNode",
    "DesignDataRepository",
    "DiagramNode",
    "EnumNode",
    "EnumValueNode",
    "InterfaceNode",
    "MethodNode",
    "ModuleNode",
    "class_diagram_from_oo_design",
    "oo_design_from_class_diagram",
]