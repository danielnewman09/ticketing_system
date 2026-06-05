"""Frontend Cytoscape transform — LayerGraph → Cytoscape dict.

Walks the CompositeEntry tree to produce Cytoscape {nodes, edges},
replacing the old DesignRepository → OntologyGraph → format_ontology_graph
pipeline.  Also provides in-memory filtering on LayerGraph before
conversion.
"""

from __future__ import annotations

import logging

from codegraph.graph import CompositeEntry, LayerGraph

from frontend.graph.labels import (
    _CODEGRAPH_KIND_GROUP,
    _CODEGRAPH_STEREOTYPE_MAP,
    _ENTITY_KINDS,
    _build_uml_html,
    _build_uml_label,
)

log = logging.getLogger(__name__)

# Namespace-like kinds whose children get parented in the Cytoscape tree.
_NAMESPACE_KINDS = {"namespace", "module", "package"}

# Compound-like kinds that are rendered as separate Cytoscape nodes
# (as opposed to leaf members which are collapsed into UML labels).
_COMPOUND_KINDS = {"class", "struct", "interface", "enum", "union", "template_class",
                    "abstract_class", "enum_class", "module"}


def _is_compound(node) -> bool:
    """Return True if the node represents a compound (class, struct, etc.)."""
    return getattr(node, "kind", "") in _COMPOUND_KINDS


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def layer_graph_to_cytoscape(graph: LayerGraph) -> dict:
    """Walk CompositeEntry tree → Cytoscape {nodes, edges}.

    This is the new replacement for ``format_ontology_graph()``.
    """
    nodes: list[dict] = []
    edges: list[dict] = []
    seen: set[str] = set()

    for entry in graph.entries.values():
        _walk_entry(entry, parent_id=None, nodes=nodes, edges=edges, seen=seen)

    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# Tree walk
# ---------------------------------------------------------------------------


def _collect_skipped_member_refs(entry: CompositeEntry) -> list[tuple[str, str, str]]:
    """Collect references from leaf members that are collapsed into the UML label.

    These members won't be walked by _walk_entry, so their references need
    to be collected here.  Only collects from immediate leaf children —
    entity-kind and namespace children will be walked separately.
    """
    refs: list[tuple[str, str, str]] = []
    for _type_key, children in entry.children.items():
        for _child_key, child_entry in children.items():
            child_kind = getattr(child_entry.node, "kind", "")
            # If this child will be walked as a separate node, skip it
            if child_kind in _ENTITY_KINDS or child_kind in _NAMESPACE_KINDS or _is_compound(child_entry.node):
                continue
            # This is a collapsed member — collect its references
            child_qname = getattr(child_entry.node, "qualified_name", "") or getattr(child_entry.node, "name", "")
            for rel_type, tgt_key, tgt_type in child_entry.references:
                refs.append((child_qname, tgt_key, rel_type))
            # Also recurse into member's children (e.g. nested locals)
            refs.extend(_collect_skipped_member_refs(child_entry))
    return refs


def _walk_entry(
    entry: CompositeEntry,
    parent_id: str | None,
    nodes: list[dict],
    edges: list[dict],
    seen: set[str],
) -> None:
    """Recursively walk a CompositeEntry, emitting Cytoscape nodes and edges.

    Leaf members (methods, attributes, enum values, etc.) are NOT emitted
    as separate Cytoscape nodes — they are collapsed into their parent
    compound's UML label.  However, references from collapsed members
    ARE emitted as edges.
    """
    node = entry.node
    qname = getattr(node, "qualified_name", None) or getattr(node, "name", "")
    if qname in seen:
        return
    seen.add(qname)

    # Build the Cytoscape node
    cy_node = _build_node(entry, parent_id=parent_id)
    nodes.append(cy_node)

    # Emit this entry's own references
    for rel_type, target_key, target_type in entry.references:
        edges.append(_build_edge(qname, target_key, rel_type))

    # Emit references from collapsed members (they won't be walked)
    for src, tgt, rel in _collect_skipped_member_refs(entry):
        edges.append(_build_edge(src, tgt, rel))

    # Recurse into composed children that should appear as Cy nodes.
    for _type_key, children in entry.children.items():
        for _child_key, child_entry in children.items():
            child_kind = getattr(child_entry.node, "kind", "")
            if child_kind not in _ENTITY_KINDS and child_kind not in _NAMESPACE_KINDS and not _is_compound(child_entry.node):
                continue
            child_parent = qname if _is_namespace(node) else parent_id
            _walk_entry(child_entry, parent_id=child_parent, nodes=nodes, edges=edges, seen=seen)


