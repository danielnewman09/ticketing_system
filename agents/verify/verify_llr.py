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

## Design context

{design_context}

## Instructions

For each verification method on the LLR, flesh out:

1. **Pre-conditions** — assertions on member variables that must hold before the
   test action. Each has:
   - member_qualified_name: fully qualified member given as its fully qualified name with `<namespace>::` prefix
   - operator: one of "==", "!=", "<", ">", "<=", ">=", "is_true", "is_false", "contains", "not_null"
   - expected_value: the expected state (e.g., "0.0", "Operation::None", "true")

2. **Actions** — ordered stimulus steps performed during the test. Each has:
   - description: human-readable step (e.g., "Press the + button")
   - member_qualified_name: the member invoked, if applicable, given as its fully qualified name with `<namespace>::` prefix

3. **Post-conditions** — assertions on member variables that must hold after the
   actions. Same format as pre-conditions.

Guidelines:
- Reference ONLY real qualified names from the design context above
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
    """Wrapper for the agent's structured output with validation report."""

    def __init__(self, verifications: list[VerificationSchema], validation=None):
        self.verifications = verifications
        self.validation = validation


_VIS_PREFIX = {"private": "-", "protected": "#", "public": "+", "": " "}


def _format_structured_context(class_contexts: list[dict]) -> str:
    """Format class-level design context as a PlantUML-like prompt section."""
    if not class_contexts:
        return "(no design context)"

    sections = []
    for cls in class_contexts:
        lines = [f"## {cls['qualified_name']} ({cls['kind']})"]
        if cls.get("description"):
            lines.append(f"  {cls['description']}")

        attrs = cls.get("attributes", [])
        if attrs:
            lines.append("")
            lines.append("  Attributes:")
            for a in attrs:
                vis = _VIS_PREFIX.get(a.get("visibility", ""), " ")
                sig = f": {a['type_signature']}" if a.get("type_signature") else ""
                lines.append(f"    {vis} {a['name']}{sig}")
                if a.get("description"):
                    lines.append(f"      {a['description']}")

        methods = cls.get("methods", [])
        if methods:
            lines.append("")
            lines.append("  Methods:")
            for m in methods:
                vis = _VIS_PREFIX.get(m.get("visibility", ""), " ")
                args = m.get("argsstring") or "()"
                sig = f" -> {m['type_signature']}" if m.get("type_signature") else ""
                lines.append(f"    {vis} {m['name']}{args}{sig}")
                if m.get("description"):
                    lines.append(f"      {m['description']}")

        rels = cls.get("relationships", [])
        if rels:
            lines.append("")
            lines.append("  Relationships:")
            for r in rels:
                lines.append(f"    {r['predicate'].upper()} -> {r['target']}")

        sections.append("\n".join(lines))

    return "\n\n".join(sections)


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

    context_text = _format_structured_context(class_contexts)
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
