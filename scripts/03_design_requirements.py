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
import logging
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv

load_dotenv()

from services.dependencies import init_neo4j, close_neo4j, get_neo4j
from backend.db import init_db, get_session
from backend.db.models import (
    OntologyNode,
    OntologyTriple,
)
from backend.db.neo4j.repositories.requirement import RequirementRepository

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
LOGS_DIR = os.path.join(REPO_ROOT, "logs")


def _configure_logging():
    """Set up file logging for the pipeline run."""
    os.makedirs(LOGS_DIR, exist_ok=True)
    log_file = os.path.join(LOGS_DIR, "design_pipeline.log")

    # Configure root logger to write to file
    file_handler = logging.FileHandler(log_file, mode="w")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    ))
    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)
    root_logger.setLevel(logging.DEBUG)

    # Suppress noisy neo4j driver/pool/io logs in the pipeline log
    for _neo_name in ["neo4j", "neo4j.driver", "neo4j.io", "neo4j.pool"]:
        logging.getLogger(_neo_name).setLevel(logging.WARNING)

    # Also set up a handler that captures agent-level logs
    for logger_name in ["agents.verify", "agents.design", "agents.discover"]:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.DEBUG)

    # Link the app.log file
    app_handler = logging.FileHandler(os.path.join(LOGS_DIR, "app.log"), mode="w")
    app_handler.setLevel(logging.INFO)
    app_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    ))
    logging.getLogger("app").addHandler(app_handler)

    return log_file


def step_decompose():
    print("=" * 60)
    print("STEP 1: Decompose requirements")
    print("=" * 60)

    from backend.ticketing_agent.decompose.decompose_hlr import decompose
    from backend.requirements.services.persistence import persist_decomposition

    os.makedirs(LOGS_DIR, exist_ok=True)

    with get_neo4j().session() as ns:
        repo = RequirementRepository(ns)
        hlrs = repo.list_hlrs()

        if not hlrs:
            print("  No HLRs found. Run setup_project.py first.\n")
            return

        print(f"  Decomposing {len(hlrs)} HLRs via AI agent...\n")

        for i, hlr in enumerate(hlrs, 1):
            print(f"  [{i}/{len(hlrs)}] {hlr.description[:65]}...")

            component_name = _get_component_name(hlr.component_id) if hlr.component_id else ""

            result = decompose(
                hlr.description,
                component=component_name,
                dependency_context=hlr.dependency_context,
                prompt_log_file=os.path.join(LOGS_DIR, f"decompose_hlr{hlr.id}.md"),
            )

            with get_neo4j().session() as ns2:
                persisted = persist_decomposition(ns2, hlr.id, result.low_level_requirements)
            print(f"    -> HLR {hlr.id}: {hlr.description[:60]}")
            print(f"       {persisted.llrs_created} LLRs generated\n")

        all_llrs = repo.list_llrs()
        print(f"  Requirements phase complete: {len(hlrs)} HLRs, {len(all_llrs)} LLRs\n")


