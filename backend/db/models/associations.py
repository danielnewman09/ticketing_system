"""M2M junction tables — explicit Table objects matching Django's auto-generated names.

Phase 1 note: HLR/LLR ↔ OntologyNode and HLR/LLR ↔ OntologyTriple M2M tables
have been removed. Requirement-to-design links are now handled via TRACES_TO
edges on :HLR/:LLR stub nodes in Neo4j.
"""

from sqlalchemy import Column, ForeignKey, Integer, Table

from backend.db.base import Base

# LLR ↔ Component
low_level_requirements_components = Table(
    "low_level_requirements_components",
    Base.metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "lowlevelrequirement_id",
        Integer,
        ForeignKey("low_level_requirements.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "component_id", Integer, ForeignKey("components.id", ondelete="CASCADE"), nullable=False
    ),
)

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