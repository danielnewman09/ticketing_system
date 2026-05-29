"""Graph post-processing: member collapsing and namespace grouping for Cytoscape.

Member label formatting uses a PlantUML-inspired style with:
- UML stereotypes (\u00abclass\u00bb, \u00abinterface\u00bb, \u00abenumeration\u00bb)
- Visibility prefixes (+ public, # protected, - private)
- Function argument lists shown inline
- Inline type-origin markers: \u25cf builtin, \u25c6 linked design, \u25b8 dependency
- Color-coded member-kind hints embedded in member data
- Separator lines using box-drawing characters
- Grouping: attributes \u2192 methods within each visibility compartment
"""

from __future__ import annotations

_COLLAPSIBLE_KINDS = {"attribute", "method", "variable", "function", "friend", "enum", "typedef", "enum_value", "class", "interface", "struct"}
_OWNER_KINDS = {"class", "interface", "enum", "struct"}
_VISIBILITY_PREFIX = {"private": "-", "protected": "#", "public": "+"}

# Canonical order for visibility groups in UML labels
_VISIBILITY_ORDER = ["public", "protected", "private"]

# Canonical order for member kinds within a visibility group
_KIND_ORDER = {"attribute": 0, "method": 1, "enum_value": 2}

# HTML label color scheme — used by the cytoscape-node-html-label extension
_MEMBER_COLORS = {
    "stereotype": "#a0aec0",    # muted gray-blue for <<class>> etc.
    "classname": "#f7fafc",     # bright white for class name (overridden by status)
    "separator": "#4a5568",     # muted gray for ─── lines
    "vis_public": "#68d391",    # green for +
    "vis_protected": "#fbd38d", # amber for #
    "vis_private": "#fc8181",    # red for -
    "builtin_marker": "#63b3ed", # blue for ●
    "linked_marker": "#d69e2e",  # gold for ◆
    "dep_marker": "#4fd1c5",    # teal for ▸
    "type_sig": "#a0aec0",      # gray for type signature text
    "method_name": "#9ae6b4",   # green for method names
    "attr_name": "#fbd38d",     # amber for attribute names
    "enum_val": "#a0aec0",      # gray for enum values
    "args": "#718096",          # dimmer gray for argument text
}

# Status-based colors for class names and borders
_STATUS_COLORS_HTML = {
    "new": "#6ee7b7",      # bright green (design intent, not yet implemented)
    "implemented": "#93c5fd",  # bright blue (exists in codebase)
    "modified": "#fcd34d",    # bright amber (changed design)
    "deleted": "#fca5a5",     # bright red (removed design)
    "": "#f7fafc",           # default white
}

# Kind-colored inner border colors for UML boxes.
# Used by _build_uml_html to render the inset box-shadow.
KIND_BORDER_COLORS = {
    "class": "#4a90d9",
    "struct": "#5b9bd5",
    "interface": "#9b59b6",
    "enum": "#e74c3c",
}


def _format_member_html(m: dict, suffix: str = "") -> str:
    """Format a single member as an HTML span with colored elements.

    Produces: <span class="vis">+ </span><span class="name">name</span><span class="args">(args)</span><span class="type">: ● Type</span>
    """
    import html as html_mod

    mc = _MEMBER_COLORS
    vis = _VISIBILITY_PREFIX.get(m["visibility"], " ")
    vis_color = mc.get(f"vis_{m.get('visibility', 'public')}", mc["vis_public"])
    vis_html = f'<span style="color:{vis_color}">{html_mod.escape(vis)}</span>'

    kind = m.get("_kind", "")
    name = html_mod.escape(m["name"])
    name_color = mc["method_name"] if kind == "method" else mc["attr_name"] if kind == "attribute" else mc["enum_val"]
    name_html = f'<span style="color:{name_color}">{name}</span>'

    args = m.get("argsstring", "")
    if args and suffix == "()":
        suffix = html_mod.escape(args)
    else:
        suffix = html_mod.escape(suffix) if suffix else ""
    args_html = f'<span style="color:{mc["args"]}">{suffix}</span>' if suffix else ""

    type_sig = m.get("type_signature", "")
    marker = _type_origin_marker(type_sig, m.get("layer", ""))
    if type_sig:
        marker_color = mc["builtin_marker"] if marker == "\u25cf " else mc["dep_marker"] if marker == "\u25b8 " else mc["linked_marker"]
        marker_html = f'<span style="color:{marker_color}">{html_mod.escape(marker)}</span>'
        type_html = f'<span style="color:{mc["type_sig"]}">{html_mod.escape(type_sig)}</span>'
        type_part = f': {marker_html}{type_html}'
    else:
        type_part = ""

    return f'{vis_html} {name_html}{args_html}{type_part}'


