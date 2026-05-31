"""CompoundNode — :Compound in Neo4j.

Ticketing-system extensions on top of ``codegraph.nodes.CompoundNode``.
All core fields (qualified_name, kind, layer, component_id, file_path, etc.)
are inherited from the codegraph base model.
"""

from __future__ import annotations

from typing import Literal

from codegraph.models import CompoundNode as BaseCompoundNode


class CompoundNode(BaseCompoundNode):
    """A compound entity in the codebase graph (:Compound in Neo4j).

    Inherits core fields from ``codegraph.nodes.CompoundNode`` and adds
    ticketing-system-specific fields for project context and implementation
    tracking.
    """

    model_config = {"from_attributes": True, "extra": "ignore"}

    # --- Ticketing-system extensions ONLY ---
    specialization: str = ""
    is_intercomponent: bool = False
    implementation_status: Literal[
        "designed", "scaffolded", "tested", "implemented", "verified"
    ] = "designed"
    test_file: str = ""
