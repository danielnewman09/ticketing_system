"""HLR CRUD, decomposition, and requirements dashboard data.

Phase 3: All verification data lives in Neo4j via VerificationRepository.
"""

import logging

from backend.db.neo4j.repositories.requirement import RequirementRepository
from backend.db.neo4j.repositories.verification import VerificationRepository
from services.dependencies import get_neo4j
from backend.db import get_session

log = logging.getLogger(__name__)


def fetch_requirements_data():
    """Fetch all data needed for the requirements dashboard."""
    with get_neo4j().session() as ns:
        repo = RequirementRepository(ns)
        ver_repo = VerificationRepository(ns)
        hlrs_neo4j = repo.list_hlrs()

        hlrs = []
        for hlr in hlrs_neo4j:
            llrs_neo4j = repo.list_llrs(hlr_id=hlr.id)
            llrs = []
            for llr in llrs_neo4j:
                methods = [vm.method for vm in ver_repo.list_verifications(llr.id)]
                llrs.append({
                    "id": llr.id,
                    "description": llr.description,
                    "methods": methods,
                })

            component_name = None
            if hlr.component_id:
                component_name = _get_component_name(hlr.component_id)

            hlrs.append({
                "id": hlr.id,
                "description": hlr.description,
                "component": component_name,
                "llrs": llrs,
            })

        all_llrs = repo.list_llrs()
        hlr_ids_in_neo4j = {h.id for h in hlrs_neo4j}
        unlinked = []
        for llr in all_llrs:
            if llr.high_level_requirement_id not in hlr_ids_in_neo4j:
                methods = [vm.method for vm in ver_repo.list_verifications(llr.id)]
                unlinked.append({
                    "id": llr.id,
                    "description": llr.description,
                    "methods": methods,
                })

        total_verifications = ns.run(
            "MATCH (vm:VerificationMethod) RETURN count(vm) AS cnt"
        ).single()["cnt"]
        total_nodes = ns.run(
            "MATCH (d) WHERE d:Compound OR d:Member OR d:Namespace RETURN count(d) AS cnt"
        ).single()["cnt"]
        total_triples = ns.run(
            "MATCH (s)-[r]->(t) "
            "WHERE (s:Compound OR s:Member OR s:Namespace) "
            "AND (t:Compound OR t:Member OR t:Namespace) "
            "RETURN count(r) AS cnt"
        ).single()["cnt"]

    return {
        "hlrs": hlrs,
        "unlinked_llrs": unlinked,
        "total_hlrs": len(hlrs_neo4j),
        "total_llrs": len(all_llrs),
        "total_verifications": total_verifications,
        "total_nodes": total_nodes,
        "total_triples": total_triples,
    }


def fetch_hlr_detail(hlr_id):
    """Fetch all data needed for HLR detail page."""
    with get_neo4j().session() as ns:
        repo = RequirementRepository(ns)
        ver_repo = VerificationRepository(ns)
        hlr = repo.get_hlr(hlr_id)
        if not hlr:
            return None

        llrs_neo4j = repo.list_llrs(hlr_id=hlr.id)
        llrs = []
        for llr in llrs_neo4j:
            methods = [vm.method for vm in ver_repo.list_verifications(llr.id)]
            llrs.append({
                "id": llr.id,
                "description": llr.description,
                "methods": methods,
            })

        triples = _fetch_hlr_triples(ns, hlr.id)

    component_name = None
    if hlr.component_id:
        component_name = _get_component_name(hlr.component_id)

    return {
        "id": hlr.id,
        "description": hlr.description,
        "component": component_name,
        "component_id": hlr.component_id,
        "llrs": llrs,
        "triples": triples,
    }


def create_hlr(description: str, component_id: int | None = None) -> int:
    """Create a new HLR in Neo4j. Returns the new HLR id."""
    from codegraph.neo4j import Neo4jConnection
    from backend.db.neo4j.constraints import ensure_ticketing_constraints
    neo4j_conn = Neo4jConnection()
    ensure_ticketing_constraints(neo4j_conn)

    with get_neo4j().session() as ns:
        repo = RequirementRepository(ns)
        hlr = repo.create_hlr(description=description, component_id=component_id)
        return hlr.id


def update_hlr(hlr_id: int, description: str, component_id: int | None = None) -> bool:
    """Update an HLR's description and component in Neo4j. Returns True on success."""
    with get_neo4j().session() as ns:
        repo = RequirementRepository(ns)
        result = repo.update_hlr(hlr_id, description=description, component_id=component_id)
        return result is not None


def delete_hlr(hlr_id: int) -> bool:
    """Delete an HLR and its child LLRs from Neo4j. Returns True on success."""
    with get_neo4j().session() as ns:
        repo = RequirementRepository(ns)
        return repo.delete_hlr(hlr_id)


def decompose_hlr(hlr_id: int) -> dict:
    """Run the decomposition agent on an HLR and persist results to Neo4j."""
    import os

    from backend.ticketing_agent.decompose.decompose_hlr import decompose
    from backend.requirements.services.persistence import persist_decomposition

    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
    os.makedirs(log_dir, exist_ok=True)
    prompt_log_file = os.path.join(log_dir, f"decompose_hlr{hlr_id}_raw.txt")

    with get_neo4j().session() as ns:
        repo = RequirementRepository(ns)
        hlr = repo.get_hlr(hlr_id)
        if not hlr:
            raise ValueError(f"HLR {hlr_id} not found")

        siblings = repo.list_hlrs()
        other_hlrs = [
            {
                "id": s.id,
                "description": s.description,
                "component__name": _get_component_name(s.component_id) if s.component_id else None,
            }
            for s in siblings
            if s.id != hlr_id
        ]

        component_name = _get_component_name(hlr.component_id) if hlr.component_id else ""

        decomposed = decompose(
            description=hlr.description,
            other_hlrs=other_hlrs,
            component=component_name,
            dependency_context=hlr.dependency_context,
            prompt_log_file=prompt_log_file,
        )

        result = persist_decomposition(ns, hlr_id, decomposed.low_level_requirements)
        return {
            "llrs_created": result.llrs_created,
            "verifications_created": result.verifications_created,
        }


def design_single_hlr(hlr_id: int) -> dict:
    """Run the design agent on an HLR and persist the ontology results."""
    import os

    from backend.ticketing_agent.design.design_per_hlr import design_and_persist_hlr

    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
    os.makedirs(log_dir, exist_ok=True)

    return design_and_persist_hlr(hlr_id, log_dir=log_dir)


# ---------------------------------------------------------------------------
# Helper functions (private)
# ---------------------------------------------------------------------------


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


def _fetch_hlr_triples(neo4j_session, hlr_id: int) -> list[dict]:
    """Fetch triples from TRACES_TO edges for an HLR subgraph."""
    triples = []
    try:
        result = neo4j_session.run(
            """
            MATCH (hlr:HLR {id: $hid})-[:TRACES_TO]->(d)
            WHERE d:Compound OR d:Member OR d:Namespace
            OPTIONAL MATCH (d)-[r]->(d2)
            WHERE (d2:Compound OR d2:Member OR d2:Namespace)
              AND type(r) <> 'IMPLEMENTED_BY' AND type(r) <> 'TRACES_TO'
            RETURN d.qualified_name AS subj, type(r) AS pred, d2.qualified_name AS obj
            """,
            {"hid": hlr_id},
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
        log.warning("Failed to fetch HLR triples from Neo4j", exc_info=True)
    return triples
