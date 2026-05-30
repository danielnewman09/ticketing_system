"""
Master orchestrator for the spec-driven development pipeline.

Given an initial prompt, runs the full pipeline:
  HLR -> Decomposition -> Verification -> Design -> Tasks ->
  Skeleton -> Tests -> Implementation -> Sync Hooks -> Neo4j update

Phase 3: Verification data lives in Neo4j via VerificationRepository.
"""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.db.models.tasks import Task

log = logging.getLogger("pipeline.orchestrator")


def _get_component_name(component_id: int | None) -> str | None:
    """Look up a component name by ID from SQLite."""
    if component_id is None:
        return None
    try:
        from backend.db.models import Component
        from backend.db import get_session
        with get_session() as session:
            comp = session.query(Component).filter_by(id=component_id).first()
            return comp.name if comp else None
    except Exception:
        return None




def _merge_diagrams(base, new):
    """Merge new diagram into base, returning a fresh ClassDiagram with rebuilt index."""
    from backend.design_data.models import ClassDiagram
    return ClassDiagram(
        module_names=list(dict.fromkeys(base.module_names + new.module_names)),
        classes=base.classes + new.classes,
        interfaces=base.interfaces + new.interfaces,
        enums=base.enums + new.enums,
        associations=base.associations + new.associations,
    )


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


def _get_verification_dicts(neo4j_session) -> list[dict]:
    """Fetch all verification methods from Neo4j as dicts for the pipeline."""
    from backend.db.neo4j.repositories.verification import VerificationRepository

    repo = VerificationRepository(neo4j_session)
    # Get all LLRs to find their verifications
    from backend.db.neo4j.repositories.requirement import RequirementRepository
    req_repo = RequirementRepository(neo4j_session)
    all_llrs = req_repo.list_llrs()

    result = []
    for llr in all_llrs:
        for vm in repo.list_verifications(llr.id):
            conditions = repo.list_conditions(vm.id)
            actions = repo.list_actions(vm.id)
            pre = [c for c in conditions if c.phase == "pre"]
            post = [c for c in conditions if c.phase == "post"]
            result.append({
                "id": vm.id,
                "test_name": vm.test_name,
                "method": vm.method,
                "description": vm.description,
                "llr_id": vm.llr_id,
                "preconditions": [
                    f"{c.subject_qualified_name} {c.operator} {c.expected_value}"
                    for c in pre
                ],
                "actions": [a.description for a in actions],
                "postconditions": [
                    f"{c.subject_qualified_name} {c.operator} {c.expected_value}"
                    for c in post
                ],
            })
    return result


