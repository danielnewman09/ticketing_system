"""LLR CRUD and detail data."""

from backend.db import get_session
from backend.db.models import LowLevelRequirement


def fetch_llr_detail(llr_id):
    """Fetch all data needed for LLR detail page."""
    with get_session() as session:
        llr = session.query(LowLevelRequirement).filter_by(id=llr_id).first()
        if not llr:
            return None

        hlr = llr.high_level_requirement
        hlr_data = None
        if hlr:
            hlr_data = {
                "id": hlr.id,
                "description": hlr.description,
                "component": hlr.component.name if hlr.component else None,
            }

        verifications = []
        for v in llr.verifications:
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

        components = [c.name for c in llr.components]

        triples = [
            {
                "subject": t.subject.name,
                "predicate": t.predicate.name,
                "object": t.object.name,
            }
            for t in llr.triples
        ]

        return {
            "id": llr.id,
            "description": llr.description,
            "hlr": hlr_data,
            "verifications": verifications,
            "components": components,
            "triples": triples,
        }


def create_llr(hlr_id: int, description: str) -> int:
    """Create a new LLR under an HLR. Returns the new LLR id."""
    with get_session() as session:
        llr = LowLevelRequirement(
            high_level_requirement_id=hlr_id,
            description=description,
        )
        session.add(llr)
        session.flush()
        return llr.id


def update_llr(llr_id: int, description: str) -> bool:
    """Update an LLR's description. Returns True on success."""
    with get_session() as session:
        llr = session.query(LowLevelRequirement).filter_by(id=llr_id).first()
        if not llr:
            return False
        llr.description = description
        return True


def delete_llr(llr_id: int) -> bool:
    """Delete an LLR. Returns True on success."""
    with get_session() as session:
        llr = session.query(LowLevelRequirement).filter_by(id=llr_id).first()
        if not llr:
            return False
        session.delete(llr)
        return True
