"""
Pydantic schemas for the design pipeline.

Two schema families:
- OO design schemas (Stage 1 output): pure object-oriented class diagram.
- Ontology schemas (Stage 2 output): nodes, triples, requirement links.
"""

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel

from backend.db.models.ontology import NODE_KINDS, SOURCE_TYPES, VISIBILITY_CHOICES
from backend.requirements.schemas import VerificationSchema

# Derived from the canonical NODE_KINDS list so there is one place to
# add or remove kinds.
NodeKind = Literal[tuple(k for k, _ in NODE_KINDS)]
Visibility = Literal[tuple(v for v, _ in VISIBILITY_CHOICES)]
SourceType = Literal[tuple(k for k, _ in SOURCE_TYPES)]


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
    requirement_ids: list[str] = []  # tagged: "hlr:3", "llr:7" (also accepts "HLR 3", "LLR 7")


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
    kind: Literal["associates", "aggregates", "composes", "depends_on", "references", "returns", "invokes"]
    description: str = ""
    mechanism: str = ""
    requirement_ids: list[str] = []  # tagged: "hlr:3", "llr:7" (also accepts "HLR 3", "LLR 7")


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

    # Codebase linkage
    source_type: SourceType | str = ""

    # Code-level detail
    type_signature: str = ""
    argsstring: str = ""
    definition: str = ""

    # Source location (empty at design time, populated after implementation)
    file_path: str = ""
    line_number: int | None = None

    # Flags
    is_static: bool = False
    is_const: bool = False
    is_virtual: bool = False
    is_abstract: bool = False
    is_final: bool = False


class OntologyTripleSchema(BaseModel):
    subject_qualified_name: str
    predicate: str  # Must match a Predicate.name in the database
    object_qualified_name: str
    mechanism: str = ""  # Container/smart-ptr type for aggregates/references
    position: int | None = None  # For TYPE_ARGUMENT: parameter position (0-based)
    name: str = ""  # For TEMPLATE_PARAM: parameter name (e.g. "T")
    display_name: str = ""  # Alias display name (e.g. "std::string" for std::basic_string edge)


class RequirementTripleLinkSchema(BaseModel):
    """Maps a requirement to an ontology triple by index or by subject/predicate/object."""

    requirement_type: Literal["hlr", "llr"]
    requirement_id: int
    triple_index: int = -1
    subject_qualified_name: str = ""
    predicate: str = ""
    object_qualified_name: str = ""


@dataclass
class TypeRef:
    """Structured reference to a type extracted from a type signature string.

    Handles qualified names (std::vector), template nesting
    (std::vector<std::string>), and builtin detection (int, double, void).
    """
    name: str                       # "std::vector" or "Calculator"
    template_args: list["TypeRef"]  # [] for non-templates, or nested TypeRefs
    is_builtin: bool                # True for int, double, void, etc.
    original_text: str              # "std::vector<const std::string&>"
    qualifiers: list[str]           # ["const", "&", "*"] etc.


class DesignSchema(BaseModel):
    nodes: list[OntologyNodeSchema]
    triples: list[OntologyTripleSchema]
    requirement_links: list[RequirementTripleLinkSchema] = []


# ---------------------------------------------------------------------------
# Combined Design + Verification schema (for combined tool loop)
# ---------------------------------------------------------------------------


class DesignAndVerificationSchema(BaseModel):
    """Combined output for the design+verify tool loop.

    The oo_design is the final OO class design, and verifications maps
    LLR ids to their verification procedures.
    """

    oo_design: OODesignSchema
    verifications: dict[int, list[VerificationSchema]] = {}