def step_design():
    print("=" * 60)
    print("STEP 2: Design — discover + design + map per HLR")
    print("=" * 60)
    print("  Designing each HLR individually in dependency order...\n")
    step_log = logging.getLogger("pipeline.design")

    from backend.ticketing_agent.design.design_hlr import design_hlr
    from backend.design_data import class_diagram_from_oo_design
    from backend.ticketing_agent.design.design_per_hlr import (
        _extract_existing_classes,
        _extract_intercomponent_context,
    )
    from backend.ticketing_agent.design.order_hlrs import order_hlrs
    from backend.codebase.schemas import OODesignSchema
    from backend.requirements.services.persistence import persist_design

    with get_neo4j().session() as ns:
        repo = RequirementRepository(ns)
        hlrs_neo4j = repo.list_hlrs()
        all_llrs_neo4j = repo.list_llrs()

    hlrs = [
        {
            "id": h.id,
            "description": h.description,
            "component_id": h.component_id,
            "dependency_context": h.dependency_context,
            "component_name": _get_component_name(h.component_id) if h.component_id else None,
            "component_namespace": _get_component_namespace(h.component_id) if h.component_id else "",
            "component_description": _get_component_description(h.component_id) if h.component_id else "",
        }
        for h in hlrs_neo4j
    ]
    llrs = [
        {"id": l.id, "description": l.description, "hlr_id": l.high_level_requirement_id}
        for l in all_llrs_neo4j
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

    # Get a Neo4j session for container lookup seeding
    neo4j_session = get_neo4j().get_driver().session()

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
                        prev_oo,
                        prev_comp_name,
                        component_id,
                        prev_comp_id,
                    )
                )

            # Design single HLR
            step_log.info("Designing HLR %d: %s", hlr_id, hlr['description'])
            try:
                oo, ontology, verifs = design_hlr(
                    hlr=hlr,
                    llrs=hlr_llrs,
                    existing_classes=existing_classes or None,
                    intercomponent_classes=intercomponent_classes or None,
                    component_namespace=component_namespace,
                    sibling_namespaces=sibling_namespaces or None,
                    component_id=component_id,
                    prior_class_lookup=accumulated_class_lookup,
                    toolset=dep_toolset,
                    neo4j_session=neo4j_session,
                    log_dir=LOGS_DIR,
                )
            except Exception as e:
                step_log.exception("HLR %d design failed: %s", hlr_id, e)
                print(f"    ERROR: HLR {hlr_id} design failed: {e}")
                raise

            step_log.info("HLR %d: %d classes, %d associations", hlr_id, len(oo.classes), len(oo.associations))

            # Check for cross-component associations
            for assoc in oo.associations:
                to_cls = assoc.to_class
                if '::' in to_cls:
                    to_ns = to_cls.split('::')[0]
                    if to_ns != component_namespace:
                        step_log.info("HLR %d: cross-component association: %s -> %s (%s)",
                                      hlr_id, assoc.from_class, to_cls, assoc.relationship)
                        print(f"    CROSS-COMPONENT: {assoc.from_class} -> {to_cls} ({assoc.relationship})")

            # Accumulate
            accumulated_class_lookup.update(class_diagram_from_oo_design(oo).to_class_lookup())
            designed[hlr_id] = (oo, component_id, component_name)

            # Persist
            with get_session() as session:
                for node_data in ontology.nodes:
                    if node_data.qualified_name not in qname_to_node:
                        flag = " [intercomponent]" if node_data.is_intercomponent else ""
                        print(f"    Node: {node_data.qualified_name} ({node_data.kind}){flag}")

                with get_neo4j().session() as neo4j_session:
                    persisted = persist_design(ontology, neo4j_session, qname_to_node=qname_to_node)
                total_nodes += persisted.nodes_created
                total_triples += persisted.triples_created
                total_linked += persisted.links_applied
                total_skipped += persisted.links_skipped
    finally:
        try:
            neo4j_session.close()
        except Exception:
            pass
        if dep_toolset:
            dep_toolset.close()
            print("  Dependency graph disconnected")

    print(f"\n  Design phase complete:")
    print(f"    {total_nodes} nodes, {total_triples} triples")
    print(f"    {total_linked} requirement-to-triple links applied, {total_skipped} skipped\n")


