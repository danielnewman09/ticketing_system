"""Service layer for task persistence and retrieval."""

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.db.models.tasks import Task, TaskDesignNode, TaskVerification
from backend.db.models.ontology import OntologyNode
from backend.db.models.verification import VerificationMethod
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
    qname_to_node: dict[str, OntologyNode],
) -> TaskPersistResult:
    """Persist a batch of tasks to SQLite.

    Args:
        session: Active SQLAlchemy session.
        batch: TaskBatchSchema from the generate_tasks agent.
        qname_to_node: Mapping from qualified_name to OntologyNode.

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
            if qname in qname_to_node:
                session.add(TaskDesignNode(
                    task=task,
                    ontology_node=qname_to_node[qname],
                ))
                result.links_to_design += 1
            else:
                log.warning(
                    "Task %s references unknown design node: %s",
                    ts.title, qname,
                )

        for test_name in ts.verification_test_names:
            vm = _find_verification_by_test_name(session, test_name)
            if vm:
                session.add(TaskVerification(
                    task=task, verification_method=vm,
                ))
                result.links_to_verification += 1
            else:
                log.warning(
                    "Task %s references unknown test: %s",
                    ts.title, test_name,
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


def _find_verification_by_test_name(
    session: Session, test_name: str,
) -> VerificationMethod | None:
    """Find a VerificationMethod by its test_name."""
    if not test_name:
        return None
    return session.query(VerificationMethod).filter_by(
        test_name=test_name,
    ).first()


def get_tasks_for_component(
    session: Session, component_name: str,
) -> list[Task]:
    """Get all tasks for a component."""
    from backend.db.models.components import Component
    comp = session.query(Component).filter_by(name=component_name).first()
    if not comp:
        return []
    tasks = session.query(Task).filter_by(component=comp).all()
    # Eager-load the relationships
    result = []
    for t in tasks:
        session.refresh(t)
        result.append(t)
    return result


def mark_task_status(
    session: Session, task: Task, status: str,
) -> None:
    """Update a task's status and flush."""
    valid = {"pending", "scaffolded", "tested", "implemented", "verified"}
    if status not in valid:
        raise ValueError(f"Invalid status {status!r}, must be one of {valid}")
    task.status = status
    session.flush()


def build_qname_to_node(session: Session) -> dict[str, OntologyNode]:
    """Build a qualified_name -> OntologyNode lookup map."""
    nodes = session.query(OntologyNode).all()
    return {n.qualified_name: n for n in nodes if n.qualified_name}
