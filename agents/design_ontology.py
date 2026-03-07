"""
Agent that derives an ontology design (classes, relationships) from
a set of decomposed requirements.

Takes the existing HLRs and LLRs and produces:
- Ontology nodes (classes, structs, enums, etc.) with fully qualified names
- Triples (subject --predicate--> object) between nodes
- Links mapping each requirement to its associated triples

Can be used standalone (CLI) or imported by Django views/management commands.
"""

import json
import anthropic

from codebase.schemas import DesignSchema


SYSTEM_PROMPT = """\
You are a software design agent. Given a set of decomposed requirements
(high-level and low-level), your job is to derive an object-oriented ontology
design that could satisfy those requirements.

Produce:
1. **Nodes** — the classes, structs, enums, interfaces, or namespaces needed.
   Each must have:
   - kind: one of "class", "struct", "enum", "union", "namespace", "interface", "concept"
   - name: short class name (e.g., "Calculator")
   - qualified_name: fully qualified name (e.g., "calc::Calculator")
   - description: what this entity is responsible for

2. **Triples** — semantic triples (subject --predicate--> object) between nodes,
   using their qualified_names. The predicate is a verb describing the
   relationship (e.g., "inherits", "composes", "displays", "validates").
   Each must have:
   - subject_qualified_name: the node performing the action
   - predicate: the verb/action (e.g., "inherits", "composes", "compiles")
   - object_qualified_name: the node being acted upon

3. **Requirement links** — map each requirement to the triples that express it.
   Each must have:
   - requirement_type: "hlr" or "llr"
   - requirement_id: the ID of the requirement
   - triple_index: the 0-based index of the triple in your triples array

Guidelines:
- Design should follow SOLID principles and separation of concerns
- Use namespaces to organize related classes (e.g., "calc::gui::", "calc::core::")
- Every HLR should be linked to at least one triple
- LLRs should be linked where they clearly correspond to a design relationship
  (skip mappings for vague requirements unless a triple fits)
- Prefer composition over inheritance
- Keep the design minimal — only include entities needed by the requirements

You MUST use the produce_design tool to return your result.
"""

TOOL_DEFINITION = {
    "name": "produce_design",
    "description": "Return the ontology design derived from the requirements",
    "input_schema": DesignSchema.model_json_schema(),
}


def format_requirements_for_prompt(hlrs, llrs):
    """Format HLR/LLR data into a text block for the agent prompt."""
    lines = []
    for hlr in hlrs:
        lines.append(f"HLR {hlr['id']}: {hlr['actor']} {hlr['action']} {hlr['subject']}")
        if hlr.get("description"):
            lines.append(f"  Description: {hlr['description']}")
        for llr in [l for l in llrs if l["hlr_id"] == hlr["id"]]:
            lines.append(f"  LLR {llr['id']}: {llr['actor']} {llr['action']} {llr['subject']}")
            if llr.get("description"):
                lines.append(f"    Description: {llr['description']}")
    # Unlinked LLRs
    unlinked = [l for l in llrs if l["hlr_id"] is None]
    if unlinked:
        lines.append("\nUnlinked LLRs:")
        for llr in unlinked:
            lines.append(f"  LLR {llr['id']}: {llr['actor']} {llr['action']} {llr['subject']}")
            if llr.get("description"):
                lines.append(f"    Description: {llr['description']}")
    return "\n".join(lines)


def design(hlrs: list[dict], llrs: list[dict], model: str = "claude-sonnet-4-20250514") -> DesignSchema:
    """
    Takes lists of HLR/LLR dicts and returns an ontology design.

    Each HLR dict: {id, actor, action, subject, description}
    Each LLR dict: {id, hlr_id, actor, action, subject, description}
    """
    client = anthropic.Anthropic()

    requirements_text = format_requirements_for_prompt(hlrs, llrs)

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    "Derive an ontology design from these requirements:\n\n"
                    f"{requirements_text}"
                ),
            }
        ],
        tools=[TOOL_DEFINITION],
        tool_choice={"type": "tool", "name": "produce_design"},
    )

    for block in response.content:
        if block.type == "tool_use":
            return DesignSchema.model_validate(block.input)

    raise RuntimeError("Agent did not return a tool call")


if __name__ == "__main__":
    import os
    import sys

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django
    django.setup()

    from django.db.models import F
    from requirements.models import HighLevelRequirement, LowLevelRequirement

    hlrs = list(HighLevelRequirement.objects.values("id", "actor", "action", "subject", "description"))
    llrs = list(LowLevelRequirement.objects.values(
        "id", "actor", "action", "subject", "description",
    ).annotate(hlr_id=F("high_level_requirement_id")))

    if not hlrs:
        print("No requirements found. Run the demo or create some first.")
        sys.exit(1)

    result = design(hlrs, llrs)
    print(json.dumps(result.model_dump(), indent=2))
