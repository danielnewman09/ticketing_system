"""
Orchestration: per-HLR design loop.

Processes each HLR individually through design_oo() -> map_oo_to_ontology(),
with awareness of intercomponent boundaries from previously designed HLRs.
"""

import logging
import os

from codebase.schemas import DesignSchema, OODesignSchema
from agents.design.design_oo import design_oo
from agents.design.map_to_ontology import map_oo_to_ontology
from agents.design.order_hlrs import order_hlrs

log = logging.getLogger("agents.design")


def _extract_existing_classes(oo: OODesignSchema) -> list[dict]:
    """Extract class summaries from an OO design for the existing_classes prompt.

    Returns list of dicts matching the format expected by
    _build_existing_classes_section.
    """
    results = []

    # Build association lookup: from_class -> list of associations
    assoc_lookup: dict[str, list[dict]] = {}
    for assoc in oo.associations:
        assoc_lookup.setdefault(assoc.from_class, []).append({
            "target": assoc.to_class,
            "kind": assoc.kind,
            "description": assoc.description,
        })

    for cls in oo.classes:
        module = cls.module
        qname = f"{module}::{cls.name}" if module else cls.name
        results.append({
            "qualified_name": qname,
            "kind": "class",
            "description": cls.description,
            "methods": [
                {"name": m.name, "visibility": m.visibility}
                for m in cls.methods
            ],
            "attributes": [
                {"name": a.name, "visibility": a.visibility}
                for a in cls.attributes
            ],
            "inherits_from": cls.inherits_from,
            "realizes": cls.realizes_interfaces,
            "associations": assoc_lookup.get(cls.name, []),
        })

    for iface in oo.interfaces:
        module = iface.module
        qname = f"{module}::{iface.name}" if module else iface.name
        results.append({
            "qualified_name": qname,
            "kind": "interface",
            "description": iface.description,
            "methods": [
                {"name": m.name, "visibility": m.visibility}
                for m in iface.methods
            ],
            "attributes": [],
            "inherits_from": [],
            "realizes": [],
            "associations": [],
        })

    return results


def _build_class_lookup(oo: OODesignSchema) -> dict[str, str]:
    """Build a name -> qualified_name mapping from an OO design.

    Used to seed map_oo_to_ontology's class_lookup so cross-HLR
    references (inheritance, associations, etc.) resolve correctly.
    """
    lookup: dict[str, str] = {}
    for cls in oo.classes:
        qname = f"{cls.module}::{cls.name}" if cls.module else cls.name
        lookup[cls.name] = qname
    for iface in oo.interfaces:
        qname = f"{iface.module}::{iface.name}" if iface.module else iface.name
        lookup[iface.name] = qname
    for enum in oo.enums:
        qname = f"{enum.module}::{enum.name}" if enum.module else enum.name
        lookup[enum.name] = qname
    return lookup


def _extract_intercomponent_context(
    oo: OODesignSchema,
    component_name: str,
    exclude_component_id: int | None,
    source_component_id: int | None,
) -> list[dict]:
    """Extract public API classes from an OO design for intercomponent context.

    Only includes classes/interfaces with is_intercomponent=True.

    Args:
        oo: The OO design to extract from.
        component_name: Name of the component this design belongs to.
        exclude_component_id: Skip if this matches source_component_id
            (i.e., don't include same-component classes as intercomponent).
        source_component_id: The component ID of the design being extracted.
    """
    if source_component_id is not None and source_component_id == exclude_component_id:
        return []

    results = []

    for cls in oo.classes:
        if not cls.is_intercomponent:
            continue
        module = cls.module
        qname = f"{module}::{cls.name}" if module else cls.name
        results.append({
            "qualified_name": qname,
            "kind": "class",
            "description": cls.description,
            "component_name": component_name,
            "methods": [
                {"name": m.name, "visibility": m.visibility}
                for m in cls.methods
            ],
        })

    for iface in oo.interfaces:
        if not iface.is_intercomponent:
            continue
        module = iface.module
        qname = f"{module}::{iface.name}" if module else iface.name
        results.append({
            "qualified_name": qname,
            "kind": "interface",
            "description": iface.description,
            "component_name": component_name,
            "methods": [
                {"name": m.name, "visibility": m.visibility}
                for m in iface.methods
            ],
        })

    return results


