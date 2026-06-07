"""Ontology graph page — stub.

Interactive Cytoscape.js visualization with a collapsible detail panel.
Requires data layer for graph loading, filtering, search, and node detail.
"""

from nicegui import ui


@ui.page("/ontology/graph")
async def ontology_graph_page():
    """STUB: Ontology graph page with Cytoscape.js visualization and detail panel."""
    raise NotImplementedError("ontology_graph_page — requires data layer reimplementation")