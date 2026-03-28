"""HighLevelRequirement, LowLevelRequirement, TicketRequirement models."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from backend.db.base import Base
from backend.db.models.associations import (
    high_level_requirements_triples,
    low_level_requirements_components,
    low_level_requirements_triples,
)

if TYPE_CHECKING:
    from backend.db.models.components import Component
    from backend.db.models.ontology import OntologyTriple
    from backend.db.models.verification import VerificationMethod


class HighLevelRequirement(Base):
    __tablename__ = "high_level_requirements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    component_id: Mapped[Optional[int]] = mapped_column(ForeignKey("components.id", ondelete="SET NULL"), nullable=True)
    dependency_context: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    component: Mapped[Optional[Component]] = relationship("Component", back_populates="high_level_requirements")
    low_level_requirements: Mapped[list[LowLevelRequirement]] = relationship("LowLevelRequirement", back_populates="high_level_requirement")
    triples: Mapped[list[OntologyTriple]] = relationship("OntologyTriple", secondary=high_level_requirements_triples)

    def __repr__(self):
        return self.description[:80] if self.description else f"HLR {self.id}"

    def to_prompt_text(self, include_llrs=False, include_component=False):
        comp = ""
        if include_component and self.component_id:
            comp = f" [Component: {self.component.name}]"
        line = f"HLR {self.id}{comp}: {self.description}"
        if not include_llrs:
            return line
        lines = [line]
        for llr in self.low_level_requirements:
            lines.append(f"  {llr.to_prompt_text()}")
        return "\n".join(lines)


def format_hlr_dict(hlr, include_component=False):
    """Format a single HLR dict as a prompt line."""
    comp = ""
    if include_component:
        comp_name = hlr.get("component_name") or hlr.get("component__name")
        if comp_name:
            comp = f" [Component: {comp_name}]"
    return f"HLR {hlr['id']}{comp}: {hlr['description']}"


def format_hlrs_for_prompt(hlrs, llrs=None, include_component=False):
    """Format HLR/LLR dicts into a text block for agent prompts."""
    lines = []
    for hlr in hlrs:
        lines.append(format_hlr_dict(hlr, include_component))
        if llrs:
            for llr in [l for l in llrs if l.get("hlr_id") == hlr["id"]]:
                lines.append(f"  {format_llr_dict(llr)}")
    if llrs:
        unlinked = [l for l in llrs if l.get("hlr_id") is None]
        if unlinked:
            lines.append("\nUnlinked LLRs:")
            for llr in unlinked:
                lines.append(f"  {format_llr_dict(llr)}")
    return "\n".join(lines)


class LowLevelRequirement(Base):
    __tablename__ = "low_level_requirements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    high_level_requirement_id: Mapped[Optional[int]] = mapped_column(ForeignKey("high_level_requirements.id", ondelete="SET NULL"), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    high_level_requirement: Mapped[Optional[HighLevelRequirement]] = relationship("HighLevelRequirement", back_populates="low_level_requirements")
    verifications: Mapped[list[VerificationMethod]] = relationship("VerificationMethod", back_populates="low_level_requirement", cascade="all, delete-orphan")
    components: Mapped[list[Component]] = relationship("Component", secondary=low_level_requirements_components)
    triples: Mapped[list[OntologyTriple]] = relationship("OntologyTriple", secondary=low_level_requirements_triples)

    def __repr__(self):
        return self.description[:80] if self.description else f"LLR {self.id}"

    def to_prompt_text(self, include_verifications=False):
        line = f"LLR {self.id}: {self.description}"
        if not include_verifications:
            return line
        lines = [line]
        for v in self.verifications:
            lines.append(f"    {v.to_prompt_text()}")
        return "\n".join(lines)


def format_llr_dict(llr):
    """Format a single LLR dict as a prompt line."""
    return f"LLR {llr['id']}: {llr['description']}"


class TicketRequirement(Base):
    __tablename__ = "ticket_requirements"
    __table_args__ = (
        UniqueConstraint("ticket_id", "low_level_requirement_id", name="uq_ticket_requirements_ticket_llr"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False)
    low_level_requirement_id: Mapped[int] = mapped_column(ForeignKey("low_level_requirements.id", ondelete="CASCADE"), nullable=False)

    def __repr__(self):
        return f"Ticket {self.ticket_id} -> LLR {self.low_level_requirement_id}"
