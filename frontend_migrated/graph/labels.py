"""UML label builders for Cytoscape node rendering.

Extracted from backend/graph/transforms.py for use by frontend/graph/format.py.
This module has no dependencies on backend or codegraph — stdlib only.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Kinds that can be collapsed into a UML compartment inside an owner.
_COLLAPSIBLE_KINDS = {
    "attribute", "method", "variable", "function", "friend",
    "enum", "typedef", "enum_value", "class", "interface", "struct",
}

# Kinds that own collapsible members.
_OWNER_KINDS = {"class", "interface", "enum", "struct"}

# Visibility prefix mapping.
_VISIBILITY_PREFIX = {"private": "-", "protected": "#", "public": "+"}

# Canonical order for visibility groups in UML labels.
_VISIBILITY_ORDER = ["public", "protected", "private"]

# Canonical order for member kinds within a visibility group.
_KIND_ORDER = {"attribute": 0, "method": 1, "enum_value": 2}

# HTML label color scheme — used by the cytoscape-node-html-label extension.
_MEMBER_COLORS = {
    "stereotype": "#a0aec0",      # muted gray-blue for <<class>> etc.
    "classname": "#f7fafc",       # bright white for class name (overridden by status)
    "separator": "#4a5568",       # muted gray for ─── lines
    "vis_public": "#68d391",      # green for +
    "vis_protected": "#fbd38d",   # amber for #
    "vis_private": "#fc8181",     # red for -
    "builtin_marker": "#63b3ed",  # blue for ●
    "linked_marker": "#d69e2e",   # gold for ◆
    "dep_marker": "#4fd1c5",      # teal for ▸
    "type_sig": "#a0aec0",        # gray for type signature text
    "method_name": "#9ae6b4",     # green for method names
    "attr_name": "#fbd38d",      # amber for attribute names
    "enum_val": "#a0aec0",       # gray for enum values
    "args": "#718096",           # dimmer gray for argument text
}

# Status-based colors for class names and borders.
_STATUS_COLORS_HTML = {
    "new": "#6ee7b7",         # bright green (design intent, not yet implemented)
    "implemented": "#93c5fd", # bright blue (exists in codebase)
    "modified": "#fcd34d",    # bright amber (changed design)
    "deleted": "#fca5a5",     # bright red (removed design)
    "": "#f7fafc",            # default white
}

# Kind-colored inner border colors for UML boxes.
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

# Builtin / primitive types for type-origin markers.
_BUILTIN_TYPES = frozenset({
    "void", "bool", "int", "double", "float", "char", "long", "short",
    "unsigned", "signed", "size_t", "uint8_t", "uint16_t", "uint32_t",
    "uint64_t", "int8_t", "int16_t", "int32_t", "int64_t",
    # std::string, std::vector, etc. are NO LONGER builtin — they resolve to
    # dependency nodes via alias_lookup and TYPE_ARGUMENT edges.
    "str", "int", "float", "bool", "bytes", "list", "dict", "set",
    "tuple", "Optional", "List", "Dict", "Set", "Any", "None",
})

# Template / parameterized type prefixes.
_TEMPLATE_PREFIXES = ("std::", "boost::", "absl::")

# Kinds that represent design entities — skipped in member compartments.
_ENTITY_KINDS = {"class", "interface", "enum", "struct"}

# Map codegraph MemberNode.kind → canonical UML compartment group.
_CODEGRAPH_KIND_GROUP = {
    "variable": "attribute",
    "function": "method",
    "method": "method",
    "enumvalue": "enum_value",
    "define": "attribute",
}

# Map codegraph CompoundNode.kind → stereotype key for _build_uml_html.
_CODEGRAPH_STEREOTYPE_MAP = {
    "class": "class",
    "struct": "class",
    "template_class": "class_template",
    "interface": "interface",
    "abstract_class": "class",
    "enum": "enum",
    "enum_class": "enum",
    "union": "class",
}

# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------


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

    ●  builtin / primitive (e.g. bool, int, std::string)
    ◆  linked design type (same-project class/interface/enum)
    ▸  dependency / external library type
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


def _format_member_html(m: dict, suffix: str = "") -> str:
    """Format a single member as an HTML span with colored elements."""
    import html as html_mod

    mc = _MEMBER_COLORS
    vis = _VISIBILITY_PREFIX.get(m["visibility"], " ")
    vis_color = mc.get(f"vis_{m.get('visibility', 'public')}", mc["vis_public"])
    vis_html = f'<span style="color:{vis_color}">{html_mod.escape(vis)}</span>'

    kind = m.get("_kind", "")
    name = html_mod.escape(m["name"])
    name_color = (
        mc["method_name"] if kind == "method"
        else mc["attr_name"] if kind == "attribute"
        else mc["enum_val"]
    )
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
        marker_color = (
            mc["builtin_marker"] if marker == "\u25cf "
            else mc["dep_marker"] if marker == "\u25b8 "
            else mc["linked_marker"]
        )
        marker_html = f'<span style="color:{marker_color}">{html_mod.escape(marker)}</span>'
        type_html = f'<span style="color:{mc["type_sig"]}">{html_mod.escape(type_sig)}</span>'
        type_part = f': {marker_html}{type_html}'
    else:
        type_part = ""

    return f'{vis_html} {name_html}{args_html}{type_part}'


def _build_uml_html(
    class_name: str,
    by_kind: dict[str, list[dict]],
    is_dependency: bool,
    *,
    owner_kind: str = "",
    change_status: str = "",
) -> str:
    """Build a colored HTML label for the cytoscape-node-html-label extension."""
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
        lines.append(
            f'<div style="color:{mc["stereotype"]};font-size:9px;text-align:center">'
            f'{html_mod.escape(stereotype)}</div>'
        )

    # Class name
    lines.append(
        f'<div style="color:{name_color};font-weight:bold;text-align:center">'
        f'{html_mod.escape(class_name)}</div>'
    )

    # Collect all members
    all_members: list[dict] = []
    for kind, members in by_kind.items():
        suf = "()" if kind == "method" else ""
        for m in members:
            all_members.append({**m, "_kind": kind, "_suffix": suf})

    if is_dependency:
        all_members = _dedup_by_name(all_members)

    # Group by visibility
    visibility_groups: dict[str, list[dict]] = {}
    for m in all_members:
        vis = m.get("visibility", "") or "public"
        if vis not in _VISIBILITY_ORDER:
            vis = "public"
        visibility_groups.setdefault(vis, []).append(m)

    separator_html = (
        f'<hr style="border:none;border-top:1px solid {mc["separator"]};margin:2px 0">'
    )
    thin_sep_html = (
        f'<hr style="border:none;border-top:1px dashed {mc["separator"]};margin:1px 0">'
    )

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
        m_sorted = sorted(
            all_members,
            key=lambda m: (_KIND_ORDER.get(m.get("_kind", ""), 99), m["name"]),
        )
        for m in m_sorted:
            lines.append(f'<div>{_format_member_html(m, m.get("_suffix", ""))}</div>')
        total_members = len(m_sorted)

    kind_border = KIND_BORDER_COLORS.get(owner_kind, "transparent")
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
    return wrapper + "\n".join(lines) + "</div>"


def _format_member_line(m: dict, suffix: str = "") -> str:
    """Format a single member as a UML-style line with type-origin marker."""
    vis = _VISIBILITY_PREFIX.get(m["visibility"], " ")
    args = m.get("argsstring", "")
    if args and suffix == "()":
        suffix = args
    type_sig = m.get("type_signature", "")
    marker = _type_origin_marker(type_sig, m.get("layer", ""))
    if type_sig:
        return f"{vis} {m['name']}{suffix}: {marker}{type_sig}"
    return f"{vis} {m['name']}{suffix}"


def _build_uml_label(
    class_name: str,
    by_kind: dict[str, list[dict]],
    is_dependency: bool,
    *,
    owner_kind: str = "",
) -> tuple[str, int]:
    """Build a UML-style class label with stereotype, visibility grouping,
    and member-kind visual sections.

    Returns (label_text, member_count).
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
        suf = "()" if kind == "method" else ""
        for m in members:
            all_members.append({**m, "_kind": kind, "_suffix": suf})

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

        attrs = [m for m in group if m.get("_kind") == "attribute"]
        methods = [m for m in group if m.get("_kind") == "method"]
        enum_vals = [m for m in group if m.get("_kind") == "enum_value"]
        attrs.sort(key=lambda m: m["name"])
        methods.sort(key=lambda m: m["name"])
        enum_vals.sort(key=lambda m: m["name"])

        lines.append(separator)

        if enum_vals:
            for m in enum_vals:
                lines.append(_format_member_line(m, m.get("_suffix", "")))
            total_members += len(enum_vals)

        if attrs:
            for m in attrs:
                lines.append(_format_member_line(m, m.get("_suffix", "")))
            total_members += len(attrs)

        if methods and (attrs or enum_vals):
            lines.append("\u2500" * max(len(class_name) - 2, 8))

        if methods:
            for m in methods:
                lines.append(_format_member_line(m, m.get("_suffix", "")))
            total_members += len(methods)

    if total_members == 0 and all_members:
        lines.append(separator)
        m_sorted = sorted(
            all_members,
            key=lambda m: (_KIND_ORDER.get(m.get("_kind", ""), 99), m["name"]),
        )
        for m in m_sorted:
            lines.append(_format_member_line(m, m.get("_suffix", "")))
        total_members = len(m_sorted)

    return "\n".join(lines), total_members