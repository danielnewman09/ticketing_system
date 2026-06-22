"""Migrated prompt builders for the design_oo agent.

Pure functions — no backend dependencies.  Take plain dicts (or
``LayerGraph`` objects) and return markdown sections for the LLM
prompt.  Each builder delegates to codegraph's ``export_markdown()``
for node formatting.

Usage::

    from backend_migrated.agents.design_oo_prompt import (
        build_as_built_section,
        build_existing_classes_section,
        build_intercomponent_section,
        build_namespace_section,
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from codegraph.graph import CompositeEntry, LayerGraph
from codegraph.markdown import export_markdown
from codegraph.models.tags import CodeGraphNode

if TYPE_CHECKING:
    pass

# Kind → neomodel type name mapping for deserialize()
_KIND_TO_TYPE: dict[str, str] = {
    "class": "ClassNode",
    "interface": "InterfaceNode",
    "enum": "EnumNode",
    "namespace": "NamespaceNode",
    "module": "ModuleNode",
    "function": "FunctionNode",
    "union": "UnionNode",
}

_MEMBER_KIND_TO_TYPE: dict[str, str] = {
    "method": "MethodNode",
    "attribute": "AttributeNode",
    "enumvalue": "EnumValueNode",
}


def _deserialize_class_dict(cls: dict) -> CodeGraphNode:
    """Convert a design-pipeline class dict to a codegraph node.

    Adds the ``type`` discriminator and maps ``description`` →
    ``brief_description`` so that ``to_markdown()`` picks it up.
    """
    data = dict(cls)
    kind = data.pop("kind", None) or "class"
    data["type"] = _KIND_TO_TYPE.get(kind, "ClassNode")
    data.setdefault("name", cls.get("qualified_name", "").split("::")[-1])
    data["brief_description"] = data.pop("description", "")
    # Strip keys deserialize doesn't expect
    for key in ("methods", "attributes", "relevance", "component_name",
                "associations", "realizes"):
        data.pop(key, None)
    return CodeGraphNode.deserialize(data)


def _deserialize_member_dict(member: dict, parent_qn: str) -> CodeGraphNode:
    """Convert a method/attribute dict to a codegraph member node."""
    data = dict(member)
    name = data["name"]
    data["type"] = _MEMBER_KIND_TO_TYPE.get(data.pop("kind", "method"), "MethodNode")
    data.setdefault("qualified_name", f"{parent_qn}::{name}")
    data["brief_description"] = data.pop("description", "")
    # Ensure visibility and signature fields exist
    data.setdefault("visibility", "public")
    data.setdefault("type_signature", "")
    data.setdefault("argsstring", "")
    for key in ("inherits_from", "realizes"):
        data.pop(key, None)
    return CodeGraphNode.deserialize(data)


def _dicts_to_layer_graph(classes: list[dict], tags: frozenset[str] | None = None) -> LayerGraph:
    """Build a minimal ``LayerGraph`` from a list of class dicts.

    Each class becomes a root ``CompositeEntry``.  Methods and
    attributes from the class dict are deserialized and added as
    COMPOSES children so that ``export_markdown()`` renders them
    inline.
    """
    graph = LayerGraph(tags=tags or frozenset(["design"]))
    for cls in classes:
        class_node = _deserialize_class_dict(cls)
        key = LayerGraph._node_key(class_node)
        entry = CompositeEntry(node=class_node)

        # Methods
        for m in cls.get("methods", []):
            member_node = _deserialize_member_dict(m, class_node.qualified_name)
            member_key = LayerGraph._node_key(member_node)
            child_entry = CompositeEntry(node=member_node)
            entry.children.setdefault("MethodNode", {})[member_key] = child_entry

        # Attributes
        for a in cls.get("attributes", []):
            attr_node = _deserialize_member_dict(a, class_node.qualified_name)
            attr_node.type = "AttributeNode"  # override since kind defaults to method
            # Re-deserialize with correct type
            attr_data = dict(a)
            attr_data["type"] = "AttributeNode"
            attr_data["qualified_name"] = f"{class_node.qualified_name}::{a['name']}"
            attr_data["brief_description"] = attr_data.pop("description", "")
            attr_data.setdefault("visibility", "public")
            attr_data.setdefault("type_signature", "")
            for k in ("name", "kind", "inherits_from", "realizes", "methods", "attributes"):
                attr_data.pop(k, None)
            attr_node = CodeGraphNode.deserialize({**attr_data, "name": a["name"]})
            attr_key = LayerGraph._node_key(attr_node)
            child_entry = CompositeEntry(node=attr_node)
            entry.children.setdefault("AttributeNode", {})[attr_key] = child_entry

        # References (inherits_from, realizes)
        for parent_qn in cls.get("inherits_from", []):
            entry.references.append(("INHERITS_FROM", parent_qn, "ClassNode"))
        for iface_qn in cls.get("realizes", []):
            entry.references.append(("REALIZES", iface_qn, "InterfaceNode"))

        graph.entries[key] = entry

    return graph

# ---------------------------------------------------------------------------
# build_as_built_section
# ---------------------------------------------------------------------------


def build_as_built_section(as_built_classes: list[dict]) -> str:
    """Build the prompt section describing as-built project classes.

    Converts class dicts to a ``LayerGraph`` and delegates to
    ``export_markdown()`` for all formatting (headings, methods,
    attributes, signatures, relationships).

    Args:
        as_built_classes: List of dicts from discover_classes (category
            ``"as-built"``), each with keys: qualified_name, kind,
            description, methods, attributes, inherits_from, relevance.
    """
    if not as_built_classes:
        return ""

    header = [
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

    graph = _dicts_to_layer_graph(as_built_classes)
    body = export_markdown(graph)
    return "\n".join(header) + "\n" + body


# ---------------------------------------------------------------------------
# build_existing_classes_section
# ---------------------------------------------------------------------------


def build_existing_classes_section(existing_classes: list[dict]) -> str:
    """Build the prompt section describing classes already in the design.

    Args:
        existing_classes: List of dicts, each with keys:
            - qualified_name: e.g., "climate::core::Thermostat"
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
            grouped: dict[str, list[str]] = {}
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
# build_intercomponent_section
# ---------------------------------------------------------------------------


