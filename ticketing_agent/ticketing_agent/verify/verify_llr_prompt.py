"""
Prompt templates and formatters for the verify_llr agent.
"""

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


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

_VIS_PREFIX = {"private": "-", "protected": "#", "public": "+", "": " "}


def format_structured_context(class_contexts: list[dict]) -> str:
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
