"""Graph data formatting — transforms typed & raw Neo4j data into Cytoscape.js shape."""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.graph.builders import build_cytoscape_edge, build_cytoscape_node
from backend.graph.transforms import (
    _assign_component_parents,
    _assign_inferred_parents,
    _build_uml_html,
    _build_uml_label,
    _COLLAPSIBLE_KINDS,
    _ENTITY_KINDS,
    _KIND_NORMALIZE,
    _OWNER_KINDS,
    assign_namespace_parents,
    collapse_members,
)

if TYPE_CHECKING:
    from backend.db.neo4j.models.graph import (
        CompoundGraph,
        GraphEdge,
        NamespaceGraph,
        OntologyGraph,
    )

__all__ = [
    "build_cytoscape_node",
    "build_cytoscape_edge",
    "collapse_members",
    "assign_namespace_parents",
    "tag_cross_layer",
    "format_cytoscape_graph",
    "format_ontology_graph",
    "_remove_composes_edges",
]


def tag_cross_layer(nodes: list[dict], edges: list[dict]) -> tuple[list[dict], list[dict]]:
    """Tag dependency/as-built nodes and cross-layer edges for Cytoscape styling.

    Adds data attributes:
    - has_source='true' on dependency nodes with a non-empty source property
    - is_as_built='true' on as-built layer nodes
    - is_cross_layer='true' on edges connecting nodes of different layers
    """
    node_layers: dict[str, str] = {}
    for n in nodes:
        d = n["data"]
        layer = d.get("layer", "")
        node_layers[d["id"]] = layer

        if d.get("source") and layer == "dependency":
            d["has_source"] = "true"

        if layer == "as-built":
            d["is_as_built"] = "true"

    for e in edges:
        d = e["data"]
        src_layer = node_layers.get(d.get("source", ""), "")
        tgt_layer = node_layers.get(d.get("target", ""), "")
        if src_layer and tgt_layer and src_layer != tgt_layer:
            d["is_cross_layer"] = "true"

    return nodes, edges


def _remove_composes_edges(edges: list[dict]) -> list[dict]:
    """Remove all remaining COMPOSES edges from the graph output."""
    return [e for e in edges if e["data"].get("label") != "COMPOSES"]


def format_cytoscape_graph(raw: dict) -> dict:
    """Transform raw Neo4j query result into Cytoscape.js format.

    Input: {"nodes": [{flat properties}...], "edges": [{"source", "target", "type"}...]}
    Output: {"nodes": [{"data": {...}}...], "edges": [{"data": {"id", "source", "target", "label"}}...]}
    """
    nodes = [{"data": build_cytoscape_node(n)} for n in raw.get("nodes", [])]
    edges = [{"data": build_cytoscape_edge(e)} for e in raw.get("edges", [])]
    nodes, edges = collapse_members(nodes, edges)
    nodes, edges = assign_namespace_parents(nodes, edges)
    nodes, edges = tag_cross_layer(nodes, edges)
    edges = _remove_composes_edges(edges)
    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# Typed-pipeline: format directly from OntologyGraph (no raw-dict round-trip)
# ---------------------------------------------------------------------------

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


