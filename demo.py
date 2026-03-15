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

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.core.management import call_command
from django.db import transaction
from django.db.models import F

from agents.design.design_ontology import design
from agents.verify.verify_llr import verify
from requirements.views.hlr import assign_hlr_components, decompose_hlr
from codebase.models import OntologyNode, OntologyTriple, Predicate
from requirements.models import (
    HighLevelRequirement,
    LowLevelRequirement,
    VerificationAction,
    VerificationCondition,
    VerificationMethod,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LOGS_DIR = os.path.join(os.path.dirname(__file__), "logs")

HLR_DESCRIPTIONS = [
    "The application displays a GUI window suitable for a calculator interface",
    "The calculator performs basic arithmetic with correct input handling and error recovery"
]


def step_flush():
    print("=" * 60)
    print("STEP 1: Flush database")
    print("=" * 60)
    call_command("flush", "--no-input", verbosity=0)
    Predicate.ensure_defaults()

    # Clear and recreate logs directory
    import shutil
    if os.path.exists(LOGS_DIR):
        shutil.rmtree(LOGS_DIR)
    os.makedirs(LOGS_DIR, exist_ok=True)

    print("  Database cleared.\n")


def step_assign_components():
    print("=" * 60)
    print("STEP 2: Create HLRs and assign components")
    print("=" * 60)

    for desc in HLR_DESCRIPTIONS:
        hlr = HighLevelRequirement.objects.create(description=desc)
        print(f"  Created HLR {hlr.pk}: {desc[:60]}")

    print(f"\n  Assigning {HighLevelRequirement.objects.count()} HLRs to components via AI agent...")
    assignments = assign_hlr_components(
        prompt_log_file=os.path.join(LOGS_DIR, "step2_assign_components.md"),
    )

    for a in assignments:
        print(f"  HLR {a['hlr_id']} -> {a['component_name']} ({a['rationale'][:60]})")

    print()


def step_decompose():
    print("=" * 60)
    print("STEP 3: Decompose requirements")
    print("=" * 60)

    hlrs = HighLevelRequirement.objects.all()
    print(f"  Decomposing {hlrs.count()} HLRs via AI agent...")
    print("  (each call hits the Anthropic API)\n")

    for i, hlr in enumerate(hlrs, 1):
        print(f"  [{i}/{hlrs.count()}] {hlr.description[:65]}...")
        llr_count = decompose_hlr(
            hlr,
            prompt_log_file=os.path.join(LOGS_DIR, f"step3_decompose_hlr{hlr.pk}.md"),
        )
        print(f"    -> HLR {hlr.pk}: {hlr.description[:60]}")
        print(f"       {llr_count} LLRs generated\n")

    total_hlrs = HighLevelRequirement.objects.count()
    total_llrs = LowLevelRequirement.objects.count()
    print(f"  Requirements phase complete: {total_hlrs} HLRs, {total_llrs} LLRs\n")


def step_design():
    print("=" * 60)
    print("STEP 4: Design — derive ontology from requirements")
    print("=" * 60)
    print("  Feeding all requirements to the design agent...\n")

    hlrs = list(HighLevelRequirement.objects.values("id", "description"))
    llrs = list(LowLevelRequirement.objects.values(
        "id", "description",
    ).annotate(hlr_id=F("high_level_requirement_id")))

    result = design(
        hlrs, llrs,
        prompt_log_file=os.path.join(LOGS_DIR, "step4_design.md"),
    )

    # Save ontology nodes
    qname_to_node = {}
    with transaction.atomic():
        for node_data in result.nodes:
            node = OntologyNode.objects.create(
                kind=node_data.kind,
                name=node_data.name,
                qualified_name=node_data.qualified_name,
                compound_refid=node_data.qualified_name,
                description=node_data.description,
            )
            qname_to_node[node_data.qualified_name] = node
            print(f"  Node: {node_data.qualified_name} ({node_data.kind})")

        # Save ontology triples in order (index-based lookup for requirement links)
        saved_triples = []
        for triple_data in result.triples:
            subj = qname_to_node.get(triple_data.subject_qualified_name)
            obj = qname_to_node.get(triple_data.object_qualified_name)
            pred = Predicate.objects.filter(name=triple_data.predicate).first()
            if subj and obj and pred:
                triple, _ = OntologyTriple.objects.get_or_create(
                    subject=subj,
                    predicate=pred,
                    object=obj,
                )
                saved_triples.append(triple)
                print(f"  Triple [{len(saved_triples)-1}]: {subj.name} --{pred.name}--> {obj.name}")
            else:
                saved_triples.append(None)
                if not pred:
                    print(f"  Triple [{len(saved_triples)-1}] skipped (unknown predicate: {triple_data.predicate})")
                else:
                    missing = triple_data.subject_qualified_name if not subj else triple_data.object_qualified_name
                    print(f"  Triple [{len(saved_triples)-1}] skipped (missing node: {missing})")

        # Apply requirement links
        linked = 0
        skipped = 0
        for link in result.requirement_links:
            triple = None
            if 0 <= link.triple_index < len(saved_triples):
                triple = saved_triples[link.triple_index]

            if not triple:
                skipped += 1
                print(f"    Link skipped (triple_index={link.triple_index}): {link.requirement_type} {link.requirement_id}")
                continue

            if link.requirement_type == "hlr":
                req = HighLevelRequirement.objects.filter(pk=link.requirement_id).first()
            else:
                req = LowLevelRequirement.objects.filter(pk=link.requirement_id).first()

            if req:
                req.triples.add(triple)
                linked += 1
            else:
                skipped += 1
                print(f"    Link skipped (no matching {link.requirement_type} {link.requirement_id})")

    print(f"\n  Design phase complete:")
    print(f"    {len(result.nodes)} nodes, {len(result.triples)} triples")
    print(f"    {linked} requirement-to-triple links applied, {skipped} skipped\n")


def step_verify():
    print("=" * 60)
    print("STEP 5: Verify — flesh out LLR verification procedures")
    print("=" * 60)

    ontology_nodes = list(
        OntologyNode.objects.values("qualified_name", "kind", "description")
    )
    llrs = LowLevelRequirement.objects.prefetch_related("verifications").all()

    print(f"  Processing {llrs.count()} LLRs against {len(ontology_nodes)} ontology nodes...\n")

    total_conditions = 0
    total_actions = 0

    for llr in llrs:
        llr_dict = {"id": llr.pk, "description": llr.description}
        existing = list(llr.verifications.values("method", "test_name", "description"))

        if not existing:
            print(f"  LLR {llr.pk}: no verifications to flesh out, skipping")
            continue

        print(f"  LLR {llr.pk}: {llr.description[:60]}...")
        result = verify(
            llr_dict, existing, ontology_nodes,
            prompt_log_file=os.path.join(LOGS_DIR, f"step5_verify_llr{llr.pk}.md"),
        )

        with transaction.atomic():
            # Replace existing verification stubs with fleshed-out versions
            llr.verifications.all().delete()

            for v in result.verifications:
                vm = VerificationMethod.objects.create(
                    low_level_requirement=llr,
                    method=v.method,
                    test_name=v.test_name,
                    description=v.description,
                )

                # Resolve ontology node references by qualified name prefix
                def resolve_node(member_qname):
                    if not member_qname:
                        return None
                    # Match the longest ontology node qualified_name that is a
                    # prefix of the member qualified name
                    for node in sorted(
                        ontology_nodes, key=lambda n: len(n["qualified_name"]), reverse=True
                    ):
                        if member_qname.startswith(node["qualified_name"]):
                            return OntologyNode.objects.filter(
                                qualified_name=node["qualified_name"]
                            ).first()
                    return None

                for i, cond in enumerate(v.preconditions):
                    VerificationCondition.objects.create(
                        verification=vm,
                        phase="pre",
                        order=i,
                        ontology_node=resolve_node(cond.member_qualified_name),
                        member_qualified_name=cond.member_qualified_name,
                        operator=cond.operator,
                        expected_value=cond.expected_value,
                    )
                    total_conditions += 1

                for i, action in enumerate(v.actions):
                    VerificationAction.objects.create(
                        verification=vm,
                        order=i,
                        description=action.description,
                        ontology_node=resolve_node(action.member_qualified_name),
                        member_qualified_name=action.member_qualified_name,
                    )
                    total_actions += 1

                for i, cond in enumerate(v.postconditions):
                    VerificationCondition.objects.create(
                        verification=vm,
                        phase="post",
                        order=i,
                        ontology_node=resolve_node(cond.member_qualified_name),
                        member_qualified_name=cond.member_qualified_name,
                        operator=cond.operator,
                        expected_value=cond.expected_value,
                    )
                    total_conditions += 1

                print(f"    [{vm.method}] {vm.test_name}: "
                      f"{len(v.preconditions)} pre, {len(v.actions)} actions, "
                      f"{len(v.postconditions)} post")

    print(f"\n  Verification phase complete:")
    print(f"    {total_conditions} conditions, {total_actions} actions created\n")


def step_summary():
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  HLRs:             {HighLevelRequirement.objects.count()}")
    print(f"  LLRs:             {LowLevelRequirement.objects.count()}")
    print(f"  Verifications:    {VerificationMethod.objects.count()}")
    print(f"  Conditions:       {VerificationCondition.objects.count()}")
    print(f"  Actions:          {VerificationAction.objects.count()}")
    print(f"  Ontology nodes:   {OntologyNode.objects.count()}")
    print(f"  Ontology triples: {OntologyTriple.objects.count()}")

    # Show which HLRs got linked
    for hlr in HighLevelRequirement.objects.prefetch_related("triples__subject", "triples__object").all():
        print(f"\n  HLR {hlr.pk}: {hlr.description[:60]}")
        for triple in hlr.triples.all():
            print(f"    -> {triple.subject.name} --{triple.predicate}--> {triple.object.name}")
        if not hlr.triples.exists():
            print(f"    (no triples linked)")

    print("\n" + "=" * 60)
    print("Start the server to explore:")
    print("  python manage.py runserver")
    print()
    print("Then visit:")
    print("  http://127.0.0.1:8000/ontology/        — graph visualization")
    print("  http://127.0.0.1:8000/requirements/     — requirements list")
    print("=" * 60)


if __name__ == "__main__":
    step_flush()
    step_assign_components()
    step_decompose()
    step_design()
    step_verify()
    step_summary()
