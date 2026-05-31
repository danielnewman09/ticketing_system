"""TODO(2026-06): Remove this module once all callers use ClassDiagram directly.

OODesignSchema has been absorbed into ClassDiagram (codegraph.designs).
class_diagram_from_oo_design() enriches a ClassDiagram with computed fields
(qualified_name, owner) that the LLM does not need to supply.
oo_design_from_class_diagram() is a pass-through for ClassDiagram→ClassDiagram.
"""

from codegraph.diagram import ClassDiagram


def class_diagram_from_oo_design(
    oo: ClassDiagram,
    component_id: int | None = None,
) -> ClassDiagram:
    """Enrich a ClassDiagram with qualified_name for each entity.

    The LLM writes short names and module strings; this function computes
    qualified_name (module::name).
    """
    def _qualify(module: str, name: str) -> str:
        return f"{module}::{name}" if module else name

    for cls in oo.classes:
        if not cls.qualified_name:
            cls.qualified_name = _qualify(cls.module, cls.name)
        if component_id is not None:
            cls.component_id = component_id
        for attr in cls.attributes:
            if not attr.qualified_name:
                attr.qualified_name = f"{cls.qualified_name}::{attr.name}"
            if component_id is not None:
                attr.component_id = component_id
        for method in cls.methods:
            if not method.qualified_name:
                method.qualified_name = f"{cls.qualified_name}::{method.name}"
            if component_id is not None:
                method.component_id = component_id

    for iface in oo.interfaces:
        if not iface.qualified_name:
            iface.qualified_name = _qualify(iface.module, iface.name)
        if component_id is not None:
            iface.component_id = component_id
        for method in iface.methods:
            if not method.qualified_name:
                method.qualified_name = f"{iface.qualified_name}::{method.name}"
            if component_id is not None:
                method.component_id = component_id

    for enum in oo.enums:
        if not enum.qualified_name:
            enum.qualified_name = _qualify(enum.module, enum.name)
        if component_id is not None:
            enum.component_id = component_id
        for val in enum.values:
            if not val.qualified_name:
                val.qualified_name = f"{enum.qualified_name}::{val.name}"

    return oo


def oo_design_from_class_diagram(diagram: ClassDiagram) -> ClassDiagram:
    """Pass-through — both sides are now ClassDiagram."""
    return diagram
