"""Ticketing-system schemas — requirement linkage and design aggregation.

LLM shapes and OO design models now live in codegraph.
TypeRef moved to codegraph.type_parser.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from codegraph.constants import NODE_KIND_KEYS, VISIBILITY_CHOICES
from codegraph.diagram import ClassDiagram
from backend.requirements.schemas import VerificationSchema

NodeKind = Literal[tuple(NODE_KIND_KEYS)]
Visibility = Literal[tuple(k for k, _ in VISIBILITY_CHOICES)]
SourceType = Literal["compound", "member", "namespace"]


class RequirementTripleLinkSchema(BaseModel):
    """Maps a requirement to an ontology entity by qualified name.

    Replaces the old triple_index approach with direct subject/object references.
    """
    requirement_type: Literal["hlr", "llr"]
    requirement_id: int
    subject_qualified_name: str = ""
    predicate: str = ""
    object_qualified_name: str = ""


class DesignSchema(BaseModel):
    """Stage 2 output: ontology design with nodes, associations, and requirement links.

    nodes are codegraph atomized neomodel types (ClassNode, MethodNode, etc.).
    associations replace the old CodebaseEdge triples — each is a dict with keys:
    subject, predicate, object, mechanism (optional), position (optional),
    name (optional), display_name (optional).
    """
    nodes: list  # codegraph atomized neomodel types
    associations: list[dict] = []
    requirement_links: list[RequirementTripleLinkSchema] = []


class DesignAndVerificationSchema(BaseModel):
    """Combined output for the design+verify tool loop."""
    model_config = {"arbitrary_types_allowed": True}

    oo_design: ClassDiagram
    verifications: dict[int, list[VerificationSchema]] = {}
