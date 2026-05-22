"""HLR CRUD, decomposition, and requirements dashboard data."""

import logging

from backend.db import get_session
from backend.db.models import (
    HighLevelRequirement,
    LowLevelRequirement,
    VerificationMethod,
)

log = logging.getLogger(__name__)


def fetch_requirements_data():
    """Fetch all data needed for the requirements dashboard."""
    with get_session() as session:
        hlrs = []
        for hlr in session.query(HighLevelRequirement).all():
            llrs = []
            for llr in hlr.low_level_requirements:
                methods = [v.method for v in llr.verifications]
                llrs.append(
                    {
                        "id": llr.id,
                        "description": llr.description,
                        "methods": methods,
                    }
                )
            hlrs.append(
                {
                    "id": hlr.id,
                    "description": hlr.description,
                    "component": hlr.component.name if hlr.component else None,
                    "llrs": llrs,
                }
            )

        unlinked = []
        for llr in (
            session.query(LowLevelRequirement)
            .filter(
                LowLevelRequirement.high_level_requirement_id.is_(None),
            )
            .all()
        ):
            methods = [v.method for v in llr.verifications]
            unlinked.append(
                {
                    "id": llr.id,
                    "description": llr.description,
                    "methods": methods,
                }
            )

        # Design node and triple counts from Neo4j
        total_nodes = 0
        total_triples = 0
        try:
            from services.dependencies import get_neo4j
            with get_neo4j().session() as ns:
                rec = ns.run("MATCH (d:Design) RETURN count(d) AS cnt").single()
                total_nodes = rec["cnt"] if rec else 0
                rec2 = ns.run(
                    "MATCH (:Design)-[r]->(:Design) RETURN count(r) AS cnt"
                ).single()
                total_triples = rec2["cnt"] if rec2 else 0
        except Exception:
            log.warning("Failed to fetch Neo4j design counts", exc_info=True)

        return {
            "hlrs": hlrs,
            "unlinked_llrs": unlinked,
            "total_hlrs": session.query(HighLevelRequirement).count(),
            "total_llrs": session.query(LowLevelRequirement).count(),
            "total_verifications": session.query(VerificationMethod).count(),
            "total_nodes": total_nodes,
            "total_triples": total_triples,
        }


