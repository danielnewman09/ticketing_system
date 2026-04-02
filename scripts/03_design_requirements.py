#!/usr/bin/env python
"""
Design requirements: decompose, design, verify.

Steps:
  1. Decompose HLRs into LLRs
  2. Design — discover + design + map per HLR (in dependency order)
  3. Verify — flesh out LLR verification procedures
  4. Print summary

Assumes setup_project.py has been run (HLRs and components exist).

Usage:
    source .venv/bin/activate
    python scripts/design_requirements.py

Requires ANTHROPIC_API_KEY in the environment.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from backend.db import init_db, get_session
from backend.db.models import (
    HighLevelRequirement,
    LowLevelRequirement,
    OntologyNode,
    OntologyTriple,
    VerificationAction,
    VerificationCondition,
    VerificationMethod,
)

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
LOGS_DIR = os.path.join(REPO_ROOT, "logs")


def step_decompose():
    print("=" * 60)
    print("STEP 1: Decompose requirements")
    print("=" * 60)

    from backend.ticketing_agent.decompose.decompose_hlr import decompose
    from backend.requirements.services.persistence import persist_decomposition

    os.makedirs(LOGS_DIR, exist_ok=True)

    with get_session() as session:
        hlrs = session.query(HighLevelRequirement).all()
        if not hlrs:
            print("  No HLRs found. Run setup_project.py first.\n")
            return

        print(f"  Decomposing {len(hlrs)} HLRs via AI agent...\n")

        for i, hlr in enumerate(hlrs, 1):
            print(f"  [{i}/{len(hlrs)}] {hlr.description[:65]}...")

            other_hlrs = [
                {"id": h.id, "description": h.description, "component__name": h.component.name if h.component else None}
                for h in session.query(HighLevelRequirement).filter(HighLevelRequirement.id != hlr.id).all()
            ]
            component_name = hlr.component.name if hlr.component_id else ""

            result = decompose(
                hlr.description,
                other_hlrs=other_hlrs,
                component=component_name,
                dependency_context=hlr.dependency_context,
                prompt_log_file=os.path.join(LOGS_DIR, f"decompose_hlr{hlr.id}.md"),
            )

            persisted = persist_decomposition(session, hlr, result.low_level_requirements)
            print(f"    -> HLR {hlr.id}: {hlr.description[:60]}")
            print(f"       {persisted.llrs_created} LLRs generated\n")

        total_hlrs = session.query(HighLevelRequirement).count()
        total_llrs = session.query(LowLevelRequirement).count()
        print(f"  Requirements phase complete: {total_hlrs} HLRs, {total_llrs} LLRs\n")


def step_design():
    print("=" * 60)
    print("STEP 2: Design — discover + design + map per HLR")
    print("=" * 60)
    print("  Designing each HLR individually in dependency order...\n")

    from backend.ticketing_agent.design.design_hlr import design_hlr
    from backend.ticketing_agent.design.design_per_hlr import (
        _build_class_lookup,
        _extract_existing_classes,
        _extract_intercomponent_context,
    )
    from backend.ticketing_agent.design.order_hlrs import order_hlrs
    from backend.codebase.schemas import OODesignSchema
    from backend.requirements.services.persistence import persist_design

    with get_session() as session:
        hlrs = [
            {
                "id": h.id,
                "description": h.description,
                "component_id": h.component_id,
                "dependency_context": h.dependency_context,
                "component_name": h.component.name if h.component else None,
                "component_namespace": h.component.namespace if h.component else "",
                "component_description": h.component.description if h.component else "",
            }
            for h in session.query(HighLevelRequirement).all()
        ]
        llrs = [
            {"id": l.id, "description": l.description, "hlr_id": l.high_level_requirement_id}
            for l in session.query(LowLevelRequirement).all()
        ]

    if not hlrs:
        print("  No HLRs found. Run setup_project.py first.\n")
        return

    # Order HLRs
    prompt_log = os.path.join(LOGS_DIR, "order_hlrs.md")
    ordered = order_hlrs(hlrs, prompt_log_file=prompt_log)
    ordered_ids = [entry["id"] for entry in ordered]

    hlr_by_id = {h["id"]: h for h in hlrs}
    llrs_by_hlr: dict[int, list[dict]] = {}
    for llr in llrs:
        hlr_id = llr.get("hlr_id")
        if hlr_id is not None:
            llrs_by_hlr.setdefault(hlr_id, []).append(llr)

    # Accumulate
    designed: dict[int, tuple[OODesignSchema, int | None, str]] = {}
    accumulated_class_lookup: dict[str, str] = {}
    total_nodes = 0
    total_triples = 0
    total_linked = 0
    total_skipped = 0
    qname_to_node: dict = {}

    # Connect to dependency graph
    dep_toolset = None
    try:
        from doxygen_index.tools import create_toolset
        dep_toolset = create_toolset()
        print("  Dependency graph connected\n")
    except Exception as e:
        print(f"  Dependency graph unavailable: {e}\n")

    try:
        for i, hlr_id in enumerate(ordered_ids, 1):
            hlr = hlr_by_id.get(hlr_id)
            if not hlr:
                continue

            hlr_llrs = llrs_by_hlr.get(hlr_id, [])
            component_id = hlr.get("component_id")
            component_name = hlr.get("component_name", "")

            print(f"  [{i}/{len(ordered_ids)}] HLR {hlr_id}: {hlr['description'][:55]}...")

            # Gather in-memory context
            existing_classes = []
            for prev_id, (prev_oo, prev_comp_id, _) in designed.items():
                if prev_comp_id == component_id:
                    existing_classes.extend(_extract_existing_classes(prev_oo))

            intercomponent_classes = []
            for prev_id, (prev_oo, prev_comp_id, prev_comp_name) in designed.items():
                intercomponent_classes.extend(
                    _extract_intercomponent_context(
                        prev_oo, prev_comp_name, component_id, prev_comp_id,
                    )
                )

            other_hlr_summaries = [
                {
                    "id": h["id"],
                    "description": h["description"],
                    "status": "designed" if h["id"] in designed else "pending",
                }
                for h in hlrs if h["id"] != hlr_id
            ]

            dep_ctx = hlr.get("dependency_context")
            dependency_contexts = {hlr_id: dep_ctx} if dep_ctx else None

            component_namespace = hlr.get("component_namespace", "")
            sibling_namespaces = [
                h.get("component_namespace", "")
                for h in hlrs
                if h["id"] != hlr_id and h.get("component_namespace")
            ]

            # Design single HLR
            oo, ontology = design_hlr(
                hlr=hlr,
                llrs=hlr_llrs,
                existing_classes=existing_classes or None,
                intercomponent_classes=intercomponent_classes or None,
                other_hlr_summaries=other_hlr_summaries or None,
                dependency_contexts=dependency_contexts,
                component_namespace=component_namespace,
                sibling_namespaces=sibling_namespaces or None,
                component_id=component_id,
                prior_class_lookup=accumulated_class_lookup,
                toolset=dep_toolset,
                log_dir=LOGS_DIR,
            )

            # Accumulate
            accumulated_class_lookup.update(_build_class_lookup(oo))
            designed[hlr_id] = (oo, component_id, component_name)

            # Persist
            with get_session() as session:
                for node_data in ontology.nodes:
                    if node_data.qualified_name not in qname_to_node:
                        flag = " [intercomponent]" if node_data.is_intercomponent else ""
                        print(f"    Node: {node_data.qualified_name} ({node_data.kind}){flag}")

                persisted = persist_design(session, ontology, qname_to_node=qname_to_node)
                total_nodes += persisted.nodes_created
                total_triples += persisted.triples_created
                total_linked += persisted.links_applied
                total_skipped += persisted.links_skipped
    finally:
        if dep_toolset:
            dep_toolset.close()
            print("  Dependency graph disconnected")

    print(f"\n  Design phase complete:")
    print(f"    {total_nodes} nodes, {total_triples} triples")
    print(f"    {total_linked} requirement-to-triple links applied, {total_skipped} skipped\n")


def step_verify():
    print("=" * 60)
    print("STEP 3: Verify — flesh out LLR verification procedures")
    print("=" * 60)

    from backend.ticketing_agent.verify.verify_llr import verify
    from backend.requirements.services.persistence import (
        build_verification_context,
        persist_verification,
        augment_design_for_unresolved,
    )

    with get_session() as session:
        class_contexts = build_verification_context(session)
        ontology_nodes = [
            {"qualified_name": n.qualified_name, "pk": n.id, "kind": n.kind, "description": n.description}
            for n in session.query(OntologyNode).all()
        ]
        llrs = session.query(LowLevelRequirement).all()

        if not llrs:
            print("  No LLRs found.\n")
            return

        print(f"  Processing {len(llrs)} LLRs with {len(class_contexts)} class contexts...\n")

        total_conditions = 0
        total_actions = 0
        total_augmented = 0

        for llr in llrs:
            llr_dict = {"id": llr.id, "description": llr.description}
            existing = [
                {"method": v.method, "test_name": v.test_name, "description": v.description}
                for v in llr.verifications
            ]

            if not existing:
                print(f"  LLR {llr.id}: no verifications to flesh out, skipping")
                continue

            print(f"  LLR {llr.id}: {llr.description[:60]}...")
            agent_result = verify(
                llr_dict, existing, class_contexts,
                ontology_nodes=ontology_nodes,
                prompt_log_file=os.path.join(LOGS_DIR, f"verify_llr{llr.id}.md"),
            )

            if agent_result.validation and not agent_result.validation.all_resolved:
                print(f"    WARN: {len(agent_result.validation.unresolved)} unresolved references")
                for qname, ctx in agent_result.validation.unresolved:
                    print(f"      - {qname} ({ctx})")

            persisted = persist_verification(session, llr, agent_result.verifications, ontology_nodes)
            total_conditions += persisted.conditions_created
            total_actions += persisted.actions_created

            if agent_result.validation and not agent_result.validation.all_resolved:
                augmented = augment_design_for_unresolved(
                    session, agent_result.validation.unresolved,
                )
                if augmented.nodes_created:
                    total_augmented += augmented.nodes_created
                    print(f"    Created {augmented.nodes_created} missing design nodes, "
                          f"{augmented.triples_created} triples")
                    ontology_nodes = [
                        {"qualified_name": n.qualified_name, "pk": n.id, "kind": n.kind, "description": n.description}
                        for n in session.query(OntologyNode).all()
                    ]
                    class_contexts = build_verification_context(session)

            for v in agent_result.verifications:
                print(f"    [{v.method}] {v.test_name}: "
                      f"{len(v.preconditions)} pre, {len(v.actions)} actions, "
                      f"{len(v.postconditions)} post")

        print(f"\n  Verification phase complete:")
        print(f"    {total_conditions} conditions, {total_actions} actions created")
        if total_augmented:
            print(f"    {total_augmented} design nodes created via closed loop\n")
        else:
            print()


def step_summary():
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)

    with get_session() as session:
        print(f"  HLRs:             {session.query(HighLevelRequirement).count()}")
        print(f"  LLRs:             {session.query(LowLevelRequirement).count()}")
        print(f"  Verifications:    {session.query(VerificationMethod).count()}")
        print(f"  Conditions:       {session.query(VerificationCondition).count()}")
        print(f"  Actions:          {session.query(VerificationAction).count()}")
        print(f"  Ontology nodes:   {session.query(OntologyNode).count()}")
        print(f"  Ontology triples: {session.query(OntologyTriple).count()}")

        for hlr in session.query(HighLevelRequirement).all():
            print(f"\n  HLR {hlr.id}: {hlr.description[:60]}")
            for triple in hlr.triples:
                print(f"    -> {triple.subject.name} --{triple.predicate}--> {triple.object.name}")
            if not hlr.triples:
                print(f"    (no triples linked)")

    print("\n" + "=" * 60)
    print("Explore in the dashboard:")
    print("  python nicegui_app.py")
    print("  http://127.0.0.1:8081/")
    print("=" * 60)


if __name__ == "__main__":
    init_db()
    step_decompose()
    step_design()
    step_verify()
    step_summary()
