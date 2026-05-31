"""draft_design tool: submit or revise the OO design draft."""

import json

from codegraph.designs import ClassDiagram
from backend.design_data import class_diagram_from_oo_design
from backend.ticketing_agent.tools.helpers.design_validation import check_enum_collisions
from backend.ticketing_agent.tools.helpers.design_validation import validate_oo_design

SCHEMA = {
    "name": "draft_design",
    "description": (
        "Submit or revise the current OO design draft. The design is stored "
        "in the tool loop state so that subsequent validate_qualified_names "
        "and lookup_design_element calls can check references against it. "
        "Returns validation results and a summary of the stored draft."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "design": ClassDiagram.model_json_schema(),
        },
        "required": ["design"],
    },
}


def handle(ctx, tool_input: dict) -> str:
    """Parse, validate, and store the draft design."""
    try:
        design = ClassDiagram.model_validate(tool_input.get("design", tool_input))
    except Exception as e:
        return json.dumps({
            "valid": False,
            "errors": [f"Invalid design format: {e}"],
            "draft_summary": {},
        })

    errors = validate_oo_design(
        design,
        prior_class_lookup=ctx.prior_class_lookup,
        dependency_lookup=ctx.dep_lookup,
        intercomponent_classes=ctx.intercomponent_classes,
    )

    warnings = check_enum_collisions(design, ctx.prior_class_lookup)

    # Store draft — mutable state on ctx
    ctx.draft_design = design
    diagram = class_diagram_from_oo_design(design)
    ctx.draft_lookup = diagram.to_draft_lookup()

    return json.dumps({
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "draft_summary": diagram.to_summary(),
    })