def _build_compound_cytoscape_node(
    cg: "CompoundGraph",
) -> dict:
    """Build a Cytoscape node-data dict from a CompoundGraph.

    Members are collapsed into UML-style labels (both plain-text and
    HTML variants) using the same rendering functions that
    ``collapse_members`` calls.  Entity-kind members (nested
    classes/enums/etc.) are excluded from the compartment — their
    typed attributes already convey the reference.
    """
    node = cg.node
    owner_kind = getattr(node, "kind", "")
    layer = getattr(node, "layer", "design")
    is_dep = layer == "dependency"
    change_status = getattr(node, "change_status", "") or "new"

    # Group members by canonical UML kind, skipping entity kinds.
    by_kind: dict[str, list[dict]] = {}
    for m in cg.members:
        m_kind = getattr(m, "kind", "")
        if m_kind in _ENTITY_KINDS:
            continue
        norm = _CODEGRAPH_KIND_GROUP.get(m_kind, m_kind)
        by_kind.setdefault(norm, []).append({
            "name": m.name,
            "type_signature": getattr(m, "type_signature", ""),
            "argsstring": getattr(m, "argsstring", ""),
            "visibility": getattr(m, "protection", ""),
            "qualified_name": m.qualified_name,
            "layer": getattr(m, "layer", layer),
        })

    stereo_key = _CODEGRAPH_STEREOTYPE_MAP.get(owner_kind, "")
    data: dict = {
        "id": node.qualified_name,
        "label": node.name,
        "qualified_name": node.qualified_name,
        "kind": owner_kind,
        "description": getattr(node, "description", ""),
        "component_id": getattr(node, "component_id", None),
        "visibility": getattr(node, "protection", ""),
        "type_signature": getattr(node, "type_signature", ""),
        "argsstring": getattr(node, "argsstring", ""),
        "layer": layer,
        "source_type": getattr(node, "source_type", ""),
        "change_status": change_status,
        "requirements": [],
    }

    if by_kind:
        label_text, member_count = _build_uml_label(
            node.name, by_kind, is_dep, owner_kind=stereo_key,
        )
        html_label = _build_uml_html(
            node.name, by_kind, is_dep, owner_kind=stereo_key,
            change_status=change_status,
        )
        data["label"] = label_text
        data["html_label"] = html_label
        data["has_members"] = "true"
        data["member_count"] = member_count

    return {"data": data}


def _build_graph_edge(e: "GraphEdge") -> dict:
    """Build a Cytoscape edge-data dict from a typed GraphEdge."""
    return {
        "data": {
            "id": f"e_{e.source_qualified_name}_{e.target_qualified_name}_{e.predicate}",
            "source": e.source_qualified_name,
            "target": e.target_qualified_name,
            "label": e.predicate,
            "mechanism": e.mechanism,
            "position": e.position,
            "name": e.name,
            "display_name": e.display_name,
        }
    }


def _build_namespace_cytoscape_node(ns_node) -> dict:
    """Build a Cytoscape node-data dict from a NamespaceNode."""
    return {
        "data": {
            "id": ns_node.qualified_name,
            "label": ns_node.name,
            "qualified_name": ns_node.qualified_name,
            "kind": "module",
            "description": getattr(ns_node, "description", ""),
            "visibility": "",
            "type_signature": "",
            "layer": getattr(ns_node, "layer", "design"),
            "is_namespace": "true",
        }
    }


def format_ontology_graph(ontograph: "OntologyGraph") -> dict:
    """Transform a typed OntologyGraph into Cytoscape.js format.

    Walks the typed hierarchy directly — members are pre-grouped inside
    CompoundGraph objects, so there is no need for a separate collapse
    step.  Namespace parent references come from the typed tree, with
    component/inferred namespaces applied as a fallback for unparented
    nodes.

    Returns ``{"nodes": [...], "edges": [...]}`` in Cytoscape shape.
    """
    nodes: list[dict] = []
    edges: list[dict] = []
    assigned_parents: set[str] = set()

    # Walk namespace tree — explicit namespace → compound hierarchy.
    for nsg in ontograph.namespaces:
        ns_node_data = _build_namespace_cytoscape_node(nsg.node)
        nodes.append(ns_node_data)
        ns_id = ns_node_data["data"]["id"]

        for cg in nsg.compounds:
            c_node = _build_compound_cytoscape_node(cg)
            c_node["data"]["parent"] = ns_id
            assigned_parents.add(c_node["data"]["id"])
            nodes.append(c_node)
            for ge in cg.edges_out:
                edges.append(_build_graph_edge(ge))

    # Unparented compounds.
    for cg in ontograph.compounds:
        c_node = _build_compound_cytoscape_node(cg)
        nodes.append(c_node)
        for ge in cg.edges_out:
            edges.append(_build_graph_edge(ge))

    # Cross-cutting edges (between namespaces or unparented compounds).
    for ge in ontograph.edges:
        edges.append(_build_graph_edge(ge))

    # Apply component / inferred namespace parents for nodes that were
    # not already parented by the explicit namespace tree.
    synth_ns: dict[str, str] = {}
    _assign_component_parents(nodes, assigned_parents, synth_ns)
    _assign_inferred_parents(nodes, assigned_parents, synth_ns)

    # Style tags (cross-layer, as-built, dependency source).
    nodes, edges = tag_cross_layer(nodes, edges)

    return {"nodes": nodes, "edges": edges}
