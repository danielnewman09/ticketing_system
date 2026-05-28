"""Draft design state helpers."""

from backend.codebase.schemas import OODesignSchema


def build_draft_lookup(design: OODesignSchema) -> dict[str, dict]:
    """Build a lookup dict from a draft OODesignSchema.

    Returns qualified_name -> {qualified_name, kind, description, source: 'draft'}
    for all classes, interfaces, enums, their attributes, and methods.
    """
    lookup: dict[str, dict] = {}

    for cls in design.classes:
        qname = f"{cls.module}::{cls.name}" if cls.module else cls.name
        lookup[qname] = {
            "qualified_name": qname,
            "kind": "class",
            "description": cls.description,
            "source": "draft",
        }
        for attr in cls.attributes:
            attr_qname = f"{qname}::{attr.name}"
            lookup[attr_qname] = {
                "qualified_name": attr_qname,
                "kind": "attribute",
                "description": attr.description,
                "source": "draft",
            }
        for method in cls.methods:
            method_qname = f"{qname}::{method.name}"
            lookup[method_qname] = {
                "qualified_name": method_qname,
                "kind": "method",
                "description": method.description,
                "source": "draft",
            }

    for iface in design.interfaces:
        qname = f"{iface.module}::{iface.name}" if iface.module else iface.name
        lookup[qname] = {
            "qualified_name": qname,
            "kind": "interface",
            "description": iface.description,
            "source": "draft",
        }
        for method in iface.methods:
            method_qname = f"{qname}::{method.name}"
            lookup[method_qname] = {
                "qualified_name": method_qname,
                "kind": "method",
                "description": method.description,
                "source": "draft",
            }

    for enum in design.enums:
        qname = f"{enum.module}::{enum.name}" if enum.module else enum.name
        lookup[qname] = {
            "qualified_name": qname,
            "kind": "enum",
            "description": enum.description,
            "source": "draft",
        }

    return lookup


def draft_summary(design: OODesignSchema) -> dict:
    """Return a summary dict of the draft design for tool responses."""
    total_attrs = sum(len(cls.attributes) for cls in design.classes)
    total_methods = sum(len(cls.methods) for cls in design.classes)
    return {
        "classes": len(design.classes),
        "interfaces": len(design.interfaces),
        "enums": len(design.enums),
        "associations": len(design.associations),
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
