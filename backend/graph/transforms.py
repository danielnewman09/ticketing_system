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
    "class_template": "#9b59b6",  # Purple border for templates
}

# Status-colored outer border colors for UML boxes.
STATUS_BORDER_COLORS = {
    "new": "#10b981",
    "implemented": "#3b82f6",
    "modified": "#f59e0b",
    "deleted": "#ef4444",
    "": "#4a5568",  # neutral gray default
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
        "class_template": "\u00ABclass template\u00BB",
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
    status_border = STATUS_BORDER_COLORS.get(change_status, "#4a5568")
    wrapper = (
        f'<div style="'
        f'font-family:JetBrains Mono,monospace;'
        f'font-size:9px;'
        f'line-height:1.3;'
        f'padding:2px;'
        f'white-space:nowrap;'
        f'border-radius:5px;'
        f'outline:3px solid {kind_border};'
        f'outline-offset:-2px;'
        f'">'
    )
    return wrapper + '\n'.join(lines) + '</div>'
_BUILTIN_TYPES = frozenset({
    "void", "bool", "int", "double", "float", "char", "long", "short",
    "unsigned", "signed", "size_t", "uint8_t", "uint16_t", "uint32_t", "uint64_t",
    "int8_t", "int16_t", "int32_t", "int64_t",
    # std::string, std::vector, etc. are NO LONGER builtin — they resolve to
    # dependency nodes via alias_lookup and TYPE_ARGUMENT edges.
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

# Kinds that represent design entities which may have their own
# external relationships (DEPENDS_ON, GENERALIZES, etc.).  When
# such a node is aggregated by an owner class AND it has non-
# containment edges, we keep the node visible as an external node
# in addition to showing it collapsed inside the owner's compartment.
_ENTITY_KINDS = {"class", "interface", "enum", "struct"}


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
        "class_template": "\u00ABclass template\u00BB",
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
