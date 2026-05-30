"""MemberNode — :Member in Neo4j.

Members are owned by compounds — methods and variables on classes,
values inside enums, defines inside namespaces. The `kind` field refines
the specific member type. The `layer` field indicates origin.
"""

from __future__ import annotations

from codegraph.nodes import MemberNode as BaseMemberNode


class MemberNode(BaseMemberNode):
    """A member entity in the codebase graph (:Member in Neo4j).

    Inherits all core fields from ``codegraph.nodes.MemberNode``
    (including ``component_id``). Kept as a thin subclass for the
    ``extra: "ignore"`` model config and import compatibility.
    """

    model_config = {"from_attributes": True, "extra": "ignore"}
