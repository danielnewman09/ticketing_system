"""check_class_name tool: look up class/interface/enum names across design contexts."""

import json

SCHEMA = {
    "name": "check_class_name",
    "description": (
        "Check if a class, interface, or enum name exists in the design "
        "context (prior designs, dependency APIs, intercomponent boundaries, "
        "or the current draft). Use this to verify that association targets "
        "and type references are valid. Supports partial matching."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "A class, interface, or enum name to look up. Can be a "
                    "bare name or qualified name. Supports substring matching."
                ),
            },
        },
        "required": ["name"],
    },
}


def handle(ctx, tool_input: dict) -> str:
    """Search draft, prior designs, dependency APIs, and intercomponent
    classes for matching names."""
    name = tool_input.get("name", "")
    if not name:
        return json.dumps({"found": False, "matches": []})

    matches = []
    name_lower = name.lower()

    # Search draft
    if ctx.draft_lookup:
        for qname, info in ctx.draft_lookup.items():
            if name_lower in qname.lower() or name_lower in info.get("description", "").lower():
                matches.append({
                    "qualified_name": qname,
                    "kind": info["kind"],
                    "source": "draft",
                })

    # Search prior designs
    for bare, qname in ctx.prior_class_lookup.items():
        if name_lower in bare.lower() or name_lower in qname.lower():
            matches.append({
                "qualified_name": qname,
                "kind": "class",
                "source": "prior_design",
            })

    # Search dependency APIs
    for bare, qname in ctx.dep_lookup.items():
        if name_lower in bare.lower() or name_lower in qname.lower():
            matches.append({
                "qualified_name": qname,
                "kind": "dependency",
                "source": "dependency",
            })

    # Search intercomponent classes
    for cls in ctx.intercomponent_classes:
        qname = cls.get("qualified_name", "")
        bare = qname.rsplit("::", 1)[-1] if qname else ""
        cls_name = cls.get("name", bare)
        if name_lower in cls_name.lower() or name_lower in qname.lower():
            matches.append({
                "qualified_name": qname,
                "kind": cls.get("kind", "class"),
                "source": "intercomponent",
            })

    return json.dumps({"found": len(matches) > 0, "matches": matches})
