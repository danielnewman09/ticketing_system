"""HLR CRUD, decomposition, and requirements dashboard data."""

from backend.db import get_session
from backend.db.models import (
    HighLevelRequirement,
    LowLevelRequirement,
    OntologyNode,
    OntologyTriple,
    VerificationMethod,
)


def fetch_requirements_data():
    """Fetch all data needed for the requirements dashboard."""
    with get_session() as session:
        hlrs = []
        for hlr in session.query(HighLevelRequirement).all():
            llrs = []
            for llr in hlr.low_level_requirements:
                methods = [v.method for v in llr.verifications]
                llrs.append({
                    "id": llr.id,
                    "description": llr.description,
                    "methods": methods,
                })
            hlrs.append({
                "id": hlr.id,
                "description": hlr.description,
                "component": hlr.component.name if hlr.component else None,
                "llrs": llrs,
            })

        unlinked = []
        for llr in session.query(LowLevelRequirement).filter(
            LowLevelRequirement.high_level_requirement_id.is_(None),
        ).all():
            methods = [v.method for v in llr.verifications]
            unlinked.append({
                "id": llr.id,
                "description": llr.description,
                "methods": methods,
            })

        return {
            "hlrs": hlrs,
            "unlinked_llrs": unlinked,
            "total_hlrs": session.query(HighLevelRequirement).count(),
            "total_llrs": session.query(LowLevelRequirement).count(),
            "total_verifications": session.query(VerificationMethod).count(),
            "total_nodes": session.query(OntologyNode).count(),
            "total_triples": session.query(OntologyTriple).count(),
        }


def fetch_hlr_detail(hlr_id):
    """Fetch all data needed for HLR detail page."""
    with get_session() as session:
        hlr = session.query(HighLevelRequirement).filter_by(id=hlr_id).first()
        if not hlr:
            return None

        llrs = []
        for llr in hlr.low_level_requirements:
            methods = [v.method for v in llr.verifications]
            llrs.append({
                "id": llr.id,
                "description": llr.description,
                "methods": methods,
            })

        all_triples = set(hlr.triples)
        for llr_obj in hlr.low_level_requirements:
            all_triples.update(llr_obj.triples)
        triples = [
            {
                "subject": t.subject.name,
                "predicate": t.predicate.name,
                "object": t.object.name,
            }
            for t in sorted(all_triples, key=lambda t: t.id)
        ]

        return {
            "id": hlr.id,
            "description": hlr.description,
            "component": hlr.component.name if hlr.component else None,
            "component_id": hlr.component_id,
            "llrs": llrs,
            "triples": triples,
        }


def create_hlr(description: str, component_id: int | None = None) -> int:
    """Create a new HLR. Returns the new HLR id."""
    with get_session() as session:
        hlr = HighLevelRequirement(
            description=description,
            component_id=component_id or None,
        )
        session.add(hlr)
        session.flush()
        return hlr.id


def update_hlr(hlr_id: int, description: str, component_id: int | None = None) -> bool:
    """Update an HLR's description and component. Returns True on success."""
    with get_session() as session:
        hlr = session.query(HighLevelRequirement).filter_by(id=hlr_id).first()
        if not hlr:
            return False
        hlr.description = description
        hlr.component_id = component_id or None
        return True


def delete_hlr(hlr_id: int) -> bool:
    """Delete an HLR and its child LLRs. Returns True on success."""
    with get_session() as session:
        hlr = session.query(HighLevelRequirement).filter_by(id=hlr_id).first()
        if not hlr:
            return False
        # Delete child LLRs first (cascade handles verifications)
        for llr in hlr.low_level_requirements:
            session.delete(llr)
        session.delete(hlr)
        return True


def decompose_hlr(hlr_id: int) -> dict:
    """Run the decomposition agent on an HLR and persist results.

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

        siblings = session.query(HighLevelRequirement).filter(
            HighLevelRequirement.id != hlr_id,
        ).all()
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
