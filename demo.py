#!/usr/bin/env python
"""
Demo: end-to-end workflow from requirements to ontology design.

Workflow:
  1. Flush all data (clean slate, no re-migration)
  2. Create HLRs, assign components, and assess dependencies
  3. Decompose HLR descriptions into structured Actor/Action/Subject + LLRs
  4. Run the design agent to derive ontology nodes, triples, and requirement links
  5. Verify — flesh out LLR verification procedures
  6. Print summary and launch instructions

Usage:
    source .venv/bin/activate
    python demo.py

Requires ANTHROPIC_API_KEY in the environment.
"""

import os
import sys

from db import init_db, get_session, get_or_create
from db.base import Base
from db.models import (
    Component,
    HighLevelRequirement,
    LowLevelRequirement,
    OntologyNode,
    OntologyTriple,
    Predicate,
    VerificationAction,
    VerificationCondition,
    VerificationMethod,
)
from db.vec import ensure_vec_table

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LOGS_DIR = os.path.join(os.path.dirname(__file__), "logs")

HLR_DESCRIPTIONS = [
    "The application displays a GUI window with a numeric display area and buttons for digits 0-9, basic arithmetic operators (+, -, ×, ÷), a clear button, and an equals button",
    "The calculator performs addition, subtraction, multiplication, and division operations with proper input validation, returns results immediately, and recovers from errors such as division by zero or invalid syntax",
]


def step_flush():
    print("=" * 60)
    print("STEP 1: Flush database")
    print("=" * 60)

    from db import get_main_engine
    from db.neo4j_sync import clear_design_graph

    engine = get_main_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    ensure_vec_table()

    with get_session() as session:
        Predicate.ensure_defaults(session)

    # Clear Neo4j design graph
    clear_design_graph()

    # Clear and recreate logs directory
    import shutil
    if os.path.exists(LOGS_DIR):
        shutil.rmtree(LOGS_DIR)
    os.makedirs(LOGS_DIR, exist_ok=True)

    print("  Database cleared (SQLite + Neo4j).\n")


def step_assign_components():
    print("=" * 60)
    print("STEP 2: Create HLRs and assign components")
    print("=" * 60)

    from agents.design.assign_components import assign_components

    with get_session() as session:
        for desc in HLR_DESCRIPTIONS:
            hlr = HighLevelRequirement(description=desc)
            session.add(hlr)
        session.flush()

        hlr_count = session.query(HighLevelRequirement).count()
        print(f"\n  Assigning {hlr_count} HLRs to components via AI agent...")

        hlr_dicts = [
            {"id": h.id, "description": h.description}
            for h in session.query(HighLevelRequirement).all()
        ]
        existing = [name for (name,) in session.query(Component.name).all()]

        assignments = assign_components(
            hlr_dicts,
            existing_components=existing or None,
            prompt_log_file=os.path.join(LOGS_DIR, "step2_assign_components.md"),
        )

        # First pass: create/update components with namespaces and parents
        component_cache: dict[str, Component] = {}
        for a in assignments:
            comp_name = a["component_name"]
            if comp_name in component_cache:
                continue
            namespace = a.get("namespace", "")
            desc = a.get("description", "")
            component, _ = get_or_create(
                session, Component,
                defaults={"namespace": namespace, "description": desc},
                name=comp_name,
            )
            if not component.namespace and namespace:
                component.namespace = namespace
            if not component.description and desc:
                component.description = desc
            component_cache[comp_name] = component

        # Set parent relationships
        session.flush()
        for a in assignments:
            parent_name = a.get("parent_component_name", "")
            if parent_name and parent_name in component_cache:
                child = component_cache[a["component_name"]]
                parent = component_cache[parent_name]
                if child.id != parent.id:
                    child.parent_id = parent.id

        session.flush()

        # Second pass: assign HLRs
        for a in assignments:
            component = component_cache[a["component_name"]]
            session.query(HighLevelRequirement).filter_by(id=a["hlr_id"]).update(
                {"component_id": component.id}
            )
            ns_info = f" ns={component.namespace}" if component.namespace else ""
            print(f"  HLR {a['hlr_id']} -> {a['component_name']}{ns_info} ({a['rationale'][:50]})")

    print()


