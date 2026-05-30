"""MemberNode — :Member in Neo4j.

Members are owned by compounds — methods and attributes on classes,
values inside enums, constants inside namespaces. The `kind` field refines
the specific member type. The `layer` field indicates origin.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class MemberNode(BaseModel):
    """A member entity in the codebase graph (:Member in Neo4j).

    Members are owned by compounds — methods and attributes on classes,
    values inside enums, constants inside namespaces.

    The `kind` field refines the specific member type. The `layer` field
    indicates origin.
    """

    # --- Identity & classification ---
    qualified_name: str
    name: str
    kind: Literal["method", "attribute", "constant", "enum_value"]
    layer: Literal["design", "as-built", "dependency"] = "design"
    visibility: Literal["public", "private", "protected", ""] = ""
    description: str = ""

    # --- Code-level detail ---
    type_signature: str = ""
    argsstring: str = ""
    definition: str = ""

    # --- Source location ---
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

    model_config = {"from_attributes": True}