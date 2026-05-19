#!/usr/bin/env python
"""
Generate tasks from HLRs through the design pipeline.

Reads existing HLRs + LLRs from the database, runs decomposition/design,
then generates implementation tasks linked to design nodes and verifications.

Usage:
    source .venv/bin/activate
    python scripts/05_generate_tasks.py [--hlr-id ID] [--model MODEL]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from backend.db import init_db, get_session
from backend.db.models import HighLevelRequirement, LowLevelRequirement
from backend.db.models.requirements import format_hlrs_for_prompt
from backend.ticketing_agent.decompose.decompose_hlr import decompose
from backend.ticketing_agent.design.design_hlr import design_hlr
from backend.ticketing_agent.generate_tasks import generate_tasks
from backend.pipeline.services import persist_tasks, build_qname_to_node

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
LOGS_DIR = os.path.join(REPO_ROOT, "logs")


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--hlr-id", type=int, help="Specific HLR to process")
    parser.add_argument("--model", default="", help="LLM model override")
    args = parser.parse_args()

    init_db()
    os.makedirs(LOGS_DIR, exist_ok=True)

    with get_session() as session:
        if args.hlr_id:
            hlrs = [session.query(HighLevelRequirement).filter_by(id=args.hlr_id).first()]
            hlrs = [h for h in hlrs if h]  # filter None
        else:
            hlrs = session.query(HighLevelRequirement).all()

        if not hlrs:
            print("No HLRs found. Run 02_setup_project.py first.")
            return

        for hlr in hlrs:
            print(f"\n{'='*60}")
            print(f"HLR {hlr.id}: {hlr.description[:60]}...")
            print(f"{'='*60}")

            llrs = [
                {"id": l.id, "description": l.description, "hlr_id": l.high_level_requirement_id}
                for l in hlr.low_level_requirements
            ]

            # Decompose if no LLRs exist
            if not llrs:
                print("  Decomposing...")
                result = decompose(
                    hlr.description,
                    prompt_log_file=os.path.join(LOGS_DIR, f"decompose_hlr{hlr.id}.md"),
                )
                from backend.requirements.services.persistence import persist_decomposition
                persist_decomposition(session, hlr, result.low_level_requirements)
                llrs = [
                    {"id": l.id, "description": l.description, "hlr_id": l.high_level_requirement_id}
                    for l in hlr.low_level_requirements
                ]
                print(f"  Generated {len(llrs)} LLRs")

            # Design
            hlr_dict = {
                "id": hlr.id,
                "description": hlr.description,
                "component_name": hlr.component.name if hlr.component else "",
            }
            component_namespace = hlr.component.namespace if hlr.component else ""
            component_id = hlr.component_id

            print("  Designing...")
            oo, ontology = design_hlr(
                hlr=hlr_dict,
                llrs=llrs,
                component_namespace=component_namespace,
                component_id=component_id,
                prompt_log_file=os.path.join(LOGS_DIR, f"design_oo_hlr{hlr.id}.md"),
            )
            print(f"  Design: {len(oo.classes)} classes, {len(oo.interfaces)} interfaces")

            # Verifications
            verifications = []
            for llr in hlr.low_level_requirements:
                verifications.extend([
                    {**v.model_dump(), "llr_id": llr.id}
                    for v in llr.verifications
                ])
            print(f"  Verifications: {len(verifications)}")

            # Tasks
            print("  Generating tasks...")
            batch = generate_tasks(
                hlr=hlr_dict,
                llrs=llrs,
                oo_design=oo.model_dump(),
                verifications=verifications,
                model=args.model,
                prompt_log_file=os.path.join(LOGS_DIR, f"generate_tasks_hlr{hlr.id}.md"),
            )
            print(f"  Generated {len(batch.tasks)} tasks")

            # Persist
            qname_map = build_qname_to_node(session)
            qname_map.update({
                c.name: component_namespace + "::" + c.name
                for c in oo.classes
            })
            result = persist_tasks(session, batch, qname_map)
            print(f"  Persisted: {result.tasks_created} tasks, "
                  f"{result.links_to_design} design links, "
                  f"{result.links_to_verification} verification links")


if __name__ == "__main__":
    main()
