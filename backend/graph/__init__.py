"""Graph data formatting — transforms raw Neo4j data into Cytoscape.js shape."""

from backend.graph.builders import build_cytoscape_edge, build_cytoscape_node
from backend.graph.transforms import assign_namespace_parents, collapse_members

__all__ = [
    "build_cytoscape_node",
    "build_cytoscape_edge",
    "collapse_members",
    "assign_namespace_parents",
    "tag_cross_layer",
    "format_cytoscape_graph",
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
    return {"nodes": nodes, "edges": edges}
