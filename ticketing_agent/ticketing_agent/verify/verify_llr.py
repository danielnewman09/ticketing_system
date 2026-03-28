"""
Agent that fleshes out verification procedures for low-level requirements.

Takes existing LLRs (with basic verification stubs from decompose_hlr) and
the ontology design (nodes from design_ontology), and produces structured
verification specifications with:
- Pre-conditions: member state assertions before the stimulus
- Actions: ordered steps/stimuli referencing ontology members
- Post-conditions: expected member state after the stimulus

Runs after design_ontology so it can reference concrete ontology members.
"""

import json

from llm_caller import call_tool
from requirements.schemas import VerificationSchema

from ticketing_agent.verify.verify_llr_prompt import (
    SYSTEM_PROMPT,
    TOOL_DEFINITION,
    format_structured_context,
)


class VerifyResult:
    """Wrapper for the agent's structured output with validation report."""

    def __init__(self, verifications: list[VerificationSchema], validation=None):
        self.verifications = verifications
        self.validation = validation


def _flatten_class_contexts(class_contexts: list[dict]) -> list[dict]:
    """Flatten structured class contexts into a flat ontology node list for validation."""
    nodes = []
    for cls in class_contexts:
        nodes.append({
            "qualified_name": cls["qualified_name"],
            "kind": cls["kind"],
            "description": cls.get("description", ""),
        })
        for m in cls.get("attributes", []) + cls.get("methods", []):
            nodes.append({
                "qualified_name": m["qualified_name"],
                "kind": m["kind"],
                "description": m.get("description", ""),
            })
    return nodes


def verify(
    llr: dict,
    existing_verifications: list[dict],
    class_contexts: list[dict],
    ontology_nodes: list[dict] | None = None,
    model: str = "",
    prompt_log_file: str = "",
) -> VerifyResult:
    """
    Takes an LLR dict, its existing verifications, and structured design context.
    Returns fleshed-out verification procedures with a validation report.

    llr: {id, description}
    existing_verifications: [{method, test_name, description}, ...]
    class_contexts: [{qualified_name, kind, description, attributes, methods, relationships}, ...]
    ontology_nodes: optional flat node list for validation (derived from class_contexts if omitted)
    """
    from requirements.services.persistence import validate_verification_references

    context_text = format_structured_context(class_contexts)
    system_prompt = SYSTEM_PROMPT.format(design_context=context_text)

    verifications_text = "\n".join(
        f"  - [{v['method']}] {v['test_name']}: {v['description']}"
        for v in existing_verifications
    )

    user_message = (
        f"Flesh out the verification procedures for this LLR:\n\n"
        f"LLR {llr['id']}: {llr['description']}\n\n"
        f"Existing verification stubs:\n{verifications_text}"
    )

    result = call_tool(
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
        tools=[TOOL_DEFINITION],
        tool_name="produce_verifications",
        model=model,
        prompt_log_file=prompt_log_file,
    )

    verifications = [
        VerificationSchema.model_validate(v)
        for v in result["verifications"]
    ]

    # Validate references against known nodes
    if ontology_nodes is None:
        ontology_nodes = _flatten_class_contexts(class_contexts)
    validation = validate_verification_references(verifications, ontology_nodes)

    return VerifyResult(verifications=verifications, validation=validation)


if __name__ == "__main__":
    import os
    import sys

    from db import init_db, get_session
    from db.models import LowLevelRequirement
    from requirements.services.persistence import build_verification_context

    init_db()

    llr_id = int(sys.argv[1]) if len(sys.argv) > 1 else None
    if not llr_id:
        print("Usage: python -m agents.verify_llr <llr_id>")
        sys.exit(1)

    with get_session() as session:
        llr = session.query(LowLevelRequirement).filter_by(id=llr_id).first()
        llr_dict = {"id": llr.id, "description": llr.description}

        existing = [
            {"method": v.method, "test_name": v.test_name, "description": v.description}
            for v in llr.verifications
        ]

        class_contexts = build_verification_context(session)

    result = verify(llr_dict, existing, class_contexts)

    if result.validation and not result.validation.all_resolved:
        print(f"WARNING: {len(result.validation.unresolved)} unresolved references:")
        for qname, ctx in result.validation.unresolved:
            print(f"  - {qname} ({ctx})")
        print()

    print(json.dumps(
        [v.model_dump() for v in result.verifications],
        indent=2,
    ))
