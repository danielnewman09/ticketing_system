"""LLR CRUD and detail data.

Phase 3: All verification data lives in Neo4j via VerificationRepository.
"""

import logging

from backend.db.neo4j.repositories.requirement import RequirementRepository
from backend.db.neo4j.repositories.verification import VerificationRepository
from services.dependencies import get_neo4j
from backend.db import get_session

log = logging.getLogger(__name__)


def fetch_llr_detail(llr_id):
    """Fetch all data needed for LLR detail page."""
    with get_neo4j().session() as ns:
        repo = RequirementRepository(ns)
        ver_repo = VerificationRepository(ns)
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

        verifications = _get_verification_detail(ver_repo, llr_id)
        components = _get_llr_components(repo, llr_id)
        triples = _fetch_llr_triples(ns, llr_id)

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
# Helper functions (private)
# ---------------------------------------------------------------------------


def _get_verification_detail(ver_repo: VerificationRepository, llr_id: int) -> list[dict]:
    """Get full verification detail for an LLR from Neo4j."""
    verifications = []
    try:
        for vm in ver_repo.list_verifications(llr_id):
            conditions = ver_repo.list_conditions(vm.id)
            actions = ver_repo.list_actions(vm.id)
            preconditions = [
                {
                    "subject_qualified_name": c.subject_qualified_name,
                    "operator": c.operator,
                    "expected_value": c.expected_value,
                }
                for c in conditions if c.phase == "pre"
            ]
            postconditions = [
                {
                    "subject_qualified_name": c.subject_qualified_name,
                    "operator": c.operator,
                    "expected_value": c.expected_value,
                }
                for c in conditions if c.phase == "post"
            ]
            action_list = [
                {
                    "order": a.order,
                    "description": a.description,
                    "callee_qualified_name": a.callee_qualified_name,
                    "caller_qualified_name": a.caller_qualified_name,
                }
                for a in actions
            ]
            verifications.append({
                "id": vm.id,
                "method": vm.method,
                "test_name": vm.test_name,
                "description": vm.description,
                "preconditions": preconditions,
                "actions": action_list,
                "postconditions": postconditions,
            })
    except Exception:
        log.warning("Failed to fetch verification detail for LLR %d", llr_id, exc_info=True)
    return verifications


def _get_llr_components(repo: RequirementRepository, llr_id: int) -> list[str]:
    """Get component names for an LLR from Neo4j component_ids + SQLite name lookup."""
    try:
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
            MATCH (l:LLR {id: $lid})-[:TRACES_TO]->(d)
            WHERE d:Compound OR d:Member OR d:Namespace
            OPTIONAL MATCH (d)-[r]->(d2)
            WHERE (d2:Compound OR d2:Member OR d2:Namespace)
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
