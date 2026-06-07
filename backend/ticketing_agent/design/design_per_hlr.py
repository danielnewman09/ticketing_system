"""
Orchestration: per-HLR design loop.

Processes each HLR individually through the design_hlr skill
(discover → design_oo → map_to_ontology), with awareness of
intercomponent boundaries from previously designed HLRs.
"""

from __future__ import annotations

import logging
import os

from backend.codebase.schemas import DesignSchema
from codegraph.diagram import ClassDiagram
from backend.design_data import class_diagram_from_oo_design
from backend.ticketing_agent.design.design_hlr import design_hlr
from backend.ticketing_agent.design.order_hlrs import order_hlrs

log = logging.getLogger("agents.design")


def _get_comp_ns(component_id: int | None) -> str:
    """Look up a component namespace by ID from SQLite."""
    if component_id is None:
        return ""
    try:
        from backend.db import get_session
        from backend.db.models import Component
        with get_session() as session:
            comp = session.query(Component).filter_by(id=component_id).first()
            return comp.namespace if comp and comp.namespace else ""
    except Exception:
        return ""


def _extract_existing_classes(oo: ClassDiagram) -> list[dict]:
    """Extract class summaries from an OO design for the existing_classes prompt.

    # TODO: Replace with design_data module once prompt builders accept ClassNode directly

    Returns list of dicts matching the format expected by
    _build_existing_classes_section.
    """
    results = []

    # Build association lookup: from_class -> list of associations
    assoc_lookup: dict[str, list[dict]] = {}
    for assoc in oo.associations:
        assoc_lookup.setdefault(assoc.subject, []).append(
            {
                "target": assoc.object,
                "kind": assoc.kind,
                "description": assoc.description,
            }
        )

    for cls in oo.classes:
        module = cls.module
        qname = f"{module}::{cls.name}" if module else cls.name
        results.append(
            {
                "qualified_name": qname,
                "kind": "class",
                "description": cls.description,
                "methods": [{"name": m.name, "visibility": m.visibility} for m in cls.methods],
                "attributes": [
                    {"name": a.name, "visibility": a.visibility} for a in cls.attributes
                ],
                "inherits_from": cls.inherits_from,
                "realizes": cls.realizes,
                "associations": assoc_lookup.get(cls.name, []),
            }
        )

    for iface in oo.interfaces:
        module = iface.module
        qname = f"{module}::{iface.name}" if module else iface.name
        results.append(
            {
                "qualified_name": qname,
                "kind": "interface",
                "description": iface.description,
                "methods": [{"name": m.name, "visibility": m.visibility} for m in iface.methods],
                "attributes": [],
                "inherits_from": [],
                "realizes": [],
                "associations": [],
            }
        )

    return results


def _extract_intercomponent_context(
    oo: ClassDiagram,
    component_name: str,
    exclude_component_id: int | None,
    source_component_id: int | None,
) -> list[dict]:
    """Extract public API classes from an OO design for intercomponent context.

    # TODO: Replace with design_data module once prompt builders accept ClassNode directly

    Only includes classes/interfaces with is_intercomponent=True.
    """
    if source_component_id is not None and source_component_id == exclude_component_id:
        return []

    results = []

    for cls in oo.classes:
        if not cls.is_intercomponent:
            continue
        module = cls.module
        qname = f"{module}::{cls.name}" if module else cls.name
        results.append(
            {
                "qualified_name": qname,
                "kind": "class",
                "description": cls.description,
                "component_name": component_name,
                "methods": [{"name": m.name, "visibility": m.visibility} for m in cls.methods],
            }
        )

    for iface in oo.interfaces:
        if not iface.is_intercomponent:
            continue
        module = iface.module
        qname = f"{module}::{iface.name}" if module else iface.name
        results.append(
            {
                "qualified_name": qname,
                "kind": "interface",
                "description": iface.description,
                "component_name": component_name,
                "methods": [{"name": m.name, "visibility": m.visibility} for m in iface.methods],
            }
        )

    return results


