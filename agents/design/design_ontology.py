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

from agents.llm_client import call_tool
from codebase.models import Predicate
from codebase.schemas import DesignSchema


SYSTEM_PROMPT = """\
You are a software design agent. Given a set of decomposed requirements
(high-level and low-level), your job is to derive an object-oriented ontology
design that could satisfy those requirements.

Produce:
1. **Nodes** — the code constructs needed. Each must have:
   - kind: one of "class", "attribute", "enum", "enum_value", "interface",
     "function", "primitive"
   - name: short name (e.g., "Calculator", "title")
   - qualified_name: fully qualified name (e.g., "calc::Calculator",
     "calc::Calculator::title")
   - description: what this entity is responsible for

2. **Triples** — semantic triples (subject --predicate--> object) between nodes,
   using their qualified_names. The predicate MUST be one of the allowed
   predicates listed below. Each must have:
   - subject_qualified_name: the node performing the action
   - predicate: one of the allowed predicate names (see below)
   - object_qualified_name: the node being acted upon

   **Allowed predicates:** {predicates}

3. **Requirement links** — map each requirement to the triples that express it.
   Each must have:
   - requirement_type: "hlr" or "llr"
   - requirement_id: the ID of the requirement
   - triple_index: the 0-based index of the triple in your triples array

## Node kind guidance

- **class** — An entity with its own behavior that participates in
  relationships beyond its parent. Use for things that *do* something or
  that other classes depend on.
- **attribute** — A property, characteristic, or data field belonging to a
  class. Use for things that *describe* a class (title, color, layout style,
  width, name, etc.). An attribute is NOT a class. If something is a simple
  property of a parent entity, it must be an attribute, not a class.
  Attributes are composed by their owning class via `composes`.
  Attributes must NEVER appear as the subject of any triple — they are
  always the object of a `composes` relationship.
- **enum** — A fixed set of named values. Contains enum_value children.
- **enum_value** — A member of an enum. Must be nested under its parent
  enum using qualified_name scoping (e.g., `core::Color::RED`).
- **interface** — A contract that classes realize. Use only when multiple
  classes share a common interface.
- **function** — A callable unit of behavior. Use for standalone functions
  or methods that participate in `invokes` relationships.
- **primitive** — A built-in type (int, str, bool, float). Use sparingly
  when a relationship to a primitive type is important.

## Guidelines

- Use namespaces to organize related classes (e.g., "calc::gui::", "calc::core::")
- Every HLR should be linked to at least one triple
- LLRs should be linked where they clearly correspond to a design relationship
  (skip mappings for vague requirements unless a triple fits)
- Use inheritance (`generalizes`) where there is a clear is-a relationship
  (e.g., NumberButton generalizes Button). A container that aggregates or
  composes the base class implicitly covers all derived types.
- Keep the design minimal — only include entities needed by the requirements
- Prefer attributes over classes for properties. Ask: "Does this entity have
  its own behavior or relationships?" If no, it is an attribute.

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
        lines.append(f"HLR {hlr['id']}: {hlr['description']}")
        for llr in [l for l in llrs if l["hlr_id"] == hlr["id"]]:
            lines.append(f"  LLR {llr['id']}: {llr['description']}")
    # Unlinked LLRs
    unlinked = [l for l in llrs if l["hlr_id"] is None]
    if unlinked:
        lines.append("\nUnlinked LLRs:")
        for llr in unlinked:
            lines.append(f"  LLR {llr['id']}: {llr['description']}")
    return "\n".join(lines)


def design(hlrs: list[dict], llrs: list[dict], model: str = "", prompt_log_file: str = "") -> DesignSchema:
    """
    Takes lists of HLR/LLR dicts and returns an ontology design.

    Each HLR dict: {id, description}
    Each LLR dict: {id, hlr_id, description}
    """
    requirements_text = format_requirements_for_prompt(hlrs, llrs)

    # Build system prompt with allowed predicates from DB
    predicate_names = list(Predicate.objects.values_list("name", flat=True))
    if not predicate_names:
        Predicate.ensure_defaults()
        predicate_names = list(Predicate.objects.values_list("name", flat=True))
    system_prompt = SYSTEM_PROMPT.format(predicates=", ".join(predicate_names))

    result = call_tool(
        system=system_prompt,
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
        tool_name="produce_design",
        model=model,
        prompt_log_file=prompt_log_file,
    )

    return DesignSchema.model_validate(result)


if __name__ == "__main__":
    import os
    import sys

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django
    django.setup()

    from django.db.models import F
    from requirements.models import HighLevelRequirement, LowLevelRequirement

    hlrs = list(HighLevelRequirement.objects.values("id", "description"))
    llrs = list(LowLevelRequirement.objects.values(
        "id", "description",
    ).annotate(hlr_id=F("high_level_requirement_id")))

    if not hlrs:
        print("No requirements found. Run the demo or create some first.")
        sys.exit(1)

    result = design(hlrs, llrs)
    print(json.dumps(result.model_dump(), indent=2))
