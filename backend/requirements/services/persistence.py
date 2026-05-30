"""Service layer for persisting agent outputs to the database.

Consolidates the persistence logic used by the MCP server,
pipeline, and NiceGUI views into a single place.

Phase 3: All verification data is persisted to Neo4j via
VerificationRepository. HLR/LLR data uses RequirementRepository.
Design data uses DesignRepository. SQLAlchemy is not used for
requirements or verification data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from backend.codebase.schemas import DesignSchema
from backend.db.neo4j.repositories.design import DesignRepository
from backend.db.neo4j.repositories.models.design import DesignNode
from backend.design_data.repository import DesignDataRepository
from backend.db.neo4j.repositories.requirement import RequirementRepository
from backend.db.neo4j.repositories.verification import VerificationRepository
from backend.requirements.schemas import LowLevelRequirementSchema, VerificationSchema

if TYPE_CHECKING:
    from neo4j import Session as Neo4jSession

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class DecompositionResult:
    llrs_created: int = 0
    verifications_created: int = 0
    conditions_created: int = 0
    actions_created: int = 0


@dataclass
class DesignResult:
    nodes_created: int = 0
    nodes_existing: int = 0
    triples_created: int = 0
    triples_skipped: int = 0
    links_applied: int = 0
    links_skipped: int = 0
    node_links_applied: int = 0
    node_links_skipped: int = 0
    qname_to_node: dict[str, "DesignNode"] = field(default_factory=dict)


@dataclass
class VerificationResult:
    verifications_saved: int = 0
    conditions_created: int = 0
    actions_created: int = 0


# ---------------------------------------------------------------------------
# Verification context building (Neo4j only)
# ---------------------------------------------------------------------------


def build_verification_context(neo4j_session: "Neo4jSession") -> list[dict]:
    """Build structured class-level context for the verification agent.

    .. deprecated::
        Use :func:`build_verification_context_from_diagram` instead, which routes
        through the design_data module and returns typed models.

    Queries Neo4j :Design nodes only. Returns a list of class/interface
    dicts with attributes, methods, and relationships.
    """
    contexts: dict[str, dict] = {}

    result = neo4j_session.run("""
        MATCH (parent:Design)
        WHERE parent.kind IN ['class', 'interface', 'struct', 'type_alias']
        OPTIONAL MATCH (parent)-[:COMPOSES]->(member:Design)
        OPTIONAL MATCH (parent)-[r]->(target:Design)
        WHERE type(r) <> 'COMPOSES' AND type(r) <> 'IMPLEMENTED_BY' AND type(r) <> 'TRACES_TO'
        RETURN parent, collect(DISTINCT member) AS members,
               collect(DISTINCT {pred: type(r), tgt_qn: target.qualified_name, tgt_name: target.name}) AS rels
    """)
    for record in result:
        p = dict(record["parent"])
        qn = p.get("qualified_name", "")
        if not qn:
            continue

        attrs = []
        methods = []
        for m in (record["members"] or []):
            if m is None:
                continue
            md = dict(m)
            member = {
                "name": md.get("name", ""),
                "qualified_name": md.get("qualified_name", ""),
                "kind": md.get("kind", ""),
                "visibility": md.get("visibility", ""),
                "type_signature": md.get("type_signature", ""),
                "argsstring": md.get("argsstring", ""),
                "description": md.get("description", ""),
            }
            if md.get("kind") in ("attribute", "constant"):
                attrs.append(member)
            else:
                methods.append(member)

        relationships = []
        for rel in (record["rels"] or []):
            if rel is None or rel.get("pred") is None:
                continue
            relationships.append({
                "predicate": rel["pred"],
                "target": rel.get("tgt_qn", ""),
                "target_name": rel.get("tgt_name", ""),
            })

        contexts[qn] = {
            "qualified_name": qn,
            "kind": p.get("kind", ""),
            "description": p.get("description", ""),
            "attributes": sorted(attrs, key=lambda a: a["name"]),
            "methods": sorted(methods, key=lambda m: m["name"]),
            "relationships": relationships,
        }

    return sorted(contexts.values(), key=lambda c: c["qualified_name"])


def build_verification_context_from_diagram(neo4j_session: "Neo4jSession", component_id: int | None = None) -> list[dict]:
    """Build verification context using the design_data module.

    This is the preferred replacement for build_verification_context().
    Uses DesignDataRepository to query Neo4j and return typed ClassDiagram
    objects, then extracts verification dicts.

    Args:
        neo4j_session: A Neo4j session.
        component_id: Optional component filter.

    Returns:
        List of dicts with verification context (same format as
        build_verification_context()).
    """
    repo = DesignDataRepository(neo4j_session)
    diagram = repo.get_class_diagram(component_id=component_id)
    return diagram.to_verification_dicts()


# ---------------------------------------------------------------------------
# 1. Decomposition persistence
# ---------------------------------------------------------------------------


def persist_decomposition(
    neo4j_session: "Neo4jSession",
    hlr_id: int,
    llrs: list[LowLevelRequirementSchema],
) -> DecompositionResult:
    """Create LLRs under an existing HLR in Neo4j, with verification methods,
    conditions, and actions.

    Phase 3: Both LLRs and verification data go to Neo4j.
    """
    result = DecompositionResult()
    req_repo = RequirementRepository(neo4j_session)
    ver_repo = VerificationRepository(neo4j_session)

    for llr_data in llrs:
        llr = req_repo.create_llr(hlr_id=hlr_id, description=llr_data.description)
        result.llrs_created += 1

        # Persist verification methods with conditions and actions
        for v in llr_data.verifications:
            vm = ver_repo.create_verification(
                llr_id=llr.id,
                method=v.method,
                test_name=v.test_name,
                description=v.description,
            )
            result.verifications_created += 1

            for i, cond in enumerate(v.preconditions):
                ver_repo.add_condition(
                    vm_id=vm.id,
                    phase="pre",
                    order=i,
                    operator=cond.operator,
                    expected_value=cond.expected_value,
                    subject_qualified_name=cond.subject_qualified_name,
                    object_qualified_name=cond.object_qualified_name,
                )
                result.conditions_created += 1

            for i, action in enumerate(v.actions):
                ver_repo.add_action(
                    vm_id=vm.id,
                    order=i,
                    description=action.description,
                    callee_qualified_name=action.callee_qualified_name,
                    caller_qualified_name=action.caller_qualified_name,
                )
                result.actions_created += 1

            for i, cond in enumerate(v.postconditions):
                ver_repo.add_condition(
                    vm_id=vm.id,
                    phase="post",
                    order=i,
                    operator=cond.operator,
                    expected_value=cond.expected_value,
                    subject_qualified_name=cond.subject_qualified_name,
                    object_qualified_name=cond.object_qualified_name,
                )
                result.conditions_created += 1

    return result


# ---------------------------------------------------------------------------
# 2. Design persistence (ontology nodes, triples, requirement links)
# ---------------------------------------------------------------------------


def persist_design(
    design: DesignSchema,
    neo4j_session: "Neo4jSession",
    qname_to_node: dict[str, DesignNode] | None = None,
) -> DesignResult:
    """Create ontology nodes, triples, and requirement-to-node links in Neo4j.

    Design nodes and triples are written directly to Neo4j via
    DesignRepository. Requirement links use TRACES_TO edges from
    :HLR/:LLR nodes to :Design nodes.

    Args:
        design: DesignSchema from the agent.
        neo4j_session: Active Neo4j session for graph writes.
        qname_to_node: Optional cache of qualified_name → DesignNode.
    """
    if qname_to_node is None:
        qname_to_node = {}

    result = DesignResult(qname_to_node=qname_to_node)
    repo = DesignRepository(neo4j_session)

    # --- Nodes ---
    for node_data in design.nodes:
        if node_data.qualified_name in qname_to_node:
            result.nodes_existing += 1
            continue

        dn = DesignNode(
            qualified_name=node_data.qualified_name,
            name=node_data.name,
            kind=node_data.kind,
            specialization=node_data.specialization or "",
            visibility=node_data.visibility or "",
            description=node_data.description or "",
            refid=node_data.qualified_name,
            source_type=node_data.source_type or "",
            type_signature=node_data.type_signature or "",
            argsstring=node_data.argsstring or "",
            definition=node_data.definition or "",
            file_path=node_data.file_path or "",
            line_number=node_data.line_number,
            is_static=node_data.is_static or False,
            is_const=node_data.is_const or False,
            is_virtual=node_data.is_virtual or False,
            is_abstract=node_data.is_abstract or False,
            is_final=node_data.is_final or False,
            component_id=node_data.component_id,
            is_intercomponent=node_data.is_intercomponent or False,
        )
        repo.merge_node(dn)
        qname_to_node[node_data.qualified_name] = dn
        result.nodes_created += 1

    # --- Triples ---
    for triple_data in design.triples:
        if triple_data.subject_qualified_name not in qname_to_node:
            log.warning(
                "Triple skipped: subject %r not found",
                triple_data.subject_qualified_name,
            )
            result.triples_skipped += 1
            continue
        if triple_data.object_qualified_name not in qname_to_node:
            dep_stub_qnames = {
                nd.qualified_name for nd in design.nodes if nd.source_type == "dependency"
            }
            if triple_data.object_qualified_name not in dep_stub_qnames:
                log.warning(
                    "Triple skipped: object %r not found",
                    triple_data.object_qualified_name,
                )
                result.triples_skipped += 1
                continue

        repo.merge_triple(
            triple_data.subject_qualified_name,
            triple_data.predicate,
            triple_data.object_qualified_name,
            mechanism=getattr(triple_data, "mechanism", "") or "",
            position=getattr(triple_data, "position", None),
            name=getattr(triple_data, "name", "") or "",
            display_name=getattr(triple_data, "display_name", "") or "",
        )
        result.triples_created += 1

    # --- Requirement links (explicit from LLM) ---
    if design.requirement_links:
        req_repo = RequirementRepository(neo4j_session)
        for link in design.requirement_links:
            if link.requirement_type == "hlr":
                if 0 <= link.triple_index < len(design.triples):
                    triple_data = design.triples[link.triple_index]
                    for qn in [triple_data.subject_qualified_name, triple_data.object_qualified_name]:
                        if qn in qname_to_node:
                            try:
                                req_repo.trace_to_design(
                                    hlr_id=link.requirement_id,
                                    design_qualified_name=qn,
                                )
                                result.node_links_applied += 1
                            except Exception:
                                log.warning(
                                    "Failed to trace HLR %d → %s",
                                    link.requirement_id,
                                    qn,
                                    exc_info=True,
                                )
                                result.node_links_skipped += 1
                result.links_applied += 1
            elif link.requirement_type == "llr":
                if 0 <= link.triple_index < len(design.triples):
                    triple_data = design.triples[link.triple_index]
                    for qn in [triple_data.subject_qualified_name, triple_data.object_qualified_name]:
                        if qn in qname_to_node:
                            try:
                                req_repo.trace_to_design(
                                    llr_id=link.requirement_id,
                                    design_qualified_name=qn,
                                )
                                result.node_links_applied += 1
                            except Exception:
                                log.warning(
                                    "Failed to trace LLR %d → %s",
                                    link.requirement_id,
                                    qn,
                                    exc_info=True,
                                )
                                result.node_links_skipped += 1
                result.links_applied += 1

    return result


# ---------------------------------------------------------------------------
# 3. Verification persistence
# ---------------------------------------------------------------------------


def persist_verification(
    neo4j_session: "Neo4jSession",
    llr_id: int,
    verifications: list[VerificationSchema],
) -> VerificationResult:
    """Replace an LLR's verification methods with fleshed-out versions in Neo4j.

    Creates :VerificationMethod nodes linked via (:LLR)-[:VERIFIES], with
    :Condition nodes (via :HAS_CONDITION with :LEFT_OPERAND/:RIGHT_OPERAND
    edges to :Design) and :Action nodes (via :HAS_ACTION with :CALLER/:CALLEE
    edges to :Design).
    """
    result = VerificationResult()
    repo = VerificationRepository(neo4j_session)

    # Delete existing verifications for this LLR
    existing_vms = repo.list_verifications(llr_id)
    for vm in existing_vms:
        repo.delete_verification(vm.id)

    # Clean up orphaned stub :Design nodes left behind by notional references
    # from the decompose phase.  When Condition/Action nodes are deleted
    # above, stub Design nodes (is_stub=true) that only had edges from those
    # deleted nodes become isolated.  They've served their purpose as
    # temporary placeholders and should be removed.
    neo4j_session.run(
        """
        MATCH (d:Design {is_stub: true})
        WHERE NOT (d)--()
        DETACH DELETE d
        """
    )

    # Create new verifications
    for v in verifications:
        vm = repo.create_verification(
            llr_id=llr_id,
            method=v.method,
            test_name=v.test_name,
            description=v.description,
        )
        result.verifications_saved += 1

        # Preconditions
        for i, cond in enumerate(v.preconditions):
            repo.add_condition(
                vm_id=vm.id,
                phase="pre",
                order=i,
                operator=cond.operator,
                expected_value=cond.expected_value,
                subject_qualified_name=cond.subject_qualified_name,
                object_qualified_name=cond.object_qualified_name,
            )
            result.conditions_created += 1

        # Actions
        for i, action in enumerate(v.actions):
            repo.add_action(
                vm_id=vm.id,
                order=i,
                description=action.description,
                caller_qualified_name=action.caller_qualified_name,
                callee_qualified_name=action.callee_qualified_name,
            )
            result.actions_created += 1

        # Postconditions
        for i, cond in enumerate(v.postconditions):
            repo.add_condition(
                vm_id=vm.id,
                phase="post",
                order=i,
                operator=cond.operator,
                expected_value=cond.expected_value,
                subject_qualified_name=cond.subject_qualified_name,
                object_qualified_name=cond.object_qualified_name,
            )
            result.conditions_created += 1

    return result
