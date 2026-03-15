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

from agents.llm_client import call_tool
from requirements.schemas import VerificationSchema


SYSTEM_PROMPT = """\
You are a verification engineer. Given a low-level requirement and the
ontology design (classes, structs, enums, etc.), your job is to produce
a detailed, structured verification procedure.

## Ontology nodes available

{nodes}

## Instructions

For each verification method on the LLR, flesh out:

1. **Pre-conditions** — assertions on member variables that must hold before the
   test action. Each has:
   - member_qualified_name: fully qualified member (e.g., "calc::core::Calculator::operand_a")
   - operator: one of "==", "!=", "<", ">", "<=", ">=", "is_true", "is_false", "contains", "not_null"
   - expected_value: the expected state (e.g., "0.0", "Operation::None", "true")

2. **Actions** — ordered stimulus steps performed during the test. Each has:
   - description: human-readable step (e.g., "Press the + button")
   - member_qualified_name: the member invoked, if applicable
     (e.g., "calc::gui::OperatorButton::onClick")

3. **Post-conditions** — assertions on member variables that must hold after the
   actions. Same format as pre-conditions.

Guidelines:
- Reference real qualified names from the ontology nodes above
- Member qualified names follow C++ convention: ClassName::memberName
- Keep conditions specific and testable — avoid vague assertions
- Actions should be concrete, ordered steps
- For "review" or "inspection" methods, conditions/actions can be lighter
- Preserve the existing method, test_name, and description from the input

You MUST use the produce_verifications tool to return your result.
"""

TOOL_DEFINITION = {
    "name": "produce_verifications",
    "description": "Return the fleshed-out verification procedures for an LLR",
    "input_schema": {
        "type": "object",
        "properties": {
            "verifications": {
                "type": "array",
                "items": VerificationSchema.model_json_schema(),
            },
        },
        "required": ["verifications"],
    },
}


class VerifyResult:
    """Wrapper for the agent's structured output."""

    def __init__(self, verifications: list[VerificationSchema]):
        self.verifications = verifications


def _format_ontology_nodes(nodes: list[dict]) -> str:
    """Format ontology nodes for the system prompt."""
    lines = []
    for n in nodes:
        lines.append(f"- {n['qualified_name']} ({n['kind']}): {n['description']}")
    return "\n".join(lines) if lines else "(no ontology nodes)"


def verify(
    llr: dict,
    existing_verifications: list[dict],
    ontology_nodes: list[dict],
    model: str = "",
    prompt_log_file: str = "",
) -> VerifyResult:
    """
    Takes an LLR dict, its existing verifications, and ontology context.
    Returns fleshed-out verification procedures.

    llr: {id, description}
    existing_verifications: [{method, test_name, description}, ...]
    ontology_nodes: [{qualified_name, kind, description}, ...]
    """
    nodes_text = _format_ontology_nodes(ontology_nodes)
    system_prompt = SYSTEM_PROMPT.format(nodes=nodes_text)

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
    return VerifyResult(verifications=verifications)


if __name__ == "__main__":
    import os
    import sys

    from db import init_db, get_session
    from db.models import OntologyNode, LowLevelRequirement

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

        nodes = [
            {"qualified_name": n.qualified_name, "kind": n.kind, "description": n.description}
            for n in session.query(OntologyNode).all()
        ]

    result = verify(llr_dict, existing, nodes)
    print(json.dumps(
        [v.model_dump() for v in result.verifications],
        indent=2,
    ))
