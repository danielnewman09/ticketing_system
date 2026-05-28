"""validate_design tool: validate draft design for structural consistency."""

import json

from backend.codebase.schemas import OODesignSchema
from backend.ticketing_agent.tools.helpers.draft_state import check_enum_collisions
from backend.ticketing_agent.tools.helpers.design_validation import validate_oo_design

SCHEMA = {
    "name": "validate_design",
    "description": (
        "Validate the current draft OO design for structural consistency. "
        "Checks for unknown association targets, missing intercomponent "
        "associations, and other issues. Uses the design currently stored "
        "via draft_design. Returns errors and warnings."
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
    """Validate the provided design draft."""
    try:
        design = OODesignSchema.model_validate(tool_input.get("design", tool_input))
    except Exception as e:
        return json.dumps({
            "valid": False,
            "errors": [f"Invalid design format: {e}"],
            "warnings": [],
        })

    errors = validate_oo_design(
        design,
        prior_class_lookup=ctx.prior_class_lookup,
        dependency_lookup=ctx.dep_lookup,
        intercomponent_classes=ctx.intercomponent_classes,
    )

    warnings = check_enum_collisions(design, ctx.prior_class_lookup)

    return json.dumps({
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    })