def build_intercomponent_section(intercomponent_classes: list[dict]) -> str:
    """Build prompt section for cross-component public API classes.

    These classes belong to OTHER components and should be referenced
    but NOT redesigned.
    """
    if not intercomponent_classes:
        return ""

    lines = [
        "## Cross-component interfaces (read-only context)\n",
        "The following classes/interfaces belong to OTHER components and are ",
        "marked as inter-component boundaries.\n",
        "\u003cCONTRACT\u003e\n",
        "You MUST create associations from your classes to intercomponent classes ",
        "when your design depends on them (e.g., calls their methods, receives ",
        "their return types, holds references to them). Omitting them creates ",
        "disconnected components in the design.\n\n",
        "Do NOT redesign or duplicate these classes in your output classes — only ",
        "reference their qualified names in associations, inherits_from, attribute ",
        "types, and method return types.\n",
        "\u003c/CONTRACT\u003e\n",
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

    # Example showing expected cross-component associations
    if len(intercomponent_classes) > 0:
        example_class = intercomponent_classes[0]
        example_qname = example_class["qualified_name"]
        lines.append("### Example: cross-component association")
        lines.append(
            f"If your class calls methods on `{example_qname}`, "
            "include an association like:"
        )
        lines.append(
            f"  - from_class: YourClass, to_class: {example_qname}, kind: depends_on"
        )
        lines.append("")
        lines.append(
            "Note: Use the qualified name (with namespace prefix) for "
            "intercomponent classes in from_class/to_class fields of associations."
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# build_namespace_section
# ---------------------------------------------------------------------------


def build_namespace_section(
    component_namespace: str, sibling_namespaces: list[str] | None = None
) -> str:
    """Build the namespace constraint section for the prompt.

    Args:
        component_namespace: Required namespace for this component.
        sibling_namespaces: Other component namespaces (for reference only).
    """
    if not component_namespace:
        return ""
    lines = [
        f"The required namespace for this component is: `{component_namespace}`",
        f'All classes, interfaces, and enums MUST use module = "{component_namespace}".',
    ]
    if sibling_namespaces:
        lines.append(
            "\nOther component namespaces (for reference, do NOT use as module):"
        )
        for ns in sibling_namespaces:
            lines.append(f"  - {ns}")
    return "\n".join(lines)