def design_all_hlrs(
    hlrs: list[dict],
    llrs: list[dict],
    language: str = "",
    model: str = "",
    log_dir: str = "",
) -> list[tuple[dict, OODesignSchema, DesignSchema]]:
    """Design each HLR individually in dependency order.

    Args:
        hlrs: All HLR dicts with keys: id, description, component_id?,
              component_name?, dependency_context?.
        llrs: All LLR dicts with keys: id, hlr_id, description.
        language: Target programming language.
        model: LLM model override.
        log_dir: Directory for per-step prompt logs.

    Returns:
        List of (hlr_dict, oo_design, ontology_design) tuples in design order.
    """
    # Step 1: Order HLRs (foundational first)
    prompt_log = os.path.join(log_dir, "order_hlrs.md") if log_dir else ""
    ordered = order_hlrs(hlrs, model=model, prompt_log_file=prompt_log)
    ordered_ids = [entry["id"] for entry in ordered]

    # Build lookup: hlr_id -> hlr dict
    hlr_by_id = {h["id"]: h for h in hlrs}

    # Build lookup: hlr_id -> list of LLR dicts
    llrs_by_hlr: dict[int, list[dict]] = {}
    for llr in llrs:
        hlr_id = llr.get("hlr_id")
        if hlr_id is not None:
            llrs_by_hlr.setdefault(hlr_id, []).append(llr)

    # Accumulate results per HLR
    # Maps hlr_id -> (oo_design, component_id, component_name)
    designed: dict[int, tuple[OODesignSchema, int | None, str]] = {}
    # Accumulated name -> qualified_name lookup across all prior designs
    accumulated_class_lookup: dict[str, str] = {}
    results: list[tuple[dict, OODesignSchema, DesignSchema]] = []

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
            hlr_id, i, len(ordered_ids), hlr["description"][:60],
        )

        # Gather existing_classes: same-component designs so far
        existing_classes = []
        for prev_id, (prev_oo, prev_comp_id, _) in designed.items():
            if prev_comp_id == component_id:
                existing_classes.extend(_extract_existing_classes(prev_oo))

        # Gather intercomponent_classes: other components' public APIs
        intercomponent_classes = []
        for prev_id, (prev_oo, prev_comp_id, prev_comp_name) in designed.items():
            intercomponent_classes.extend(
                _extract_intercomponent_context(
                    prev_oo, prev_comp_name, component_id, prev_comp_id,
                )
            )

        # Gather other HLR summaries
        other_hlr_summaries = []
        for other_hlr in hlrs:
            if other_hlr["id"] == hlr_id:
                continue
            status = "designed" if other_hlr["id"] in designed else "pending"
            other_hlr_summaries.append({
                "id": other_hlr["id"],
                "description": other_hlr["description"],
                "status": status,
            })

        # Build dependency context for this HLR
        dep_ctx = hlr.get("dependency_context")
        dependency_contexts = {hlr_id: dep_ctx} if dep_ctx else None

        # Design
        prompt_log = (
            os.path.join(log_dir, f"design_oo_hlr{hlr_id}.md") if log_dir else ""
        )
        # Gather component namespace and siblings
        component_namespace = hlr.get("component_namespace", "")
        sibling_namespaces = [
            h.get("component_namespace", "")
            for h in hlrs
            if h["id"] != hlr_id and h.get("component_namespace")
        ]

        oo = design_oo(
            hlr=hlr,
            llrs=hlr_llrs,
            language=language,
            existing_classes=existing_classes or None,
            intercomponent_classes=intercomponent_classes or None,
            other_hlr_summaries=other_hlr_summaries or None,
            dependency_contexts=dependency_contexts,
            component_namespace=component_namespace,
            sibling_namespaces=sibling_namespaces or None,
            model=model,
            prompt_log_file=prompt_log,
        )

        # Map to ontology — pass prior class lookup so cross-HLR
        # references (inheritance, associations) resolve to correct qnames
        ontology = map_oo_to_ontology(
            oo, component_id=component_id,
            prior_class_lookup=accumulated_class_lookup,
            component_namespace=component_namespace,
        )

        # Accumulate — update class lookup with this design's classes
        accumulated_class_lookup.update(_build_class_lookup(oo))
        designed[hlr_id] = (oo, component_id, component_name)
        results.append((hlr, oo, ontology))

        log.info(
            "  HLR %d: %d classes, %d interfaces, %d nodes, %d triples",
            hlr_id,
            len(oo.classes),
            len(oo.interfaces),
            len(ontology.nodes),
            len(ontology.triples),
        )

    return results
