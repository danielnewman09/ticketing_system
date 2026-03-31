"""Graph post-processing: member collapsing and namespace grouping."""

from __future__ import annotations

from backend.db.neo4j_queries._node_builders import (
    _COLLAPSIBLE_KINDS,
    _OWNER_KINDS,
    _VISIBILITY_PREFIX,
)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _dedup_by_name(members: list[dict]) -> list[dict]:
    """Keep only the first member with each name (removes overloads)."""
    seen: set[str] = set()
    out: list[dict] = []
    for m in members:
        if m["name"] not in seen:
            seen.add(m["name"])
            out.append(m)
    return out


def _fetch_component_namespaces() -> dict[str, str]:
    """Fetch Component namespace -> name mapping from the SQLite database.

    Returns ``{namespace: component_name}`` for all components with a
    namespace defined.
    """
    try:
        from backend.db import get_session
        from backend.db.models.components import Component
        with get_session() as session:
            return {
                c.namespace: c.name
                for c in session.query(Component).all()
                if c.namespace
            }
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Member collapsing
# ---------------------------------------------------------------------------

# Map codebase member kinds to design-intent kinds for grouping
_KIND_NORMALIZE = {
    "variable": "attribute",
    "function": "method",
    "friend": "attribute",
    "enum": "attribute",
    "typedef": "attribute",
}

_CONTAINMENT_RELS = {"COMPOSES", "CONTAINS"}


def _collect_collapsible(
    nodes: list[dict],
    edges: list[dict],
) -> tuple[dict[str, dict[str, list[dict]]], set[str], set[str]]:
    """Walk edges and identify members to fold into their owner nodes.

    Returns ``(collapsed, remove_node_ids, remove_edge_ids)`` where
    *collapsed* maps ``owner_id -> {kind -> [member_dicts]}``.
    """
    node_by_id: dict[str, dict] = {n["data"]["id"]: n for n in nodes}
    collapsed: dict[str, dict[str, list[dict]]] = {}
    remove_node_ids: set[str] = set()
    remove_edge_ids: set[str] = set()

    for e in edges:
        d = e["data"]
        if d["label"] not in _CONTAINMENT_RELS:
            continue
        target = node_by_id.get(d["target"])
        if target is None:
            continue
        td = target["data"]
        if td["kind"] not in _COLLAPSIBLE_KINDS:
            continue
        owner = node_by_id.get(d["source"])
        if owner is None or owner["data"]["kind"] not in _OWNER_KINDS:
            continue

        # For dependency nodes, only show public API
        if td.get("layer") == "dependency" and td.get("visibility") in ("private", "protected"):
            remove_node_ids.add(d["target"])
            remove_edge_ids.add(d["id"])
            continue

        norm_kind = _KIND_NORMALIZE.get(td["kind"], td["kind"])
        collapsed.setdefault(d["source"], {}).setdefault(norm_kind, []).append({
            "name": td["label"],
            "type_signature": td.get("type_signature", ""),
            "visibility": td.get("visibility", ""),
            "qualified_name": td.get("qualified_name", ""),
            "layer": td.get("layer", ""),
        })
        remove_node_ids.add(d["target"])
        remove_edge_ids.add(d["id"])

    return collapsed, remove_node_ids, remove_edge_ids


def _format_compartment(
    members: list[dict],
    is_dependency: bool,
    suffix: str = "",
) -> list[str]:
    """Format one UML compartment (attributes or methods).

    *suffix* is appended to the name (e.g. ``"()"`` for methods).
    Returns the formatted lines (without a leading separator).
    """
    if is_dependency:
        members = _dedup_by_name(members)
    members.sort(key=lambda m: m["name"])
    lines: list[str] = []
    for m in members:
        vis = _VISIBILITY_PREFIX.get(m["visibility"], " ")
        sig = f": {m['type_signature']}" if m["type_signature"] else ""
        lines.append(f"{vis} {m['name']}{suffix}{sig}")
    return lines


