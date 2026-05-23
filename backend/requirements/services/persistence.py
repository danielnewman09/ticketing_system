"""Service layer for persisting agent outputs to the database.

Consolidates the persistence logic used by demo.py, the MCP server,
and NiceGUI views into a single place.

Phase 1 note: design nodes and triples are persisted to Neo4j via
DesignRepository. HLR/LLR and verification data still use SQLAlchemy
until Phase 2 and Phase 3 respectively.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from backend.db import get_or_create
from backend.db.models import (
    HighLevelRequirement,
    LowLevelRequirement,
    VerificationAction,
    VerificationCondition,
    VerificationMethod,
)
from backend.codebase.schemas import DesignSchema
from backend.db.neo4j.repositories.design import DesignRepository
from backend.db.neo4j.repositories.models.design import DesignNode
from backend.requirements.schemas import LowLevelRequirementSchema, VerificationSchema

if TYPE_CHECKING:
    from neo4j import Session as Neo4jSession
    from backend.db.models.ontology import OntologyNode

log = logging.getLogger(__name__)


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
    node_links_applied: int = 0
    node_links_skipped: int = 0
    qname_to_node: dict[str, "DesignNode"] = field(default_factory=dict)


@dataclass
class VerificationResult:
    verifications_saved: int = 0
    conditions_created: int = 0
    actions_created: int = 0


@dataclass
class VerificationValidationReport:
    """Report from validating member_qualified_name references against the ontology."""

    resolved: list[tuple[str, str]] = field(
        default_factory=list
    )  # (member_qname, matched_node_qname)
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
# Ontology node resolution (still uses SQLAlchemy — Phase 3 will move to Neo4j)
# ---------------------------------------------------------------------------


def resolve_ontology_node(
    session: Session,
    member_qname: str,
    node_list: list[dict] | None = None,
) -> "OntologyNode | None":
    """Resolve a member qualified name to an OntologyNode via longest prefix match.

    NOTE: This still uses SQLAlchemy OntologyNode. Phase 3 will replace
    this with Neo4j-based resolution.
    """
    from backend.db.models import OntologyNode

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
# Verification context building (still uses SQLAlchemy — Phase 3 will move)
# ---------------------------------------------------------------------------


def build_verification_context(session: Session) -> list[dict]:
    """Build structured class-level context for the verification agent.

    Queries both Neo4j (primary source for design nodes) and SQLAlchemy
    (bridge for any nodes not yet migrated). Falls back to SQLAlchemy-only
    if Neo4j is unavailable.
    """
    from backend.db.models.ontology import TYPE_KINDS, VALUE_KINDS, OntologyNode, OntologyTriple

    contexts: dict[str, dict] = {}  # qualified_name -> context dict

    # --- Neo4j design nodes (primary source) ---
    try:
        from services.dependencies import get_neo4j
        with get_neo4j().session() as ns:
            result = ns.run("""
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
    except Exception:
        log.warning("Neo4j verification context query failed", exc_info=True)

    # --- SQLAlchemy bridge nodes (augment with anything missing from Neo4j) ---
    all_nodes = session.query(OntologyNode).all()
    node_by_id: dict[int, OntologyNode] = {n.id: n for n in all_nodes}
    all_triples = session.query(OntologyTriple).all()

    for n in all_nodes:
        if n.kind not in TYPE_KINDS:
            continue
        if n.qualified_name in contexts:
            continue  # Already have it from Neo4j

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
                relationships.append(
                    {
                        "predicate": pred.name,
                        "target": obj.qualified_name,
                        "target_name": obj.name,
                    }
                )

        contexts[n.qualified_name] = {
            "qualified_name": n.qualified_name,
            "kind": n.kind,
            "description": n.description or "",
            "attributes": sorted(attrs, key=lambda a: a["name"]),
            "methods": sorted(methods, key=lambda m: m["name"]),
            "relationships": relationships,
        }

    return sorted(contexts.values(), key=lambda c: c["qualified_name"])


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
# Closed-loop design augmentation (still uses SQLAlchemy — Phase 3)
# ---------------------------------------------------------------------------


