#!/usr/bin/env python
"""Generate tasks from HLRs through the design pipeline.

Reads existing HLRs + LLRs from Neo4j, runs decomposition/design,
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

from services.dependencies import init_neo4j, close_neo4j, get_neo4j
from backend.db import init_db, get_session
from backend.db.neo4j.repositories.verification import VerificationRepository
from backend.db.neo4j.repositories.requirement import RequirementRepository
from backend.requirements.formatting import format_hlrs_for_prompt
from backend.ticketing_agent.decompose.decompose_hlr import decompose
from backend.ticketing_agent.design.design_hlr import design_hlr
from backend.ticketing_agent.generate_tasks import generate_tasks
from backend.pipeline.services import persist_tasks, build_qname_to_node

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
LOGS_DIR = os.path.join(REPO_ROOT, "logs")


def _get_component_name(component_id):
    if component_id is None:
        return ""
    try:
        from backend.db.models import Component
        with get_session() as session:
            comp = session.query(Component).filter_by(id=component_id).first()
            return comp.name if comp else ""
    except Exception:
        return ""


def _get_component_namespace(component_id):
    if component_id is None:
        return ""
    try:
        from backend.db.models import Component
        with get_session() as session:
            comp = session.query(Component).filter_by(id=component_id).first()
            return comp.namespace if comp and comp.namespace else ""
    except Exception:
        return ""


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--hlr-id", type=int, help="Specific HLR to process")
    parser.add_argument("--model", default="", help="LLM model override")
    args = parser.parse_args()

    init_db()
    os.makedirs(LOGS_DIR, exist_ok=True)

    with get_neo4j().session() as ns:
        repo = RequirementRepository(ns)

        if args.hlr_id:
            hlr_obj = repo.get_hlr(args.hlr_id)
            hlrs_neo4j = [hlr_obj] if hlr_obj else []
        else:
            hlrs_neo4j = repo.list_hlrs()

        if not hlrs_neo4j:
            print("No HLRs found. Run 02_setup_project.py first.")
            return

        for hlr in hlrs_neo4j:
            print(f"\n{'='*60}")
            print(f"HLR {hlr.id}: {hlr.description[:60]}...")
            print(f"{'='*60}")

            llrs_neo4j = repo.list_llrs(hlr_id=hlr.id)
            llrs = [
                {"id": l.id, "description": l.description, "hlr_id": l.high_level_requirement_id}
                for l in llrs_neo4j
            ]

            # Decompose if no LLRs exist
            if not llrs:
                print("  Decomposing...")
                from backend.requirements.services.persistence import persist_decomposition

                result = decompose(
                    hlr.description,
                    prompt_log_file=os.path.join(LOGS_DIR, f"decompose_hlr{hlr.id}.md"),
                )
                with get_neo4j().session() as ns2:
                    persisted = persist_decomposition(ns2, hlr.id, result.low_level_requirements)
                llrs_neo4j = repo.list_llrs(hlr_id=hlr.id)
                llrs = [
                    {"id": l.id, "description": l.description, "hlr_id": l.high_level_requirement_id}
                    for l in llrs_neo4j
                ]
                print(f"  Generated {len(llrs)} LLRs")

            component_name = _get_component_name(hlr.component_id)
            component_namespace = _get_component_namespace(hlr.component_id)

            # Design
            hlr_dict = {
                "id": hlr.id,
                "description": hlr.description,
                "component_name": component_name,
            }

            print("  Designing...")
            oo, ontology = design_hlr(
                hlr=hlr_dict,
                llrs=llrs,
                component_namespace=component_namespace,
                component_id=hlr.component_id,
                prompt_log_file=os.path.join(LOGS_DIR, f"design_oo_hlr{hlr.id}.md"),
            )

            # Verifications from Neo4j
            verifications = []
            with get_neo4j().session() as ns:
                ver_repo = VerificationRepository(ns)
                for llr in llrs_neo4j:
                    for vm in ver_repo.list_verifications(llr.id):
                        verifications.append({
                            "method": vm.method,
                            "test_name": vm.test_name,
                            "description": vm.description,
                            "llr_id": llr.id,
                        })
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
            with get_session() as session:
                qname_map = build_qname_to_node(session)
                qname_map.update({c.name: component_namespace + "::" + c.name for c in oo.classes})
                result = persist_tasks(session, batch, qname_map)
                print(
                    f"  Persisted: {result.tasks_created} tasks, "
                    f"{result.links_to_design} design links, "
                    f"{result.links_to_verification} verification links"
                )


if __name__ == "__main__":
    init_neo4j()
    try:
        main()
    finally:
        close_neo4j()