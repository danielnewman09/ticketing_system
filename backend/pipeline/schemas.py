"""
Pydantic schemas for the pipeline orchestrator.

Defines the shape of individual tasks and batches fed into the
spec-driven development pipeline.
"""

from typing import Literal

from pydantic import BaseModel


class TaskSchema(BaseModel):
    title: str
    description: str
    design_node_qualified_names: list[str]
    verification_test_names: list[str]
    source_files: list[str]
    test_files: list[str]
    dependencies: list[str]
    estimated_complexity: Literal["low", "medium", "high"] = "medium"


class TaskBatchSchema(BaseModel):
    tasks: list[TaskSchema]
    component_name: str = ""
    dependency_graph: list[tuple[str, str]] = []
    """Edges as (from_task_title, to_task_title)."""
