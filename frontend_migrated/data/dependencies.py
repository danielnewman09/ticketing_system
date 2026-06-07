"""Dependency recommendations and dependency graph data — stubs.

Return types are documented via TypedDicts. All functions raise
NotImplementedError until reimplemented against the migrated backend.
No imports from backend/ anywhere in this module.
"""

from __future__ import annotations

from typing import TypedDict


class DependencyRecommendation(TypedDict):
    id: int
    name: str
    github_url: str
    description: str
    version: str
    stars: int
    license: str
    last_updated: str
    pros: list[str]
    cons: list[str]
    relevant_hlrs: list[str]
    relevant_structures: list[str]
    summary: str
    status: str


class PendingRecommendationSummary(TypedDict):
    component_id: int
    component_name: str
    pending_count: int


class ComponentDependency(TypedDict):
    id: int
    name: str
    version: str
    is_dev: bool


def fetch_design_dependency_links_data(design_qnames: list[str]) -> dict:
    """Fetch cross-layer links between Design nodes and dependency Compounds.

    Returns Cytoscape-format dict with 'nodes' and 'edges' keys.
    """
    raise NotImplementedError("fetch_design_dependency_links_data — requires backend_migrated data layer")


def fetch_recommendations(component_id: int) -> list[DependencyRecommendation]:
    """Fetch all dependency recommendations for a component."""
    raise NotImplementedError("fetch_recommendations — requires backend_migrated data layer")


def save_recommendations(component_id: int, summary: str, recommendations: list[dict]) -> None:
    """Save research results as pending recommendations, replacing all previous ones."""
    raise NotImplementedError("save_recommendations — requires backend_migrated data layer")


def update_recommendation_status(rec_id: int, status: str) -> bool:
    """Update a recommendation's status (accepted/rejected). Returns True on success."""
    raise NotImplementedError("update_recommendation_status — requires backend_migrated data layer")


def accept_recommendation(rec_id: int) -> bool:
    """Accept a recommendation: mark as accepted and add to dependency manager."""
    raise NotImplementedError("accept_recommendation — requires backend_migrated data layer")


def add_manual_recommendation(component_id: int, rec: dict) -> int:
    """Add a manually researched dependency recommendation. Returns the new record ID."""
    raise NotImplementedError("add_manual_recommendation — requires backend_migrated data layer")


def reject_use_stdlib(rec_id: int) -> bool:
    """Reject a recommendation with a note that stdlib will be used instead."""
    raise NotImplementedError("reject_use_stdlib — requires backend_migrated data layer")


def fetch_pending_recommendations_summary() -> list[PendingRecommendationSummary]:
    """Fetch components that have pending dependency recommendations."""
    raise NotImplementedError("fetch_pending_recommendations_summary — requires backend_migrated data layer")