def fetch_hlr_detail(hlr_id):
    """Fetch all data needed for HLR detail page.

    Triple data now comes from Neo4j TRACES_TO edges instead of
    SQLAlchemy M2M tables.
    """
    with get_session() as session:
        hlr = session.query(HighLevelRequirement).filter_by(id=hlr_id).first()
        if not hlr:
            return None

        llrs = []
        for llr in hlr.low_level_requirements:
            methods = [v.method for v in llr.verifications]
            llrs.append(
                {
                    "id": llr.id,
                    "description": llr.description,
                    "methods": methods,
                }
            )

        # Fetch triples from Neo4j TRACES_TO edges
        triples = []
        try:
            from services.dependencies import get_neo4j
            with get_neo4j().session() as ns:
                result = ns.run(
                    """
                    MATCH (hlr:HLR {sqlite_id: $hid})-[:TRACES_TO]->(d:Design)
                    OPTIONAL MATCH (d)-[r]->(d2:Design)
                    WHERE type(r) <> 'IMPLEMENTED_BY' AND type(r) <> 'TRACES_TO'
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

        return {
            "id": hlr.id,
            "description": hlr.description,
            "component": hlr.component.name if hlr.component else None,
            "component_id": hlr.component_id,
            "llrs": llrs,
            "triples": triples,
        }


def create_hlr(description: str, component_id: int | None = None) -> int:
    """Create a new HLR. Also creates a :HLR stub in Neo4j.

    Returns the new HLR id.
    """
    with get_session() as session:
        hlr = HighLevelRequirement(
            description=description,
            component_id=component_id or None,
        )
        session.add(hlr)
        session.flush()
        hlr_id = hlr.id

    # Create HLR stub in Neo4j
    try:
        from services.dependencies import get_neo4j
        from backend.db.neo4j.repositories.design import DesignRepository
        with get_neo4j().session() as ns:
            repo = DesignRepository(ns)
            repo.merge_hlr_stub(sqlite_id=hlr_id, description=description)
    except Exception:
        log.warning("Failed to create HLR stub in Neo4j for HLR %d", hlr_id, exc_info=True)

    return hlr_id


def update_hlr(hlr_id: int, description: str, component_id: int | None = None) -> bool:
    """Update an HLR's description and component. Also updates the Neo4j stub.

    Returns True on success.
    """
    with get_session() as session:
        hlr = session.query(HighLevelRequirement).filter_by(id=hlr_id).first()
        if not hlr:
            return False
        hlr.description = description
        hlr.component_id = component_id or None

    # Update HLR stub in Neo4j
    try:
        from services.dependencies import get_neo4j
        with get_neo4j().session() as ns:
            ns.run(
                "MATCH (h:HLR {sqlite_id: $hid}) SET h.description = $desc",
                {"hid": hlr_id, "desc": description},
            )
    except Exception:
        log.warning("Failed to update HLR stub in Neo4j", exc_info=True)

    return True


def delete_hlr(hlr_id: int) -> bool:
    """Delete an HLR and its child LLRs. Also removes Neo4j stubs.

    Returns True on success.
    """
    with get_session() as session:
        hlr = session.query(HighLevelRequirement).filter_by(id=hlr_id).first()
        if not hlr:
            return False
        # Delete child LLRs first (cascade handles verifications)
        for llr in hlr.low_level_requirements:
            session.delete(llr)
        session.delete(hlr)

    # Remove HLR stub and its TRACES_TO edges from Neo4j
    try:
        from services.dependencies import get_neo4j
        with get_neo4j().session() as ns:
            ns.run(
                "MATCH (h:HLR {sqlite_id: $hid}) DETACH DELETE h",
                {"hid": hlr_id},
            )
    except Exception:
        log.warning("Failed to remove HLR stub from Neo4j", exc_info=True)

    return True


def decompose_hlr(hlr_id: int) -> dict:
    """Run the decomposition agent on an HLR and persist results.

    Also creates :LLR stubs and DECOMPOSES_INTO edges in Neo4j.

    Returns dict with llrs_created and verifications_created.
    """
    import os

    from backend.ticketing_agent.decompose.decompose_hlr import decompose
    from backend.requirements.services.persistence import persist_decomposition

    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
    os.makedirs(log_dir, exist_ok=True)
    prompt_log_file = os.path.join(log_dir, f"decompose_hlr{hlr_id}_raw.txt")

    with get_session() as session:
        hlr = session.query(HighLevelRequirement).filter_by(id=hlr_id).first()
        if not hlr:
            raise ValueError(f"HLR {hlr_id} not found")

        siblings = (
            session.query(HighLevelRequirement)
            .filter(
                HighLevelRequirement.id != hlr_id,
            )
            .all()
        )
        other_hlrs = [
            {
                "id": s.id,
                "description": s.description,
                "component__name": s.component.name if s.component else None,
            }
            for s in siblings
        ]

        decomposed = decompose(
            description=hlr.description,
            other_hlrs=other_hlrs,
            component=hlr.component.name if hlr.component else "",
            dependency_context=hlr.dependency_context,
            prompt_log_file=prompt_log_file,
        )

        result = persist_decomposition(session, hlr, decomposed.low_level_requirements)
        return {
            "llrs_created": result.llrs_created,
            "verifications_created": result.verifications_created,
        }


def design_single_hlr(hlr_id: int) -> dict:
    """Run the design agent on an HLR and persist the ontology results.

    Returns dict with nodes_created, triples_created, links_applied.
    """
    import os

    from backend.ticketing_agent.design.design_per_hlr import design_and_persist_hlr

    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
    os.makedirs(log_dir, exist_ok=True)

    return design_and_persist_hlr(hlr_id, log_dir=log_dir)