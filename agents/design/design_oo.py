"""
Stage 1 agent: derive an object-oriented class design from requirements.

Produces a pure OO class diagram (classes, methods, attributes, inheritance,
associations). No ontology vocabulary — the deterministic mapper (Stage 2)
handles that translation.

Uses the more capable model via call_tool (single-model reasoning + tool call).
"""

import json
import logging

from agents.llm_client import call_tool
from codebase.models.ontology import LANGUAGE_SPECIALIZATIONS, VISIBILITY_CHOICES
from codebase.schemas import OODesignSchema


# ---------------------------------------------------------------------------
# Reasoner prompt: asks for markdown, not a tool call
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a software design agent. Given a set of requirements (high-level and
low-level), your job is to derive an object-oriented class design that could
satisfy those requirements.

You MUST use the produce_oo_design tool to return your result.

CRITICAL: Every class MUST include its "attributes" and "methods" arrays in
the tool call. Do NOT omit them. Dropping attributes or methods is the worst
failure mode.

## Design guidance

### Modules
Use "::" as the separator (e.g., "calc::gui", "calc::core").

### Classes
Each class needs: name, module, description, attributes, methods,
inherits_from, realizes_interfaces, and requirement_ids.

### Attributes
Each attribute needs: name, type_name, visibility, description.

### Methods
Each method needs: name, visibility, description, parameters, return_type.

### Interfaces
Only create interfaces when multiple classes share a common contract and
polymorphism is required. Do NOT create an interface for a single concrete class.

### Enums
Each enum needs: name, module, description, values.

### Associations
Relationships between design entities (classes, interfaces, or enums).
Do not include attributes or methods — those are covered by composition.
Do NOT manufacture associations just to fill this section.
Kind is one of: associates, aggregates, depends_on, invokes.

## Visibility

Every method and attribute MUST have a visibility value:
- "public" — part of the class's public API
- "private" — internal implementation detail
- "protected" — accessible to subclasses but not external code

## Attributes vs. associations

Attributes and associations serve different purposes and are NOT mutually
exclusive:

- Attributes declare what a class holds — the field name and type.
- Associations declare the semantic relationship between two design entities.

When a class holds a reference to another class as an attribute, you should:
1. List the attribute in the class's attributes array
2. List the relationship in the associations array

Do NOT list primitive-type attributes (int, string, bool, etc.) in
associations — only relationships between design entities.

Do NOT put inheritance or interface realization in associations — use
inherits_from and realizes_interfaces on the class instead.

{specializations_section}

## Guidelines

- Use modules to organize related classes
- Every HLR should be addressed by at least one class
- Tag requirement_ids on classes and associations where they clearly correspond
- Use inheritance where there is a clear is-a relationship
- Keep the design minimal — only include entities needed by the requirements
- Prefer attributes over classes for simple properties. Ask: "Does this entity
  have its own behavior or relationships?" If no, it is an attribute.

