"""Ticketing-system schemas — requirement linkage and design aggregation.

LLM shapes and OO design models now live in codegraph.designs.
Ontology node/edge schemas replaced by codegraph.nodes.* / codegraph.edges.*.
TypeRef moved to codegraph.type_parser.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from codegraph.constants import NODE_KIND_KEYS, VISIBILITY_CHOICES
from codegraph.designs import ClassDiagram
from codegraph.edges import CodebaseEdge
from backend.requirements.schemas import VerificationSchema

NodeKind = Literal[tuple(NODE_KIND_KEYS)]
Visibility = Literal[tuple(k for k, _ in VISIBILITY_CHOICES)]
SourceType = Literal["compound", "member", "namespace"]


class RequirementTripleLinkSchema(BaseModel):
    """Maps a requirement to an ontology triple by index or by subject/predicate/object."""
    requirement_type: Literal["hlr", "llr"]
    requirement_id: int
    triple_index: int = -1
    subject_qualified_name: str = ""
    predicate: str = ""
    object_qualified_name: str = ""


class DesignSchema(BaseModel):
    """Stage 2 output: ontology nodes, triples, and requirement links.

    Nodes are neomodel StructuredNode instances that cannot be typed
    as Pydantic fields; they are validated at the repository layer.
    """
    nodes: list  # neomodel CompoundNode | MemberNode | NamespaceNode
    triples: list[CodebaseEdge]
    requirement_links: list[RequirementTripleLinkSchema] = []


class DesignAndVerificationSchema(BaseModel):
    """Combined output for the design+verify tool loop."""
    oo_design: ClassDiagram
    verifications: dict[int, list[VerificationSchema]] = {}