def _build_uml_html(
    class_name: str, by_kind: dict[str, list[dict]], is_dependency: bool, *, owner_kind: str = "", change_status: str = ""
) -> str:
    """Build a colored HTML label for the cytoscape-node-html-label extension.

    Produces a div with styled spans for each member line, using the
    _MEMBER_COLORS palette for visual distinction.

    change_status colors the class/enumeration name to indicate design status.
    """
    import html as html_mod

    mc = _MEMBER_COLORS
    name_color = _STATUS_COLORS_HTML.get(change_status, mc["classname"])
    lines = []

    # Stereotype
    _STEREOTYPES = {
        "enum": "\u00ABenumeration\u00BB",
        "interface": "\u00ABinterface\u00BB",
        "class": "\u00ABclass\u00BB",
    }
    stereotype = _STEREOTYPES.get(owner_kind, "")
    if stereotype:
        lines.append(f'<div style="color:{mc["stereotype"]};font-size:9px;text-align:center">{html_mod.escape(stereotype)}</div>')

    # Class name
    lines.append(f'<div style="color:{name_color};font-weight:bold;text-align:center">{html_mod.escape(class_name)}</div>')

    # Collect all members
    all_members: list[dict] = []
    for kind, members in by_kind.items():
        suffix = "()" if kind == "method" else ""
        for m in members:
            all_members.append({**m, "_kind": kind, "_suffix": suffix})

    if is_dependency:
        all_members = _dedup_by_name(all_members)

    # Group by visibility
    visibility_groups: dict[str, list[dict]] = {}
    for m in all_members:
        vis = m.get("visibility", "") or "public"
        if vis not in _VISIBILITY_ORDER:
            vis = "public"
        visibility_groups.setdefault(vis, []).append(m)

    separator_html = f'<hr style="border:none;border-top:1px solid {mc["separator"]};margin:2px 0">'
    thin_sep_html = f'<hr style="border:none;border-top:1px dashed {mc["separator"]};margin:1px 0">'

    total_members = 0
    for vis in _VISIBILITY_ORDER:
        group = visibility_groups.get(vis, [])
        if not group:
            continue
        enum_vals = [m for m in group if m.get("_kind") == "enum_value"]
        attrs = [m for m in group if m.get("_kind") == "attribute"]
        methods = [m for m in group if m.get("_kind") == "method"]
        enum_vals.sort(key=lambda m: m["name"])
        attrs.sort(key=lambda m: m["name"])
        methods.sort(key=lambda m: m["name"])

        lines.append(separator_html)
        if enum_vals:
            for m in enum_vals:
                lines.append(f'<div>{_format_member_html(m, m.get("_suffix", ""))}</div>')
            total_members += len(enum_vals)
        if attrs:
            for m in attrs:
                lines.append(f'<div>{_format_member_html(m, m.get("_suffix", ""))}</div>')
            total_members += len(attrs)
        if methods and (attrs or enum_vals):
            lines.append(thin_sep_html)
        if methods:
            for m in methods:
                lines.append(f'<div>{_format_member_html(m, m.get("_suffix", ""))}</div>')
            total_members += len(methods)

    if total_members == 0 and all_members:
        lines.append(separator_html)
        m_sorted = sorted(all_members, key=lambda m: (_KIND_ORDER.get(m.get("_kind", ""), 99), m["name"]))
        for m in m_sorted:
            lines.append(f'<div>{_format_member_html(m, m.get("_suffix", ""))}</div>')
        total_members = len(m_sorted)

    kind_border = KIND_BORDER_COLORS.get(owner_kind, "transparent")
    wrapper = (
        f'<div style="'
        f'font-family:JetBrains Mono,monospace;'
        f'font-size:9px;'
        f'line-height:1.3;'
        f'padding:0px;'
        f'white-space:nowrap;'
        f'border-radius:4px;'
        f'outline:2.5px solid {kind_border};'
        f'outline-offset:-2.5px;'
        f'">'
    )
    return wrapper + '\n'.join(lines) + '</div>'
