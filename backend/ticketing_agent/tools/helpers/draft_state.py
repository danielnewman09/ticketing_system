"""Draft design state helpers."""

from backend.codebase.schemas import OODesignSchema
from backend.design_data import class_diagram_from_oo_design


def build_draft_lookup(design: OODesignSchema) -> dict[str, dict]:
    """Build a lookup dict from a draft OODesignSchema.

    Returns qualified_name -> {qualified_name, kind, description, source: 'draft'}
    for all classes, interfaces, enums, their attributes, and methods.
    """
    diagram = class_diagram_from_oo_design(design)
    return diagram.to_draft_lookup()


def draft_summary(design: OODesignSchema) -> dict:
    """Return a summary dict of the draft design for tool responses."""
    diagram = class_diagram_from_oo_design(design)
    total_attrs = sum(len(c.attributes) for c in diagram.classes)
    total_methods = sum(len(c.methods) for c in diagram.classes)
    return {
        "classes": len(diagram.classes),
        "interfaces": len(diagram.interfaces),
        "enums": len(diagram.enums),
        "associations": len(diagram.associations),
        "attributes": total_attrs,
        "methods": total_methods,
    }


def check_enum_collisions(design: OODesignSchema, prior_class_lookup: dict[str, str]) -> list[str]:
    """Warn if enum names collide with prior designs.

    Returns a list of warning strings. Empty list means no collisions.
    """
    warnings = []
    for enum in design.enums:
        enum_qname = f"{enum.module}::{enum.name}" if enum.module else enum.name
        if enum.name in prior_class_lookup:
            existing_qname = prior_class_lookup[enum.name]
            if existing_qname != enum_qname:
                warnings.append(
                    f"Enum '{enum.name}' already exists as '{existing_qname}' in a "
                    f"prior design. Consider referencing the existing enum or "
                    f"renaming yours to avoid confusion."
                )
    return warnings