def design_all_hlrs(
    hlrs: list[dict],
    llrs: list[dict],
    language: str = "",
    model: str = "",
    log_dir: str = "",
    use_dependency_graph: bool = False,
) -> list[tuple[dict, ClassDiagram, DesignSchema]]:
    """Design each HLR individually in dependency order.

    Args:
        hlrs: All HLR dicts with keys: id, description, component_id?,
              component_name?, dependency_context?.
        llrs: All LLR dicts with keys: id, hlr_id, description.
        language: Target programming language.
        model: LLM model override.
        log_dir: Directory for per-step prompt logs.
        use_dependency_graph: If True, connect to the Neo4j dependency graph
            and use it for class discovery during design.

    Returns:
        List of (hlr_dict, oo_design, ontology_design) tuples in design order.
    """
    # Step 1: Order HLRs (foundational first)
    prompt_log = os.path.join(log_dir, "order_hlrs.md") if log_dir else ""
    ordered = order_hlrs(hlrs, model=model, prompt_log_file=prompt_log)
    ordered_ids = [entry["id"] for entry in ordered]

    # Build lookups
    hlr_by_id = {h["id"]: h for h in hlrs}
    llrs_by_hlr: dict[int, list[dict]] = {}
    for llr in llrs:
        hlr_id = llr.get("hlr_id")
        if hlr_id is not None:
            llrs_by_hlr.setdefault(hlr_id, []).append(llr)

    # Accumulate results per HLR
    designed: dict[int, tuple[ClassDiagram, int | None, str]] = {}
    accumulated_class_lookup: dict[str, str] = {}
    results: list[tuple[dict, ClassDiagram, DesignSchema]] = []

    # Optionally connect to the dependency graph
    dep_toolset = None
    if use_dependency_graph:
        try:
            from doxygen_index.tools import create_toolset

            dep_toolset = create_toolset()
            log.info("Dependency graph connected")
        except Exception as e:
            log.warning("Could not connect to dependency graph: %s", e)

    try:
        for i, hlr_id in enumerate(ordered_ids, 1):
            hlr = hlr_by_id.get(hlr_id)
            if not hlr:
                log.warning("Ordered HLR %d not found in input, skipping", hlr_id)
                continue

            hlr_llrs = llrs_by_hlr.get(hlr_id, [])
            component_id = hlr.get("component_id")
            component_name = hlr.get("component_name", "")

            log.info(
                "Designing HLR %d (%d/%d): %s",
                hlr_id,
                i,
                len(ordered_ids),
                hlr["description"][:60],
            )

            # Gather in-memory context from prior designs
            existing_classes = []
            for prev_id, (prev_oo, prev_comp_id, _) in designed.items():
                if prev_comp_id == component_id:
                    existing_classes.extend(_extract_existing_classes(prev_oo))

            intercomponent_classes = []
            for prev_id, (prev_oo, prev_comp_id, prev_comp_name) in designed.items():
                intercomponent_classes.extend(
                    _extract_intercomponent_context(
                        prev_oo,
                        prev_comp_name,
                        component_id,
                        prev_comp_id,
                    )
                )

            other_hlr_summaries = []
            for other_hlr in hlrs:
                if other_hlr["id"] == hlr_id:
                    continue
                status = "designed" if other_hlr["id"] in designed else "pending"
                other_hlr_summaries.append(
                    {
                        "id": other_hlr["id"],
                        "description": other_hlr["description"],
                        "status": status,
                    }
                )

            dep_ctx = hlr.get("dependency_context")
            dependency_contexts = {hlr_id: dep_ctx} if dep_ctx else None

            component_namespace = hlr.get("component_namespace", "")
            sibling_namespaces = [
                h.get("component_namespace", "")
                for h in hlrs
                if h["id"] != hlr_id and h.get("component_namespace")
            ]

            # Delegate to design_hlr skill
            oo, ontology = design_hlr(
                hlr=hlr,
                llrs=hlr_llrs,
                language=language,
                existing_classes=existing_classes or None,
                intercomponent_classes=intercomponent_classes or None,
                other_hlr_summaries=other_hlr_summaries or None,
                dependency_contexts=dependency_contexts,
                component_namespace=component_namespace,
                sibling_namespaces=sibling_namespaces or None,
                component_id=component_id,
                prior_class_lookup=accumulated_class_lookup,
                toolset=dep_toolset,
                model=model,
                log_dir=log_dir,
            )

            # Accumulate
            # Accumulate using design_data module
            prev_diagram = class_diagram_from_oo_design(oo, component_id=component_id)
            for cls in prev_diagram.classes:
                accumulated_class_lookup[cls.name] = cls.qualified_name
            for iface in prev_diagram.interfaces:
                accumulated_class_lookup[iface.name] = iface.qualified_name
            for enum in prev_diagram.enums:
                accumulated_class_lookup[enum.name] = enum.qualified_name
            designed[hlr_id] = (oo, component_id, component_name)
            results.append((hlr, oo, ontology))
    finally:
        if dep_toolset:
            dep_toolset.close()
            log.info("Dependency graph disconnected")

    return results


