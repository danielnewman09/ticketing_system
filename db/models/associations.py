"""M2M junction tables — explicit Table objects matching Django's auto-generated names."""

from sqlalchemy import Column, ForeignKey, Integer, Table

from db.base import Base

# HLR ↔ OntologyTriple
high_level_requirements_triples = Table(
    "high_level_requirements_triples",
    Base.metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("highlevelrequirement_id", Integer, ForeignKey("high_level_requirements.id", ondelete="CASCADE"), nullable=False),
    Column("ontologytriple_id", Integer, ForeignKey("ontology_triples.id", ondelete="CASCADE"), nullable=False),
)

# LLR ↔ OntologyTriple
low_level_requirements_triples = Table(
    "low_level_requirements_triples",
    Base.metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("lowlevelrequirement_id", Integer, ForeignKey("low_level_requirements.id", ondelete="CASCADE"), nullable=False),
    Column("ontologytriple_id", Integer, ForeignKey("ontology_triples.id", ondelete="CASCADE"), nullable=False),
)

# LLR ↔ Component
low_level_requirements_components = Table(
    "low_level_requirements_components",
    Base.metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("lowlevelrequirement_id", Integer, ForeignKey("low_level_requirements.id", ondelete="CASCADE"), nullable=False),
    Column("component_id", Integer, ForeignKey("components.id", ondelete="CASCADE"), nullable=False),
)

# Ticket ↔ Component
tickets_components = Table(
    "tickets_components",
    Base.metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ticket_id", Integer, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False),
    Column("component_id", Integer, ForeignKey("components.id", ondelete="CASCADE"), nullable=False),
)

# Ticket ↔ Language
tickets_languages = Table(
    "tickets_languages",
    Base.metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ticket_id", Integer, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False),
    Column("language_id", Integer, ForeignKey("languages.id", ondelete="CASCADE"), nullable=False),
)
