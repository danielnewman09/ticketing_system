"""Ticket, TicketAcceptanceCriteria, TicketFile, TicketReference models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base
from db.models.associations import tickets_components, tickets_languages
from db.models.components import Component, Language
from db.models.requirements import LowLevelRequirement, TicketRequirement


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    priority: Mapped[str] = mapped_column(String(50), default="", server_default="")
    complexity: Mapped[str] = mapped_column(String(50), default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    author: Mapped[str] = mapped_column(String(200), default="", server_default="")
    summary: Mapped[str] = mapped_column(Text, default="", server_default="")
    ticket_type: Mapped[str] = mapped_column(String(50), default="feature", server_default="feature")
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tickets.id", ondelete="SET NULL"), nullable=True)
    requires_math: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    generate_tutorial: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    parent: Mapped[Optional[Ticket]] = relationship("Ticket", remote_side="Ticket.id", back_populates="children")
    children: Mapped[list[Ticket]] = relationship("Ticket", back_populates="parent")
    components: Mapped[list[Component]] = relationship("Component", secondary=tickets_components)
    languages: Mapped[list[Language]] = relationship("Language", secondary=tickets_languages)
    acceptance_criteria: Mapped[list[TicketAcceptanceCriteria]] = relationship("TicketAcceptanceCriteria", back_populates="ticket", cascade="all, delete-orphan")
    files: Mapped[list[TicketFile]] = relationship("TicketFile", back_populates="ticket", cascade="all, delete-orphan")
    references: Mapped[list[TicketReference]] = relationship("TicketReference", back_populates="ticket", cascade="all, delete-orphan")
    low_level_requirements: Mapped[list[LowLevelRequirement]] = relationship(
        "LowLevelRequirement",
        secondary=TicketRequirement.__table__,
        viewonly=True,
    )

    def __repr__(self):
        return self.title

    def to_prompt_text(self, brief=False):
        if brief:
            parts = [f"Ticket {self.id}: {self.title}"]
            if self.priority:
                parts.append(f"[{self.priority}]")
            if self.complexity:
                parts.append(f"[{self.complexity}]")
            if self.ticket_type:
                parts.append(f"({self.ticket_type})")
            if self.summary:
                parts.append(f"— {self.summary[:200]}")
            return " ".join(parts)
        lines = [f"Ticket {self.id}: {self.title}"]
        if self.priority:
            lines.append(f"  Priority: {self.priority}")
        if self.complexity:
            lines.append(f"  Complexity: {self.complexity}")
        if self.ticket_type:
            lines.append(f"  Type: {self.ticket_type}")
        if self.author:
            lines.append(f"  Author: {self.author}")
        if self.summary:
            lines.append(f"  Summary: {self.summary}")
        if self.components:
            lines.append(f"  Components: {', '.join(c.name for c in self.components)}")
        if self.languages:
            lines.append(f"  Languages: {', '.join(l.name for l in self.languages)}")
        if self.acceptance_criteria:
            lines.append("  Acceptance Criteria:")
            for ac in self.acceptance_criteria:
                lines.append(f"    - {ac.description}")
        if self.files:
            lines.append("  Files:")
            for f in self.files:
                desc = f" — {f.description}" if f.description else ""
                lines.append(f"    - {f.change_type}: {f.file_path}{desc}")
        return "\n".join(lines)


class TicketAcceptanceCriteria(Base):
    __tablename__ = "ticket_acceptance_criteria"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    ticket: Mapped[Ticket] = relationship("Ticket", back_populates="acceptance_criteria")

    def __repr__(self):
        return self.description[:80]


class TicketFile(Base):
    __tablename__ = "ticket_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    change_type: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    ticket: Mapped[Ticket] = relationship("Ticket", back_populates="files")

    def __repr__(self):
        return f"{self.change_type}: {self.file_path}"


class TicketReference(Base):
    __tablename__ = "ticket_references"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False)
    ref_type: Mapped[str] = mapped_column(String(50), nullable=False)
    ref_target: Mapped[str] = mapped_column(String(200), nullable=False)

    ticket: Mapped[Ticket] = relationship("Ticket", back_populates="references")

    def __repr__(self):
        return f"{self.ref_type}: {self.ref_target}"
