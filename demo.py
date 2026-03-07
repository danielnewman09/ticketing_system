#!/usr/bin/env python
"""
Demo: end-to-end workflow from requirements to ontology design.

Workflow:
  1. Flush all data (clean slate, no re-migration)
  2. Decompose HLR descriptions into structured Actor/Action/Subject + LLRs
  3. Run the design agent to derive ontology nodes, edges, and requirement links
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
from codebase.models import OntologyNode, OntologyEdge
from requirements.models import (
    HighLevelRequirement,
    LowLevelRequirement,
    LLRVerification,
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
                actor=result.actor,
                action=result.action,
                subject=result.subject,
                description=desc,
            )
            for llr_data in result.low_level_requirements:
                llr = LowLevelRequirement.objects.create(
                    high_level_requirement=hlr,
                    actor=llr_data.actor,
                    action=llr_data.action,
                    subject=llr_data.subject,
                    description=llr_data.description,
                )
                for v in llr_data.verifications:
                    LLRVerification.objects.create(
                        low_level_requirement=llr,
                        method=v.method,
                        confirmation=v.confirmation,
                        test_name=v.test_name,
                    )

        llr_count = hlr.low_level_requirements.count()
        print(f"    -> HLR {hlr.pk}: {hlr.actor} | {hlr.action} | {hlr.subject}")
        print(f"       {llr_count} LLRs generated\n")

    total_hlrs = HighLevelRequirement.objects.count()
    total_llrs = LowLevelRequirement.objects.count()
    print(f"  Requirements phase complete: {total_hlrs} HLRs, {total_llrs} LLRs\n")


def step_design():
    print("=" * 60)
    print("STEP 3: Design — derive ontology from requirements")
    print("=" * 60)
    print("  Feeding all requirements to the design agent...\n")

    hlrs = list(HighLevelRequirement.objects.values(
        "id", "actor", "action", "subject", "description",
    ))
    llrs = list(LowLevelRequirement.objects.values(
        "id", "actor", "action", "subject", "description",
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

        # Save ontology edges
        for edge_data in result.edges:
            src = qname_to_node.get(edge_data.source_qualified_name)
            tgt = qname_to_node.get(edge_data.target_qualified_name)
            if src and tgt:
                OntologyEdge.objects.create(
                    source=src,
                    target=tgt,
                    relationship=edge_data.relationship,
                    label=edge_data.label,
                )
                print(f"  Edge: {src.name} --{edge_data.relationship}--> {tgt.name}")
            else:
                missing = edge_data.source_qualified_name if not src else edge_data.target_qualified_name
                print(f"  Edge skipped (missing node: {missing})")

        # Apply requirement links — set compound_refid on HLR/LLR actor/subject
        linked = 0
        for link in result.requirement_links:
            node = qname_to_node.get(link.node_qualified_name)
            if not node:
                continue

            refid = node.compound_refid
            if link.requirement_type == "hlr":
                obj = HighLevelRequirement.objects.filter(pk=link.requirement_id).first()
            else:
                obj = LowLevelRequirement.objects.filter(pk=link.requirement_id).first()

            if not obj:
                continue

            if link.role == "actor":
                obj.actor_compound_refid = refid
            else:
                obj.subject_compound_refid = refid
            obj.save()
            linked += 1

    print(f"\n  Design phase complete:")
    print(f"    {len(result.nodes)} nodes, {len(result.edges)} edges")
    print(f"    {linked} requirement-to-node links applied\n")


def step_summary():
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  HLRs:           {HighLevelRequirement.objects.count()}")
    print(f"  LLRs:           {LowLevelRequirement.objects.count()}")
    print(f"  Verifications:  {LLRVerification.objects.count()}")
    print(f"  Ontology nodes: {OntologyNode.objects.count()}")
    print(f"  Ontology edges: {OntologyEdge.objects.count()}")

    # Show which HLRs got linked
    for hlr in HighLevelRequirement.objects.all():
        actor_link = hlr.actor_compound_refid or "(none)"
        subject_link = hlr.subject_compound_refid or "(none)"
        print(f"\n  HLR {hlr.pk}: {hlr.actor} | {hlr.action} | {hlr.subject}")
        print(f"    actor  -> {actor_link}")
        print(f"    subject -> {subject_link}")

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
