"""
Single-HLR design skill: discover → design → map.

Orchestrates the full per-HLR pipeline:
1. Discover relevant dependency and as-built classes (LLM tool loop)
2. Design OO class structure from requirements (single-turn LLM)
3. Map OO design to ontology (deterministic)
"""

import logging
import os

from backend.codebase.schemas import DesignSchema, OODesignSchema
# from backend.ticketing_agent.design.design_oo import design_oo  # no longer called from pipeline
# from backend.ticketing_agent.design.discover_classes import discover_classes  # no longer called from pipeline
from backend.ticketing_agent.design.container_lookup import seed_container_lookup
from backend.ticketing_agent.design.map_to_ontology import map_oo_to_ontology

log = logging.getLogger("agents.design")


def design_hlr(
    hlr: dict,
    llrs: list[dict],
    language: str = "",
    existing_classes: list[dict] | None = None,
    intercomponent_classes: list[dict] | None = None,
    other_hlr_summaries: list[dict] | None = None,
    dependency_contexts: dict[int, dict] | None = None,
    component_namespace: str = "",
    sibling_namespaces: list[str] | None = None,
    component_id: int | None = None,
    prior_class_lookup: dict[str, str] | None = None,
    toolset=None,
    neo4j_session=None,
    model: str = "",
    log_dir: str = "",
) -> tuple[OODesignSchema, DesignSchema]:
    """Design a single HLR through the full pipeline.

    Args:
        hlr: HLR dict with ``{id, description, component_name?, ...}``.
        llrs: LLR dicts for this HLR.
        language: Target programming language.
        existing_classes: In-memory classes from prior HLR designs in
            the same component (from ``_extract_existing_classes``).
        intercomponent_classes: In-memory public API classes from other
            components.
        other_hlr_summaries: Other HLRs for awareness context.
        dependency_contexts: Dependency assessment keyed by HLR ID.
        component_namespace: Required C++ namespace for this component.
        sibling_namespaces: Other component namespaces.
        component_id: Component FK for ontology nodes.
        prior_class_lookup: Name → qualified_name mapping from prior
            designs, for cross-HLR reference resolution in ontology.
        toolset: A ``DependencyGraphTools`` instance for discovery.
            When ``None``, discovery is skipped.
        neo4j_session: Optional Neo4j session for container lookup seeding.
        model: LLM model override.
        log_dir: Directory for per-step prompt logs.

    Returns:
        ``(oo_design, ontology_design)`` tuple.
    """
    hlr_id = hlr.get("id", "?")

    # --- Step 1: Skip separate discovery + design_oo ---
    # Discovery is now handled inside the design_and_verify loop.
    # The agent discovers dependencies on-the-fly using search_symbols,
    # get_compound, etc.

    # --- Build dependency_lookup for the combined loop ---
    # Discovery results come through the toolset at runtime.
    # We pre-seed standard containers since they aren't searchable.
    dep_lookup: dict[str, str] = {}
    if neo4j_session is not None:
        container_lookup = seed_container_lookup(neo4j_session)
        if container_lookup:
            dep_lookup.update(container_lookup)

    # --- Step 2: Combined design + verify (includes discovery) ---
    from backend.ticketing_agent.design_verify.combined_loop import design_and_verify

    discovery_failed = toolset is None

    verify_log = os.path.join(log_dir, f"design_verify_hlr{hlr_id}.md") if log_dir else ""
    result = design_and_verify(
        hlr=hlr,
        llrs=llrs,
        existing_classes=existing_classes,
        intercomponent_classes=intercomponent_classes,

        component_namespace=component_namespace,
        sibling_namespaces=sibling_namespaces,
        prior_class_lookup=prior_class_lookup,
        dependency_lookup=dep_lookup or None,
        neo4j_session=neo4j_session,
        toolset=toolset,
        model=model,
        prompt_log_file=verify_log,
        discovery_failed=discovery_failed,
    )

    oo = result.oo_design

    # --- Step 3: Map to ontology (deterministic) ---
    dependency_lookup = None
    if dep_lookup:
        dependency_lookup = dep_lookup

    ontology = map_oo_to_ontology(
        oo,
        component_id=component_id,
        prior_class_lookup=prior_class_lookup,
        component_namespace=component_namespace,
        dependency_lookup=dependency_lookup,
    )

    log.info(
        "  HLR %s: %d classes, %d interfaces, %d nodes, %d triples",
        hlr_id,
        len(oo.classes),
        len(oo.interfaces),
        len(ontology.nodes),
        len(ontology.triples),
    )

    return oo, ontology, result.verifications
