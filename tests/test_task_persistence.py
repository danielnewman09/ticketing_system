"""Tests for backend.pipeline.services — task persistence."""

import pytest

from backend.db.models.tasks import Task, TaskDesignNode, TaskVerification
from backend.db.models.ontology import OntologyNode
from backend.pipeline.schemas import TaskSchema, TaskBatchSchema
from backend.pipeline.services import (
    persist_tasks,
    build_qname_to_node,
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
        from backend.pipeline.services import persist_tasks, build_qname_to_node

        # Create an ontology node to link to
        comp = seeded_session.query(
            __import__('backend.db.models').db.models.Component
        ).first()

        node = OntologyNode(
            kind="class", name="Foo", qualified_name="calc::Foo",
            component_id=comp.id,
            implementation_status="designed",
        )
        seeded_session.add(node)
        seeded_session.flush()

        qname_map = build_qname_to_node(seeded_session)
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

        result = persist_tasks(seeded_session, batch, qname_map)
        assert result.tasks_created == 1
        assert result.links_to_design == 1

        # Verify persistence
        task = seeded_session.query(Task).filter_by(
            title="Create Foo class",
        ).first()
        assert task is not None
        assert task.description == "Implement the Foo class"
        assert len(task.design_nodes) == 1

    def test_persist_task_with_parent(self, seeded_session):
        batch = TaskBatchSchema(
            tasks=[
                TaskSchema(title="Parent", description="root"),
                TaskSchema(
                    title="Child", description="depends_on_parent",
                    dependencies=["Parent"],
                ),
            ],
            dependency_graph=[("Parent", "Child")],
        )
        result = persist_tasks(seeded_session, batch, {})
        assert result.tasks_created == 2

        parent = seeded_session.query(Task).filter_by(title="Parent").first()
        child = seeded_session.query(Task).filter_by(title="Child").first()
        assert child.parent_id == parent.id

    def test_persist_task_with_verification_link(self, seeded_session):
        from backend.db.models.verification import VerificationMethod

        # Create a verification method
        from backend.db.models.requirements import LowLevelRequirement
        from backend.db.models.components import Component
        from backend.db.models.requirements import HighLevelRequirement

        comp = seeded_session.query(Component).first()
        hlr = HighLevelRequirement(description="test hlr", component=comp)
        seeded_session.add(hlr)
        seeded_session.flush()

        llr = LowLevelRequirement(
            description="test llr", high_level_requirement_id=hlr.id,
        )
        seeded_session.add(llr)
        seeded_session.flush()

        vm = VerificationMethod(
            low_level_requirement_id=llr.id,
            method="automated",
            test_name="test_my_verification",
        )
        seeded_session.add(vm)
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

        result = persist_tasks(seeded_session, batch, {})
        assert result.tasks_created == 1
        assert result.links_to_verification == 1

    def test_mark_task_status(self, seeded_session):
        task = Task(title="test", description="test")
        seeded_session.add(task)
        seeded_session.flush()

        mark_task_status(seeded_session, task, "implemented")
        assert task.status == "implemented"

        with pytest.raises(ValueError):
            mark_task_status(seeded_session, task, "invalid_status")

    def test_unknown_design_node_warning(self, seeded_session, caplog):
        batch = TaskBatchSchema(
            tasks=[
                TaskSchema(
                    title="Bad ref",
                    description="references unknown node",
                    design_node_qualified_names=["nonexistent::Class"],
                ),
            ],
        )
        result = persist_tasks(seeded_session, batch, {})
        assert result.tasks_created == 1
        assert result.links_to_design == 0
        assert any("unknown design node" in r.message for r in caplog.records)


class TestBuildQnameToNode:
    def test_builds_map(self, seeded_session):
        comp = seeded_session.query(
            __import__('backend.db.models').db.models.Component
        ).first()

        node = OntologyNode(
            kind="class", name="Bar", qualified_name="calc::Bar",
            component_id=comp.id,
        )
        seeded_session.add(node)
        empty_node = OntologyNode(
            kind="class", name="NoQn", qualified_name="",
            component_id=comp.id,
        )
        seeded_session.add(empty_node)
        seeded_session.flush()

        m = build_qname_to_node(seeded_session)
        assert "calc::Bar" in m
        assert "" not in m  # empty qualified_name excluded
