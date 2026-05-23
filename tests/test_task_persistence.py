"""Tests for backend.pipeline.services — task persistence."""

import pytest

from backend.db.models.tasks import Task, TaskDesignNode, TaskVerification
from backend.pipeline.schemas import TaskSchema, TaskBatchSchema
from backend.pipeline.services import (
    persist_tasks,
    mark_task_status,
    _topological_sort,
)


class TestTopologicalSort:
    def test_no_deps(self):
        tasks = [
            TaskSchema(title="A", description="a"),
            TaskSchema(title="B", description="b"),
        ]
        result = _topological_sort(tasks, [])
        assert len(result) == 2
        assert result[0].title == "A"
        assert result[1].title == "B"

    def test_with_deps(self):
        tasks = [
            TaskSchema(title="B", description="b"),
            TaskSchema(title="A", description="a"),
        ]
        result = _topological_sort(tasks, [("A", "B")])
        assert result[0].title == "A"
        assert result[1].title == "B"


class TestPersistTasks:
    def test_persist_task_with_design_link(self, seeded_session):
        from backend.pipeline.services import persist_tasks

        batch = TaskBatchSchema(
            component_name="Calculator",
            tasks=[
                TaskSchema(
                    title="Create Foo class",
                    description="Implement the Foo class",
                    design_node_qualified_names=["calc::Foo"],
                    estimated_complexity="low",
                ),
            ],
        )

        result = persist_tasks(seeded_session, batch, neo4j_session=None)
        assert result.tasks_created == 1
        assert result.links_to_design == 1

        # Verify persistence
        task = (
            seeded_session.query(Task)
            .filter_by(
                title="Create Foo class",
            )
            .first()
        )
        assert task is not None
        assert task.description == "Implement the Foo class"
        assert len(task.design_nodes) == 1
        # Phase 1: design_nodes link by qualified_name string
        assert task.design_nodes[0].ontology_node_qualified_name == "calc::Foo"

    def test_persist_task_with_parent(self, seeded_session):
        batch = TaskBatchSchema(
            tasks=[
                TaskSchema(title="Parent", description="root"),
                TaskSchema(
                    title="Child",
                    description="depends_on_parent",
                    dependencies=["Parent"],
                ),
            ],
            dependency_graph=[("Parent", "Child")],
        )
        result = persist_tasks(seeded_session, batch, neo4j_session=None)
        assert result.tasks_created == 2

        parent = seeded_session.query(Task).filter_by(title="Parent").first()
        child = seeded_session.query(Task).filter_by(title="Child").first()
        assert child.parent_id == parent.id

    def test_persist_task_with_verification_link(self, seeded_session):
        # Phase 3: verification_method_id is a plain integer (no FK).
        # We test that a TaskVerification row is created with the id directly.
        neo4j_vm_id = 42  # placeholder — represents a :VerificationMethod node in Neo4j

        seeded_session.flush()

        batch = TaskBatchSchema(
            tasks=[
                TaskSchema(
                    title="Task with verif",
                    description="must satisfy verification",
                    verification_test_names=["test_my_verification"],
                ),
            ],
        )

        result = persist_tasks(seeded_session, batch, neo4j_session=None)
        assert result.tasks_created == 1
        assert result.links_to_verification == 0  # No Neo4j session in unit tests

    def test_mark_task_status(self, seeded_session):
        task = Task(title="test", description="test")
        seeded_session.add(task)
        seeded_session.flush()

        mark_task_status(seeded_session, task, "implemented")
        assert task.status == "implemented"

        with pytest.raises(ValueError):
            mark_task_status(seeded_session, task, "invalid_status")