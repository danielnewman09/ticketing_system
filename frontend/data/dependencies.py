"""Dependency recommendations and dependency graph data."""

import logging

from backend.db import get_session
from backend.db.models import (
    Component,
    Dependency,
    DependencyManager,
    DependencyRecommendation,
    Language,
)

log = logging.getLogger(__name__)


def fetch_dependency_graph_data(
    search: str,
    source_filter: str | None = None,
) -> dict:
    """Fetch dependency graph from Neo4j for Cytoscape.js rendering."""
    try:
        from backend.db.neo4j_queries import fetch_dependency_graph
        return fetch_dependency_graph(search, source_filter)
    except Exception:
        log.warning("Neo4j dependency graph query failed — returning empty graph", exc_info=True)
        return {"nodes": [], "edges": []}


def fetch_dependency_node_detail_data(qualified_name: str) -> dict | None:
    """Fetch dependency node detail from Neo4j."""
    try:
        from backend.db.neo4j_queries import fetch_dependency_node_detail
        return fetch_dependency_node_detail(qualified_name)
    except Exception:
        log.warning("Neo4j dependency node detail query failed", exc_info=True)
        return None


def fetch_design_dependency_links_data(design_qnames: list[str]) -> dict:
    """Fetch cross-layer links between Design nodes and dependency Compounds."""
    try:
        from backend.db.neo4j_queries import fetch_design_dependency_links
        return fetch_design_dependency_links(design_qnames)
    except Exception:
        log.warning("Neo4j design-dependency links query failed", exc_info=True)
        return {"nodes": [], "edges": []}


def fetch_recommendations(component_id: int) -> list[dict]:
    """Fetch all dependency recommendations for a component."""
    with get_session() as session:
        recs = session.query(DependencyRecommendation).filter_by(
            component_id=component_id,
        ).order_by(DependencyRecommendation.status, DependencyRecommendation.name).all()
        return [
            {
                "id": r.id,
                "name": r.name,
                "github_url": r.github_url,
                "description": r.description,
                "version": r.version,
                "stars": r.stars,
                "license": r.license,
                "last_updated": r.last_updated,
                "pros": r.pros or [],
                "cons": r.cons or [],
                "relevant_hlrs": r.relevant_hlrs or [],
                "relevant_structures": r.relevant_structures or [],
                "summary": r.summary,
                "status": r.status,
            }
            for r in recs
        ]


def save_recommendations(component_id: int, summary: str, recommendations: list[dict]):
    """Save research results as pending recommendations, replacing all previous ones."""
    with get_session() as session:
        # Remove all previous recommendations (pending, accepted, rejected)
        session.query(DependencyRecommendation).filter_by(
            component_id=component_id,
        ).delete()
        session.flush()

        for rec in recommendations:
            session.add(DependencyRecommendation(
                component_id=component_id,
                name=rec.get("name", ""),
                github_url=rec.get("github_url", ""),
                description=rec.get("description", ""),
                version=rec.get("version", ""),
                stars=rec.get("stars", 0),
                license=rec.get("license", ""),
                last_updated=rec.get("last_updated", ""),
                pros=rec.get("pros"),
                cons=rec.get("cons"),
                relevant_hlrs=rec.get("relevant_hlrs"),
                relevant_structures=rec.get("relevant_structures"),
                summary=summary,
                status="pending",
            ))


def update_recommendation_status(rec_id: int, status: str) -> bool:
    """Update a recommendation's status (accepted/rejected). Returns True on success."""
    with get_session() as session:
        rec = session.query(DependencyRecommendation).filter_by(id=rec_id).first()
        if not rec:
            return False
        rec.status = status
        return True


def accept_recommendation(rec_id: int) -> bool:
    """Accept a recommendation: mark as accepted and add to dependency manager.

    If no dependency manager exists, creates one automatically.
    """
    from backend.db import get_or_create

    with get_session() as session:
        rec = session.query(DependencyRecommendation).filter_by(id=rec_id).first()
        if not rec:
            return False
        rec.status = "accepted"

        # Find the component and ensure it has a dependency manager
        comp = session.query(Component).filter_by(id=rec.component_id).first()
        if not comp:
            return True  # status updated, but can't add dep

        # Ensure language exists
        if not comp.language:
            lang, _ = get_or_create(session, Language, name="C++")
            comp.language_id = lang.id
            session.flush()
            session.refresh(comp)

        lang = comp.language

        # Ensure dependency manager exists
        managers = lang.dependency_managers
        if not managers:
            dm = DependencyManager(
                language_id=lang.id,
                name="dependencies",
                manifest_file="dependencies.txt",
            )
            session.add(dm)
            session.flush()
        else:
            dm = managers[0]

        # Add the dependency
        existing = session.query(Dependency).filter_by(
            manager_id=dm.id, name=rec.name,
        ).first()
        if not existing:
            dep = Dependency(
                manager_id=dm.id,
                name=rec.name,
                version=rec.version,
                github_url=rec.github_url,
            )
            session.add(dep)
            session.flush()
        else:
            dep = existing

        # Link dependency to the component
        if comp not in dep.components:
            dep.components.append(comp)

        return True


def add_manual_recommendation(component_id: int, rec: dict) -> int:
    """Add a manually researched dependency recommendation. Returns the new record ID."""
    with get_session() as session:
        obj = DependencyRecommendation(
            component_id=component_id,
            name=rec.get("name", ""),
            github_url=rec.get("github_url", ""),
            description=rec.get("description", ""),
            version=rec.get("version", ""),
            stars=rec.get("stars", 0),
            license=rec.get("license", ""),
            pros=rec.get("pros"),
            cons=rec.get("cons"),
            summary="Manually added",
            status="pending",
        )
        session.add(obj)
        session.flush()
        return obj.id


def reject_use_stdlib(rec_id: int) -> bool:
    """Reject a recommendation with a note that stdlib will be used instead."""
    with get_session() as session:
        rec = session.query(DependencyRecommendation).filter_by(id=rec_id).first()
        if not rec:
            return False
        rec.status = "rejected_stdlib"
        return True


def fetch_pending_recommendations_summary() -> list[dict]:
    """Fetch components that have pending dependency recommendations.

    Returns list of {component_id, component_name, pending_count}.
    """
    with get_session() as session:
        pending = session.query(DependencyRecommendation).filter_by(status="pending").all()
        by_comp: dict[int, dict] = {}
        for r in pending:
            if r.component_id not in by_comp:
                comp = session.query(Component).filter_by(id=r.component_id).first()
                by_comp[r.component_id] = {
                    "component_id": r.component_id,
                    "component_name": comp.name if comp else "Unknown",
                    "pending_count": 0,
                }
            by_comp[r.component_id]["pending_count"] += 1
        return list(by_comp.values())
