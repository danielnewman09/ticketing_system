"""M2M junction tables — explicit Table objects matching Django's auto-generated names.

Phase 2 note: HLR/LLR models and the low_level_requirements_components M2M table
have been removed. LLR↔Component links are now stored as component_ids list
properties on :LLR nodes in Neo4j.
"""

from sqlalchemy import Column, ForeignKey, Integer, Table

from backend.db.base import Base

# Ticket ↔ Component
tickets_components = Table(
    "tickets_components",
    Base.metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ticket_id", Integer, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False),
    Column(
        "component_id", Integer, ForeignKey("components.id", ondelete="CASCADE"), nullable=False
    ),
)

# Ticket ↔ Language
tickets_languages = Table(
    "tickets_languages",
    Base.metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ticket_id", Integer, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False),
    Column("language_id", Integer, ForeignKey("languages.id", ondelete="CASCADE"), nullable=False),
)