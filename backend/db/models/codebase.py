"""Reflected read-only models from backend.codebase.sqlite3.

These are never migrated by Alembic — they are populated externally
(e.g. by Doxygen tooling).
"""

from __future__ import annotations

from sqlalchemy import Column, Integer, Text
from sqlalchemy.orm import DeclarativeBase


class CodebaseBase(DeclarativeBase):
    """Separate base for the codebase database — not managed by Alembic."""
    pass


class CodebaseFile(CodebaseBase):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True)
    refid = Column(Text, unique=True)
    name = Column(Text)
    path = Column(Text, nullable=True)
    language = Column(Text, nullable=True)


class Namespace(CodebaseBase):
    __tablename__ = "namespaces"

    id = Column(Integer, primary_key=True)
    refid = Column(Text, unique=True)
    name = Column(Text)
    qualified_name = Column(Text)


class Compound(CodebaseBase):
    __tablename__ = "compounds"

    id = Column(Integer, primary_key=True)
    refid = Column(Text, unique=True)
    kind = Column(Text)
    name = Column(Text)
    qualified_name = Column(Text)
    file_id = Column(Integer, nullable=True)
    line_number = Column(Integer, nullable=True)
    brief_description = Column(Text, nullable=True)
    detailed_description = Column(Text, nullable=True)
    base_classes = Column(Text, nullable=True)
    is_final = Column(Integer, default=0)
    is_abstract = Column(Integer, default=0)


class Member(CodebaseBase):
    __tablename__ = "members"

    id = Column(Integer, primary_key=True)
    refid = Column(Text, unique=True)
    compound_id = Column(Integer, nullable=True)
    kind = Column(Text)
    name = Column(Text)
    qualified_name = Column(Text)
    type = Column(Text, nullable=True)
    definition = Column(Text, nullable=True)
    argsstring = Column(Text, nullable=True)
    file_id = Column(Integer, nullable=True)
    line_number = Column(Integer, nullable=True)
    brief_description = Column(Text, nullable=True)
    detailed_description = Column(Text, nullable=True)
    protection = Column(Text, nullable=True)
    is_static = Column(Integer, default=0)
    is_const = Column(Integer, default=0)
    is_constexpr = Column(Integer, default=0)
    is_virtual = Column(Integer, default=0)
    is_inline = Column(Integer, default=0)
    is_explicit = Column(Integer, default=0)


class Parameter(CodebaseBase):
    __tablename__ = "parameters"

    id = Column(Integer, primary_key=True)
    member_id = Column(Integer)
    position = Column(Integer)
    name = Column(Text, nullable=True)
    type = Column(Text)
    default_value = Column(Text, nullable=True)
    description = Column(Text, nullable=True)


class SymbolRef(CodebaseBase):
    __tablename__ = "symbol_refs"

    id = Column(Integer, primary_key=True)
    from_member_id = Column(Integer, nullable=True)
    to_member_refid = Column(Text)
    to_member_name = Column(Text)
    relationship = Column(Text)


class Include(CodebaseBase):
    __tablename__ = "includes"

    id = Column(Integer, primary_key=True)
    file_id = Column(Integer)
    included_file = Column(Text)
    included_refid = Column(Text, nullable=True)
    is_local = Column(Integer, default=0)


class Metadata(CodebaseBase):
    __tablename__ = "metadata"

    key = Column(Text, primary_key=True)
    value = Column(Text, nullable=True)