# ---------------------------------------------------------------------------
# Node / edge builders
# ---------------------------------------------------------------------------


def _is_namespace(node) -> bool:
    """Return True if the node represents a namespace-like kind."""
    return getattr(node, "kind", "") in _NAMESPACE_KINDS


def _build_node(entry: CompositeEntry, parent_id: str | None) -> dict:
    """Build a Cytoscape node-data dict from a CompositeEntry.

    Unified handler for all node types (namespace, compound, member).
    """
    node = entry.node
    qname = getattr(node, "qualified_name", "") or getattr(node, "name", "")
    name = getattr(node, "name", "")
    kind = getattr(node, "kind", "")
    layer = getattr(node, "layer", "design")
    source = getattr(node, "source", "")
    component_id = getattr(node, "component_id", None)
    visibility = getattr(node, "protection", "") or getattr(node, "visibility", "")
    description = getattr(node, "brief_description", "") or getattr(node, "description", "")
    is_dep = layer == "dependency"
    change_status = "new" if layer == "design" else ""

    data: dict = {
        "id": qname,
        "label": name,
        "qualified_name": qname,
        "kind": kind,
        "description": description,
        "component_id": component_id,
        "visibility": visibility,
        "layer": layer,
        "source": source,
        "change_status": change_status,
        "requirements": [],
    }

    if parent_id:
        data["parent"] = parent_id

    # Namespace nodes get a simple label, no members
    if _is_namespace(node):
        data["is_namespace"] = "true"
        return {"data": data}

    # Compound nodes with children → UML label
    if entry.children:
        by_kind = _build_member_data(entry)
        if by_kind:
            stereo_key = _CODEGRAPH_STEREOTYPE_MAP.get(kind, "")
            label_text, member_count = _build_uml_label(
                name, by_kind, is_dep, owner_kind=stereo_key,
            )
            html_label = _build_uml_html(
                name, by_kind, is_dep, owner_kind=stereo_key,
                change_status=change_status,
            )
            data["label"] = label_text
            data["html_label"] = html_label
            data["has_members"] = "true"
            data["member_count"] = member_count

    return {"data": data}


def _build_edge(source_qname: str, target_key: str, relation_type: str) -> dict:
    """Build a Cytoscape edge-data dict from a CompositeEntry reference tuple."""
    return {
        "data": {
            "id": f"e_{source_qname}_{target_key}_{relation_type}",
            "source": source_qname,
            "target": target_key,
            "label": relation_type,
        }
    }


def _build_member_data(entry: CompositeEntry) -> dict[str, list[dict]]:
    """Extract member dicts from entry.children for UML label building.

    Skips entity-kind children (nested classes/enums/etc.).
    Groups by canonical UML kind using _CODEGRAPH_KIND_GROUP.
    """
    by_kind: dict[str, list[dict]] = {}
    for _type_key, children in entry.children.items():
        for _child_key, child_entry in children.items():
            m_kind = getattr(child_entry.node, "kind", "")
            if m_kind in _ENTITY_KINDS:
                continue
            norm = _CODEGRAPH_KIND_GROUP.get(m_kind, m_kind)
            layer = getattr(child_entry.node, "layer", getattr(entry.node, "layer", "design"))
            by_kind.setdefault(norm, []).append({
                "name": getattr(child_entry.node, "name", ""),
                "type_signature": getattr(child_entry.node, "type_signature", ""),
                "argsstring": getattr(child_entry.node, "argsstring", ""),
                "visibility": getattr(child_entry.node, "protection", "") or getattr(child_entry.node, "visibility", ""),
                "qualified_name": getattr(child_entry.node, "qualified_name", ""),
                "layer": layer,
            })
    return by_kind


# ---------------------------------------------------------------------------
# In-memory filters (mutate LayerGraph in-place)
# ---------------------------------------------------------------------------


def _filter_by_kind(graph: LayerGraph, kind: str) -> None:
    """Remove entries whose node.kind != kind.  Prunes orphans and stale refs."""
    all_entries = list(graph._all_entries())
    keep_keys: set[str] = set()
    for entry in all_entries:
        if getattr(entry.node, "kind", "") == kind:
            keep_keys.add(graph._node_key(entry.node))

    # Also preserve ancestors of kept entries
    _preserve_ancestors(graph, keep_keys)
    _prune_graph(graph, keep_keys)