def step_decompose():
    print("=" * 60)
    print("STEP 3: Decompose requirements")
    print("=" * 60)

    from requirements.agents.decompose_hlr import decompose
    from requirements.services.persistence import persist_decomposition

    with get_session() as session:
        hlrs = session.query(HighLevelRequirement).all()
        print(f"  Decomposing {len(hlrs)} HLRs via AI agent...")
        print("  (each call hits the Anthropic API)\n")

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
                prompt_log_file=os.path.join(LOGS_DIR, f"step3_decompose_hlr{hlr.id}.md"),
            )

            persisted = persist_decomposition(session, hlr, result.low_level_requirements)
            print(f"    -> HLR {hlr.id}: {hlr.description[:60]}")
            print(f"       {persisted.llrs_created} LLRs generated\n")

        total_hlrs = session.query(HighLevelRequirement).count()
        total_llrs = session.query(LowLevelRequirement).count()
        print(f"  Requirements phase complete: {total_hlrs} HLRs, {total_llrs} LLRs\n")


def step_design():
    print("=" * 60)
    print("STEP 4: Design — derive ontology per HLR")
    print("=" * 60)
    print("  Designing each HLR individually in dependency order...\n")

    from agents.design.design_per_hlr import design_all_hlrs
    from requirements.services.persistence import persist_design

    with get_session() as session:
        hlrs = [
            {
                "id": h.id,
                "description": h.description,
                "component_id": h.component_id,
                "dependency_context": h.dependency_context,
                "component_name": h.component.name if h.component else None,
                "component_namespace": h.component.namespace if h.component else "",
            }
            for h in session.query(HighLevelRequirement).all()
        ]
        llrs = [
            {"id": l.id, "description": l.description, "hlr_id": l.high_level_requirement_id}
            for l in session.query(LowLevelRequirement).all()
        ]

        per_hlr_results = design_all_hlrs(
            hlrs, llrs,
            log_dir=LOGS_DIR,
        )

        total_nodes = 0
        total_triples = 0
        total_linked = 0
        total_skipped = 0
        qname_to_node = {}

        for hlr_dict, oo, result in per_hlr_results:
            print(f"\n  --- HLR {hlr_dict['id']}: {hlr_dict['description'][:50]}... ---")

            for node_data in result.nodes:
                if node_data.qualified_name not in qname_to_node:
                    flag = " [intercomponent]" if node_data.is_intercomponent else ""
                    print(f"  Node: {node_data.qualified_name} ({node_data.kind}){flag}")

            persisted = persist_design(session, result, qname_to_node=qname_to_node)
            total_nodes += persisted.nodes_created
            total_triples += persisted.triples_created
            total_linked += persisted.links_applied
            total_skipped += persisted.links_skipped

        print(f"\n  Design phase complete:")
        print(f"    {total_nodes} nodes, {total_triples} triples")
        print(f"    {total_linked} requirement-to-triple links applied, {total_skipped} skipped\n")


def step_verify():
    print("=" * 60)
    print("STEP 5: Verify — flesh out LLR verification procedures")
    print("=" * 60)

    from agents.verify.verify_llr import verify
    from requirements.services.persistence import (
        build_verification_context,
        persist_verification,
        augment_design_for_unresolved,
    )

    with get_session() as session:
        # Build structured design context
        class_contexts = build_verification_context(session)
        ontology_nodes = [
            {"qualified_name": n.qualified_name, "pk": n.id, "kind": n.kind, "description": n.description}
            for n in session.query(OntologyNode).all()
        ]
        llrs = session.query(LowLevelRequirement).all()

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
                prompt_log_file=os.path.join(LOGS_DIR, f"step5_verify_llr{llr.id}.md"),
            )

            # Report validation
            if agent_result.validation and not agent_result.validation.all_resolved:
                print(f"    WARN: {len(agent_result.validation.unresolved)} unresolved references")
                for qname, ctx in agent_result.validation.unresolved:
                    print(f"      - {qname} ({ctx})")

            persisted = persist_verification(session, llr, agent_result.verifications, ontology_nodes)
            total_conditions += persisted.conditions_created
            total_actions += persisted.actions_created

            # Closed loop: create missing design nodes
            if agent_result.validation and not agent_result.validation.all_resolved:
                augmented = augment_design_for_unresolved(
                    session, agent_result.validation.unresolved,
                )
                if augmented.nodes_created:
                    total_augmented += augmented.nodes_created
                    print(f"    Created {augmented.nodes_created} missing design nodes, "
                          f"{augmented.triples_created} triples")
                    # Refresh ontology_nodes for subsequent LLRs
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
    print("Start the NiceGUI server to explore:")
    print("  python nicegui_app.py")
    print()
    print("Then visit:")
    print("  http://127.0.0.1:8081/")
    print("=" * 60)


if __name__ == "__main__":
    init_db()
    step_flush()
    step_assign_components()
    step_decompose()
    step_design()
    # step_verify()
    # step_summary()
