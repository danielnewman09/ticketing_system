"""Pydantic models for Neo4j Design nodes and triple updates.

These replace SQLAlchemy OntologyNode/OntologyTriple as the
data contract between Neo4j and the application layer.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DesignNode(BaseModel):
    """A design-intent node in the ontology graph.

    Mirrors the properties stored on :Design nodes in Neo4j.
    qualified_name is the unique identifier and MERGE key.
    """

    qualified_name: str
    name: str
    kind: str
    specialization: str = ""
    visibility: str = ""
    description: str = ""
    refid: str = ""
    source_type: str = ""
    type_signature: str = ""
    argsstring: str = ""
    definition: str = ""
    file_path: str = ""
    line_number: int | None = None
    is_static: bool = False
    is_const: bool = False
    is_virtual: bool = False
    is_abstract: bool = False
    is_final: bool = False
    component_id: int | None = None
    is_intercomponent: bool = False
    implementation_status: str = "designed"
    source_file: str = ""
    test_file: str = ""

    model_config = {"from_attributes": True}


class DesignTripleUpdate(BaseModel):
    """A request to create or update a relationship between two Design nodes.

    subject and object are identified by qualified_name.
    predicate is the lowercase predicate name (e.g. "composes").
    """

    subject_qualified_name: str
    predicate: str
    object_qualified_name: str