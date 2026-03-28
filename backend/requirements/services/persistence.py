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

from backend.db import get_or_create
from backend.db.models import (
    HighLevelRequirement,
    LowLevelRequirement,
    OntologyNode,
    OntologyTriple,
    Predicate,
    VerificationAction,
    VerificationCondition,
    VerificationMethod,
)
from backend.codebase.schemas import DesignSchema
from backend.requirements.schemas import LowLevelRequirementSchema, VerificationSchema


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


@dataclass
class VerificationValidationReport:
    """Report from validating member_qualified_name references against the ontology."""
    resolved: list[tuple[str, str]] = field(default_factory=list)   # (member_qname, matched_node_qname)
    unresolved: list[tuple[str, str]] = field(default_factory=list)  # (member_qname, context)

    @property
    def all_resolved(self) -> bool:
        return len(self.unresolved) == 0


@dataclass
class AugmentResult:
    """Result of creating missing design nodes for unresolved verification references."""
    nodes_created: int = 0
    triples_created: int = 0


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
# Verification context building
# ---------------------------------------------------------------------------

def build_verification_context(session: Session) -> list[dict]:
    """Build structured class-level context for the verification agent.

    Returns a list of class-context dicts with grouped members and relationships,
    suitable for rendering as a PlantUML-like prompt section.
    """
    from backend.db.models.ontology import TYPE_KINDS, VALUE_KINDS

    # Load all nodes
    all_nodes = session.query(OntologyNode).all()
    node_by_id: dict[int, OntologyNode] = {n.id: n for n in all_nodes}
    node_by_qn: dict[str, OntologyNode] = {n.qualified_name: n for n in all_nodes}

    # Load all triples
    all_triples = session.query(OntologyTriple).all()

    # Build class contexts
    class_contexts = []
    for n in all_nodes:
        if n.kind not in TYPE_KINDS:
            continue

        attrs = []
        methods = []
        relationships = []

        for t in all_triples:
            if t.subject_id != n.id:
                continue
            obj = node_by_id.get(t.object_id)
            pred = t.predicate
            if obj is None or pred is None:
                continue

            if pred.name == "composes" and obj.kind in VALUE_KINDS:
                member = {
                    "name": obj.name,
                    "qualified_name": obj.qualified_name,
                    "kind": obj.kind,
                    "visibility": obj.visibility or "",
                    "type_signature": obj.type_signature or "",
                    "argsstring": obj.argsstring or "",
                    "description": obj.description or "",
                }
                if obj.kind in ("attribute", "constant"):
                    attrs.append(member)
                else:
                    methods.append(member)
            elif pred.name != "composes":
                relationships.append({
                    "predicate": pred.name,
                    "target": obj.qualified_name,
                    "target_name": obj.name,
                })

        class_contexts.append({
            "qualified_name": n.qualified_name,
            "kind": n.kind,
            "description": n.description or "",
            "attributes": sorted(attrs, key=lambda a: a["name"]),
            "methods": sorted(methods, key=lambda m: m["name"]),
            "relationships": relationships,
        })

    return sorted(class_contexts, key=lambda c: c["qualified_name"])


# ---------------------------------------------------------------------------
# Verification reference validation
# ---------------------------------------------------------------------------

def validate_verification_references(
    verifications: list[VerificationSchema],
    ontology_nodes: list[dict],
) -> VerificationValidationReport:
    """Validate all member_qualified_name values against existing ontology nodes.

    Returns a report of resolved and unresolved references.
    """
    known_qnames = {n["qualified_name"] for n in ontology_nodes}
    report = VerificationValidationReport()

    def _check(member_qname: str, context: str):
        if not member_qname:
            return
        # Exact match
        if member_qname in known_qnames:
            report.resolved.append((member_qname, member_qname))
            return
        # Longest-prefix match
        best = ""
        for qn in known_qnames:
            if member_qname.startswith(qn) and len(qn) > len(best):
                best = qn
        if best:
            report.resolved.append((member_qname, best))
        else:
            report.unresolved.append((member_qname, context))

    for v in verifications:
        for cond in v.preconditions:
            _check(cond.member_qualified_name, "precondition")
        for action in v.actions:
            _check(action.member_qualified_name, "action")
        for cond in v.postconditions:
            _check(cond.member_qualified_name, "postcondition")

    return report


