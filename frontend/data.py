"""Data-fetching functions for UI pages. Run in threads via asyncio.to_thread."""

import logging

from db import get_session
from db.models import (
    Component,
    HighLevelRequirement,
    LowLevelRequirement,
    OntologyNode,
    OntologyTriple,
    Predicate,
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


def fetch_components_data():
    """Fetch all data needed for components page."""
    with get_session() as session:
        result = []
        for comp in session.query(Component).all():
            result.append({
                "name": comp.name,
                "language": repr(comp.language) if comp.language else None,
                "parent": comp.parent.name if comp.parent else None,
                "hlr_count": len(comp.high_level_requirements),
                "node_count": len(comp.ontology_nodes),
            })
        return result


def fetch_ontology_data():
    """Fetch all data needed for ontology page."""
    with get_session() as session:
        nodes = []
        kind_counts = {}
        for n in session.query(OntologyNode).all():
            kind_counts[n.kind] = kind_counts.get(n.kind, 0) + 1
            nodes.append({
                "name": n.name,
                "kind": n.kind,
                "qualified_name": n.qualified_name,
                "component": n.component.name if n.component else "-",
            })

        return {
            "nodes": nodes[:200],
            "kind_counts": kind_counts,
            "total_nodes": len(nodes),
            "total_triples": session.query(OntologyTriple).count(),
            "total_predicates": session.query(Predicate).count(),
        }


# ---------------------------------------------------------------------------
# Mutations — requirements
# ---------------------------------------------------------------------------

def fetch_components_options():
    """Return list of {id, name} for component dropdowns."""
    with get_session() as session:
        return [
            {"id": c.id, "name": c.name}
            for c in session.query(Component).order_by(Component.name).all()
        ]


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


def decompose_hlr(hlr_id: int) -> dict:
    """Run the decomposition agent on an HLR and persist results.

    Returns dict with llrs_created and verifications_created.
    """
    from requirements.agents.decompose_hlr import decompose
    from requirements.services.persistence import persist_decomposition

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
        )

        result = persist_decomposition(session, hlr, decomposed.low_level_requirements)
        return {
            "llrs_created": result.llrs_created,
            "verifications_created": result.verifications_created,
        }


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


# ---------------------------------------------------------------------------
# Neo4j-backed graph data
# ---------------------------------------------------------------------------

def fetch_ontology_graph_data(
    kind_filter: str | None = None,
    search: str | None = None,
    component_id: int | None = None,
) -> dict:
    """Fetch design graph from Neo4j for Cytoscape.js rendering."""
    try:
        from db.neo4j_queries import fetch_design_graph
        return fetch_design_graph(kind_filter, search, component_id)
    except Exception:
        log.warning("Neo4j query failed — returning empty graph", exc_info=True)
        return {"nodes": [], "edges": []}


def fetch_hlr_graph_data(hlr_id: int, component_id: int | None = None) -> dict:
    """Fetch the ontology subgraph around an HLR for Cytoscape.js."""
    try:
        from db.neo4j_queries import fetch_hlr_subgraph
        return fetch_hlr_subgraph(hlr_id, component_id)
    except Exception:
        log.warning("Neo4j HLR subgraph query failed — returning empty graph", exc_info=True)
        return {"nodes": [], "edges": []}


def fetch_graph_node_detail(qualified_name: str) -> dict | None:
    """Fetch node detail from Neo4j (properties + relationships + requirements)."""
    try:
        from db.neo4j_queries import fetch_node_detail
        return fetch_node_detail(qualified_name)
    except Exception:
        log.warning("Neo4j node detail query failed", exc_info=True)
        return None


def fetch_node_detail_full(node_id: int) -> dict | None:
    """Fetch ontology node by SQLite id with all properties + Neo4j relationships."""
    with get_session() as session:
        node = session.query(OntologyNode).filter_by(id=node_id).first()
        if not node:
            return None

        node_data = {
            "id": node.id,
            "name": node.name,
            "qualified_name": node.qualified_name,
            "kind": node.kind,
            "specialization": node.specialization or "",
            "visibility": node.visibility or "",
            "description": node.description or "",
            "component": node.component.name if node.component else "",
            "component_id": node.component_id,
            "type_signature": node.type_signature or "",
            "argsstring": node.argsstring or "",
            "definition": node.definition or "",
            "file_path": node.file_path or "",
            "line_number": node.line_number,
            "refid": node.refid or "",
            "source_type": node.source_type or "",
            "is_static": node.is_static,
            "is_const": node.is_const,
            "is_virtual": node.is_virtual,
            "is_abstract": node.is_abstract,
            "is_final": node.is_final,
        }

    # Fetch Neo4j relationships if available
    neo4j_data = None
    if node_data["qualified_name"]:
        neo4j_data = fetch_graph_node_detail(node_data["qualified_name"])

    return {"node": node_data, "neo4j": neo4j_data}


def resolve_node_id_by_qualified_name(qualified_name: str) -> int | None:
    """Look up the SQLite id for an ontology node by qualified_name."""
    with get_session() as session:
        node = session.query(OntologyNode).filter_by(
            qualified_name=qualified_name
        ).first()
        return node.id if node else None
