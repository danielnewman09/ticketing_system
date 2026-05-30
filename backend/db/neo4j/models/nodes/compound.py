"""CompoundNode — :Compound in Neo4j.

Compounds are top-level containers — classes, structs, interfaces, enums —
that own members and participate in associations. The `kind` field refines
the specific type. The `layer` field indicates origin: 'design' (agent-created),
'as-built' (parsed from code), or 'dependency' (external library).

Identified by `qualified_name`, used as the MERGE key in Neo4j.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class CompoundNode(BaseModel):
    """A compound entity in the codebase graph (:Compound in Neo4j).

    Compounds are the top-level containers — classes, structs, interfaces,
    enums — that own members and participate in associations.

    The `kind` field refines the specific type. The `layer` field indicates
    origin: 'design' (agent-created), 'as-built' (parsed from code), or
    'dependency' (external library).

    Identified by `qualified_name`, used as the MERGE key in Neo4j.
    """

    # --- Identity & classification ---
    qualified_name: str
    name: str
    kind: Literal["class", "struct", "template_class", "interface", "abstract_class", "enum", "enum_class"]
    layer: Literal["design", "as-built", "dependency"] = "design"
    specialization: str = ""
    visibility: Literal["public", "private", "protected", ""] = ""
    description: str = ""

    # --- Code-level detail ---
    type_signature: str = ""
    argsstring: str = ""
    definition: str = ""

    # --- Source location (populated for as-built layer) ---
    refid: str = ""
    file_path: str = ""
    line_number: int | None = None

    # --- Flags ---
    is_static: bool = False
    is_const: bool = False
    is_virtual: bool = False
    is_abstract: bool = False
    is_final: bool = False

    # --- Project context ---
    component_id: int | None = None
    is_intercomponent: bool = False

    # --- Implementation tracking (design layer) ---
    implementation_status: Literal["designed", "scaffolded", "tested", "implemented", "verified"] = "designed"
    source_file: str = ""
    test_file: str = ""

    model_config = {"from_attributes": True}