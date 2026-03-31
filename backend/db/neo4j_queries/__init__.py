"""Read-side Neo4j queries returning plain dicts for the frontend."""

from __future__ import annotations

from backend.db.neo4j_queries.compound import fetch_design_dependency_links
from backend.db.neo4j_queries.design import fetch_design_graph, fetch_hlr_subgraph
from backend.db.neo4j_queries.detail import fetch_neighbourhood_graph, fetch_node_detail

__all__ = [
    "fetch_design_dependency_links",
    "fetch_design_graph",
    "fetch_graph",
    "fetch_hlr_subgraph",
    "fetch_neighbourhood_graph",
    "fetch_node_detail",
]


def fetch_graph(
    layer: str = "design",
    kind_filter: str | None = None,
    search: str | None = None,
    component_id: int | None = None,
    source_filter: str | None = None,
    limit: int = 100,
) -> dict:
    """Unified graph fetch — single entry point for all layers.

    *layer* is one of ``"design"``, ``"codebase"``, or ``"dependency"``.
    """
    if layer == "design":
        return fetch_design_graph(kind_filter, search, component_id)
    from backend.db.neo4j_queries.compound import _fetch_compound_layer
    return _fetch_compound_layer(layer, search, source_filter, limit)
