"""
Pydantic schemas for the ontology design agent output.

These define the structured data the design agent returns when it
derives an ontology graph from a set of requirements.
"""

from typing import Literal

from pydantic import BaseModel

NodeKind = Literal["class", "struct", "enum", "union", "namespace", "interface", "concept"]


class OntologyNodeSchema(BaseModel):
    kind: NodeKind
    name: str
    qualified_name: str
    description: str = ""


class OntologyTripleSchema(BaseModel):
    subject_qualified_name: str
    predicate: str  # Must match a Predicate.name in the database
    object_qualified_name: str


class RequirementTripleLinkSchema(BaseModel):
    """Maps a requirement to an ontology triple by index or by subject/predicate/object."""
    requirement_type: Literal["hlr", "llr"]
    requirement_id: int
    triple_index: int = -1
    subject_qualified_name: str = ""
    predicate: str = ""
    object_qualified_name: str = ""


class DesignSchema(BaseModel):
    nodes: list[OntologyNodeSchema]
    triples: list[OntologyTripleSchema]
    requirement_links: list[RequirementTripleLinkSchema] = []