# ---------------------------------------------------------------------------
# Closed-loop design augmentation
# ---------------------------------------------------------------------------

def augment_design_for_unresolved(
    session: Session,
    unresolved: list[tuple[str, str]],
) -> AugmentResult:
    """Create missing ontology nodes for unresolved verification references.

    For each unresolved member_qualified_name, parse the parent class from the
    qualified name, look it up, and create the missing member node + COMPOSES
    triple. Infers kind from context (action → method, condition → attribute).

    After creating nodes, re-links any VerificationCondition/VerificationAction
    rows that had NULL ontology_node_id.
    """
    result = AugmentResult()
    if not unresolved:
        return result

    # Ensure the "composes" predicate exists
    Predicate.ensure_defaults(session)
    composes_pred = session.query(Predicate).filter_by(name="composes").first()

    created_nodes: dict[str, OntologyNode] = {}

    for member_qname, context in unresolved:
        if "::" not in member_qname:
            continue
        if member_qname in created_nodes:
            continue

        # Parse parent and member name
        parent_qname, member_name = member_qname.rsplit("::", 1)
        parent = session.query(OntologyNode).filter_by(
            qualified_name=parent_qname,
        ).first()
        if parent is None:
            log.debug(
                "augment: parent %s not found for %s, skipping",
                parent_qname, member_qname,
            )
            continue

        # Infer kind from context
        kind = "method" if context == "action" else "attribute"

        # Create the node
        node, created = get_or_create(
            session, OntologyNode,
            defaults={
                "kind": kind,
                "name": member_name,
                "source_type": "member",
                "visibility": "public",
                "component_id": parent.component_id,
            },
            qualified_name=member_qname,
        )
        if created:
            result.nodes_created += 1
            created_nodes[member_qname] = node
            log.info("augment: created %s node %s", kind, member_qname)

            # Create COMPOSES triple
            session.flush()
            if composes_pred:
                _, triple_created = get_or_create(
                    session, OntologyTriple,
                    subject_id=parent.id,
                    predicate_id=composes_pred.id,
                    object_id=node.id,
                )
                if triple_created:
                    result.triples_created += 1

    session.flush()

    # Re-link verification records with NULL ontology_node_id
    if created_nodes:
        qn_to_node = {
            n.qualified_name: n
            for n in session.query(OntologyNode).all()
        }
        for vc in session.query(VerificationCondition).filter(
            VerificationCondition.ontology_node_id.is_(None),
            VerificationCondition.member_qualified_name != "",
        ).all():
            node = qn_to_node.get(vc.member_qualified_name)
            if node:
                vc.ontology_node_id = node.id

        for va in session.query(VerificationAction).filter(
            VerificationAction.ontology_node_id.is_(None),
            VerificationAction.member_qualified_name != "",
        ).all():
            node = qn_to_node.get(va.member_qualified_name)
            if node:
                va.ontology_node_id = node.id

        session.flush()

    # Neo4j sync
    if created_nodes:
        try:
            new_triples = session.query(OntologyTriple).filter(
                OntologyTriple.object_id.in_([n.id for n in created_nodes.values()])
            ).all()
            from backend.db.neo4j_sync import try_sync_design_nodes_and_triples
            try_sync_design_nodes_and_triples(
                list(created_nodes.values()), new_triples,
            )
        except Exception:
            log.warning("Neo4j augment sync failed", exc_info=True)

    return result


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
        from backend.db.neo4j_sync import try_sync_requirement
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
        from backend.db.neo4j_sync import try_sync_design_nodes_and_triples
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
