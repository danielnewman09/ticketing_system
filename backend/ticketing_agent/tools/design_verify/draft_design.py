"""draft_design tool: submit or revise the OO design draft."""

import json

from backend.codebase.schemas import OODesignSchema
from backend.ticketing_agent.tools.helpers.draft_state import (
    build_draft_lookup,
    check_enum_collisions,
    draft_summary,
)
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
            "design": OODesignSchema.model_json_schema(),
        },
        "required": ["design"],
    },
}


def handle(ctx, tool_input: dict) -> str:
    """Parse, validate, and store the draft design."""
    try:
        design = OODesignSchema.model_validate(tool_input.get("design", tool_input))
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
    ctx.draft_lookup = build_draft_lookup(design)

    return json.dumps({
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "draft_summary": draft_summary(design),
    })
