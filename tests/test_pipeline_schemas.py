"""Tests for backend.pipeline.schemas — TaskSchema and TaskBatchSchema."""

import pytest
from pydantic import ValidationError

from backend.pipeline.schemas import TaskSchema, TaskBatchSchema


class TestTaskSchema:
    def test_minimal_valid(self):
        """TaskSchema requires only title and description."""
        t = TaskSchema(title="Create Foo class", description="Add the Foo class")
        assert t.title == "Create Foo class"
        assert t.description == "Add the Foo class"
        assert t.estimated_complexity == "medium"
        assert t.design_node_qualified_names == []
        assert t.verification_test_names == []
        assert t.source_files == []
        assert t.test_files == []
        assert t.dependencies == []

    def test_full_task(self):
        t = TaskSchema(
            title="Implement Calculator.add",
            description="Add method for arithmetic",
            design_node_qualified_names=["calc::Calculator::add"],
            verification_test_names=["test_add_two_integers"],
            source_files=["src/calculator/engine.py"],
            test_files=["tests/calculator/test_engine.py"],
            dependencies=["Create Calculator class"],
            estimated_complexity="low",
        )
        assert t.design_node_qualified_names == ["calc::Calculator::add"]
        assert t.verification_test_names == ["test_add_two_integers"]
        assert t.source_files == ["src/calculator/engine.py"]
        assert t.test_files == ["tests/calculator/test_engine.py"]
        assert t.dependencies == ["Create Calculator class"]
        assert t.estimated_complexity == "low"

    def test_invalid_complexity(self):
        with pytest.raises(ValidationError):
            TaskSchema(
                title="t", description="d", estimated_complexity="invalid",
            )

    def test_serialization(self):
        t = TaskSchema(title="t", description="d", estimated_complexity="high")
        d = t.model_dump()
        assert d["title"] == "t"
        assert d["description"] == "d"
        assert d["estimated_complexity"] == "high"


class TestTaskBatchSchema:
    def test_minimal_valid(self):
        batch = TaskBatchSchema(tasks=[])
        assert batch.tasks == []
        assert batch.component_name == ""
        assert batch.dependency_graph == []

    def test_with_tasks(self):
        batch = TaskBatchSchema(
            component_name="Calculator",
            tasks=[
                TaskSchema(title="Task A", description="First"),
                TaskSchema(title="Task B", description="Second", dependencies=["Task A"]),
            ],
            dependency_graph=[("Task A", "Task B")],
        )
        assert len(batch.tasks) == 2
        assert batch.component_name == "Calculator"
        assert len(batch.dependency_graph) == 1
        assert batch.dependency_graph[0] == ("Task A", "Task B")

    def test_serialization(self):
        batch = TaskBatchSchema(tasks=[TaskSchema(title="t", description="d")])
        d = batch.model_dump()
        assert d["component_name"] == ""
        assert len(d["tasks"]) == 1
