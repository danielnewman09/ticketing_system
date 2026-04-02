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
from backend.ticketing_agent.design.design_oo import design_oo
from backend.ticketing_agent.design.discover_classes import discover_classes
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
        model: LLM model override.
        log_dir: Directory for per-step prompt logs.

    Returns:
        ``(oo_design, ontology_design)`` tuple.
    """
    hlr_id = hlr.get("id", "?")

    # --- Step 1: Discover dependency + as-built classes ---
    dependency_classes = None
    as_built_classes = None

    if toolset:
        discovery_log = (
            os.path.join(log_dir, f"discover_classes_hlr{hlr_id}.md")
            if log_dir else ""
        )
        try:
            discovered = discover_classes(
                hlr=hlr,
                llrs=llrs,
                dependency_contexts=dependency_contexts,
                component_namespace=component_namespace,
                toolset=toolset,
                model=model,
                prompt_log_file=discovery_log,
            )
            log.info(
                "  HLR %s: discover_classes returned %d items", hlr_id, len(discovered),
            )
            for c in discovered:
                log.info(
                    "    %s [%s] %s", c.get("category"), c.get("kind"), c.get("qualified_name"),
                )
            dependency_classes = [
                c for c in discovered if c.get("category") == "dependency"
            ] or None
            as_built_classes = [
                c for c in discovered if c.get("category") == "as-built"
            ] or None
            log.info(
                "  HLR %s: %d dependency, %d as-built classes for design_oo",
                hlr_id,
                len(dependency_classes or []),
                len(as_built_classes or []),
            )
        except Exception:
            log.exception("Class discovery failed for HLR %s", hlr_id)

    # --- Step 2: Design OO (single-turn) ---
    design_log = (
        os.path.join(log_dir, f"design_oo_hlr{hlr_id}.md")
        if log_dir else ""
    )
    oo = design_oo(
        hlr=hlr,
        llrs=llrs,
        language=language,
        existing_classes=existing_classes,
        dependency_classes=dependency_classes,
        as_built_classes=as_built_classes,
        intercomponent_classes=intercomponent_classes,
        other_hlr_summaries=other_hlr_summaries,
        dependency_contexts=dependency_contexts,
        component_namespace=component_namespace,
        sibling_namespaces=sibling_namespaces,
        model=model,
        prompt_log_file=design_log,
    )

    # --- Step 3: Map to ontology (deterministic) ---
    ontology = map_oo_to_ontology(
        oo,
        component_id=component_id,
        prior_class_lookup=prior_class_lookup,
        component_namespace=component_namespace,
    )

    log.info(
        "  HLR %s: %d classes, %d interfaces, %d nodes, %d triples",
        hlr_id,
        len(oo.classes),
        len(oo.interfaces),
        len(ontology.nodes),
        len(ontology.triples),
    )

    return oo, ontology
