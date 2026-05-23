"""Service layer for task persistence and retrieval."""

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.db.models.tasks import Task, TaskDesignNode, TaskVerification
from backend.pipeline.schemas import TaskBatchSchema, TaskSchema

log = logging.getLogger("pipeline.services")


@dataclass
class TaskPersistResult:
    tasks_created: int = 0
    links_to_design: int = 0
    links_to_verification: int = 0


def persist_tasks(
    session: Session,
    batch: TaskBatchSchema,
    neo4j_session=None,
) -> TaskPersistResult:
    """Persist a batch of tasks to SQLite.

    Args:
        session: Active SQLAlchemy session.
        batch: TaskBatchSchema from the generate_tasks agent.
        neo4j_session: Optional Neo4j session for looking up verification methods.

    Returns:
        TaskPersistResult with counts of items created.
    """
    result = TaskPersistResult()
    ordered = _topological_sort(batch.tasks, batch.dependency_graph)
    title_to_task: dict[str, Task] = {}

    for ts in ordered:
        task = Task(
            title=ts.title,
            description=ts.description,
            estimated_complexity=ts.estimated_complexity,
        )
        if ts.dependencies:
            parent = title_to_task.get(ts.dependencies[0])
            if parent:
                task.parent = parent

        session.add(task)
        session.flush()
        title_to_task[ts.title] = task
        log.info("Persisted task: %s (pk=%d)", ts.title, task.id)
        result.tasks_created += 1

        for qname in ts.design_node_qualified_names:
            session.add(
                TaskDesignNode(
                    task=task,
                    ontology_node_qualified_name=qname,
                )
            )
            result.links_to_design += 1

        for test_name in ts.verification_test_names:
            vm_id = _find_verification_id_by_test_name(neo4j_session, test_name)
            if vm_id is not None:
                session.add(
                    TaskVerification(
                        task_id=task.id,
                        verification_method_id=vm_id,
                    )
                )
                result.links_to_verification += 1
            else:
                log.warning(
                    "Task %s references unknown test: %s",
                    ts.title,
                    test_name,
                )

    return result


def _topological_sort(
    tasks: list[TaskSchema],
    graph: list[tuple[str, str]],
) -> list[TaskSchema]:
    """Simple topological sort — returns tasks with fewest deps first."""
    by_title = {t.title: t for t in tasks}
    in_degree: dict[str, int] = {t.title: 0 for t in tasks}
    adj: dict[str, list[str]] = {t.title: [] for t in tasks}

    for src, dst in graph:
        if dst in in_degree and src in by_title:
            in_degree[dst] += 1
            adj[src].append(dst)

    queue = sorted([t for t in in_degree if in_degree[t] == 0])
    result = [by_title[n] for n in queue]

    remaining = [t for t in tasks if t.title not in {r.title for r in result}]
    result.extend(remaining)
    return result


def _find_verification_id_by_test_name(
    neo4j_session,
    test_name: str,
) -> int | None:
    """Find a VerificationMethod id in Neo4j by its test_name.

    Phase 3: VerificationMethods live in Neo4j, not SQLite.
    Returns the Neo4j node id or None.
    """
    if not test_name or neo4j_session is None:
        return None
    try:
        from backend.db.neo4j.repositories.verification import VerificationRepository
        from backend.db.neo4j.repositories.requirement import RequirementRepository

        ver_repo = VerificationRepository(neo4j_session)
        req_repo = RequirementRepository(neo4j_session)
        for llr in req_repo.list_llrs():
            for vm in ver_repo.list_verifications(llr.id):
                if vm.test_name == test_name:
                    return vm.id
    except Exception:
        log.warning("Failed to look up verification by test_name in Neo4j", exc_info=True)
    return None


def get_tasks_for_component(
    session: Session,
    component_name: str,
) -> list[Task]:
    """Get all tasks for a component."""
    from backend.db.models.components import Component

    comp = session.query(Component).filter_by(name=component_name).first()
    if not comp:
        return []
    tasks = session.query(Task).filter_by(component=comp).all()
    result = []
    for t in tasks:
        session.refresh(t)
        result.append(t)
    return result


def mark_task_status(
    session: Session,
    task: Task,
    status: str,
) -> None:
    """Update a task's status and flush."""
    valid = {"pending", "scaffolded", "tested", "implemented", "verified"}
    if status not in valid:
        raise ValueError(f"Invalid status {status!r}, must be one of {valid}")
    task.status = status
    session.flush()