def run_pipeline(
    initial_prompt: str,
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
        model: LLM model override for all agents.
        language: Target programming language (default: "python").
        workspace_dir: Root directory for generated source files.
        dry_run: If True, simulate phases without generating code.

    Returns:
        PipelineResult with counts and sync status.
    """
    from backend.db import get_session
    from backend.db.models import Component, OntologyNode
    from backend.db.models.tasks import Task
    from backend.db.neo4j.repositories.requirement import RequirementRepository
    from backend.db.neo4j.repositories.verification import VerificationRepository
    from services.dependencies import get_neo4j

    result = PipelineResult()
    log.info("Pipeline started: %s", initial_prompt[:100])

    # ------------------------------------------------------------------
    # Phase 1-2: Decompose -- existing agent
    # ------------------------------------------------------------------
    log.info("Phase 1-2: Decomposing requirements...")
    from backend.ticketing_agent.decompose.decompose_hlr import decompose
    from backend.requirements.services.persistence import persist_decomposition

    with get_neo4j().session() as ns:
        req_repo = RequirementRepository(ns)
        hlrs_neo4j = req_repo.list_hlrs()
        all_llrs_neo4j = req_repo.list_llrs()

    if not hlrs_neo4j:
        log.warning("No HLRs found -- nothing to decompose.")
        return result

    for hlr in hlrs_neo4j:
        llrs_for_hlr = req_repo.list_llrs(hlr_id=hlr.id)
        if llrs_for_hlr:
            result.llrs_created += len(llrs_for_hlr)
            continue

        decomp_result = decompose(hlr.description, model=model)
        with get_neo4j().session() as ns:
            persisted = persist_decomposition(
                ns,
                hlr.id,
                decomp_result.low_level_requirements,
            )
        result.llrs_created += persisted.llrs_created

    result.hlrs_created = len(hlrs_neo4j)
    log.info("  %d HLRs, %d LLRs", result.hlrs_created, len(all_llrs_neo4j))

    # ------------------------------------------------------------------
    # Phase 3: Verification -- existing agent
    # ------------------------------------------------------------------
    log.info("Phase 3: Generating verification methods...")
    from backend.ticketing_agent.verify.verify_llr import verify
    from backend.requirements.services.persistence import (
        build_verification_context_from_diagram,
        persist_verification,
    )

    with get_neo4j().session() as ns:
        ver_repo = VerificationRepository(ns)
        class_contexts = build_verification_context_from_diagram(ns)

        for llr in all_llrs_neo4j:
            existing_vms = ver_repo.list_verifications(llr.id)
            existing_verifs = [
                {"method": vm.method, "test_name": vm.test_name, "description": vm.description}
                for vm in existing_vms
            ]
            if existing_verifs:
                result.verifications_created += len(existing_verifs)
                continue

            vv_result = verify(
                llr={"id": llr.id, "description": llr.description},
                existing_verifications=existing_verifs,
                class_contexts=class_contexts,
                neo4j_session=ns,
                model=model,
            )
            persist_result = persist_verification(ns, llr.id, vv_result.verifications)
            result.verifications_created += persist_result.conditions_created

    # ------------------------------------------------------------------
    # Phase 4: Design -- existing agents
    # ------------------------------------------------------------------
    log.info("Phase 4: Generating OO design...")
    from backend.ticketing_agent.design.design_hlr import design_hlr
    from backend.requirements.services.persistence import persist_design
    from backend.db.neo4j.repositories.models import DesignNode
    from backend.design_data import class_diagram_from_oo_design, oo_design_from_class_diagram
    from backend.design_data.models import ClassDiagram

    qname_to_node: dict[str, DesignNode] = {}
    accumulated_diagram = ClassDiagram()

    for hlr in hlrs_neo4j:
        hlr_dict = {
            "id": hlr.id,
            "description": hlr.description,
            "component_name": _get_component_name(hlr.component_id) if hlr.component_id else "",
        }
        llrs_for_hlr = req_repo.list_llrs(hlr_id=hlr.id)
        comp_ns = ""
        if hlr.component_id:
            with get_session() as cs:
                comp = cs.query(Component).filter_by(id=hlr.component_id).first()
                if comp:
                    comp_ns = comp.namespace or ""

        oo, ontology = design_hlr(
            hlr=hlr_dict,
            llrs=llrs_for_hlr,
            component_namespace=comp_ns,
            component_id=hlr.component_id,
            model=model,
        )
        result.design_nodes += len(ontology.nodes)
        result.design_triples += len(ontology.triples)

        diagram = class_diagram_from_oo_design(oo, component_id=hlr.component_id)
        accumulated_diagram = _merge_diagrams(accumulated_diagram, diagram)

        # Persist design to Neo4j
        with get_neo4j().session() as neo4j_session:
            persist_result = persist_design(
                ontology,
                neo4j_session=neo4j_session,
                qname_to_node=qname_to_node,
            )
        log.info(
            "  HLR %d: %d design nodes, %d triples",
            hlr.id,
            persist_result.nodes_created,
            persist_result.triples_created,
        )

    # ------------------------------------------------------------------
    # Phase 5: Task generation
    # ------------------------------------------------------------------
    log.info("Phase 5: Generating tasks...")
    from backend.ticketing_agent.generate_tasks import generate_tasks
    from backend.pipeline.services import persist_tasks

    with get_neo4j().session() as ns:
        all_verifications = _get_verification_dicts(ns)

    for hlr in hlrs_neo4j:
        hlr_dict = {
            "id": hlr.id,
            "description": hlr.description,
            "component_name": _get_component_name(hlr.component_id) if hlr.component_id else "",
        }
        llrs_for_hlr = req_repo.list_llrs(hlr_id=hlr.id)

        comp_name = _get_component_name(hlr.component_id) or ""

        # Filter accumulated schema by component module for task generation
        all_oo_schema = oo_design_from_class_diagram(accumulated_diagram)
        all_oo_dict = all_oo_schema.model_dump()
        hlr_classes = [
            c for c in all_oo_dict["classes"] if c.get("module") == comp_name
        ] or all_oo_dict["classes"][:3]

        batch = generate_tasks(
            hlr=hlr_dict,
            llrs=llrs_for_hlr,
            oo_design={"classes": hlr_classes},
            verifications=all_verifications,
            model=model,
        )

        with get_session() as session:
            persist_result = persist_tasks(session, batch)
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

    all_oo_schema = oo_design_from_class_diagram(accumulated_diagram)

    skeleton_results = generate_skeleton(
        oo_design=all_oo_schema,
        workspace_dir=workspace_dir,
    )
    result.skeleton_files = [r.file_path for r in skeleton_results]
    log.info("  %d skeleton files", len(result.skeleton_files))

    # ------------------------------------------------------------------
    # Phase 7: Test writing
    # ------------------------------------------------------------------
    log.info("Phase 7: Writing tests...")
    from backend.ticketing_agent.write_tests import write_tests

    for llr in all_llrs_neo4j:
        llr_verifs = [v for v in all_verifications if v.get("llr_id") == llr.id]
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
        result.tests_created += sum(len(t.test_names) for t in test_results)
        log.info(
            "  LLR %d: %d test files, %d tests",
            llr.id,
            len(test_results),
            sum(len(t.test_names) for t in test_results),
        )

    # ------------------------------------------------------------------
    # Phase 8: Implementation -- agent fills in skeleton
    # ------------------------------------------------------------------
    log.info("Phase 8: Implementing...")
    from backend.ticketing_agent.implement import (
        implement_task,
        write_implementation_files,
    )

    with get_session() as session:
        tasks = session.query(Task).all()

    skeleton_map: dict[str, str] = {}
    if workspace_dir:
        from pathlib import Path

        for sr in skeleton_results:
            p = Path(workspace_dir) / sr.file_path
            if p.exists():
                skeleton_map[sr.file_path] = p.read_text()

    for task in tasks:
        task_verifs = [v for v in all_verifications if v.get("test_name") in task.verifications]

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
        log.info("  Task '%s': %d files implemented", task.title, len(impl_results))

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
        oo_design=all_oo_schema.model_dump(),
        source_files=source_files,
    )
    if not design_report.clean:
        for c in design_report.missing_classes:
            result.sync_issues.append(f"Missing class: {c}")
        for cls, methods in design_report.missing_methods.items():
            for m in methods:
                result.sync_issues.append(f"Missing method: {cls}.{m}")

    test_names_expected = [v.get("test_name", "") for v in all_verifications if v.get("test_name")]
    test_files_actual = []
    if workspace_dir:
        from pathlib import Path
        for p in Path(workspace_dir).rglob("tests/**/*.py"):
            test_files_actual.append(str(p))

    coverage_report = check_test_coverage(
        test_names_expected,
        test_files_actual,
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
        from backend.db.neo4j.sync import (
            sync_task,
            sync_implementation_status,
            sync_full_design,
        )

        with get_session() as session:
            with get_neo4j().session() as neo4j_sess:
                full_stats = sync_full_design(neo4j_sess, session)

                for task in session.query(Task).all():
                    try:
                        sync_task(neo4j_sess, task)
                    except Exception:
                        log.warning("Neo4j task sync failed for task %d", task.id)

                for node in (
                    session.query(OntologyNode)
                    .filter_by(implementation_status="implemented")
                    .all()
                ):
                    sync_implementation_status(neo4j_sess, node)

        result.neo4j_synced = True
        log.info(
            "  Neo4j sync: %d nodes, %d triples",
            full_stats.get("nodes", 0),
            full_stats.get("triples", 0),
        )
    except Exception as e:
        log.warning("Neo4j sync skipped (unavailable): %s", e)
        result.neo4j_synced = False

    log.info(
        "Pipeline complete: %d HLRs, %d LLRs, %d tasks, "
        "%d skeleton files, %d tests, %d impl files, "
        "%d sync issues, Neo4j=%s",
        result.hlrs_created,
        result.llrs_created,
        result.tasks_created,
        len(result.skeleton_files),
        result.tests_created,
        result.implementations_created,
        len(result.sync_issues),
        result.neo4j_synced,
    )
    return result
