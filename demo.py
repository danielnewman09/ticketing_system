#!/usr/bin/env python
"""
Demo: end-to-end workflow from requirements to ontology design.

Workflow:
  1. Flush all data (clean slate, no re-migration)
  2. Decompose HLR descriptions into structured Actor/Action/Subject + LLRs
  3. Run the design agent to derive ontology nodes, triples, and requirement links
  4. Print summary and launch instructions

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

from agents.decompose_hlr import decompose
from agents.design_ontology import design
from codebase.models import OntologyNode, OntologyTriple, Predicate
from requirements.models import (
    HighLevelRequirement,
    LowLevelRequirement,
    VerificationMethod,
)

# ---------------------------------------------------------------------------
# Configuration: the raw HLR descriptions a team would start with
# ---------------------------------------------------------------------------

HLR_DESCRIPTIONS = [
    "The application displays a GUI window suitable for a calculator interface",
    "The calculator performs basic arithmetic with correct input handling and error recovery",
    "The calculator logic is fully unit-tested with 100% code coverage",
    "A CI pipeline builds, tests, and enforces quality gates automatically",
]


def step_flush():
    print("=" * 60)
    print("STEP 1: Flush database")
    print("=" * 60)
    call_command("flush", "--no-input", verbosity=0)
    Predicate.ensure_defaults()
    print("  Database cleared.\n")


def step_decompose():
    print("=" * 60)
    print("STEP 2: Decompose requirements")
    print("=" * 60)
    print(f"  Decomposing {len(HLR_DESCRIPTIONS)} HLR descriptions via AI agent...")
    print("  (each call hits the Anthropic API)\n")

    for i, desc in enumerate(HLR_DESCRIPTIONS, 1):
        print(f"  [{i}/{len(HLR_DESCRIPTIONS)}] {desc[:65]}...")

        result = decompose(desc)

        with transaction.atomic():
            hlr = HighLevelRequirement.objects.create(
                description=desc,
            )
            for llr_data in result.low_level_requirements:
                llr = LowLevelRequirement.objects.create(
                    high_level_requirement=hlr,
                    description=llr_data.description,
                )
                for v in llr_data.verifications:
                    VerificationMethod.objects.create(
                        low_level_requirement=llr,
                        method=v.method,
                        test_name=v.test_name,
                        description=v.description,
                    )

        llr_count = hlr.low_level_requirements.count()
        print(f"    -> HLR {hlr.pk}: {desc[:60]}")
        print(f"       {llr_count} LLRs generated\n")

    total_hlrs = HighLevelRequirement.objects.count()
    total_llrs = LowLevelRequirement.objects.count()
    print(f"  Requirements phase complete: {total_hlrs} HLRs, {total_llrs} LLRs\n")


def step_design():
    print("=" * 60)
    print("STEP 3: Design — derive ontology from requirements")
    print("=" * 60)
    print("  Feeding all requirements to the design agent...\n")

    hlrs = list(HighLevelRequirement.objects.values("id", "description"))
    llrs = list(LowLevelRequirement.objects.values(
        "id", "description",
    ).annotate(hlr_id=F("high_level_requirement_id")))

    result = design(hlrs, llrs)

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


def step_summary():
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  HLRs:             {HighLevelRequirement.objects.count()}")
    print(f"  LLRs:             {LowLevelRequirement.objects.count()}")
    print(f"  Verifications:    {VerificationMethod.objects.count()}")
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
    step_decompose()
    step_design()
    step_summary()