_BUILTIN_TYPES = frozenset({
    "void", "bool", "int", "double", "float", "char", "long", "short",
    "unsigned", "signed", "size_t", "uint8_t", "uint16_t", "uint32_t", "uint64_t",
    "int8_t", "int16_t", "int32_t", "int64_t",
    "std::string", "std::vector", "std::map", "std::set",
    "std::optional", "std::shared_ptr", "std::unique_ptr",
    "std::pair", "std::array", "std::variant",
    "str", "int", "float", "bool", "bytes", "list", "dict", "set",
    "tuple", "Optional", "List", "Dict", "Set", "Any", "None",
})

# Template / parameterized type prefixes
_TEMPLATE_PREFIXES = ("std::", "boost::", "absl::")


def _is_builtin_type(type_sig: str) -> bool:
    """Check if a type signature refers to a builtin / primitive type."""
    if not type_sig:
        return False
    base = type_sig.strip().rstrip("&*").strip()
    # Remove template arguments for std:: types
    if "<" in base:
        base = base[:base.index("<")].strip()
    return base in _BUILTIN_TYPES or any(base.startswith(p) for p in _TEMPLATE_PREFIXES)


def _type_origin_marker(type_sig: str, member_layer: str) -> str:
    """Return an inline marker indicating where a type originates.

    \u25cf  builtin / primitive (e.g. bool, int, std::string)
    \u25c6  linked design type (same-project class/interface/enum)
    \u25b8  dependency / external library type
    (empty) when type information is unavailable
    """
    if not type_sig:
        return ""
    if _is_builtin_type(type_sig):
        return "\u25cf "   # filled circle
    if member_layer == "dependency":
        return "\u25b8 "   # right-pointing triangle
    return "\u25c6 "   # diamond for design-linked types


