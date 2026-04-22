"""
Master orchestrator for the spec-driven development pipeline.

Given an initial prompt, runs the full pipeline:
  HLR -> Decomposition -> Verification -> Design -> Tasks ->
  Skeleton -> Tests -> Implementation -> Sync Hooks -> Neo4j update
"""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from backend.db.models.tasks import Task

log = logging.getLogger("pipeline.orchestrator")


@dataclass
class PipelineResult:
    """Aggregated results from a full pipeline run."""
    hlrs_created: int = 0
    llrs_created: int = 0
    verifications_created: int = 0
    design_nodes: int = 0
    design_triples: int = 0
    tasks_created: int = 0
    skeleton_files: list[str] = field(default_factory=list)
    tests_created: int = 0
    implementations_created: int = 0
    sync_issues: list[str] = field(default_factory=list)
    neo4j_synced: bool = False
    benchmark_metrics: dict = field(default_factory=dict)


def _get_verification_dicts(session: Session) -> list[dict]:
    """Fetch all verification methods as dicts for the pipeline."""
    from backend.db.models import VerificationMethod
    verifs = session.query(VerificationMethod).all()
    result = []
    for v in verifs:
        result.append({
            "id": v.id,
            "test_name": v.test_name,
            "method": v.method,
            "description": v.description,
            "llr_id": v.low_level_requirement_id,
            "preconditions": [
                f"{c.member_qualified_name} {c.operator} {c.expected_value}"
                for c in v.conditions if c.phase == "pre"
            ],
            "actions": [a.description for a in v.actions],
            "postconditions": [
                f"{c.member_qualified_name} {c.operator} {c.expected_value}"
                for c in v.conditions if c.phase == "post"
            ],
        })
    return result