def design_and_persist_hlr(
    hlr_id: int,
    log_dir: str = "",
) -> dict:
    """Design a single HLR end-to-end: load context, discover, design, persist.

    Intended for dashboard use. Handles DB loading, dependency graph
    toolset lifecycle, context gathering, and persistence.

    Returns dict with nodes_created, triples_created, links_applied.
    """
    from backend.db import get_session
    from backend.db.models import Component
    from backend.db.neo4j.repositories.requirement import RequirementRepository
    from backend.requirements.services.persistence import persist_design
    from codegraph.connection import get_session as get_neo4j_session

    # --- Load data from Neo4j ---
    with get_neo4j_session() as ns:
        req_repo = RequirementRepository(ns)
        hlr_obj = req_repo.get_hlr(hlr_id)
        if not hlr_obj:
            raise ValueError(f"HLR {hlr_id} not found")
        llrs_for_hlr = req_repo.list_llrs(hlr_id=hlr_id)
        if not llrs_for_hlr:
            raise ValueError(f"HLR {hlr_id} has no LLRs. Decompose it first.")
        all_hlrs_neo4j = req_repo.list_hlrs()

    component_name = None
    component_namespace = ""
    if hlr_obj.component_id:
        with get_session() as session:
            comp = session.query(Component).filter_by(id=hlr_obj.component_id).first()
            if comp:
                component_name = comp.name
                component_namespace = comp.namespace or ""

    hlr_dict = {
        "id": hlr_obj.id,
        "description": hlr_obj.description,
        "component_id": hlr_obj.component_id,
        "component_name": component_name,
        "component_namespace": component_namespace,
    }
    llr_dicts = [
        {"id": l.id, "description": l.description, "hlr_id": hlr_obj.id}
        for l in llrs_for_hlr
    ]

    other_hlr_summaries = [
        {"id": h.id, "description": h.description, "status": "unknown"}
        for h in all_hlrs_neo4j
        if h.id != hlr_id
    ]

    sibling_namespaces = list(
        {
            _get_comp_ns(h.component_id)
            for h in all_hlrs_neo4j
            if h.id != hlr_id and h.component_id
        }
    )

    dep_ctx = hlr_obj.dependency_context
    dependency_contexts = {hlr_id: dep_ctx} if dep_ctx else None

    # --- Dependency graph toolset ---
    dep_toolset = None
    try:
        from doxygen_index.tools import create_toolset

        dep_toolset = create_toolset()
        log.info("Dependency graph connected for HLR %d", hlr_id)
    except Exception as exc:
        log.warning("Dependency graph unavailable for HLR %d: %s", hlr_id, exc)

    try:
        _, ontology = design_hlr(
            hlr=hlr_dict,
            llrs=llr_dicts,
            other_hlr_summaries=other_hlr_summaries or None,
            dependency_contexts=dependency_contexts,
            component_namespace=component_namespace,
            sibling_namespaces=sibling_namespaces or None,
            component_id=hlr_dict["component_id"],
            toolset=dep_toolset,
            log_dir=log_dir,
        )
    finally:
        if dep_toolset:
            dep_toolset.close()
            log.info("Dependency graph disconnected for HLR %d", hlr_id)

    # --- Persist ---
    from codegraph.connection import get_session as get_neo4j_session
    with get_session() as session:
        with get_neo4j_session() as neo4j_session:
            result = persist_design(ontology, neo4j_session)
            return {
                "nodes_created": result.nodes_created,
                "triples_created": result.triples_created,
                "links_applied": result.links_applied,
            }
