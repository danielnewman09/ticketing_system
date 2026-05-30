"""CompoundNode — :Compound in Neo4j.

Compounds are top-level containers — classes, structs, interfaces, enums, unions —
that own members and participate in associations. The `kind` field refines
the specific type. The `layer` field indicates origin: 'design' (agent-created),
'as-built' (parsed from code), or 'dependency' (external library).

Ticketing-system extensions (specialization, implementation_status, etc.) are
added on top of the ``codegraph`` base model.
"""

from __future__ import annotations

from typing import Literal

from codegraph.nodes import CompoundNode as BaseCompoundNode


class CompoundNode(BaseCompoundNode):
    """A compound entity in the codebase graph (:Compound in Neo4j).

    Inherits core fields from ``codegraph.nodes.CompoundNode`` (including
    ``component_id`` and ``file_path``) and adds ticketing-system-specific
    fields for project context and implementation tracking.
    """

    model_config = {"from_attributes": True, "extra": "ignore"}

    # --- Ticketing-system extensions ---
    specialization: str = ""
    is_intercomponent: bool = False
    implementation_status: Literal[
        "designed", "scaffolded", "tested", "implemented", "verified"
    ] = "designed"
    test_file: str = ""