def _filter_by_search(graph: LayerGraph, text: str) -> None:
    """Keep entries where text appears in name or qualified_name.

    Preserves ancestor chain — if a member matches, its parent
    compound and grandparent namespace are kept.
    """
    text_lower = text.lower()
    all_entries = list(graph._all_entries())
    keep_keys: set[str] = set()
    for entry in all_entries:
        name = getattr(entry.node, "name", "") or ""
        qname = getattr(entry.node, "qualified_name", "") or ""
        if text_lower in name.lower() or text_lower in qname.lower():
            keep_keys.add(graph._node_key(entry.node))

    _preserve_ancestors(graph, keep_keys)
    _prune_graph(graph, keep_keys)


def _filter_by_component(graph: LayerGraph, component_id: int) -> None:
    """Keep entries whose node.component_id matches.  Preserves ancestry."""
    all_entries = list(graph._all_entries())
    keep_keys: set[str] = set()
    for entry in all_entries:
        if getattr(entry.node, "component_id", None) == component_id:
            keep_keys.add(graph._node_key(entry.node))

    _preserve_ancestors(graph, keep_keys)
    _prune_graph(graph, keep_keys)


# ---------------------------------------------------------------------------
# Filter helpers
# ---------------------------------------------------------------------------


def _preserve_ancestors(graph: LayerGraph, keep_keys: set[str]) -> None:
    """Walk up from each kept entry, adding ancestor keys to keep_keys.

    An entry's ancestors are found by walking the tree from root entries
    down and recording the path.  When we find a kept entry, all entries
    on the path to it are also kept.
    """
    # Walk the tree depth-first.  When we find a kept entry, mark all
    # entries on the current path as kept.
    def _mark_ancestors(entry: CompositeEntry, path: list[str]) -> None:
        key = graph._node_key(entry.node)
        path.append(key)
        # If this entry matches, mark everyone on the path
        if key in keep_keys:
            for ancestor_key in path:
                keep_keys.add(ancestor_key)
        # Recurse into children
        for _type_key, children in entry.children.items():
            for _child_key, child_entry in children.items():
                _mark_ancestors(child_entry, path)
        path.pop()

    for entry in graph.entries.values():
        _mark_ancestors(entry, [])


def _is_leaf_member(entry: CompositeEntry) -> bool:
    """Return True if this entry is a leaf member (method, attribute, etc.)
    that would be collapsed into a parent compound's UML label."""
    kind = getattr(entry.node, "kind", "")
    return kind not in _ENTITY_KINDS and kind not in _NAMESPACE_KINDS and not _is_compound(entry.node)


def _prune_tree(entry: CompositeEntry, keep_keys: set[str], key_fn) -> CompositeEntry | None:
    """Recursively prune a CompositeEntry's children.

    An entry is kept if it's in keep_keys, or if it has matching descendants.
    Leaf members of a matching compound are always kept (they're part of
    the UML label).  Siblings that aren't matching and have no matching
    descendants are pruned.
    """
    node_key = key_fn(entry.node)
    is_match = node_key in keep_keys

    new_children: dict[str, dict[str, CompositeEntry]] = {}
    for type_key, children in entry.children.items():
        kept: dict[str, CompositeEntry] = {}
        for child_key, child_entry in children.items():
            child_key_str = key_fn(child_entry.node)
            child_is_match = child_key_str in keep_keys

            # Leaf members of a matching parent are always kept (UML label)
            if is_match and _is_leaf_member(child_entry):
                kept[child_key] = child_entry
                continue

            if child_is_match:
                # Child matches — keep it and recurse
                _prune_tree(child_entry, keep_keys, key_fn)
                kept[child_key] = child_entry
            else:
                # Neither parent nor child matches — check descendants
                pruned = _prune_tree(child_entry, keep_keys, key_fn)
                if pruned is not None:
                    kept[child_key] = pruned
        if kept:
            new_children[type_key] = kept
    entry.children = new_children

    # Keep this entry if it matches or has matching descendants (children)
    if is_match or new_children:
        return entry
    return None


def _prune_graph(graph: LayerGraph, keep_keys: set[str]) -> None:
    """Remove entries not in keep_keys, pruning root entries, subtrees, and stale refs."""
    key_fn = graph._node_key

    # First, prune children of each root entry
    new_entries: dict[str, CompositeEntry] = {}
    for key, entry in graph.entries.items():
        pruned = _prune_tree(entry, keep_keys, key_fn)
        if pruned is not None:
            new_entries[key] = pruned
    graph.entries = new_entries

    # Prune references: remove edges whose target is no longer in the graph
    all_entry_keys: set[str] = set()
    for entry in graph._all_entries():
        all_entry_keys.add(key_fn(entry.node))

    for entry in graph._all_entries():
        entry.references = [
            (rel_type, target_key, target_type)
            for rel_type, target_key, target_type in entry.references
            if target_key in all_entry_keys
        ]