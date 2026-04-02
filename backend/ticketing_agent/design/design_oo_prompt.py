"""
Prompt templates and section builders for the design_oo agent.
"""

from backend.codebase.schemas import OODesignSchema
from backend.db.models.ontology import LANGUAGE_SPECIALIZATIONS


# ---------------------------------------------------------------------------
# System prompt template
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

IMPORTANT: You MUST use ONLY the component namespace provided in the user
message as the module for all classes. Do NOT invent sub-namespaces (e.g.,
if the namespace is "calculation_engine", use "calculation_engine" — NOT
"calculation_engine::core" or "calculation_engine::validation"). Sub-namespaces
can only come from child components, which are defined separately.

{namespace_section}

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

## Inter-component boundary flag

Set `is_intercomponent: true` on any class or interface that forms a public
API boundary meant to be used by OTHER components. These are the types that
other components will reference — e.g., shared data models, service
interfaces, or event contracts. Internal implementation classes should have
`is_intercomponent: false` (the default).

## Guidelines

- Use modules to organize related classes
- Every HLR should be addressed by at least one class
- Tag requirement_ids on classes and associations where they clearly correspond
- Use inheritance where there is a clear is-a relationship
- Keep the design minimal — only include entities needed by the requirements
- Prefer attributes over classes for simple properties. Ask: "Does this entity
  have its own behavior or relationships?" If no, it is an attribute.

{dependency_api_section}

{as_built_section}

{existing_classes_section}

{intercomponent_section}