{existing_classes_section}
"""


# ---------------------------------------------------------------------------
# Tool definition (used by the formatter only)
# ---------------------------------------------------------------------------

TOOL_DEFINITION = {
    "name": "produce_oo_design",
    "description": "Return the object-oriented class design derived from the requirements",
    "input_schema": OODesignSchema.model_json_schema(),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_specializations_section(language):
    """Build the specializations prompt section for a target language."""
    specs = LANGUAGE_SPECIALIZATIONS.get(language)
    if not specs:
        return ""
    lines = [f"## Language-specific specializations ({language})\n"]
    lines.append(
        "When a specialization applies, set the `specialization` field on the class. "
        "Only use specializations from this list:\n"
    )
    for kind in sorted(specs):
        if specs[kind]:
            values = ", ".join(f'"{s}"' for s in specs[kind])
            lines.append(f"- **{kind}**: {values}")
    return "\n".join(lines)


def format_requirements_for_prompt(hlrs, llrs):
    """Format HLR/LLR data into a text block for the agent prompt."""
    lines = []
    for hlr in hlrs:
        component = hlr.get("component_name")
        comp_tag = f" [Component: {component}]" if component else ""
        lines.append(f"HLR hlr:{hlr['id']}{comp_tag}: {hlr['description']}")
        for llr in [l for l in llrs if l["hlr_id"] == hlr["id"]]:
            lines.append(f"  LLR llr:{llr['id']}: {llr['description']}")
    unlinked = [l for l in llrs if l["hlr_id"] is None]
    if unlinked:
        lines.append("\nUnlinked LLRs:")
        for llr in unlinked:
            lines.append(f"  LLR llr:{llr['id']}: {llr['description']}")
    return "\n".join(lines)


def _build_existing_classes_section(existing_classes):
    """Build the prompt section describing classes already in the design.

    Args:
        existing_classes: List of dicts, each with keys:
            - qualified_name: e.g., "calc::core::Calculator"
            - kind: e.g., "class", "interface", "enum"
            - description: what the class does
            - methods: list of {"name": str, "visibility": str} dicts
            - attributes: list of {"name": str, "visibility": str} dicts
            - inherits_from: list of parent class qualified names
            - realizes: list of interface qualified names
            - associations: list of dicts with 'target', 'kind', 'description'
    """
    if not existing_classes:
        return ""

    lines = [
        "## Existing classes in the design\n",
        "The following classes have already been designed for previous requirements. ",
        "You MUST reuse and extend these where appropriate rather than creating ",
        "duplicates. You may add new methods/attributes to existing classes by ",
        "including them in your output with the same name and module. You may ",
        "also create new classes that associate with or inherit from these.\n",
    ]

    for cls in existing_classes:
        kind = cls.get("kind", "class")
        qname = cls["qualified_name"]
        desc = cls.get("description", "")
        lines.append(f"### {kind}: `{qname}`")
        if desc:
            lines.append(f"  {desc}")

        methods = cls.get("methods", [])
        if methods:
            grouped = {}
            for m in methods:
                grouped.setdefault(m["visibility"], []).append(m["name"])
            parts = [f"{vis}: {', '.join(names)}" for vis, names in grouped.items()]
            lines.append(f"  Methods: {'; '.join(parts)}")

        attributes = cls.get("attributes", [])
        if attributes:
            grouped = {}
            for a in attributes:
                grouped.setdefault(a["visibility"], []).append(a["name"])
            parts = [f"{vis}: {', '.join(names)}" for vis, names in grouped.items()]
            lines.append(f"  Attributes: {'; '.join(parts)}")

        inherits = cls.get("inherits_from", [])
        if inherits:
            lines.append(f"  Inherits from: {', '.join(inherits)}")

        realizes = cls.get("realizes", [])
        if realizes:
            lines.append(f"  Realizes: {', '.join(realizes)}")

        assocs = cls.get("associations", [])
        for a in assocs:
            lines.append(f"  {a['kind']} -> {a['target']}: {a.get('description', '')}")

        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _build_dependency_section(dependency_contexts: dict[int, dict]) -> str:
    """Build a prompt section describing known dependencies for HLRs."""
    if not dependency_contexts:
        return ""
    lines = [
        "\n## Known Dependencies\n",
        "Use these library types where appropriate rather than re-implementing:\n",
    ]
    for hlr_id, ctx in sorted(dependency_contexts.items()):
        rec = ctx.get("recommendation", "none")
        if rec == "none":
            continue
        dep_name = ctx.get("dependency_name", "")
        structures = ctx.get("relevant_structures", [])
        structs_text = f" ({', '.join(structures)})" if structures else ""
        lines.append(f"- HLR {hlr_id}: {dep_name}{structs_text}")
    # If all were "none", return empty
    if len(lines) == 3:
        return ""
    return "\n".join(lines)


def design_oo(
    hlrs: list[dict],
    llrs: list[dict],
    language: str = "",
    existing_classes: list[dict] | None = None,
    dependency_contexts: dict[int, dict] | None = None,
    model: str = "",
    prompt_log_file: str = "",
) -> OODesignSchema:
    """
    Stage 1: derive an OO class design from requirements.

    Each HLR dict: {id, description}
    Each LLR dict: {id, hlr_id, description}
    existing_classes: Optional context about classes already designed for
        previous HLRs. See _build_existing_classes_section for format.
    """
    requirements_text = format_requirements_for_prompt(hlrs, llrs)

    system = SYSTEM_PROMPT.format(
        specializations_section=_build_specializations_section(language),
        existing_classes_section=_build_existing_classes_section(existing_classes or []),
    )
    dep_section = _build_dependency_section(dependency_contexts or {})
    if dep_section:
        system += dep_section

    # Build component context for the user prompt
    components = {h.get("component_name") for h in hlrs if h.get("component_name")}
    component_hint = ""
    if components:
        names = ", ".join(sorted(components))
        component_hint = (
            f"\n\nThese requirements belong to the following architectural "
            f"component(s): {names}. Your class design should be scoped to "
            f"and appropriate for this component context.\n"
        )

    result = call_tool(
        system=system,
        messages=[
            {
                "role": "user",
                "content": (
                    "Derive an object-oriented class design from these requirements:\n\n"
                    f"{requirements_text}"
                    f"{component_hint}"
                ),
            }
        ],
        tools=[TOOL_DEFINITION],
        tool_name="produce_oo_design",
        model=model,
        prompt_log_file=prompt_log_file,
    )

    schema = OODesignSchema.model_validate(result)

    log = logging.getLogger("agents.design")
    for cls in schema.classes:
        if not cls.methods and not cls.attributes:
            log.warning(
                "design_oo: class %s has no methods or attributes — "
                "the model may have dropped nested arrays",
                cls.name,
            )

    return schema
