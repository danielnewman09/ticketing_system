"""
Service layer for persisting agent outputs to the database.

Consolidates the persistence logic used by demo.py, the MCP server,
and Django views into a single place.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.db import transaction

from codebase.models import OntologyNode, OntologyTriple, Predicate
from codebase.schemas import DesignSchema
from requirements.models import (
    HighLevelRequirement,
    LowLevelRequirement,
    VerificationAction,
    VerificationCondition,
    VerificationMethod,
)
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
    member_qname: str,
    node_list: list[dict] | None = None,
) -> OntologyNode | None:
    """Resolve a member qualified name to an OntologyNode via longest prefix match.

    Args:
        member_qname: The member qualified name to resolve (e.g.
            "calc::core::Calculator::operand_a").
        node_list: Optional pre-fetched list of dicts with at least
            "qualified_name" and "pk" keys.  If None, queries the DB.

    Returns:
        The matching OntologyNode, or None if no prefix matches.
    """
    if not member_qname:
        return None

    if node_list is None:
        node_list = [
            {"qualified_name": qn, "pk": pk}
            for qn, pk in OntologyNode.objects.values_list("qualified_name", "pk")
        ]

    # Longest prefix match
    best_match = None
    best_len = 0
    for node in node_list:
        qn = node["qualified_name"]
        if member_qname.startswith(qn) and len(qn) > best_len:
            best_match = node
            best_len = len(qn)

    if best_match is None:
        return None
    return OntologyNode.objects.filter(pk=best_match["pk"]).first()


# ---------------------------------------------------------------------------
# 1. Decomposition persistence
# ---------------------------------------------------------------------------

def persist_decomposition(
    hlr: HighLevelRequirement,
    llrs: list[LowLevelRequirementSchema],
) -> DecompositionResult:
    """Create LLRs (with verification stubs) under an existing HLR.

    Wraps the writes in a transaction.
    """
    result = DecompositionResult()

    with transaction.atomic():
        for llr_data in llrs:
            llr = LowLevelRequirement.objects.create(
                high_level_requirement=hlr,
                description=llr_data.description,
            )
            result.llrs_created += 1

            for v in llr_data.verifications:
                VerificationMethod.objects.create(
                    low_level_requirement=llr,
                    method=v.method,
                    test_name=v.test_name,
                    description=v.description,
                )
                result.verifications_created += 1

    return result


# ---------------------------------------------------------------------------
# 2. Design persistence (ontology nodes, triples, requirement links)
# ---------------------------------------------------------------------------

def persist_design(
    design: DesignSchema,
    qname_to_node: dict[str, OntologyNode] | None = None,
) -> DesignResult:
    """Create ontology nodes, triples, and requirement-to-triple links.

    Args:
        design: DesignSchema with nodes, triples, and requirement_links.
        qname_to_node: Optional pre-existing node lookup. When processing
            multiple designs in a batch (e.g. per-HLR loop), pass the same
            dict across calls so cross-HLR references resolve. New nodes
            are added to this dict in-place.
    """
    if qname_to_node is None:
        qname_to_node = {}

    result = DesignResult(qname_to_node=qname_to_node)

    with transaction.atomic():
        # --- Nodes ---
        for node_data in design.nodes:
            if node_data.qualified_name in qname_to_node:
                result.nodes_existing += 1
                continue

            node, created = OntologyNode.objects.get_or_create(
                qualified_name=node_data.qualified_name,
                defaults={
                    "kind": node_data.kind,
                    "specialization": node_data.specialization,
                    "visibility": node_data.visibility,
                    "name": node_data.name,
                    "description": node_data.description,
                    "compound_refid": node_data.qualified_name,
                    "component_id": node_data.component_id,
                    "is_intercomponent": node_data.is_intercomponent,
                },
            )
            qname_to_node[node_data.qualified_name] = node
            if created:
                result.nodes_created += 1
            else:
                result.nodes_existing += 1

        # --- Triples (order matters for index-based requirement links) ---
        saved_triples: list[OntologyTriple | None] = []
        for triple_data in design.triples:
            subj = qname_to_node.get(triple_data.subject_qualified_name)
            obj = qname_to_node.get(triple_data.object_qualified_name)
            pred = Predicate.objects.filter(name=triple_data.predicate).first()

            if subj and obj and pred:
                triple, _ = OntologyTriple.objects.get_or_create(
                    subject=subj, predicate=pred, object=obj,
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
                req = HighLevelRequirement.objects.filter(pk=link.requirement_id).first()
            else:
                req = LowLevelRequirement.objects.filter(pk=link.requirement_id).first()

            if req:
                req.triples.add(triple)
                result.links_applied += 1
            else:
                result.links_skipped += 1

    return result


# ---------------------------------------------------------------------------
# 3. Verification persistence
# ---------------------------------------------------------------------------

def persist_verification(
    llr: LowLevelRequirement,
    verifications: list[VerificationSchema],
    ontology_nodes: list[dict] | None = None,
) -> VerificationResult:
    """Replace an LLR's verification methods with fleshed-out versions.

    Deletes all existing verifications for the LLR, then creates new ones
    with preconditions, actions, and postconditions.

    Args:
        llr: The LLR to update.
        verifications: List of VerificationSchema from the verify agent.
        ontology_nodes: Optional pre-fetched list of dicts with at least
            "qualified_name" and "pk" keys. If None, queries the DB.
    """
    if ontology_nodes is None:
        ontology_nodes = [
            {"qualified_name": qn, "pk": pk}
            for qn, pk in OntologyNode.objects.values_list("qualified_name", "pk")
        ]

    result = VerificationResult()

    def _save_conditions(vm, conditions, phase):
        for i, cond in enumerate(conditions):
            VerificationCondition.objects.create(
                verification=vm,
                phase=phase,
                order=i,
                ontology_node=resolve_ontology_node(
                    cond.member_qualified_name, ontology_nodes,
                ),
                member_qualified_name=cond.member_qualified_name,
                operator=cond.operator,
                expected_value=cond.expected_value,
            )
            result.conditions_created += 1

    with transaction.atomic():
        llr.verifications.all().delete()

        for v in verifications:
            vm = VerificationMethod.objects.create(
                low_level_requirement=llr,
                method=v.method,
                test_name=v.test_name,
                description=v.description,
            )
            result.verifications_saved += 1

            _save_conditions(vm, v.preconditions, "pre")

            for i, action in enumerate(v.actions):
                VerificationAction.objects.create(
                    verification=vm,
                    order=i,
                    description=action.description,
                    ontology_node=resolve_ontology_node(
                        action.member_qualified_name, ontology_nodes,
                    ),
                    member_qualified_name=action.member_qualified_name,
                )
                result.actions_created += 1

            _save_conditions(vm, v.postconditions, "post")

    return result
