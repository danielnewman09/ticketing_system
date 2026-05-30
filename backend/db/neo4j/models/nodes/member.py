"""MemberNode — :Member in Neo4j.

Members are owned by compounds — methods and variables on classes,
values inside enums, defines inside namespaces. The `kind` field refines
the specific member type. The `layer` field indicates origin.

Ticketing-system extensions (component_id, is_abstract, is_final) are added
on top of the ``codegraph`` base model.
"""

from __future__ import annotations

from codegraph.nodes import MemberNode as BaseMemberNode


class MemberNode(BaseMemberNode):
    """A member entity in the codebase graph (:Member in Neo4j).

    Inherits core fields from ``codegraph.nodes.MemberNode`` and adds
    ticketing-system-specific fields for project context.
    """

    # --- Ticketing-system extensions ---
    is_abstract: bool = False
    is_final: bool = False
    component_id: int | None = None
