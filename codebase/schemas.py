"""
Pydantic schemas for the design pipeline.

Two schema families:
- OO design schemas (Stage 1 output): pure object-oriented class diagram.
- Ontology schemas (Stage 2 output): nodes, triples, requirement links.
"""

from typing import Literal

from pydantic import BaseModel

from db.models.ontology import NODE_KINDS, VISIBILITY_CHOICES

# Derived from the canonical NODE_KINDS list so there is one place to
# add or remove kinds.
NodeKind = Literal[tuple(k for k, _ in NODE_KINDS)]
Visibility = Literal[tuple(v for v, _ in VISIBILITY_CHOICES)]


# ---------------------------------------------------------------------------
# Stage 1: OO Design schemas (LLM output — no ontology vocabulary)
# ---------------------------------------------------------------------------

class AttributeSchema(BaseModel):
    name: str
    type_name: str = ""
    visibility: Visibility
    description: str = ""


class MethodSchema(BaseModel):
    name: str
    visibility: Visibility
    description: str = ""
    parameters: list[str] = []
    return_type: str = ""


class ClassSchema(BaseModel):
    name: str
    module: str = ""
    specialization: str = ""
    description: str = ""
    is_intercomponent: bool = False
    attributes: list[AttributeSchema] = []
    methods: list[MethodSchema] = []
    inherits_from: list[str] = []
    realizes_interfaces: list[str] = []
    requirement_ids: list[str] = []  # tagged: "hlr:3", "llr:7"


class EnumSchema(BaseModel):
    name: str
    module: str = ""
    description: str = ""
    values: list[str] = []


class InterfaceSchema(BaseModel):
    name: str
    module: str = ""
    specialization: str = ""
    description: str = ""
    is_intercomponent: bool = False
    methods: list[MethodSchema] = []


class AssociationSchema(BaseModel):
    from_class: str
    to_class: str
    kind: Literal["associates", "aggregates", "depends_on", "invokes"]
    description: str = ""
    requirement_ids: list[str] = []  # tagged: "hlr:3", "llr:7"


class OODesignSchema(BaseModel):
    """Stage 1 output: pure OO class diagram."""
    modules: list[str] = []
    classes: list[ClassSchema] = []
    interfaces: list[InterfaceSchema] = []
    enums: list[EnumSchema] = []
    associations: list[AssociationSchema] = []


# ---------------------------------------------------------------------------
# Stage 2: Ontology schemas (deterministic mapper output)
# ---------------------------------------------------------------------------

class OntologyNodeSchema(BaseModel):
    kind: NodeKind
    specialization: str = ""
    visibility: Visibility | str = ""
    name: str
    qualified_name: str
    description: str = ""
    component_id: int | None = None
    is_intercomponent: bool = False


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
