"""Ontology graph layer — nodes, predicates, triples."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Integer, String, Text, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base

if TYPE_CHECKING:
    from backend.db.models.components import Component

# ---------------------------------------------------------------------------
# Node kinds — language-agnostic base kinds
# ---------------------------------------------------------------------------

NODE_KINDS = [
    ("attribute", "Attribute"),
    ("class", "Class"),
    ("constant", "Constant"),
    ("enum", "Enum"),
    ("enum_value", "Enum Value"),
    ("function", "Function"),
    ("interface", "Interface"),
    ("method", "Method"),
    ("module", "Module"),
    ("primitive", "Primitive Type"),
    ("type_alias", "Type Alias"),
]

NODE_KIND_VALUES = {k for k, _ in NODE_KINDS}

# ---------------------------------------------------------------------------
# Visibility / access specifiers
# ---------------------------------------------------------------------------

VISIBILITY_CHOICES = [
    ("public", "Public"),
    ("private", "Private"),
    ("protected", "Protected"),
]

# Semantic groupings used by validation and review agents.
TYPE_KINDS = {"class", "interface", "enum", "type_alias"}
VALUE_KINDS = {"enum_value", "function", "method", "attribute", "constant"}

# ---------------------------------------------------------------------------
# Codebase source types — which entity in the codebase DB a node maps to
# ---------------------------------------------------------------------------

SOURCE_TYPES = [
    ("namespace", "Namespace"),
    ("compound", "Compound"),
    ("member", "Member"),
]

SOURCE_TYPE_VALUES = {k for k, _ in SOURCE_TYPES}

# ---------------------------------------------------------------------------
# Language-specific specializations
# ---------------------------------------------------------------------------

LANGUAGE_SPECIALIZATIONS = {
    "cpp": {
        "class": [
            "struct",
            "template_class",
            "abstract_class",
        ],
        "method": [
            "virtual_method",
            "pure_virtual_method",
            "template_method",
            "static_method",
            "const_method",
            "operator_overload",
        ],
        "function": [
            "template_function",
        ],
        "constant": [
            "constexpr",
            "const",
        ],
        "enum": [
            "enum_class",
        ],
        "type_alias": [
            "using",
            "typedef",
        ],
        "module": [
            "namespace",
        ],
    },
    "python": {
        "class": [
            "dataclass",
            "namedtuple",
        ],
        "method": [
            "classmethod",
            "staticmethod",
            "property",
            "abstractmethod",
            "async_method",
        ],
        "function": [
            "async_function",
            "generator",
            "decorator",
        ],
        "interface": [
            "protocol",
            "abc",
        ],
        "constant": [
            "final",
        ],
        "module": [
            "package",
        ],
    },
    "javascript": {
        "class": [],
        "method": [
            "getter",
            "setter",
            "static_method",
            "async_method",
        ],
        "function": [
            "arrow_function",
            "async_function",
            "generator",
        ],
        "module": [
            "es_module",
            "commonjs_module",
        ],
    },
}

SUPPORTED_LANGUAGES = set(LANGUAGE_SPECIALIZATIONS.keys())


def valid_specializations(language, kind):
    """Return the set of valid specializations for a language + kind."""
    lang_spec = LANGUAGE_SPECIALIZATIONS.get(language, {})
    return set(lang_spec.get(kind, []))


class OntologyNode(Base):
    __tablename__ = "ontology_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # --- Identity & classification ---
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    specialization: Mapped[str] = mapped_column(String(40), default="", server_default="")
    visibility: Mapped[str] = mapped_column(String(10), default="", server_default="")
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    qualified_name: Mapped[str] = mapped_column(String(500), default="", server_default="")
    description: Mapped[str] = mapped_column(Text, default="", server_default="")

    # --- Codebase linkage ---
    # refid is the unique Doxygen reference id (e.g. "classmsd__sim_1_1Foo").
    # Replaces the old compound_refid; works for namespaces, compounds, and members.
    refid: Mapped[str] = mapped_column(String(200), default="", server_default="")
    source_type: Mapped[str] = mapped_column(String(20), default="", server_default="")

    # --- Code-level detail (mirrors compounds + members) ---
    type_signature: Mapped[str] = mapped_column(String(500), default="", server_default="")
    argsstring: Mapped[str] = mapped_column(String(500), default="", server_default="")
    definition: Mapped[str] = mapped_column(Text, default="", server_default="")

    # --- Source location ---
    file_path: Mapped[str] = mapped_column(String(500), default="", server_default="")
    line_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # --- Flags (applicable across compounds & members) ---
    is_static: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    is_const: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    is_virtual: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    is_abstract: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    is_final: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    # --- Project-level context ---
    component_id: Mapped[Optional[int]] = mapped_column(ForeignKey("components.id", ondelete="SET NULL"), nullable=True)
    is_intercomponent: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    # --- Relationships ---
    component: Mapped[Optional[Component]] = relationship("Component", back_populates="ontology_nodes")
    triples_as_subject: Mapped[list[OntologyTriple]] = relationship("OntologyTriple", foreign_keys="OntologyTriple.subject_id", back_populates="subject")
    triples_as_object: Mapped[list[OntologyTriple]] = relationship("OntologyTriple", foreign_keys="OntologyTriple.object_id", back_populates="object")

    def __repr__(self):
        return self.qualified_name or self.name


class Predicate(Base):
    __tablename__ = "ontology_predicates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", server_default="")

    triples: Mapped[list[OntologyTriple]] = relationship("OntologyTriple", back_populates="predicate")

    def __repr__(self):
        return self.name

    # Seed data: UML-aligned defaults
    DEFAULT_PREDICATES = [
        ("associates", "General association between two entities"),
        ("aggregates", "Whole-part relationship where the part can exist independently"),
        ("composes", "Strong whole-part relationship where the part is owned by the whole"),
        ("depends_on", "One entity depends on another"),
        ("generalizes", "Inheritance / is-a relationship"),
        ("realizes", "A class implements/realizes an interface or contract"),
        ("invokes", "Weak association, signififying a caller-callee relationship"),
    ]

    @classmethod
    def ensure_defaults(cls, session):
        """Create default predicates if they don't exist."""
        from backend.db import get_or_create
        for name, description in cls.DEFAULT_PREDICATES:
            get_or_create(session, cls, defaults={"description": description}, name=name)


class OntologyTriple(Base):
    __tablename__ = "ontology_triples"
    __table_args__ = (
        UniqueConstraint("subject_id", "predicate_id", "object_id", name="uq_ontology_triples_subject_predicate_object"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("ontology_nodes.id", ondelete="CASCADE"), nullable=False)
    predicate_id: Mapped[int] = mapped_column(ForeignKey("ontology_predicates.id", ondelete="RESTRICT"), nullable=False)
    object_id: Mapped[int] = mapped_column(ForeignKey("ontology_nodes.id", ondelete="CASCADE"), nullable=False)

    subject: Mapped[OntologyNode] = relationship("OntologyNode", foreign_keys=[subject_id], back_populates="triples_as_subject")
    predicate: Mapped[Predicate] = relationship("Predicate", back_populates="triples")
    object: Mapped[OntologyNode] = relationship("OntologyNode", foreign_keys=[object_id], back_populates="triples_as_object")

    def __repr__(self):
        return f"{self.subject} --{self.predicate}--> {self.object}"