def augment_design_for_unresolved(
    session: Session,
    unresolved: list[tuple[str, str]],
) -> AugmentResult:
    """Create missing ontology nodes for unresolved verification references.

    NOTE: This still uses SQLAlchemy OntologyNode. Phase 3 will replace
    this with Neo4j-based Constraint creation.
    """
    from backend.db.models import OntologyNode, OntologyTriple, Predicate

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
        parent = (
            session.query(OntologyNode)
            .filter_by(
                qualified_name=parent_qname,
            )
            .first()
        )
        if parent is None:
            log.debug(
                "augment: parent %s not found for %s, skipping",
                parent_qname,
                member_qname,
            )
            continue

        # Infer kind from context
        kind = "method" if context == "action" else "attribute"

        # Create the node
        node, created = get_or_create(
            session,
            OntologyNode,
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
                    session,
                    OntologyTriple,
                    subject_id=parent.id,
                    predicate_id=composes_pred.id,
                    object_id=node.id,
                )
                if triple_created:
                    result.triples_created += 1

    session.flush()

    # Re-link verification records with NULL ontology_node_id
    if created_nodes:
        qn_to_node = {n.qualified_name: n for n in session.query(OntologyNode).all()}
        for vc in (
            session.query(VerificationCondition)
            .filter(
                VerificationCondition.ontology_node_id.is_(None),
                VerificationCondition.member_qualified_name != "",
            )
            .all()
        ):
            node = qn_to_node.get(vc.member_qualified_name)
            if node:
                vc.ontology_node_id = node.id

        for va in (
            session.query(VerificationAction)
            .filter(
                VerificationAction.ontology_node_id.is_(None),
                VerificationAction.member_qualified_name != "",
            )
            .all()
        ):
            node = qn_to_node.get(va.member_qualified_name)
            if node:
                va.ontology_node_id = node.id

        session.flush()

    # Neo4j sync of newly created nodes
    if created_nodes:
        try:
            from backend.db.neo4j.repositories.design import DesignRepository as DR
            from services.dependencies import get_neo4j

            new_triples = (
                session.query(OntologyTriple)
                .filter(OntologyTriple.object_id.in_([n.id for n in created_nodes.values()]))
                .all()
            )
            with get_neo4j().session() as neo4j_session:
                repo = DR(neo4j_session)
                for node in created_nodes.values():
                    dn = DesignNode(
                        qualified_name=node.qualified_name or node.name,
                        name=node.name,
                        kind=node.kind,
                        specialization=node.specialization or "",
                        visibility=node.visibility or "",
                        description=node.description or "",
                        source_type=node.source_type or "",
                        component_id=node.component_id,
                    )
                    repo.merge_node(dn)
                for triple in new_triples:
                    if triple.subject and triple.object and triple.predicate:
                        repo.merge_triple(
                            triple.subject.qualified_name,
                            triple.predicate.name,
                            triple.object.qualified_name,
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
    """Create LLRs (with verification stubs) under an existing HLR.

    Also creates :LLR stub nodes in Neo4j and DECOMPOSES_INTO edges
    from the HLR stub (Phase 1 bridge).
    """
    result = DecompositionResult()

    for llr_data in llrs:
        llr = LowLevelRequirement(
            high_level_requirement=hlr,
            description=llr_data.description,
        )
        session.add(llr)
        session.flush()
        result.llrs_created += 1

        # Create LLR stub in Neo4j
        try:
            from services.dependencies import get_neo4j
            with get_neo4j().session() as neo4j_session:
                repo = DesignRepository(neo4j_session)
                repo.merge_llr_stub(sqlite_id=llr.id, description=llr.description)
                # Link HLR → LLR in Neo4j
                neo4j_session.run(
                    """
                    MATCH (h:HLR {sqlite_id: $hid})
                    MATCH (l:LLR {sqlite_id: $lid})
                    MERGE (h)-[:DECOMPOSES_INTO]->(l)
                    """,
                    {"hid": hlr.id, "lid": llr.id},
                )
        except Exception:
            log.warning("Neo4j LLR stub sync failed for LLR %d", llr.id, exc_info=True)

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

    return result


# ---------------------------------------------------------------------------
# 2. Design persistence (ontology nodes, triples, requirement links)
# ---------------------------------------------------------------------------


def persist_design(
    design: DesignSchema,
    neo4j_session: "Neo4jSession",
    sql_session: Session | None = None,
    qname_to_node: dict[str, DesignNode] | None = None,
) -> DesignResult:
    """Create ontology nodes, triples, and requirement-to-node links in Neo4j.

    Design nodes and triples are written directly to Neo4j via
    DesignRepository. Requirement links use TRACES_TO edges from
    :HLR/:LLR stub nodes to :Design nodes.

    Args:
        design: DesignSchema from the agent.
        neo4j_session: Active Neo4j session for graph writes.
        sql_session: Optional SQLAlchemy session for HLR/LLR lookups.
            Required if design.requirement_links is non-empty.
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
            # Check if it's a dependency stub — merge_node skipped it
            # but the triple may still reference it (it exists as :Compound in Neo4j)
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
        )
        result.triples_created += 1

    # --- Requirement links (explicit from LLM) ---
    if design.requirement_links and sql_session is not None:
        for link in design.requirement_links:
            if link.requirement_type == "hlr":
                design_qn = None
                # Get the subject or object qualified_name from the triple
                if 0 <= link.triple_index < len(design.triples):
                    triple_data = design.triples[link.triple_index]
                    # Link both subject and object of the triple to the HLR
                    for qn in [triple_data.subject_qualified_name, triple_data.object_qualified_name]:
                        if qn in qname_to_node:
                            try:
                                repo.trace_design_to_hlr(
                                    hlr_sqlite_id=link.requirement_id,
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
                design_qn = None
                if 0 <= link.triple_index < len(design.triples):
                    triple_data = design.triples[link.triple_index]
                    for qn in [triple_data.subject_qualified_name, triple_data.object_qualified_name]:
                        if qn in qname_to_node:
                            try:
                                repo.trace_design_to_llr(
                                    llr_sqlite_id=link.requirement_id,
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
    session: Session,
    llr: LowLevelRequirement,
    verifications: list[VerificationSchema],
    ontology_nodes: list[dict] | None = None,
) -> VerificationResult:
    """Replace an LLR's verification methods with fleshed-out versions.

    NOTE: This still uses SQLAlchemy. Phase 3 will move to Neo4j.
    """
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
                    session,
                    cond.member_qualified_name,
                    ontology_nodes,
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
                    session,
                    action.member_qualified_name,
                    ontology_nodes,
                ),
                member_qualified_name=action.member_qualified_name,
            )
            session.add(va)
            result.actions_created += 1

        _save_conditions(vm, v.postconditions, "post")

    session.flush()
    return result