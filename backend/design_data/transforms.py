"""TODO(2026-06): Remove this module once all callers use ClassDiagram directly.

OODesignSchema has been absorbed into ClassDiagram (codegraph.designs).
class_diagram_from_oo_design() is now a pass-through for ClassDiagram→ClassDiagram.
oo_design_from_class_diagram() is a pass-through for ClassDiagram→ClassDiagram.
"""

from codegraph.designs import ClassDiagram


def class_diagram_from_oo_design(
    oo: ClassDiagram,
    component_id: int | None = None,
) -> ClassDiagram:
    """Pass-through — both sides are now ClassDiagram."""
    if component_id is not None:
        for cls in oo.classes:
            cls.component_id = component_id
            for attr in cls.attributes:
                attr.component_id = component_id
            for method in cls.methods:
                method.component_id = component_id
        for iface in oo.interfaces:
            iface.component_id = component_id
            for method in iface.methods:
                method.component_id = component_id
        for enum in oo.enums:
            enum.component_id = component_id
            for val in enum.values:
                val.component_id = component_id
    return oo


def oo_design_from_class_diagram(diagram: ClassDiagram) -> ClassDiagram:
    """Pass-through — both sides are now ClassDiagram."""
    return diagram
