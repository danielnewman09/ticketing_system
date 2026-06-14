"""Migrated design agent — the canonical HLR design pipeline for
``backend_migrated``.

The LLM design pipeline (``design_hlr`` in ``backend.ticketing_agent``)
was built around integer requirement IDs (the LLM writes ``hlr:1``,
``llr:3``, etc.).  Neomodel uses hex ``refid`` strings as identifiers.

This module bridges the two worlds:

1. ``design_and_persist_hlr(refid)`` — complete entry point: loads
   context from Neo4j via neomodel, runs the design pipeline, persists
   ontology nodes / associations / TRACES_TO edges, returns a summary.

2. ``design_hlr_migrated(hlr, llrs, ...)`` — lower-level: runs the
   pipeline for given neomodel HLR/LLR instances and returns the
   raw ``DesignHLRResult`` (without persistence).

Usage::

    from backend_migrated.agents.design_hlr import design_and_persist_hlr

    summary = design_and_persist_hlr(
        refid="2c3463b2…",
        log_dir="/path/to/logs",
    )
    # → {"nodes_created": 5, "triples_created": 12, "links_applied": 8}
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from backend.ticketing_agent.design.design_hlr import (
    design_hlr as _design_hlr_legacy,
)
from backend_migrated.models.requirement import HLR, LLR

log = logging.getLogger(__name__)


@dataclass
class DesignHLRResult:
    """Output of ``design_hlr_migrated()``.

    Carries the same ``oo_design`` and ``ontology`` as the original
    pipeline, plus ``links`` — a list of requirement-link dicts keyed
    by ``refid`` strings instead of integer IDs.
    """

    oo_design: object
    ontology: object
    verifications: dict = field(default_factory=dict)
    links: list[dict] = field(default_factory=list)


def design_hlr_migrated(
    hlr: HLR,
    llrs: list[LLR],
    *,
    other_hlrs: list[dict] | None = None,
    component_namespace: str = "",
    sibling_namespaces: list[str] | None = None,
    neo4j_session=None,
    toolset=None,
    model: str = "",
    log_dir: str = "",
) -> DesignHLRResult:
    """Design a single HLR — refid-aware wrapper around the legacy pipeline.

    Args:
        hlr: Neomodel HLR instance.
        llrs: Neomodel LLR instances belonging to this HLR.
        other_hlrs: Sibling HLR summaries (dicts with ``id``, ``description``).
        component_namespace: C++ namespace for this component.
        sibling_namespaces: Other component namespaces.
        neo4j_session: Optional Neo4j session for container lookup.
        toolset: Optional dependency graph toolset for discovery.
        model: LLM model override.
        log_dir: Directory for per-step prompt logs.

    Returns:
        ``DesignHLRResult`` with ``oo_design``, ``ontology``, ``verifications``,
        and ``links`` (requirement link dicts with string refids).
    """
    # --- Build ID mappings: refid ↔ short integer alias ---
    hlr_refid = hlr.refid
    refid_to_alias: dict[str, int] = {}
    alias_to_refid: dict[str, str] = {}

    next_id = 1
    refid_to_alias[hlr_refid] = next_id
    alias_to_refid[str(next_id)] = hlr_refid
    next_id += 1

    llr_alias_map: dict[str, int] = {}  # llr_refid → alias
    for l in llrs:
        if l.refid not in refid_to_alias:
            refid_to_alias[l.refid] = next_id
            alias_to_refid[str(next_id)] = l.refid
            llr_alias_map[l.refid] = next_id
            next_id += 1

    # Build other HLR aliases (for context)
    other_alias_map: dict[str, int] = {}
    if other_hlrs:
        for oh in other_hlrs:
            oh_id = oh.get("id", "")
            if oh_id and oh_id not in refid_to_alias:
                refid_to_alias[oh_id] = next_id
                alias_to_refid[str(next_id)] = oh_id
                other_alias_map[oh_id] = next_id
                next_id += 1

    # --- Build HLR/LLR dicts with integer aliases ---
    hlr_dict = {
        "id": refid_to_alias[hlr_refid],
        "description": hlr.description,
        "component_id": None,
        "component_name": "",
        "component_namespace": component_namespace,
    }

    llr_dicts = [
        {
            "id": llr_alias_map[l.refid],
            "description": l.description,
            "hlr_id": refid_to_alias[hlr_refid],
        }
        for l in llrs
    ]

    other_hlr_summaries = None
    if other_hlrs:
        other_hlr_summaries = [
            {
                "id": other_alias_map.get(oh["id"], 0),
                "description": oh.get("description", ""),
                "status": oh.get("status", "unknown"),
            }
            for oh in other_hlrs
        ]

    # --- Call the original pipeline ---
    oo, ontology, verifications = _design_hlr_legacy(
        hlr=hlr_dict,
        llrs=llr_dicts,
        other_hlr_summaries=other_hlr_summaries,
        component_namespace=component_namespace,
        sibling_namespaces=sibling_namespaces,
        component_id=None,
        neo4j_session=neo4j_session,
        toolset=toolset,
        model=model,
        log_dir=log_dir,
    )

    # --- Convert integer requirement IDs back to refids ---
    links: list[dict] = []
    for link in ontology.requirement_links:
        req_type = getattr(link, "requirement_type", "")
        int_id = getattr(link, "requirement_id", 0)
        subj_qn = getattr(link, "subject_qualified_name", "") or ""
        obj_qn = getattr(link, "object_qualified_name", "") or ""

        # Map integer ID back to refid
        refid = alias_to_refid.get(str(int_id), str(int_id))
        links.append({
            "requirement_type": req_type,
            "requirement_id": refid,
            "subject_qualified_name": subj_qn,
            "object_qualified_name": obj_qn,
        })

    return DesignHLRResult(
        oo_design=oo,
        ontology=ontology,
        verifications=verifications,
        links=links,
    )


# ---------------------------------------------------------------------------
# Full entry point — context loading + pipeline + persistence
# ---------------------------------------------------------------------------


def design_and_persist_hlr(
    refid: str,
    *,
    log_dir: str = "",
) -> dict:
    """Design a single HLR end-to-end: load context → run pipeline → persist.

    Reads the HLR and its LLRs from Neo4j via neomodel, gathers component
    and namespace context, runs the design agent, persists the resulting
    ontology nodes/associations/TRACES_TO edges, and returns a summary.

    Args:
        refid: The HLR's ``refid`` (hex UUID string).
        log_dir: Directory for per-step prompt logs.

    Returns:
        Dict with keys ``nodes_created``, ``triples_created``,
        ``links_applied``.

    Raises:
        ValueError: If the HLR is not found or has no LLRs.
    """
    from codegraph.connection import get_session as get_neo

    # --- Load data from Neo4j via neomodel ---
    hlr = HLR.nodes.get_or_none(refid=refid)
    if not hlr:
        raise ValueError(f"HLR {refid} not found")

    llr_nodes = hlr.llrs.all()
    if not llr_nodes:
        raise ValueError(f"HLR {refid} has no LLRs — decompose it first")

    # Component context
    comp_nodes = hlr.component.all()
    component_namespace = getattr(comp_nodes[0], "namespace", "") if comp_nodes else ""

    # Sibling namespaces
    sibling_namespaces: list[str] = []
    for s in HLR.nodes.all():
        if s.refid == refid:
            continue
        sc = s.component.all()
        if sc:
            ns = getattr(sc[0], "namespace", "")
            if ns and ns not in sibling_namespaces:
                sibling_namespaces.append(ns)

    # --- Run the design pipeline ---
    with get_neo() as neo4j_session:
        result = design_hlr_migrated(
            hlr=hlr,
            llrs=llr_nodes,
            other_hlrs=[
                {"id": s.refid, "description": s.description}
                for s in HLR.nodes.all()
                if s.refid != refid
            ],
            component_namespace=component_namespace,
            sibling_namespaces=sibling_namespaces or None,
            neo4j_session=neo4j_session,
            log_dir=log_dir,
        )

    ontology = result.ontology
    requirement_links = result.links

    # --- Persist ontology nodes ---
    nodes_created = 0
    qname_to_node: dict[str, object] = {}
    for node in ontology.nodes:
        qn = getattr(node, "qualified_name", "")
        if qn and qn not in qname_to_node:
            try:
                node.save()
                qname_to_node[qn] = node
                nodes_created += 1
            except Exception as exc:
                log.warning("Failed to save ontology node %s: %s", qn, exc)

    # --- Persist associations ---
    triples_created = 0
    with get_neo() as neo4j_session:
        for assoc in ontology.associations:
            subj = assoc.get("subject", "")
            pred = assoc.get("predicate", "")
            obj = assoc.get("object", "")
            if not all([subj, pred, obj]):
                continue
            try:
                query = (
                    "MATCH (a {qualified_name: $subj}) "
                    "MATCH (b {qualified_name: $obj}) "
                    "WHERE (a:CompoundNode OR a:MemberNode OR a:NamespaceNode) "
                    "  AND (b:CompoundNode OR b:MemberNode OR b:NamespaceNode) "
                    "MERGE (a)-[r:" + pred + "]->(b) "
                    "RETURN count(r) AS cnt"
                )
                neo4j_session.run(query, {"subj": subj, "obj": obj})
                triples_created += 1
            except Exception as exc:
                log.warning(
                    "Failed to create association %s -[%s]-> %s: %s",
                    subj, pred, obj, exc,
                )

    # --- Create TRACES_TO edges from HLR/LLR to design nodes ---
    links_applied = 0
    for link in requirement_links:
        req_type = link["requirement_type"]
        req_id = link["requirement_id"]
        subj_qn = link.get("subject_qualified_name", "")
        obj_qn = link.get("object_qualified_name", "")

        for qn in (subj_qn, obj_qn):
            if not qn or qn not in qname_to_node:
                continue
            target = qname_to_node[qn]
            try:
                if req_type == "hlr" and req_id == refid:
                    for mgr in (
                        hlr.traces_to_compounds,
                        hlr.traces_to_members,
                        hlr.traces_to_namespaces,
                    ):
                        mgr.connect(target)
                        links_applied += 1
                        break
                elif req_type == "llr":
                    llr = next((l for l in llr_nodes if l.refid == req_id), None)
                    if llr:
                        for mgr in (
                            llr.traces_to_compounds,
                            llr.traces_to_members,
                            llr.traces_to_namespaces,
                        ):
                            mgr.connect(target)
                            links_applied += 1
                            break
            except Exception as exc:
                log.warning(
                    "Failed to TRACES_TO link %s -> %s: %s",
                    req_id, qn, exc,
                )

    log.info(
        "Design complete for HLR %s: %d nodes, %d triples, %d links",
        refid[:8], nodes_created, triples_created, links_applied,
    )

    return {
        "nodes_created": nodes_created,
        "triples_created": triples_created,
        "links_applied": links_applied,
    }
