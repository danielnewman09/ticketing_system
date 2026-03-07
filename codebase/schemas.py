"""
Pydantic schemas for the ontology design agent output.

These define the structured data the design agent returns when it
derives an ontology graph from a set of requirements.
"""

from typing import Literal

from pydantic import BaseModel

from codebase.models import EDGE_TYPES

NodeKind = Literal["class", "struct", "enum", "union", "namespace", "interface", "concept"]
EdgeRelationship = Literal["inherits", "composes", "aggregates", "depends_on", "calls", "implements", "uses"]

# Runtime check against the Django model choices
_schema_edge_types = set(EdgeRelationship.__args__)
_model_edge_types = {t[0] for t in EDGE_TYPES}
if _schema_edge_types != _model_edge_types:
    raise RuntimeError(
        f"EdgeRelationship Literal {_schema_edge_types} is out of sync "
        f"with EDGE_TYPES {_model_edge_types}. Update schemas.py."
    )


class OntologyNodeSchema(BaseModel):
    kind: NodeKind
    name: str
    qualified_name: str
    description: str = ""


class OntologyEdgeSchema(BaseModel):
    source_qualified_name: str
    target_qualified_name: str
    relationship: EdgeRelationship
    label: str = ""


class RequirementLinkSchema(BaseModel):
    """Maps a requirement's actor or subject to an ontology node."""
    requirement_type: Literal["hlr", "llr"]
    requirement_id: int
    role: Literal["actor", "subject"]
    node_qualified_name: str


class DesignSchema(BaseModel):
    nodes: list[OntologyNodeSchema]
    edges: list[OntologyEdgeSchema]
    requirement_links: list[RequirementLinkSchema]
