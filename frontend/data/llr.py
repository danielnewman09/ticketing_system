"""LLR CRUD and detail data.

In Phase 2, LLR data lives in Neo4j via RequirementRepository.
VerificationMethod data still comes from SQLite (Phase 3 will move it).
"""

import logging

from backend.db.neo4j.repositories.requirement import RequirementRepository
from services.dependencies import get_neo4j
from backend.db import get_session
from backend.db.models import VerificationMethod, VerificationCondition, VerificationAction

log = logging.getLogger(__name__)


def fetch_llr_detail(llr_id):
    """Fetch all data needed for LLR detail page."""
    with get_neo4j().session() as ns:
        repo = RequirementRepository(ns)
        llr = repo.get_llr(llr_id)
        if not llr:
            return None

        hlr = repo.get_hlr(llr.high_level_requirement_id)
        hlr_data = None
        if hlr:
            hlr_data = {
                "id": hlr.id,
                "description": hlr.description,
                "component": _get_component_name(hlr.component_id) if hlr.component_id else None,
            }

        # Triples from TRACES_TO edges
        triples = _fetch_llr_triples(ns, llr_id)

    # Verification data still from SQLite (Phase 3)
    verifications = _get_verification_detail(llr_id)

    # Component names from LLR's component links (still in Neo4j property for now)
    components = _get_llr_components(ns, llr_id)

    return {
        "id": llr.id,
        "description": llr.description,
        "hlr": hlr_data,
        "verifications": verifications,
        "components": components,
        "triples": triples,
    }


def create_llr(hlr_id: int, description: str) -> int:
    """Create a new LLR under an HLR in Neo4j. Returns the new LLR id."""
    with get_neo4j().session() as ns:
        repo = RequirementRepository(ns)
        llr = repo.create_llr(hlr_id=hlr_id, description=description)
        return llr.id


def update_llr(llr_id: int, description: str) -> bool:
    """Update an LLR's description in Neo4j. Returns True on success."""
    with get_neo4j().session() as ns:
        repo = RequirementRepository(ns)
        result = repo.update_llr(llr_id, description=description)
        return result is not None


def delete_llr(llr_id: int) -> bool:
    """Delete an LLR from Neo4j. Returns True on success."""
    with get_neo4j().session() as ns:
        repo = RequirementRepository(ns)
        return repo.delete_llr(llr_id)


# ---------------------------------------------------------------------------
# Helper functions (private, bridging to SQLite for verification data)
# ---------------------------------------------------------------------------


def _get_verification_detail(llr_id: int) -> list[dict]:
    """Get full verification detail for an LLR from SQLite."""
    try:
        with get_session() as session:
            verifications = []
            for v in session.query(VerificationMethod).filter_by(low_level_requirement_id=llr_id).all():
                preconditions = [
                    {
                        "member_qualified_name": c.member_qualified_name,
                        "operator": c.operator,
                        "expected_value": c.expected_value,
                    }
                    for c in sorted(
                        [c for c in v.conditions if c.phase == "pre"],
                        key=lambda c: c.order,
                    )
                ]
                postconditions = [
                    {
                        "member_qualified_name": c.member_qualified_name,
                        "operator": c.operator,
                        "expected_value": c.expected_value,
                    }
                    for c in sorted(
                        [c for c in v.conditions if c.phase == "post"],
                        key=lambda c: c.order,
                    )
                ]
                actions = [
                    {
                        "order": a.order,
                        "description": a.description,
                        "member_qualified_name": a.member_qualified_name,
                    }
                    for a in sorted(v.actions, key=lambda a: a.order)
                ]
                verifications.append({
                    "id": v.id,
                    "method": v.method,
                    "test_name": v.test_name,
                    "description": v.description,
                    "preconditions": preconditions,
                    "actions": actions,
                    "postconditions": postconditions,
                })
            return verifications
    except Exception:
        log.warning("Failed to fetch verification detail for LLR %d", llr_id, exc_info=True)
        return []


def _get_llr_components(neo4j_session, llr_id: int) -> list[str]:
    """Get component names for an LLR from Neo4j component_ids + SQLite name lookup."""
    try:
        repo = RequirementRepository(neo4j_session)
        comp_ids = repo.get_llr_components(llr_id)
        names = []
        for cid in comp_ids:
            name = _get_component_name(cid)
            if name:
                names.append(name)
        return names
    except Exception:
        return []


def _get_component_name(component_id: int | None) -> str | None:
    """Look up a component name by ID from SQLite."""
    if component_id is None:
        return None
    try:
        from backend.db.models import Component
        with get_session() as session:
            comp = session.query(Component).filter_by(id=component_id).first()
            return comp.name if comp else None
    except Exception:
        return None


def _fetch_llr_triples(neo4j_session, llr_id: int) -> list[dict]:
    """Fetch triples from TRACES_TO edges for an LLR subgraph."""
    triples = []
    try:
        result = neo4j_session.run(
            """
            MATCH (l:LLR {id: $lid})-[:TRACES_TO]->(d:Design)
            OPTIONAL MATCH (d)-[r]->(d2:Design)
            WHERE type(r) <> 'IMPLEMENTED_BY' AND type(r) <> 'TRACES_TO'
            RETURN d.qualified_name AS subj, type(r) AS pred, d2.qualified_name AS obj
            """,
            {"lid": llr_id},
        )
        seen = set()
        for rec in result:
            key = (rec["subj"], rec["pred"], rec["obj"])
            if key not in seen and all(key):
                seen.add(key)
                triples.append({
                    "subject": rec["subj"],
                    "predicate": rec["pred"],
                    "object": rec["obj"],
                })
    except Exception:
        log.warning("Failed to fetch LLR triples from Neo4j", exc_info=True)
    return triples