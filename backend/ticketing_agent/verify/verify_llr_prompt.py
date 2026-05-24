"""
Prompt templates and formatters for the verify_llr agent.
"""

from backend.requirements.schemas import VerificationSchema

SYSTEM_PROMPT = """\
You are a verification engineer. Given a low-level requirement and the
ontology design (classes, structs, enums, etc.), your job is to produce
a detailed, structured verification procedure.

You have three tools available:

### validate_qualified_names
Validates a list of qualified names for format correctness (no test_ prefixes,
dot separators, bare identifiers) and checks if they exist as :Design nodes
in the ontology. Returns per-name validation results. Use this to verify your
references before committing.

### lookup_design_element
Searches the design context for elements matching a name pattern. Returns
qualified names, kind, and description. Use this to find the correct qualified
name for a class, method, or attribute before referencing it in conditions.

### produce_verifications
Commits your verification procedures. This terminates the agent loop — only
call this when you are confident the procedures are complete and all
references are correct.

**Recommended workflow:** Draft your verifications, use lookup_design_element
to find correct qualified names, call validate_qualified_names to check for
issues, fix any errors, then call produce_verifications.

## Design context

{design_context}

<FORMAT-CONTRACT name="qualified-names">
All `subject_qualified_name`, `object_qualified_name`, `callee_qualified_name`,
and `caller_qualified_name` fields MUST use qualified names that exactly match
the design context section above.

Pattern: <namespace>::<ClassName>::<memberName>

✓ calculation_engine::CalculatorEngine::validateInput
✓ user_interface::CalculatorWindow::equalsButton
✗ user_interface::CalculatorWindow.equalsButton
  → Dot separator — use :: everywhere
✗ calculation_engine::CalculatorEngine::last_result.is_success
  → Nested attribute path — reference the outer attribute directly
    (calculation_engine::CalculatorEngine::last_result)
    and the inner class member separately
    (calculation_engine::CalculatorResult::is_success)
✗ result_of_first_call
  → Test variable, not a design element
✗ test_validate_input_syntax
  → Test function, not a design element

If no exact match exists in the design context, do NOT fabricate a name.
Omit the reference field or use expected_value alone.
</FORMAT-CONTRACT>

## Instructions

For each verification method on the LLR, flesh out:

1. **Pre-conditions** — assertions on design elements that must hold before the
   test action. Each has:
   - subject_qualified_name: fully qualified name of the element being checked, with `<namespace>::` prefix
   - object_qualified_name: (optional) the right-hand operand, e.g. a constant or enum value
   - operator: one of "==", "!=", "<", ">", "<=", ">=", "is_true", "is_false", "contains", "not_null"
   - expected_value: the expected state (e.g., "0.0", "Operation::None", "true")

2. **Actions** — ordered stimulus steps performed during the test. Each has:
   - description: human-readable step (e.g., "Press the + button")
   - callee_qualified_name: the method or function being called, if applicable, with `<namespace>::` prefix
   - caller_qualified_name: (optional) the caller context, with `<namespace>::` prefix

3. **Post-conditions** — assertions on member variables that must hold after the
   actions. Same format as pre-conditions.

Guidelines:
- Reference ONLY real qualified names from the design context above
- Qualified names follow C++ convention: ClassName::memberName
- Keep conditions specific and testable. Every qualified name you write MUST
  exactly match a name shown in the design context section. If no exact match
  exists, do not fabricate one — omit the reference field or use expected_value alone.
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
