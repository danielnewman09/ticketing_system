"""Task model — scoped work items generated from design + verification."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base

if TYPE_CHECKING:
    from backend.db.models.components import Component
    from backend.db.models.ontology import OntologyNode
    from backend.db.models.verification import VerificationMethod


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    estimated_complexity: Mapped[str] = mapped_column(
        String(10), default="medium", server_default="medium",
    )
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    # pending, scaffolded, tested, implemented, verified

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    component_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("components.id", ondelete="SET NULL"), nullable=True,
    )
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True,
    )

    component: Mapped[Optional[Component]] = relationship("Component")
    parent: Mapped[Optional[Task]] = relationship(
        "Task", remote_side="Task.id", back_populates="children",
    )
    children: Mapped[list[Task]] = relationship("Task", back_populates="parent")

    # Design elements this task implements
    design_nodes: Mapped[list[TaskDesignNode]] = relationship(
        "TaskDesignNode", back_populates="task", cascade="all, delete-orphan",
    )
    # Verifications this task covers
    verifications: Mapped[list[TaskVerification]] = relationship(
        "TaskVerification", back_populates="task", cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"Task {self.id}: {self.title}"


class TaskDesignNode(Base):
    """Links a task to one or more ontology design nodes."""
    __tablename__ = "task_design_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False,
    )
    ontology_node_id: Mapped[int] = mapped_column(
        ForeignKey("ontology_nodes.id", ondelete="CASCADE"), nullable=False,
    )

    task: Mapped[Task] = relationship("Task", back_populates="design_nodes")
    ontology_node: Mapped["OntologyNode"] = relationship("OntologyNode")


class TaskVerification(Base):
    """Links a task to one or more verification methods it must satisfy."""
    __tablename__ = "task_verifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False,
    )
    verification_method_id: Mapped[int] = mapped_column(
        ForeignKey("verification_methods.id", ondelete="CASCADE"), nullable=False,
    )

    task: Mapped[Task] = relationship("Task", back_populates="verifications")
    verification_method: Mapped[VerificationMethod] = relationship("VerificationMethod")
