"""Graph data formatting — transforms raw Neo4j data into Cytoscape.js shape."""

from backend.graph.builders import build_cytoscape_edge, build_cytoscape_node
from backend.graph.transforms import assign_namespace_parents, collapse_members

__all__ = [
    "build_cytoscape_node",
    "build_cytoscape_edge",
    "collapse_members",
    "assign_namespace_parents",
    "format_cytoscape_graph",
]


def format_cytoscape_graph(raw: dict) -> dict:
    """Transform raw Neo4j query result into Cytoscape.js format.

    Input: {"nodes": [{flat properties}...], "edges": [{"source", "target", "type"}...]}
    Output: {"nodes": [{"data": {...}}...], "edges": [{"data": {"id", "source", "target", "label"}}...]}
    """
    nodes = [{"data": build_cytoscape_node(n)} for n in raw.get("nodes", [])]
    edges = [{"data": build_cytoscape_edge(e)} for e in raw.get("edges", [])]
    nodes, edges = collapse_members(nodes, edges)
    nodes, edges = assign_namespace_parents(nodes, edges)
    return {"nodes": nodes, "edges": edges}
