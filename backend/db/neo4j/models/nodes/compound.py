"""CompoundNode — :Compound in Neo4j.

Compounds are top-level containers — classes, structs, interfaces, enums, unions —
that own members and participate in associations. The `kind` field refines
the specific type. The `layer` field indicates origin: 'design' (agent-created),
'as-built' (parsed from code), or 'dependency' (external library).

Identified by `qualified_name`, used as the MERGE key in Neo4j.

Ticketing-system extensions (component_id, implementation_status, etc.) are
added on top of the ``codegraph`` base model.
"""

from __future__ import annotations

from typing import Literal

from codegraph.nodes import CompoundNode as BaseCompoundNode


class CompoundNode(BaseCompoundNode):
    """A compound entity in the codebase graph (:Compound in Neo4j).

    Inherits core fields from ``codegraph.nodes.CompoundNode`` and adds
    ticketing-system-specific fields for project context and implementation
    tracking.
    """

    # --- Ticketing-system extensions ---
    specialization: str = ""
    type_signature: str = ""
    argsstring: str = ""
    definition: str = ""
    is_static: bool = False
    is_const: bool = False
    is_virtual: bool = False
    component_id: int | None = None
    is_intercomponent: bool = False
    implementation_status: Literal[
        "designed", "scaffolded", "tested", "implemented", "verified"
    ] = "designed"
    source_file: str = ""
    test_file: str = ""
