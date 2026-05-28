"""commit_design_and_verifications tool: atomically commit design + verifications."""

import json

from backend.codebase.schemas import DesignAndVerificationSchema
from backend.db.neo4j.repositories.verification import _is_valid_verification_qname
from backend.ticketing_agent.tools.helpers.commit_schema import commit_tool_schema
from backend.ticketing_agent.tools.helpers.design_validation import validate_oo_design
from backend.ticketing_agent.tools.helpers.draft_state import build_draft_lookup
from backend.ticketing_agent.tools.helpers.qname import qname_resolves, suggest_qname

_input_schema = commit_tool_schema()
SCHEMA = {
    "name": "commit_design_and_verifications",
    "description": (
        "Commit the final OO design and all verification procedures. This "
        "terminates the agent loop. Validates that all qualified names "
        "reference real design elements and that the design is structurally "
        "sound. If there are errors, returns them for the agent to fix "
        "before retrying."
    ),
    "input_schema": _input_schema,
}


def handle(ctx, tool_input: dict) -> str:
    """Validate and commit the final design + verifications."""
    try:
        schema = DesignAndVerificationSchema.model_validate(tool_input)
    except Exception as e:
        return json.dumps({"committed": False, "errors": [f"Invalid input format: {e}"]})

    errors = []

    # 1. Design validation
    design_errors = validate_oo_design(
        schema.oo_design,
        prior_class_lookup=ctx.prior_class_lookup,
        dependency_lookup=ctx.dep_lookup,
        intercomponent_classes=ctx.intercomponent_classes,
    )
    errors.extend(design_errors)

    # 2. QName validation across all verifications
    all_qnames = _collect_verification_qnames(schema, errors)

    # 3. Existence check for all referenced qnames
    commit_lookup = build_draft_lookup(schema.oo_design)
    for qn in all_qnames:
        if qname_resolves(qn, commit_lookup, ctx.prior_class_lookup, ctx.dep_lookup, ctx.intercomponent_classes, ctx.neo4j_session):
            continue
        suggestion = suggest_qname(qn, commit_lookup, ctx.prior_class_lookup, ctx.dep_lookup, ctx.intercomponent_classes)
        error_msg = f"Unresolved reference: '{qn}' does not exist in the design context."
        if suggestion:
            error_msg += f" Did you mean '{suggestion}'?"
        errors.append(error_msg)

    if errors:
        return json.dumps({"committed": False, "errors": errors})

    return json.dumps({
        "committed": True,
        "oo_design": schema.oo_design.model_dump(),
        "verifications": {
            str(k): [v.model_dump() for v in vs] for k, vs in schema.verifications.items()
        },
    })


def _collect_verification_qnames(schema, errors: list[str]) -> set[str]:
    """Collect all qname references from verifications and validate object_qualified_name format."""
    all_qnames = set()
    for llr_id, verifs in schema.verifications.items():
        for v in verifs:
            for cond in v.preconditions + v.postconditions:
                if cond.subject_qualified_name:
                    all_qnames.add(cond.subject_qualified_name)
                if cond.object_qualified_name:
                    is_valid, _ = _is_valid_verification_qname(cond.object_qualified_name)
                    if not is_valid:
                        errors.append(
                            f"LLR {llr_id}: Invalid object_qualified_name "
                            f"in condition: '{cond.object_qualified_name}'. "
                            f"Use expected_value for literal values."
                        )
            for action in v.actions:
                if action.caller_qualified_name:
                    all_qnames.add(action.caller_qualified_name)
                if action.callee_qualified_name:
                    all_qnames.add(action.callee_qualified_name)
    return all_qnames
