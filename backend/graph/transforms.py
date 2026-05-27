"""Graph post-processing: member collapsing and namespace grouping for Cytoscape."""

from __future__ import annotations

_COLLAPSIBLE_KINDS = {"attribute", "method", "variable", "function", "friend", "enum", "typedef", "enum_value", "class", "interface", "struct"}
_OWNER_KINDS = {"class", "interface", "enum", "struct"}
_VISIBILITY_PREFIX = {"private": "-", "protected": "#", "public": "+"}

# Canonical order for visibility groups in UML labels
_VISIBILITY_ORDER = ["public", "protected", "private"]

# Canonical order for member kinds within a visibility group
_KIND_ORDER = {"attribute": 0, "method": 1, "enum_value": 2}


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

        norm_kind = _KIND_NORMALIZE.get(td["kind"], td["kind"])
        collapsed.setdefault(d["source"], {}).setdefault(norm_kind, []).append(
            {
                "name": td["label"],
                "type_signature": td.get("type_signature", ""),
                "visibility": td.get("visibility", ""),
                "qualified_name": td.get("qualified_name", ""),
                "layer": td.get("layer", ""),
            }
        )
        remove_node_ids.add(d["target"])
        remove_edge_ids.add(d["id"])

    # Identify entity nodes (class/interface/struct) that have non-
    # containment external edges.  These should remain visible as
    # external nodes so their DEPENDS_ON / GENERALIZES / etc. edges
    # are shown, even though they're also collapsed into an owner.
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

    # Identify entity nodes that are composed by another non-module entity.
    # When a design entity (class, interface, enum, struct) is composed
    # by another design entity (not a module), the composition relationship
    # is meaningful at the entity level and the target should remain visible
    # as a separate node in the graph alongside the collapsed representation.
    entity_composed_by_owner: set[str] = set()
    for e in edges:
        d = e["data"]
        if d["label"] not in _CONTAINMENT_RELS:
            continue
        target = node_by_id.get(d["target"])
        source = node_by_id.get(d["source"])
        if target is None or source is None:
            continue
        if source["data"].get("kind") == "module":
            continue  # module containment → parent, not composition
        if target["data"].get("kind") in _ENTITY_KINDS:
            entity_composed_by_owner.add(d["target"])

    # Don't remove entity nodes composed by another entity
    remove_node_ids -= entity_composed_by_owner

    # Don't remove containment edges to entity-composed nodes — the
    # COMPOSES/AGGREGATES edge itself represents a meaningful relationship
    # that should be visible in the graph.
    for e in edges:
        d = e["data"]
        if d["label"] not in _CONTAINMENT_RELS:
            continue
        if d["target"] in entity_composed_by_owner:
            remove_edge_ids.discard(d["id"])

    # Also preserve containment edges to external entity nodes
    for e in edges:
        d = e["data"]
        if d["label"] not in _CONTAINMENT_RELS:
            continue
        if d["target"] in external_entity_ids:
            remove_edge_ids.discard(d["id"])

    return collapsed, remove_node_ids, remove_edge_ids, external_entity_ids, entity_composed_by_owner


def _format_member_line(m: dict, suffix: str = "") -> str:
    """Format a single member as a UML-style line: visibility prefix + name + suffix + type."""
    vis = _VISIBILITY_PREFIX.get(m["visibility"], " ")
    sig = f": {m['type_signature']}" if m["type_signature"] else ""
    return f"{vis} {m['name']}{suffix}{sig}"


def _build_uml_label(
    class_name: str, by_kind: dict[str, list[dict]], is_dependency: bool, *, owner_kind: str = ""
) -> tuple[str, int]:
    """Build a UML-style class label grouped by visibility.

    Produces a label where public (+) members are above the divider
    and private (-) / protected (#) members are below it:

        ────────────
        + public_method()
        + public_attr: string
        ────────────
        - private_attr: int
        # protected_method(): bool
    """
    separator = "\u2500" * max(len(class_name), 10)
    lines = [class_name]

    # Add UML stereotype for enums
    if owner_kind == "enum":
        lines.insert(0, "\u00ABenumeration\u00BB")

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
        # Sort within group: kind order first, then name
        group.sort(key=lambda m: (_KIND_ORDER.get(m.get("_kind", ""), 99), m["name"]))
        lines.append(separator)
        for m in group:
            lines.append(_format_member_line(m, m.get("_suffix", "")))
        total_members += len(group)

    # If there were no visibility groups but we had members, add a single compartment
    if total_members == 0 and all_members:
        lines.append(separator)
        for m in all_members:
            m_sorted = sorted(all_members, key=lambda m: (_KIND_ORDER.get(m.get("_kind", ""), 99), m["name"]))
        for m in m_sorted:
            lines.append(_format_member_line(m, m.get("_suffix", "")))
        total_members = len(m_sorted)

    return "\n".join(lines), total_members


def collapse_members(nodes: list[dict], edges: list[dict]) -> tuple[list[dict], list[dict]]:
    """Collapse members into their owning class/interface/enum nodes.

    Collapses attributes, methods, enum_values, and aggregated classes
    into their owner node's label as PlantUML-style compartment lists.
    Enum nodes get a «enumeration» stereotype.  Aggregated classes show
    as typed attributes in the owner's compartment.

    Aggregated entity nodes (class/interface/struct) that also have
    non-containment external edges (DEPENDS_ON, GENERALIZES, etc.)
    are shown BOTH inside the owner's compartment AND as separate
    external nodes, so their external relationships remain visible in
    the diagram.

    External edges from fully-collapsed nodes (attributes, methods,
    enum_values) are rerouted to the owner.  For entity nodes kept as
    external, their edges are preserved as-is so they point to/from
    the entity node itself.
    """
    node_by_id: dict[str, dict] = {n["data"]["id"]: n for n in nodes}
    collapsed, remove_node_ids, remove_edge_ids, external_entity_ids, entity_composed_ids = _collect_collapsible(nodes, edges)

    # Combined set of entity node IDs that should NOT be rerouted to their owner
    preserved_entity_ids = external_entity_ids | entity_composed_ids

    if not collapsed:
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
        od["label"] = label
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