"""VerificationMethod, VerificationCondition, VerificationAction models."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base

if TYPE_CHECKING:
    from db.models.ontology import OntologyNode
    from db.models.requirements import LowLevelRequirement

VERIFICATION_METHODS = ["automated", "review", "inspection"]

CONDITION_OPERATORS = [
    ("==", "equals"),
    ("!=", "not equals"),
    ("<", "less than"),
    (">", "greater than"),
    ("<=", "less than or equal"),
    (">=", "greater than or equal"),
    ("is_true", "is true"),
    ("is_false", "is false"),
    ("contains", "contains"),
    ("not_null", "is not null"),
]


class VerificationMethod(Base):
    __tablename__ = "verification_methods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    low_level_requirement_id: Mapped[int] = mapped_column(ForeignKey("low_level_requirements.id", ondelete="CASCADE"), nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    test_name: Mapped[str] = mapped_column(String(300), default="", server_default="")
    description: Mapped[str] = mapped_column(Text, default="", server_default="")

    low_level_requirement: Mapped[LowLevelRequirement] = relationship("LowLevelRequirement", back_populates="verifications")
    conditions: Mapped[list[VerificationCondition]] = relationship("VerificationCondition", back_populates="verification", cascade="all, delete-orphan")
    actions: Mapped[list[VerificationAction]] = relationship("VerificationAction", back_populates="verification", cascade="all, delete-orphan")

    def __repr__(self):
        parts = [self.method]
        if self.test_name:
            parts.append(f"[{self.test_name}]")
        return " - ".join(parts)

    def to_prompt_text(self):
        parts = [self.method]
        if self.test_name:
            parts.append(self.test_name)
        if self.description:
            parts.append(self.description)
        return " — ".join(parts)

    @property
    def preconditions(self):
        return [c for c in self.conditions if c.phase == "pre"]

    @property
    def postconditions(self):
        return [c for c in self.conditions if c.phase == "post"]


class VerificationCondition(Base):
    __tablename__ = "verification_conditions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    verification_id: Mapped[int] = mapped_column(ForeignKey("verification_methods.id", ondelete="CASCADE"), nullable=False)
    phase: Mapped[str] = mapped_column(String(4), nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    ontology_node_id: Mapped[Optional[int]] = mapped_column(ForeignKey("ontology_nodes.id", ondelete="SET NULL"), nullable=True)
    member_qualified_name: Mapped[str] = mapped_column(String(500), nullable=False)
    operator: Mapped[str] = mapped_column(String(20), default="==", server_default="==")
    expected_value: Mapped[str] = mapped_column(String(500), nullable=False)

    verification: Mapped[VerificationMethod] = relationship("VerificationMethod", back_populates="conditions")
    ontology_node: Mapped[Optional[OntologyNode]] = relationship("OntologyNode")

    def __repr__(self):
        return f"{self.member_qualified_name} {self.operator} {self.expected_value}"


class VerificationAction(Base):
    __tablename__ = "verification_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    verification_id: Mapped[int] = mapped_column(ForeignKey("verification_methods.id", ondelete="CASCADE"), nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    ontology_node_id: Mapped[Optional[int]] = mapped_column(ForeignKey("ontology_nodes.id", ondelete="SET NULL"), nullable=True)
    member_qualified_name: Mapped[str] = mapped_column(String(500), default="", server_default="")

    verification: Mapped[VerificationMethod] = relationship("VerificationMethod", back_populates="actions")
    ontology_node: Mapped[Optional[OntologyNode]] = relationship("OntologyNode")

    def __repr__(self):
        return self.description[:80]
