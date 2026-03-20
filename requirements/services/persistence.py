"""
Service layer for persisting agent outputs to the database.

Consolidates the persistence logic used by demo.py, the MCP server,
and NiceGUI views into a single place.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

from db import get_or_create
from db.models import (
    HighLevelRequirement,
    LowLevelRequirement,
    OntologyNode,
    OntologyTriple,
    Predicate,
    VerificationAction,
    VerificationCondition,
    VerificationMethod,
)
from codebase.schemas import DesignSchema
from requirements.schemas import LowLevelRequirementSchema, VerificationSchema


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class DecompositionResult:
    llrs_created: int = 0
    verifications_created: int = 0


@dataclass
class DesignResult:
    nodes_created: int = 0
    nodes_existing: int = 0
    triples_created: int = 0
    triples_skipped: int = 0
    links_applied: int = 0
    links_skipped: int = 0
    qname_to_node: dict[str, OntologyNode] = field(default_factory=dict)


@dataclass
class VerificationResult:
    verifications_saved: int = 0
    conditions_created: int = 0
    actions_created: int = 0


# ---------------------------------------------------------------------------
# Ontology node resolution
# ---------------------------------------------------------------------------

def resolve_ontology_node(
    session: Session,
    member_qname: str,
    node_list: list[dict] | None = None,
) -> OntologyNode | None:
    """Resolve a member qualified name to an OntologyNode via longest prefix match."""
    if not member_qname:
        return None

    if node_list is None:
        node_list = [
            {"qualified_name": n.qualified_name, "pk": n.id}
            for n in session.query(OntologyNode.qualified_name, OntologyNode.id).all()
        ]

    best_match = None
    best_len = 0
    for node in node_list:
        qn = node["qualified_name"]
        if member_qname.startswith(qn) and len(qn) > best_len:
            best_match = node
            best_len = len(qn)

    if best_match is None:
        return None
    return session.query(OntologyNode).filter_by(id=best_match["pk"]).first()


# ---------------------------------------------------------------------------
# 1. Decomposition persistence
# ---------------------------------------------------------------------------

def persist_decomposition(
    session: Session,
    hlr: HighLevelRequirement,
    llrs: list[LowLevelRequirementSchema],
) -> DecompositionResult:
    """Create LLRs (with verification stubs) under an existing HLR."""
    result = DecompositionResult()

    for llr_data in llrs:
        llr = LowLevelRequirement(
            high_level_requirement=hlr,
            description=llr_data.description,
        )
        session.add(llr)
        session.flush()
        result.llrs_created += 1

        for v in llr_data.verifications:
            vm = VerificationMethod(
                low_level_requirement=llr,
                method=v.method,
                test_name=v.test_name,
                description=v.description,
            )
            session.add(vm)
            result.verifications_created += 1

    session.flush()

    # -- Neo4j dual-write (best-effort) --
    try:
        from db.neo4j_sync import try_sync_requirement
        for llr_obj in hlr.low_level_requirements:
            try_sync_requirement(llr_obj, "LLR", hlr=hlr)
    except Exception:
        log.warning("Neo4j decomposition sync failed — will catch up via migration script", exc_info=True)

    return result


# ---------------------------------------------------------------------------
# 2. Design persistence (ontology nodes, triples, requirement links)
# ---------------------------------------------------------------------------

def persist_design(
    session: Session,
    design: DesignSchema,
    qname_to_node: dict[str, OntologyNode] | None = None,
) -> DesignResult:
    """Create ontology nodes, triples, and requirement-to-triple links."""
    if qname_to_node is None:
        qname_to_node = {}

    result = DesignResult(qname_to_node=qname_to_node)

    # --- Nodes ---
    for node_data in design.nodes:
        if node_data.qualified_name in qname_to_node:
            result.nodes_existing += 1
            continue

        node, created = get_or_create(
            session, OntologyNode,
            defaults={
                "kind": node_data.kind,
                "specialization": node_data.specialization,
                "visibility": node_data.visibility,
                "name": node_data.name,
                "description": node_data.description,
                "refid": node_data.qualified_name,
                "component_id": node_data.component_id,
                "is_intercomponent": node_data.is_intercomponent,
                "source_type": node_data.source_type,
                "type_signature": node_data.type_signature,
                "argsstring": node_data.argsstring,
                "definition": node_data.definition,
                "file_path": node_data.file_path,
                "line_number": node_data.line_number,
                "is_static": node_data.is_static,
                "is_const": node_data.is_const,
                "is_virtual": node_data.is_virtual,
                "is_abstract": node_data.is_abstract,
                "is_final": node_data.is_final,
            },
            qualified_name=node_data.qualified_name,
        )
        qname_to_node[node_data.qualified_name] = node
        if created:
            result.nodes_created += 1
        else:
            result.nodes_existing += 1

    # --- Triples ---
    saved_triples: list[OntologyTriple | None] = []
    for triple_data in design.triples:
        subj = qname_to_node.get(triple_data.subject_qualified_name)
        obj = qname_to_node.get(triple_data.object_qualified_name)
        pred = session.query(Predicate).filter_by(name=triple_data.predicate).first()

        if subj and obj and pred:
            triple, _ = get_or_create(
                session, OntologyTriple,
                subject_id=subj.id, predicate_id=pred.id, object_id=obj.id,
            )
            saved_triples.append(triple)
            result.triples_created += 1
        else:
            saved_triples.append(None)
            result.triples_skipped += 1

    # --- Requirement links ---
    for link in design.requirement_links:
        triple = None
        if 0 <= link.triple_index < len(saved_triples):
            triple = saved_triples[link.triple_index]

        if not triple:
            result.links_skipped += 1
            continue

        if link.requirement_type == "hlr":
            req = session.query(HighLevelRequirement).filter_by(id=link.requirement_id).first()
        else:
            req = session.query(LowLevelRequirement).filter_by(id=link.requirement_id).first()

        if req:
            req.triples.append(triple)
            result.links_applied += 1
        else:
            result.links_skipped += 1

    session.flush()

    # -- Neo4j dual-write (best-effort) --
    try:
        from db.neo4j_sync import try_sync_design_nodes_and_triples
        created_nodes = [
            qname_to_node[nd.qualified_name]
            for nd in design.nodes
            if nd.qualified_name in qname_to_node
        ]
        created_triples = [t for t in saved_triples if t is not None]
        try_sync_design_nodes_and_triples(created_nodes, created_triples)
    except Exception:
        log.warning("Neo4j design sync failed — will catch up via migration script", exc_info=True)

    return result


# ---------------------------------------------------------------------------
# 3. Verification persistence
# ---------------------------------------------------------------------------

def persist_verification(
    session: Session,
    llr: LowLevelRequirement,
    verifications: list[VerificationSchema],
    ontology_nodes: list[dict] | None = None,
) -> VerificationResult:
    """Replace an LLR's verification methods with fleshed-out versions."""
    if ontology_nodes is None:
        ontology_nodes = [
            {"qualified_name": n.qualified_name, "pk": n.id}
            for n in session.query(OntologyNode.qualified_name, OntologyNode.id).all()
        ]

    result = VerificationResult()

    def _save_conditions(vm, conditions, phase):
        for i, cond in enumerate(conditions):
            vc = VerificationCondition(
                verification=vm,
                phase=phase,
                order=i,
                ontology_node=resolve_ontology_node(
                    session, cond.member_qualified_name, ontology_nodes,
                ),
                member_qualified_name=cond.member_qualified_name,
                operator=cond.operator,
                expected_value=cond.expected_value,
            )
            session.add(vc)
            result.conditions_created += 1

    # Delete existing verifications
    for vm in list(llr.verifications):
        session.delete(vm)
    session.flush()

    for v in verifications:
        vm = VerificationMethod(
            low_level_requirement=llr,
            method=v.method,
            test_name=v.test_name,
            description=v.description,
        )
        session.add(vm)
        session.flush()
        result.verifications_saved += 1

        _save_conditions(vm, v.preconditions, "pre")

        for i, action in enumerate(v.actions):
            va = VerificationAction(
                verification=vm,
                order=i,
                description=action.description,
                ontology_node=resolve_ontology_node(
                    session, action.member_qualified_name, ontology_nodes,
                ),
                member_qualified_name=action.member_qualified_name,
            )
            session.add(va)
            result.actions_created += 1

        _save_conditions(vm, v.postconditions, "post")

    session.flush()
    return result