def step_design_and_verify():
    print("=" * 60)
    print("STEP 2: Design + Verify — combined per-HLR loop")
    print("=" * 60)
    print("  Designing and verifying each HLR in dependency order...\n")
    step_log = logging.getLogger("pipeline.design_verify")

    from backend.design_data import class_diagram_from_oo_design
    from backend.ticketing_agent.design.design_per_hlr import (
        _extract_existing_classes,
        _extract_intercomponent_context,
    )
    from backend.ticketing_agent.design.order_hlrs import order_hlrs
    from backend.codebase.schemas import OODesignSchema
    from backend.requirements.services.persistence import persist_design, persist_verification

    # --- Design phase context ---
    from backend.ticketing_agent.design.design_hlr import design_hlr

    with get_neo4j().session() as ns:
        repo = RequirementRepository(ns)
        hlrs_neo4j = repo.list_hlrs()
        all_llrs_neo4j = repo.list_llrs()

    hlrs = [
        {
            "id": h.id,
            "description": h.description,
            "component_id": h.component_id,
            "dependency_context": h.dependency_context,
            "component_name": _get_component_name(h.component_id) if h.component_id else None,
            "component_namespace": _get_component_namespace(h.component_id) if h.component_id else "",
            "component_description": _get_component_description(h.component_id) if h.component_id else "",
        }
        for h in hlrs_neo4j
    ]
    llrs = [
        {"id": l.id, "description": l.description, "hlr_id": l.high_level_requirement_id}
        for l in all_llrs_neo4j
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
    total_conditions = 0
    total_actions = 0
    total_qname_errors = 0
    total_unresolved = 0
    qname_to_node: dict = {}

    # Connect to dependency graph
    dep_toolset = None
    try:
        from doxygen_index.tools import create_toolset
        dep_toolset = create_toolset()
        print("  Dependency graph connected\n")
    except Exception as e:
        print(f"  Dependency graph unavailable: {e}\n")

    # Build dependency lookup from toolset
    dependency_lookup: dict[str, str] = {}
    if dep_toolset:
        try:
            for cls_info in dep_toolset.get_all_classes():
                qname = cls_info.get("qualified_name", "")
                bare = qname.rsplit("::", 1)[-1] if qname else ""
                if bare:
                    dependency_lookup[bare] = qname
        except Exception:
            pass

    # Get a Neo4j session for container lookup seeding
    neo4j_session = get_neo4j().get_driver().session()

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
                        prev_oo,
                        prev_comp_name,
                        component_id,
                        prev_comp_id,
                    )
                )

            component_namespace = hlr.get("component_namespace", "")
            sibling_namespaces = [
                h.get("component_namespace", "")
                for h in hlrs
                if h["id"] != hlr_id and h.get("component_namespace")
            ]

            # --- Single unified call: design_hlr now includes discovery + verify ---
            step_log.info("Designing + verifying HLR %d: %s", hlr_id, hlr['description'])
            try:
                oo, ontology, verifs = design_hlr(
                    hlr=hlr,
                    llrs=hlr_llrs,
                    existing_classes=existing_classes or None,
                    intercomponent_classes=intercomponent_classes or None,
                    component_namespace=component_namespace,
                    sibling_namespaces=sibling_namespaces or None,
                    component_id=component_id,
                    prior_class_lookup=accumulated_class_lookup or None,
                    toolset=dep_toolset,
                    neo4j_session=neo4j_session,
                    log_dir=LOGS_DIR,
                )
            except Exception as e:
                step_log.exception("HLR %d design+verify failed: %s", hlr_id, e)
                print(f"    ERROR: HLR {hlr_id} design+verify failed: {e}")
                raise

            step_log.info(
                "HLR %d: %d classes, %d interfaces, %d enums, %d nodes, %d triples",
                hlr_id, len(oo.classes), len(oo.interfaces), len(oo.enums),
                len(ontology.nodes), len(ontology.triples),
            )

            # Accumulate from the verified design
            accumulated_class_lookup.update(class_diagram_from_oo_design(oo).to_class_lookup())
            designed[hlr_id] = (oo, component_id, component_name)

            # Print nodes
            for node_data in ontology.nodes:
                if node_data.qualified_name not in qname_to_node:
                    flag = " [intercomponent]" if node_data.is_intercomponent else ""
                    print(f"    Node: {node_data.qualified_name} ({node_data.kind}){flag}")

            # Persist design to Neo4j
            with get_neo4j().session() as ns:
                persisted = persist_design(ontology, ns, qname_to_node=qname_to_node)
            total_nodes += persisted.nodes_created
            total_triples += persisted.triples_created
            total_linked += persisted.links_applied
            total_skipped += persisted.links_skipped

            # Persist verifications
            if verifs:
                with get_neo4j().session() as ns:
                    for llr_id, llr_verifs in verifs.items():
                        persisted = persist_verification(ns, llr_id, llr_verifs)
                        total_conditions += persisted.conditions_created
                        total_actions += persisted.actions_created

                        for v in llr_verifs:
                            print(
                                f"    [{v.method}] {v.test_name}: "
                                f"{len(v.preconditions)} pre, {len(v.actions)} actions, "
                                f"{len(v.postconditions)} post"
                            )

            # Check for cross-component associations
            for assoc in oo.associations:
                to_cls = assoc.to_class
                if '::' in to_cls:
                    to_ns = to_cls.split('::')[0]
                    if to_ns != component_namespace:
                        step_log.info("HLR %d: cross-component association: %s -> %s (%s)",
                                      hlr_id, assoc.from_class, to_cls, assoc.relationship)
                        print(f"    CROSS-COMPONENT: {assoc.from_class} -> {to_cls} ({assoc.relationship})")
    finally:
        try:
            neo4j_session.close()
        except Exception:
            pass
        if dep_toolset:
            dep_toolset.close()
            print("  Dependency graph disconnected")

    print(f"\n  Design + Verify phase complete:")
    print(f"    {total_nodes} nodes, {total_triples} triples")
    print(f"    {total_linked} requirement-to-triple links applied, {total_skipped} skipped")
    print(f"    {total_conditions} conditions, {total_actions} actions created")
    if total_unresolved:
        print(f"    {total_unresolved} unresolved references (see logs)")
    if total_qname_errors:
        print(f"    {total_qname_errors} qname format issues (see logs)")
    print()

