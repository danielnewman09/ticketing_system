"""Read-side Neo4j queries returning plain dicts for the frontend."""

from __future__ import annotations

from backend.db.neo4j_queries.compound import fetch_design_dependency_links
from backend.db.neo4j_queries.detail import fetch_neighbourhood_graph, fetch_node_detail
from backend.db.neo4j_queries.fetch import (
    fetch_graph_layer,
)

__all__ = [
    "fetch_design_dependency_links",
    "fetch_graph",
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
    return fetch_graph_layer(
        layer,
        kind_filter=kind_filter,
        search=search,
        component_id=component_id,
        source_filter=source_filter,
        limit=limit,
    )