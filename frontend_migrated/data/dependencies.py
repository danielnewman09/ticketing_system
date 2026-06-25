"""Dependency recommendations and dependency graph data — migrated.

Uses codegraph GraphRepository for design-dependency cross-layer links.
Other functions remain stubs until the recommendation system is migrated.
No imports from backend/ anywhere in this module.
"""

from __future__ import annotations

import logging

from codegraph import GraphRepository
from codegraph.graph import LayerGraph, CompositeEntry

from frontend_migrated.graph.format import layer_graph_to_cytoscape

log = logging.getLogger(__name__)


def fetch_design_dependency_links_data(design_qnames: list[str]) -> dict:
    """Fetch cross-layer links between Design nodes and dependency Compounds.

    Uses GraphRepository to build neighbourhood subgraphs for each design
    node qualified name, then merges them into a single LayerGraph and
    converts to Cytoscape format.

    Args:
        design_qnames: List of qualified names of design nodes whose
            dependency links should be fetched.

    Returns:
        Cytoscape-format dict with 'nodes' and 'edges' keys.
    """
    try:
        repo = GraphRepository()
        # Merge entries from multiple neighbourhood subgraphs
        merged_entries: dict[str, CompositeEntry] = {}
        for qn in design_qnames:
            sub = repo.get_by_neighbourhood(qn)
            for key, entry in sub.entries.items():
                if key not in merged_entries:
                    merged_entries[key] = entry

        if not merged_entries:
            return {"nodes": [], "edges": []}

        # Infer tags from the first entry
        tags: frozenset[str] = frozenset()
        for entry in merged_entries.values():
            node_tags = getattr(entry.node, "tags", None)
            if node_tags:
                tags = frozenset(node_tags)
                break
        if not tags:
            tags = frozenset({"design"})

        graph = LayerGraph(tags=tags, entries=merged_entries)
        return layer_graph_to_cytoscape(graph)
    except Exception:
        log.warning("Neo4j design-dependency links query failed", exc_info=True)
        return {"nodes": [], "edges": []}


# ---------------------------------------------------------------------------
# Stubs — to be migrated when the recommendation system moves to backend_migrated
# ---------------------------------------------------------------------------


def fetch_recommendations(component_id: int) -> list[dict]:
    """Fetch all dependency recommendations for a component."""
    raise NotImplementedError("fetch_recommendations — requires backend_migrated recommendation model")


def save_recommendations(component_id: int, summary: str, recommendations: list[dict]) -> None:
    """Save research results as pending recommendations, replacing all previous ones."""
    raise NotImplementedError("save_recommendations — requires backend_migrated recommendation model")


def update_recommendation_status(rec_id: int, status: str) -> bool:
    """Update a recommendation's status (accepted/rejected). Returns True on success."""
    raise NotImplementedError("update_recommendation_status — requires backend_migrated recommendation model")


def accept_recommendation(rec_id: int) -> bool:
    """Accept a recommendation: mark as accepted and add to dependency manager."""
    raise NotImplementedError("accept_recommendation — requires backend_migrated recommendation model")


def add_manual_recommendation(component_id: int, rec: dict) -> int:
    """Add a manually researched dependency recommendation. Returns the new record ID."""
    raise NotImplementedError("add_manual_recommendation — requires backend_migrated recommendation model")


def reject_use_stdlib(rec_id: int) -> bool:
    """Reject a recommendation with a note that stdlib will be used instead."""
    raise NotImplementedError("reject_use_stdlib — requires backend_migrated recommendation model")


def fetch_pending_recommendations_summary() -> list[dict]:
    """Fetch components that have pending dependency recommendations."""
    raise NotImplementedError("fetch_pending_recommendations_summary — requires backend_migrated recommendation model")