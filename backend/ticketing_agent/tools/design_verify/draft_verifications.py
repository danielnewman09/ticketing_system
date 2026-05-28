"""draft_verifications tool: submit/revise verification procedures with reference validation."""

import json

from backend.requirements.schemas import VerificationSchema
from backend.ticketing_agent.tools.helpers.qname import qname_resolves, suggest_qname

SCHEMA = {
    "name": "draft_verifications",
    "description": (
        "Submit or revise verification procedures for LLRs. Validates all "
        "qualified name references against the current design draft and "
        "design context (prior classes, dependency APIs, intercomponent). "
        "Returns a validation report showing which references resolved and "
        "which didn't, with suggestions for corrections. Use this after "
        "drafting your design to iteratively resolve verification stub "
        "references before committing."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "verifications": {
                "type": "object",
                "description": (
                    "Map of LLR ID (integer string) to list of verification "
                    "procedures. Keys MUST be LLR IDs like \"1\", \"2\" \u2014 "
                    "NOT test names."
                ),
                "additionalProperties": {
                    "type": "array",
                    "items": VerificationSchema.model_json_schema(),
                },
            },
        },
        "required": ["verifications"],
    },
}


def handle(ctx, tool_input: dict) -> str:
    """Parse, validate, and store drafted verifications."""
    verifs_input = tool_input.get("verifications", {})
    if not verifs_input:
        return json.dumps({"valid": False, "errors": ["No verifications provided"]})

    parsed: dict[int, list[VerificationSchema]] = {}
    parse_errors = []
    for llr_id_str, v_list in verifs_input.items():
        try:
            llr_id = int(llr_id_str)
        except (ValueError, TypeError):
            parse_errors.append(f"Non-integer LLR ID key: '{llr_id_str}'")
            continue
        parsed[llr_id] = []
        for v in v_list:
            try:
                parsed[llr_id].append(VerificationSchema.model_validate(v))
            except Exception as e:
                parse_errors.append(f"LLR {llr_id_str}: invalid verification: {e}")

    if parse_errors:
        return json.dumps({"valid": False, "errors": parse_errors})

    # Validate all qname references
    warnings = []
    unresolved_details = []
    verification_summary = {}

    # Warn if no design draft exists
    if not ctx.draft_design:
        warnings.append(
            "No design draft exists. Verification references cannot be "
            "validated against design elements. Call draft_design first."
        )

    for llr_id, verifs in parsed.items():
        llr_key = str(llr_id)
        resolved = 0
        total = 0
        for v in verifs:
            test_label = v.test_name or v.method
            for cond in v.preconditions + v.postconditions:
                if cond.subject_qualified_name:
                    total += 1
                    if qname_resolves(
                        cond.subject_qualified_name,
                        ctx.draft_lookup, ctx.prior_class_lookup,
                        ctx.dep_lookup, ctx.intercomponent_classes,
                        ctx.neo4j_session,
                    ):
                        resolved += 1
                    else:
                        suggestion = suggest_qname(
                            cond.subject_qualified_name,
                            ctx.draft_lookup, ctx.prior_class_lookup,
                            ctx.dep_lookup, ctx.intercomponent_classes,
                        )
                        detail = {
                            "llr_id": llr_key,
                            "verification": test_label,
                            "field": "subject_qualified_name",
                            "value": cond.subject_qualified_name,
                        }
                        if suggestion:
                            detail["suggestion"] = suggestion
                        unresolved_details.append(detail)
                if cond.object_qualified_name:
                    total += 1
                    if qname_resolves(
                        cond.object_qualified_name,
                        ctx.draft_lookup, ctx.prior_class_lookup,
                        ctx.dep_lookup, ctx.intercomponent_classes,
                        ctx.neo4j_session,
                    ):
                        resolved += 1
                    else:
                        suggestion = suggest_qname(
                            cond.object_qualified_name,
                            ctx.draft_lookup, ctx.prior_class_lookup,
                            ctx.dep_lookup, ctx.intercomponent_classes,
                        )
                        detail = {
                            "llr_id": llr_key,
                            "verification": test_label,
                            "field": "object_qualified_name",
                            "value": cond.object_qualified_name,
                        }
                        if suggestion:
                            detail["suggestion"] = suggestion
                        unresolved_details.append(detail)
                # Warn about missing operator
                if not cond.operator or cond.operator == "":
                    warnings.append(
                        f"LLR {llr_key} '{test_label}': condition on "
                        f"'{cond.subject_qualified_name}' has no operator \u2014 "
                        f"will default to '=='"
                    )
                # Warn about expected_value that looks like a qname
                if cond.expected_value and "::" in cond.expected_value:
                    warnings.append(
                        f"LLR {llr_key} '{test_label}': expected_value "
                        f"'{cond.expected_value}' contains '::' \u2014 if this "
                        f"references a design member, move it to "
                        f"object_qualified_name and use the display text "
                        f"as expected_value instead"
                    )
            for action in v.actions:
                if action.callee_qualified_name:
                    total += 1
                    if qname_resolves(
                        action.callee_qualified_name,
                        ctx.draft_lookup, ctx.prior_class_lookup,
                        ctx.dep_lookup, ctx.intercomponent_classes,
                        ctx.neo4j_session,
                    ):
                        resolved += 1
                    else:
                        suggestion = suggest_qname(
                            action.callee_qualified_name,
                            ctx.draft_lookup, ctx.prior_class_lookup,
                            ctx.dep_lookup, ctx.intercomponent_classes,
                        )
                        detail = {
                            "llr_id": llr_key,
                            "verification": test_label,
                            "field": "callee_qualified_name",
                            "value": action.callee_qualified_name,
                        }
                        if suggestion:
                            detail["suggestion"] = suggestion
                        unresolved_details.append(detail)
                # Warn about unqualified caller references
                if action.caller_qualified_name and "::" not in action.caller_qualified_name:
                    warnings.append(
                        f"LLR {llr_key} '{test_label}': caller "
                        f"'{action.caller_qualified_name}' is not a "
                        f"qualified name \u2014 leave empty if the caller is "
                        f"the test harness"
                    )

        verification_summary[llr_key] = {
            "methods": len(verifs),
            "resolved_references": resolved,
            "unresolved_references": total - resolved,
        }

    # Store drafted verifications
    ctx.draft_verifications = parsed

    errors = [
        f"Unresolved reference: '{d['value']}'"
        + (f" Did you mean '{d['suggestion']}'?" if "suggestion" in d else "")
        for d in unresolved_details
    ]

    return json.dumps({
        "valid": len(unresolved_details) == 0 and len(parse_errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "verification_summary": verification_summary,
        "unresolved_details": unresolved_details,
    })