def _build_uml_label(
    class_name: str,
    by_kind: dict[str, list[dict]],
    is_dependency: bool,
) -> tuple[str, int]:
    """Format a PlantUML-style compartment label for a class node.

    Returns ``(label_string, member_count)``.
    """
    separator = "\u2500" * max(len(class_name), 10)
    lines = [class_name]

    attrs = by_kind.get("attribute", [])
    attr_lines = _format_compartment(attrs, is_dependency) if attrs else []
    if attr_lines:
        lines.append(separator)
        lines.extend(attr_lines)

    methods = by_kind.get("method", [])
    method_lines = _format_compartment(methods, is_dependency, "()") if methods else []
    if method_lines:
        lines.append(separator)
        lines.extend(method_lines)

    return "\n".join(lines), len(attr_lines) + len(method_lines)


def _collapse_members(
    nodes: list[dict],
    edges: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Collapse attributes and methods into their owning class/interface nodes.

    Members linked via COMPOSES or CONTAINS are removed as separate graph
    nodes and folded into the parent's label as a PlantUML-style
    compartment list.
    """
    node_by_id: dict[str, dict] = {n["data"]["id"]: n for n in nodes}
    collapsed, remove_node_ids, remove_edge_ids = _collect_collapsible(nodes, edges)

    if not collapsed:
        return nodes, edges

    # Also remove edges that reference a removed member node
    for e in edges:
        d = e["data"]
        if d["source"] in remove_node_ids or d["target"] in remove_node_ids:
            remove_edge_ids.add(d["id"])

    # Build UML-style compound labels
    for owner_id, by_kind in collapsed.items():
        od = node_by_id[owner_id]["data"]
        is_dependency = od.get("layer") == "dependency"
        label, member_count = _build_uml_label(od["label"], by_kind, is_dependency)
        od["label"] = label
        od["has_members"] = "true"
        od["member_count"] = member_count

    out_nodes = [n for n in nodes if n["data"]["id"] not in remove_node_ids]
    out_edges = [e for e in edges if e["data"]["id"] not in remove_edge_ids]
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
    """If *ns_qn* has a ``::`` parent, ensure it exists and return its ID."""
    if "::" not in ns_qn:
        return None
    parent_ns = ns_qn.rsplit("::", 1)[0]
    return _ensure_namespace_node(nodes, synth_ns, parent_ns, label_source, layer)


def _find_existing_module(nodes: list[dict], ns_qn: str) -> dict | None:
    """Return the data dict of an existing module node matching *ns_qn*."""
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
    """Create or reuse a namespace container node.

    *label_source* is a ``{namespace: display_name}`` dict (Component map)
    or ``None`` to derive the label from the last segment of *ns_qn*.

    Returns the node ID, or ``None`` if *label_source* is provided but
    does not contain *ns_qn*.
    """
    if ns_qn in synth_ns:
        return synth_ns[ns_qn]

    if label_source is not None and ns_qn not in label_source:
        return None

    display_name = (
        label_source[ns_qn] if label_source is not None
        else ns_qn.rsplit("::", 1)[-1]
    )

    existing = _find_existing_module(nodes, ns_qn)
    if existing is not None:
        existing["is_namespace"] = "true"
        existing["label"] = display_name
        synth_ns[ns_qn] = existing["id"]
        parent_id = _resolve_parent_ns(nodes, synth_ns, ns_qn, label_source, layer)
        if parent_id:
            existing["parent"] = parent_id
        return existing["id"]

    # No existing node — create a synthetic one
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


def _assign_explicit_parents(
    nodes: list[dict],
    edges: list[dict],
) -> tuple[list[dict], set[str]]:
    """Pass 1: convert explicit module COMPOSES edges into parent fields.

    Returns ``(pruned_edges, assigned_node_ids)``.
    """
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
    """Return the most-specific namespace that *qn* belongs to, or ``None``."""
    for ns in sorted_ns:
        if qn.startswith(ns + "::") or qn == ns:
            return ns
    return None


def _assign_component_parents(
    nodes: list[dict],
    assigned: set[str],
    synth_ns: dict[str, str],
) -> None:
    """Pass 2: assign namespace parents using Component namespaces."""
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
    nodes: list[dict],
    assigned: set[str],
    synth_ns: dict[str, str],
) -> None:
    """Pass 3: infer namespace parents from qualified_name prefixes for as-built nodes."""
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


def _assign_namespace_parents(
    nodes: list[dict],
    edges: list[dict],
) -> tuple[list[dict], list[dict]]:
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