{other_hlrs_section}
"""


# ---------------------------------------------------------------------------
# Tool definition
# ---------------------------------------------------------------------------

TOOL_DEFINITION = {
    "name": "produce_oo_design",
    "description": "Return the object-oriented class design derived from the requirements",
    "input_schema": OODesignSchema.model_json_schema(),
}


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def build_specializations_section(language):
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


def build_dependency_api_section(dependency_classes):
    """Build the prompt section describing dependency API classes.

    These are real classes from indexed third-party libraries that the
    design should reference but NOT redesign.

    Args:
        dependency_classes: List of dicts from discover_classes,
            each with keys: qualified_name, kind, source, description,
            methods, attributes, inherits_from, relevance.
    """
    if not dependency_classes:
        return ""

    lines = [
        "## Dependency API classes (read-only reference)\n",
        "The following classes come from third-party dependency libraries indexed ",
        "from their documentation. Use these types as-is in your design \u2014 inherit ",
        "from them, wrap them, use them as parameter/return types \u2014 but do NOT ",
        "redesign or duplicate them. They should be included in your output when relevant, either",
        "wrapped, dependency-injected, or generalized where appropriate.\n",
    ]

    for cls in dependency_classes:
        kind = cls.get("kind", "class")
        qname = cls["qualified_name"]
        source = cls.get("source", "")
        desc = cls.get("description", "")
        source_tag = f" (source: {source})" if source else ""
        lines.append(f"### {kind}: `{qname}`{source_tag}")
        if desc:
            lines.append(f"  {desc}")

        methods = cls.get("methods", [])
        if methods:
            public_methods = [
                m["name"] for m in methods
                if m.get("visibility", "public") == "public"
            ]
            if public_methods:
                lines.append(f"  Public methods: {', '.join(public_methods)}")

        attributes = cls.get("attributes", [])
        if attributes:
            public_attrs = [
                a["name"] for a in attributes
                if a.get("visibility", "public") == "public"
            ]
            if public_attrs:
                lines.append(f"  Public attributes: {', '.join(public_attrs)}")

        inherits = cls.get("inherits_from", [])
        if inherits:
            lines.append(f"  Inherits from: {', '.join(inherits)}")

        relevance = cls.get("relevance", "")
        if relevance:
            lines.append(f"  **Relevance:** {relevance}")

        lines.append("")

    return "\n".join(lines)


def build_as_built_section(as_built_classes):
    """Build the prompt section describing as-built project classes.

    These are existing classes from the project's codebase index that
    the design agent should evaluate for reuse, extension, or redesign.

    Args:
        as_built_classes: List of dicts from discover_classes (category
            ``"as-built"``), each with keys: qualified_name, kind,
            description, methods, attributes, inherits_from, relevance.
    """
    if not as_built_classes:
        return ""

    lines = [
        "## As-built project classes (from codebase index)\n",
        "The following classes exist in the project's current codebase. ",
        "Evaluate each and decide how to handle it:\n",
        "- **Reuse**: Use as-is if it already satisfies a requirement",
        "- **Extend**: Add methods/attributes if it partially satisfies",
        "- **Redesign**: Replace with a better design if inadequate",
        "- **Ignore**: Skip if not relevant to the current requirements\n",
        "Include reused or extended classes in your output with the same ",
        "qualified_name. For redesigned classes, include the replacement.\n",
    ]

    for cls in as_built_classes:
        kind = cls.get("kind", "class")
        qname = cls["qualified_name"]
        desc = cls.get("description", "")
        lines.append(f"### {kind}: `{qname}`")
        if desc:
            lines.append(f"  {desc}")

        methods = cls.get("methods", [])
        if methods:
            public_methods = [
                m["name"] for m in methods
                if m.get("visibility", "public") == "public"
            ]
            if public_methods:
                lines.append(f"  Public methods: {', '.join(public_methods)}")

        attributes = cls.get("attributes", [])
        if attributes:
            public_attrs = [
                a["name"] for a in attributes
                if a.get("visibility", "public") == "public"
            ]
            if public_attrs:
                lines.append(f"  Public attributes: {', '.join(public_attrs)}")

        inherits = cls.get("inherits_from", [])
        if inherits:
            lines.append(f"  Inherits from: {', '.join(inherits)}")

        relevance = cls.get("relevance", "")
        if relevance:
            lines.append(f"  **Relevance:** {relevance}")

        lines.append("")

    return "\n".join(lines)


def build_existing_classes_section(existing_classes):
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


def build_intercomponent_section(intercomponent_classes):
    """Build prompt section for cross-component public API classes.

    These classes belong to OTHER components and should be referenced
    but NOT redesigned.
    """
    if not intercomponent_classes:
        return ""

    lines = [
        "## Cross-component interfaces (read-only context)\n",
        "The following classes/interfaces belong to OTHER components and are ",
        "marked as inter-component boundaries. You may reference, depend on, ",
        "or associate with these but do NOT redesign or duplicate them. ",
        "Do NOT include them in your output.\n",
    ]

    for cls in intercomponent_classes:
        kind = cls.get("kind", "class")
        qname = cls["qualified_name"]
        desc = cls.get("description", "")
        component = cls.get("component_name", "unknown")
        lines.append(f"### {kind}: `{qname}` (component: {component})")
        if desc:
            lines.append(f"  {desc}")

        methods = cls.get("methods", [])
        if methods:
            public_methods = [m["name"] for m in methods if m.get("visibility") == "public"]
            if public_methods:
                lines.append(f"  Public methods: {', '.join(public_methods)}")

        lines.append("")

    return "\n".join(lines)


def build_other_hlrs_section(other_hlr_summaries):
    """Build prompt section listing other HLRs for awareness context."""
    if not other_hlr_summaries:
        return ""

    lines = [
        "## Other HLRs (context only)\n",
        "These other HLRs exist in the system. You are NOT designing for them — ",
        "they are provided for awareness only so you can anticipate integration points.\n",
    ]

    for hlr in other_hlr_summaries:
        status = hlr.get("status", "pending")
        lines.append(f"- HLR {hlr['id']} [{status}]: {hlr['description']}")

    return "\n".join(lines)


def build_dependency_section(dependency_contexts: dict[int, dict]) -> str:
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


def build_namespace_section(component_namespace: str, sibling_namespaces: list[str] | None = None) -> str:
    """Build the namespace constraint section for the prompt."""
    if not component_namespace:
        return ""
    lines = [
        f"The required namespace for this component is: `{component_namespace}`",
        f"All classes, interfaces, and enums MUST use module = \"{component_namespace}\".",
    ]
    if sibling_namespaces:
        lines.append("\nOther component namespaces (for reference, do NOT use as module):")
        for ns in sibling_namespaces:
            lines.append(f"  - {ns}")
    return "\n".join(lines)