def run_pipeline(
    initial_prompt: str,
    session: Session,
    model: str = "",
    language: str = "python",
    workspace_dir: str = "",
    dry_run: bool = False,
) -> PipelineResult:
    """Run the full spec-driven development pipeline.

    Each phase calls the corresponding agent module and records results.
    Neo4j is updated incrementally after each phase.

    Args:
        initial_prompt: Natural language description of what to build.
        session: Active SQLAlchemy session.
        model: LLM model override for all agents.
        language: Target programming language (default: "python").
        workspace_dir: Root directory for generated source files.
        dry_run: If True, simulate phases without generating code.

    Returns:
        PipelineResult with counts and sync status.
    """
    from backend.db.models import (
        Component, HighLevelRequirement, LowLevelRequirement,
        OntologyNode, VerificationMethod,
    )
    from backend.db.models.tasks import Task

    result = PipelineResult()
    log.info("Pipeline started: %s", initial_prompt[:100])

    # ------------------------------------------------------------------
    # Phase 1-2: Decompose -- existing agent
    # ------------------------------------------------------------------
    log.info("Phase 1-2: Decomposing requirements...")
    from backend.ticketing_agent.decompose.decompose_hlr import decompose
    from backend.requirements.services.persistence import persist_decomposition

    hlrs = session.query(HighLevelRequirement).all()
    if not hlrs:
        log.warning("No HLRs found -- nothing to decompose.")
        return result

    for hlr in hlrs:
        llrs_existing = hlr.low_level_requirements
        if llrs_existing:
            result.llrs_created += len(llrs_existing)
            continue

        decomp_result = decompose(hlr.description, model=model)
        persisted = persist_decomposition(
            session, hlr, decomp_result.low_level_requirements,
        )
        result.llrs_created += persisted.llrs_created

    result.hlrs_created = session.query(HighLevelRequirement).count()
    total_llrs = session.query(LowLevelRequirement).count()
    log.info("  %d HLRs, %d LLRs", result.hlrs_created, total_llrs)

    # ------------------------------------------------------------------
    # Phase 3: Verification -- existing agent
    # ------------------------------------------------------------------
    log.info("Phase 3: Generating verification methods...")
    from backend.ticketing_agent.verify.verify_llr import verify
    from backend.requirements.services.persistence import (
        build_verification_context, persist_verification,
    )

    class_contexts = build_verification_context(session)
    ontology_nodes_list = [
        {"qualified_name": n.qualified_name, "pk": n.id, "kind": n.kind}
        for n in session.query(OntologyNode).all()
    ]

    for llr in session.query(LowLevelRequirement).all():
        existing_verifs = [
            {
                "method": v.method,
                "test_name": v.test_name,
                "description": v.description,
            }
            for v in llr.verifications
        ]
        if existing_verifs:
            result.verifications_created += len(existing_verifs)
            continue

        vv_result = verify(
            llr={"id": llr.id, "description": llr.description},
            existing_verifications=existing_verifs,
            class_contexts=class_contexts,
            ontology_nodes=ontology_nodes_list,
            model=model,
        )
        persist_result = persist_verification(
            session, llr, vv_result.verifications, ontology_nodes_list,
        )
        result.verifications_created += persist_result.conditions_created

    # ------------------------------------------------------------------
    # Phase 4: Design -- existing agents
    # ------------------------------------------------------------------
    log.info("Phase 4: Generating OO design...")
    from backend.ticketing_agent.design.design_hlr import design_hlr
    from backend.requirements.services.persistence import persist_design

    qname_to_node: dict[str, OntologyNode] = {}
    all_oo_classes: list[dict] = []

    for hlr in hlrs:
        hlr_dict = {
            "id": hlr.id,
            "description": hlr.description,
            "component_name": hlr.component.name if hlr.component else "",
        }
        llrs_for_hlr = [
            {
                "id": l.id,
                "description": l.description,
                "hlr_id": l.high_level_requirement_id,
            }
            for l in hlr.low_level_requirements
        ]
        comp_ns = hlr.component.namespace if hlr.component else ""

        oo, ontology = design_hlr(
            hlr=hlr_dict, llrs=llrs_for_hlr,
            component_namespace=comp_ns,
            component_id=hlr.component_id,
            model=model,
        )
        result.design_nodes += len(ontology.nodes)
        result.design_triples += len(ontology.triples)

        for cls in oo.classes:
            all_oo_classes.append({
                "name": cls.name,
                "module": cls.module,
                "attributes": [
                    {"name": a.name, "type_name": a.type_name}
                    for a in cls.attributes
                ],
                "methods": [
                    {
                        "name": m.name,
                        "parameters": m.parameters,
                        "return_type": m.return_type,
                    }
                    for m in cls.methods
                ],
            })

        persist_result = persist_design(
            session, ontology, qname_to_node=qname_to_node,
        )
        log.info(
            "  HLR %d: %d design nodes, %d triples",
            hlr.id,
            persist_result.nodes_created,
            persist_result.triples_created,
        )

    qname_to_node = {
        n.qualified_name: n
        for n in session.query(OntologyNode).all()
        if n.qualified_name
    }

    # ------------------------------------------------------------------
    # Phase 5: Task generation
    # ------------------------------------------------------------------
    log.info("Phase 5: Generating tasks...")
    from backend.ticketing_agent.generate_tasks import generate_tasks
    from backend.pipeline.services import persist_tasks

    all_verifications = _get_verification_dicts(session)

    for hlr in hlrs:
        hlr_dict = {
            "id": hlr.id,
            "description": hlr.description,
            "component_name": hlr.component.name if hlr.component else "",
        }
        llrs_for_hlr = [
            {
                "id": l.id,
                "description": l.description,
                "hlr_id": l.high_level_requirement_id,
            }
            for l in hlr.low_level_requirements
        ]

        hlr_classes = [
            c for c in all_oo_classes
            if c.get("module") == (hlr.component.name if hlr.component else "")
        ] or all_oo_classes[:3]  # fallback

        batch = generate_tasks(
            hlr=hlr_dict, llrs=llrs_for_hlr,
            oo_design={"classes": hlr_classes},
            verifications=all_verifications,
            model=model,
        )

        persist_result = persist_tasks(session, batch, qname_to_node)
        result.tasks_created += persist_result.tasks_created
        log.info(
            "  %d tasks, %d design links, %d verification links",
            persist_result.tasks_created,
            persist_result.links_to_design,
            persist_result.links_to_verification,
        )

    # ------------------------------------------------------------------
    # Phase 6: Skeleton generation
    # ------------------------------------------------------------------
    log.info("Phase 6: Generating skeleton...")
    from backend.ticketing_agent.generate_skeleton import generate_skeleton

    skeleton_results = generate_skeleton(
        oo_design={"classes": all_oo_classes},
        workspace_dir=workspace_dir,
    )
    result.skeleton_files = [r.file_path for r in skeleton_results]
    log.info("  %d skeleton files", len(result.skeleton_files))

    # ------------------------------------------------------------------
    # Phase 7: Test writing
    # ------------------------------------------------------------------
    log.info("Phase 7: Writing tests...")
    from backend.ticketing_agent.write_tests import write_tests

    llrs = session.query(LowLevelRequirement).all()
    for llr in llrs:
        llr_verifs = [
            v for v in all_verifications
            if v.get("llr_id") == llr.id
        ]
        if not llr_verifs:
            continue

        test_results = write_tests(
            verifications=llr_verifs,
            skeleton_files=result.skeleton_files,
            llr_id=llr.id,
            llr_description=llr.description,
            module_path="src",
            model=model,
        )
        result.tests_created += sum(
            len(t.test_names) for t in test_results
        )
        log.info("  LLR %d: %d test files, %d tests",
                 llr.id, len(test_results),
                 sum(len(t.test_names) for t in test_results))

    # ------------------------------------------------------------------
    # Phase 8: Implementation -- agent fills in skeleton
    # ------------------------------------------------------------------
    log.info("Phase 8: Implementing...")
    from backend.ticketing_agent.implement import (
        implement_task, write_implementation_files,
    )

    tasks = session.query(Task).all()
    skeleton_map: dict[str, str] = {}
    if workspace_dir:
        from pathlib import Path
        for sr in skeleton_results:
            p = Path(workspace_dir) / sr.file_path
            if p.exists():
                skeleton_map[sr.file_path] = p.read_text()

    for task in tasks:
        task_verifs = [
            v for v in all_verifications
            if v.get("test_name") in task.verifications
        ]

        # Get skeleton code for files this task modifies
        task_skeleton = ""
        for sr in skeleton_results:
            task_skeleton += f"# File: {sr.file_path}\n"
            task_skeleton += sr.content + "\n\n"

        impl_results = implement_task(
            task_title=task.title,
            task_description=task.description,
            skeleton_code=task_skeleton,
            verifications=task_verifs,
            model=model,
        )
        write_implementation_files(impl_results, workspace_dir)
        result.implementations_created += len(impl_results)
        log.info("  Task '%s': %d files implemented",
                 task.title, len(impl_results))

    # ------------------------------------------------------------------
    # Phase 9: Sync hooks
    # ------------------------------------------------------------------
    log.info("Phase 9: Running sync hooks...")
    from backend.pipeline.sync_hooks import (
        check_design_against_code,
        check_test_coverage,
    )

    source_files = []
    if workspace_dir:
        from pathlib import Path
        for p in Path(workspace_dir).rglob("*.py"):
            source_files.append(str(p))

    design_report = check_design_against_code(
        oo_design={"classes": all_oo_classes},
        source_files=source_files,
    )
    if not design_report.clean:
        for c in design_report.missing_classes:
            result.sync_issues.append(f"Missing class: {c}")
        for cls, methods in design_report.missing_methods.items():
            for m in methods:
                result.sync_issues.append(
                    f"Missing method: {cls}.{m}")

    test_names_expected = [
        v.get("test_name", "")
        for v in all_verifications
        if v.get("test_name")
    ]
    test_files_actual = []
    if workspace_dir:
        from pathlib import Path
        for p in Path(workspace_dir).rglob("tests/**/*.py"):
            test_files_actual.append(str(p))

    coverage_report = check_test_coverage(
        test_names_expected, test_files_actual,
    )
    if not coverage_report.clean:
        for name in coverage_report.untested_verifications:
            result.sync_issues.append(f"Untested: {name}")

    log.info("  Sync issues: %d", len(result.sync_issues))

    # ------------------------------------------------------------------
    # Phase 10: Neo4j update
    # ------------------------------------------------------------------
    log.info("Phase 10: Updating Neo4j...")
    try:
        from backend.db.neo4j_sync import (
            sync_task, sync_implementation_status,
            sync_full_design,
        )
        from backend.services.neo4j_service import get_neo4j_session

        with get_neo4j_session() as neo4j_sess:
            full_stats = sync_full_design(neo4j_sess, session)

            for task in session.query(Task).all():
                try:
                    sync_task(neo4j_sess, task)
                except Exception:
                    log.warning(
                        "Neo4j task sync failed for task %d", task.id,
                    )

            for node in session.query(OntologyNode).filter_by(
                implementation_status="implemented",
            ).all():
                sync_implementation_status(neo4j_sess, node)

        result.neo4j_synced = True
        log.info("  Neo4j sync: %d nodes, %d triples",
                 full_stats.get("nodes", 0),
                 full_stats.get("triples", 0))
    except Exception as e:
        log.warning("Neo4j sync skipped (unavailable): %s", e)
        result.neo4j_synced = False

    log.info("Pipeline complete: %d HLRs, %d LLRs, %d tasks, "
             "%d skeleton files, %d tests, %d impl files, "
             "%d sync issues, Neo4j=%s",
             result.hlrs_created, result.llrs_created,
             result.tasks_created, len(result.skeleton_files),
             result.tests_created, result.implementations_created,
             len(result.sync_issues), result.neo4j_synced)
    return result
