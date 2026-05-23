"""Pydantic models for HLR/LLR requirement nodes in Neo4j.

These replace SQLAlchemy HighLevelRequirement/LowLevelRequirement
as the data contract for requirement data stored in Neo4j.
"""

from __future__ import annotations

from pydantic import BaseModel


class HLRNode(BaseModel):
    """A high-level requirement node in Neo4j.

    Stored as :HLR nodes with id as the unique identifier
    (replaces sqlite_id from Phase 1).
    """

    id: int
    description: str
    component_id: int | None = None
    dependency_context: dict | None = None

    model_config = {"from_attributes": True}


class LLRNode(BaseModel):
    """A low-level requirement node in Neo4j.

    Stored as :LLR nodes. The high_level_requirement_id links to the
    parent :HLR node via a DECOMPOSES_INTO edge.
    """

    id: int
    description: str
    high_level_requirement_id: int

    model_config = {"from_attributes": True}