def step_summary():
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)

    with get_neo4j().session() as ns:
        repo = RequirementRepository(ns)
        hlr_count = len(repo.list_hlrs())
        llr_count = len(repo.list_llrs())

        node_count = ns.run("MATCH (d:Design) RETURN count(d) AS cnt").single()["cnt"]
        triple_count = ns.run("MATCH (d:Design)-[r]->(:Design) RETURN count(r) AS cnt").single()["cnt"]
        verif_count = ns.run("MATCH (vm:VerificationMethod) RETURN count(vm) AS cnt").single()["cnt"]
        cond_count = ns.run("MATCH (c:Condition) RETURN count(c) AS cnt").single()["cnt"]
        action_count = ns.run("MATCH (a:Action) RETURN count(a) AS cnt").single()["cnt"]

        print(f"  HLRs:             {hlr_count}")
        print(f"  LLRs:             {llr_count}")
        print(f"  Verifications:    {verif_count}")
        print(f"  Conditions:       {cond_count}")
        print(f"  Actions:          {action_count}")
        print(f"  Design nodes:    {node_count}")
        print(f"  Design triples:   {triple_count}")

        # Show HLR → Design traces from Neo4j
        for hlr in repo.list_hlrs():
            print(f"\n  HLR {hlr.id}: {hlr.description[:60]}")
            traces = ns.run(
                """
                MATCH (h:HLR {id: $hid})-[:TRACES_TO]->(d:Design)
                RETURN d.qualified_name AS qn
                """,
                {"hid": hlr.id},
            ).data()
            if traces:
                for t in traces:
                    print(f"    -> {t['qn']}")
            else:
                print(f"    (no design traces)")

def _get_component_name(component_id: int | None) -> str | None:
    """Look up a component name by ID from SQLite."""
    if component_id is None:
        return None
    try:
        from backend.db.models import Component
        with get_session() as session:
            comp = session.query(Component).filter_by(id=component_id).first()
            return comp.name if comp else None
    except Exception:
        return None


def _get_component_namespace(component_id: int | None) -> str:
    """Look up a component namespace by ID from SQLite."""
    if component_id is None:
        return ""
    try:
        from backend.db.models import Component
        with get_session() as session:
            comp = session.query(Component).filter_by(id=component_id).first()
            return comp.namespace if comp and comp.namespace else ""
    except Exception:
        return ""


def _get_component_description(component_id: int | None) -> str:
    """Look up a component description by ID from SQLite."""
    if component_id is None:
        return ""
    try:
        from backend.db.models import Component
        with get_session() as session:
            comp = session.query(Component).filter_by(id=component_id).first()
            return comp.description if comp and comp.description else ""
    except Exception:
        return ""


if __name__ == "__main__":
    log_file = _configure_logging()
    print(f"Pipeline log: {log_file}")
    print(f"Started at {datetime.datetime.now().isoformat()}")
    init_neo4j()
    try:
        init_db()
        step_decompose()
        step_design_and_verify()
        step_summary()
    except Exception as e:
        logging.getLogger(__name__).exception("Pipeline failed: %s", e)
        print(f"\nPipeline failed: {e}")
        print(f"Check {log_file} for details.")
        raise
    finally:
        close_neo4j()