def _dedup_by_name(members: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for m in members:
        if m["name"] not in seen:
            seen.add(m["name"])
            out.append(m)
    return out


def _fetch_component_namespaces() -> dict[str, str]:
    try:
        from backend.db import get_session
        from backend.db.models.components import Component

        with get_session() as session:
            return {c.namespace: c.name for c in session.query(Component).all() if c.namespace}
    except Exception:
        return {}


_KIND_NORMALIZE = {
    "variable": "attribute",
    "function": "method",
    "friend": "attribute",
    "enum": "attribute",
    "typename": "attribute",
    "typedef": "attribute",
    "enum_value": "enum_value",
    "class": "attribute",
    "interface": "attribute",
    "struct": "attribute",
}

_CONTAINMENT_RELS = {"COMPOSES", "CONTAINS", "AGGREGATES"}

# Kinds that represent design entities which may have their own
# external relationships (DEPENDS_ON, GENERALIZES, etc.).  When
# such a node is aggregated by an owner class AND it has non-
# containment edges, we keep the node visible as an external node
# in addition to showing it collapsed inside the owner's compartment.
_ENTITY_KINDS = {"class", "interface", "enum", "struct"}


def _collect_collapsible(
    nodes: list[dict],
    edges: list[dict],
) -> tuple[dict[str, dict[str, list[dict]]], set[str], set[str], set[str]]:
    """Walk edges and identify members to fold into their owner nodes.

    Returns:
        collapsed: owner_id → {norm_kind → [member_info]}
        remove_node_ids: node IDs to remove from the graph
        remove_edge_ids: edge IDs to remove from the graph
        external_entity_ids: entity node IDs that should be kept visible
            because they have non-containment edges, even though they
            are also collapsed into an owner compartment.
    """
    node_by_id: dict[str, dict] = {n["data"]["id"]: n for n in nodes}
    collapsed: dict[str, dict[str, list[dict]]] = {}
    remove_node_ids: set[str] = set()
    remove_edge_ids: set[str] = set()

    # First pass: identify all containment targets
    containment_targets: set[str] = set()
    for e in edges:
        d = e["data"]
        if d["label"] not in _CONTAINMENT_RELS:
            continue
        target = node_by_id.get(d["target"])
        if target is None:
            continue
        td = target["data"]
        if td.get("kind") not in _COLLAPSIBLE_KINDS:
            continue
        owner = node_by_id.get(d["source"])
        if owner is None or owner["data"].get("kind") not in _OWNER_KINDS:
            continue
        containment_targets.add(d["target"])

    # Second pass: collect collapsible members
    for e in edges:
        d = e["data"]
        if d["label"] not in _CONTAINMENT_RELS:
            continue
        target = node_by_id.get(d["target"])
        if target is None:
            continue
        td = target["data"]
        if td.get("kind") not in _COLLAPSIBLE_KINDS:
            continue
        owner = node_by_id.get(d["source"])
        if owner is None or owner["data"].get("kind") not in _OWNER_KINDS:
            continue

        if td.get("layer") == "dependency" and td.get("visibility") in ("private", "protected"):
            remove_node_ids.add(d["target"])
            remove_edge_ids.add(d["id"])
            continue

        # Entity kinds (class/interface/enum/struct) composed by a
        # non-module owner should NOT be added as member lines in the
        # UML compartment — their typed attributes already convey the
        # reference.  They are still removed from the node list (unless
        # they have external non-COMPOSES edges) and their COMPOSES edge
        # is still removed.
        if td.get("kind") in _ENTITY_KINDS:
            remove_node_ids.add(d["target"])
            remove_edge_ids.add(d["id"])
            continue

        norm_kind = _KIND_NORMALIZE.get(td["kind"], td["kind"])
        collapsed.setdefault(d["source"], {}).setdefault(norm_kind, []).append(
            {
                "name": td["label"],
                "type_signature": td.get("type_signature", ""),
                "argsstring": td.get("argsstring", ""),
                "visibility": td.get("visibility", ""),
                "qualified_name": td.get("qualified_name", ""),
                "layer": td.get("layer", ""),
            }
        )
        remove_node_ids.add(d["target"])
        remove_edge_ids.add(d["id"])

    # Identify entity nodes (class/interface/enum/struct) that have non-
    # containment external edges.  These should remain visible as
    # external nodes so their REFERENCES / DEPENDS_ON / GENERALIZES /
    # etc. edges are shown.
    external_entity_ids: set[str] = set()
    for e in edges:
        d = e["data"]
        if d["label"] in _CONTAINMENT_RELS:
            continue
        # Check if either endpoint is a collapsed entity
        for node_id in (d.get("source", ""), d.get("target", "")):
            if node_id in remove_node_ids and node_id in containment_targets:
                target_node = node_by_id.get(node_id)
                if target_node and target_node["data"].get("kind") in _ENTITY_KINDS:
                    external_entity_ids.add(node_id)

    # Don't remove entity nodes that have external edges
    remove_node_ids -= external_entity_ids

    # COMPOSES is an implicit relationship (like dependency injection)
    # and should not be visible in the graph.  Preserve AGGREGATES and
    # CONTAINS edges to external entity nodes, but NOT COMPOSES.
    for e in edges:
        d = e["data"]
        if d["label"] not in _CONTAINMENT_RELS:
            continue
        if d["label"] == "COMPOSES":
            continue  # COMPOSES is never shown in the graph
        if d["target"] in external_entity_ids:
            remove_edge_ids.discard(d["id"])

    return collapsed, remove_node_ids, remove_edge_ids, external_entity_ids


def _format_member_line(m: dict, suffix: str = "") -> str:
    """Format a single member as a UML-style line with type-origin marker.

    Format:  visibility prefix + name + args + suffix + : type_marker type
    Example: + add(const string& a, const string& b): \u25c6 CalculationResult
    """
    vis = _VISIBILITY_PREFIX.get(m["visibility"], " ")
    args = m.get("argsstring", "")
    # Only show args for methods (suffix already has "()" placeholder)
    if args and suffix == "()":
        suffix = args  # Replace bare () with actual argument list
    type_sig = m.get("type_signature", "")
    marker = _type_origin_marker(type_sig, m.get("layer", ""))
    if type_sig:
        return f"{vis} {m['name']}{suffix}: {marker}{type_sig}"
    return f"{vis} {m['name']}{suffix}"


def _build_uml_label(
    class_name: str, by_kind: dict[str, list[dict]], is_dependency: bool, *, owner_kind: str = ""
) -> tuple[str, int]:
    """Build a UML-style class label with stereotype, visibility grouping,
    and member-kind visual sections.

    Layout:
        \u00abstereotype\u00bb          (if applicable)
        ClassName
        \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500   (attribute section)
        + attr: \u25cf int
        \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500   (method section)
        + method(arg): \u25c6 Result
        \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500   (private section, if any)
        - private_attr: \u25b8 SomeType
    """
    separator = "\u2500" * max(len(class_name) + 2, 12)
    lines = [class_name]

    # Add UML stereotype based on owner kind
    _STEREOTYPES = {
        "enum": "\u00ABenumeration\u00BB",
        "interface": "\u00ABinterface\u00BB",
        "class": "\u00ABclass\u00BB",
    }
    stereotype = _STEREOTYPES.get(owner_kind, "")
    if stereotype:
        lines.insert(0, stereotype)

    # Collect all members, tagging each with its kind for ordering
    all_members: list[dict] = []
    for kind, members in by_kind.items():
        suffix = "()" if kind == "method" else ""
        for m in members:
            all_members.append({**m, "_kind": kind, "_suffix": suffix})

    if is_dependency:
        all_members = _dedup_by_name(all_members)

    # Group members by visibility (public, protected, private)
    visibility_groups: dict[str, list[dict]] = {}
    for m in all_members:
        vis = m.get("visibility", "") or "public"
        if vis not in _VISIBILITY_ORDER:
            vis = "public"
        visibility_groups.setdefault(vis, []).append(m)

    total_members = 0
    for vis in _VISIBILITY_ORDER:
        group = visibility_groups.get(vis, [])
        if not group:
            continue

        # Within each visibility, sub-group by kind: attributes first, then methods
        attrs = [m for m in group if m.get("_kind") == "attribute"]
        methods = [m for m in group if m.get("_kind") == "method"]
        enum_vals = [m for m in group if m.get("_kind") == "enum_value"]

        # Sort each sub-group alphabetically
        attrs.sort(key=lambda m: m["name"])
        methods.sort(key=lambda m: m["name"])
        enum_vals.sort(key=lambda m: m["name"])

        lines.append(separator)

        # Attributes section (for enum, these are enum values)
        if enum_vals:
            for m in enum_vals:
                lines.append(_format_member_line(m, m.get("_suffix", "")))
            total_members += len(enum_vals)

        if attrs:
            # Add kind sub-separator if we also have methods
            for m in attrs:
                lines.append(_format_member_line(m, m.get("_suffix", "")))
            total_members += len(attrs)

        # Methods section with thin sub-separator
        if methods and (attrs or enum_vals):
            lines.append("\u2500" * max(len(class_name) - 2, 8))  # thinner sub-separator
        if methods:
            for m in methods:
                lines.append(_format_member_line(m, m.get("_suffix", "")))
            total_members += len(methods)

    # If there were no visibility groups but we had members, add a single compartment
    if total_members == 0 and all_members:
        lines.append(separator)
        m_sorted = sorted(all_members, key=lambda m: (_KIND_ORDER.get(m.get("_kind", ""), 99), m["name"]))
        for m in m_sorted:
            lines.append(_format_member_line(m, m.get("_suffix", "")))
        total_members = len(m_sorted)

    return "\n".join(lines), total_members


def collapse_members(nodes: list[dict], edges: list[dict]) -> tuple[list[dict], list[dict]]:
    """Collapse members into their owning class/interface/enum nodes.

    Collapses attributes, methods, and enum_values into their owner
    node's label as PlantUML-style compartment lists.  Enum nodes get
    a «enumeration» stereotype.

    Entity nodes (class/interface/enum/struct) composed by a non-module
    owner are NOT added as UML compartment lines — their typed attributes
    (e.g. ``error_signal: CalculationError``) already convey the
    reference, and the REFERENCES edge shows the external relationship.
    COMPOSES edges are never shown in the graph (they are implicit, like
    dependency injection).

    Aggregated entity nodes that have non-COMPOSES external edges
    (REFERENCES, DEPENDS_ON, GENERALIZES, etc.) are kept visible as
    separate nodes so those relationships remain visible in the diagram.

    External edges from fully-collapsed nodes (attributes, methods,
    enum_values) are rerouted to the owner.  For entity nodes kept as
    external, their edges are preserved as-is so they point to/from
    the entity node itself.
    """
    node_by_id: dict[str, dict] = {n["data"]["id"]: n for n in nodes}
    collapsed, remove_node_ids, remove_edge_ids, external_entity_ids = _collect_collapsible(nodes, edges)

    # Entity node IDs whose edges should NOT be rerouted to their owner
    preserved_entity_ids = external_entity_ids

    if not collapsed and not remove_node_ids and not remove_edge_ids:
        return nodes, edges

    # Build mapping from collapsed node id → owner id
    # (derived from containment edges that triggered the collapse).
    # Only fully-collapsed nodes (attributes, methods, enum_values)
    # are mapped.  External entity nodes are NOT mapped — their
    # edges should remain connected to themselves.
    collapse_to_owner: dict[str, str] = {}
    for e in edges:
        d = e["data"]
        if d["label"] not in _CONTAINMENT_RELS:
            continue
        if d["target"] in remove_node_ids and d["source"] not in remove_node_ids:
            collapse_to_owner[d["target"]] = d["source"]

    # Process edges: reroute or preserve, remove internal, deduplicate
    seen_edges: set[tuple[str, str, str]] = set()
    out_edges: list[dict] = []
    for e in edges:
        d = e["data"]
        if d["id"] in remove_edge_ids:
            continue

        src = d.get("source", "")
        tgt = d.get("target", "")

        # For external or entity-composed nodes, keep their edges pointing to
        # themselves (don't reroute to owner) so the external
        # relationship is visible in the diagram.
        if src in preserved_entity_ids:
            new_src = src
        else:
            new_src = collapse_to_owner.get(src, src)

        if tgt in preserved_entity_ids:
            new_tgt = tgt
        else:
            new_tgt = collapse_to_owner.get(tgt, tgt)

        # Self-loop after rerouting → internal relationship, remove
        if new_src == new_tgt:
            continue

        # Deduplicate by (source, target, label)
        key = (new_src, new_tgt, d.get("label", ""))
        if key in seen_edges:
            continue
        seen_edges.add(key)

        d["source"] = new_src
        d["target"] = new_tgt
        out_edges.append(e)

    # Update owner node labels with collapsed members
    for owner_id, by_kind in collapsed.items():
        od = node_by_id[owner_id]["data"]
        is_dependency = od.get("layer") == "dependency"
        label, member_count = _build_uml_label(
            od["label"], by_kind, is_dependency, owner_kind=od.get("kind", "")
        )
        html_label = _build_uml_html(
            od["label"], by_kind, is_dependency, owner_kind=od.get("kind", ""),
            change_status=od.get("change_status", "")
        )
        od["label"] = label
        od["html_label"] = html_label
        od["has_members"] = "true"
        od["member_count"] = member_count

    out_nodes = [n for n in nodes if n["data"]["id"] not in remove_node_ids]
    return out_nodes, out_edges


# ---------------------------------------------------------------------------
# Namespace grouping
# ---------------------------------------------------------------------------

_CONTAINABLE = {"class", "interface", "enum", "module", "struct"}


def _resolve_parent_ns(
    nodes: list[dict],
    synth_ns: dict[str, str],
    ns_qn: str,
    label_source: dict[str, str] | None,
    layer: str,
) -> str | None:
    if "::" not in ns_qn:
        return None
    parent_ns = ns_qn.rsplit("::", 1)[0]
    return _ensure_namespace_node(nodes, synth_ns, parent_ns, label_source, layer)


def _find_existing_module(nodes: list[dict], ns_qn: str) -> dict | None:
    for n in nodes:
        d = n["data"]
        if d.get("kind") == "module" and d.get("qualified_name") == ns_qn:
            return d
    return None


def _ensure_namespace_node(
    nodes: list[dict],
    synth_ns: dict[str, str],
    ns_qn: str,
    label_source: dict[str, str] | None,
    layer: str,
) -> str | None:
    if ns_qn in synth_ns:
        return synth_ns[ns_qn]
    if label_source is not None and ns_qn not in label_source:
        return None

    display_name = label_source[ns_qn] if label_source is not None else ns_qn.rsplit("::", 1)[-1]

    existing = _find_existing_module(nodes, ns_qn)
    if existing is not None:
        existing["is_namespace"] = "true"
        existing["label"] = display_name
        synth_ns[ns_qn] = existing["id"]
        parent_id = _resolve_parent_ns(nodes, synth_ns, ns_qn, label_source, layer)
        if parent_id:
            existing["parent"] = parent_id
        return existing["id"]

    node_id = f"ns_{ns_qn}"
    new_node = {
        "data": {
            "id": node_id,
            "label": display_name,
            "qualified_name": ns_qn,
            "kind": "module",
            "description": "",
            "visibility": "",
            "type_signature": "",
            "layer": layer,
            "is_namespace": "true",
        }
    }
    parent_id = _resolve_parent_ns(nodes, synth_ns, ns_qn, label_source, layer)
    if parent_id:
        new_node["data"]["parent"] = parent_id
    nodes.append(new_node)
    synth_ns[ns_qn] = node_id
    return node_id


def _assign_explicit_parents(nodes: list[dict], edges: list[dict]) -> tuple[list[dict], set[str]]:
    node_by_id: dict[str, dict] = {n["data"]["id"]: n for n in nodes}
    remove_edge_ids: set[str] = set()
    assigned: set[str] = set()

    for e in edges:
        d = e["data"]
        if d["label"] != "COMPOSES":
            continue
        source = node_by_id.get(d["source"])
        target = node_by_id.get(d["target"])
        if source is None or target is None:
            continue
        if source["data"]["kind"] != "module" or target["data"]["kind"] not in _CONTAINABLE:
            continue
        target["data"]["parent"] = d["source"]
        source["data"]["is_namespace"] = "true"
        remove_edge_ids.add(d["id"])
        assigned.add(d["target"])

    out_edges = [e for e in edges if e["data"]["id"] not in remove_edge_ids]
    return out_edges, assigned


def _match_namespace(qn: str, sorted_ns: list[str]) -> str | None:
    for ns in sorted_ns:
        if qn.startswith(ns + "::") or qn == ns:
            return ns
    return None


def _assign_component_parents(
    nodes: list[dict], assigned: set[str], synth_ns: dict[str, str]
) -> None:
    component_ns = _fetch_component_namespaces()
    if not component_ns:
        return
    sorted_ns = sorted(component_ns.keys(), key=len, reverse=True)
    for n in nodes:
        d = n["data"]
        if d["id"] in assigned or d.get("parent") or d.get("layer") != "design":
            continue
        ns = _match_namespace(d.get("qualified_name", ""), sorted_ns)
        if ns is None:
            continue
        parent_id = _ensure_namespace_node(nodes, synth_ns, ns, component_ns, "design")
        if parent_id and parent_id != d["id"]:
            d["parent"] = parent_id
            assigned.add(d["id"])


def _assign_inferred_parents(
    nodes: list[dict], assigned: set[str], synth_ns: dict[str, str]
) -> None:
    ns_prefixes: dict[str, set[str]] = {}
    node_by_id: dict[str, dict] = {n["data"]["id"]: n for n in nodes}

    for n in nodes:
        d = n["data"]
        if d["id"] in assigned or d.get("parent"):
            continue
        if d.get("layer") != "as-built":
            continue
        qn = d.get("qualified_name", "")
        if "::" not in qn:
            continue
        ns = qn.rsplit("::", 1)[0]
        ns_prefixes.setdefault(ns, set()).add(d["id"])

    for ns_qn, child_ids in ns_prefixes.items():
        parent_id = _ensure_namespace_node(nodes, synth_ns, ns_qn, None, "as-built")
        if parent_id:
            for cid in child_ids:
                node_by_id[cid]["data"]["parent"] = parent_id


def assign_namespace_parents(nodes: list[dict], edges: list[dict]) -> tuple[list[dict], list[dict]]:
    """Group nodes into namespace containers using Cytoscape parents.

    Three passes:
    1. Explicit module COMPOSES edges → parent fields.
    2. Component namespaces → design-intent containers.
    3. Qualified-name prefix inference → as-built containers.
    """
    synth_ns: dict[str, str] = {}
    out_edges, assigned = _assign_explicit_parents(nodes, edges)
    _assign_component_parents(nodes, assigned, synth_ns)
    _assign_inferred_parents(nodes, assigned, synth_ns)
    return nodes, out_edges