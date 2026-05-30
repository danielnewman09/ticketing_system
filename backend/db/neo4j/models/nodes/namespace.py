"""NamespaceNode — :Namespace in Neo4j.

Namespaces group compounds into modules. They form a hierarchy via
COMPOSES edges (e.g. `std` COMPOSES `std::chrono`).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class NamespaceNode(BaseModel):
    """A namespace entity in the codebase graph (:Namespace in Neo4j).

    Namespaces group compounds into modules. They form a hierarchy via
    COMPOSES edges (e.g. `std` COMPOSES `std::chrono`).
    """

    # --- Identity & classification ---
    qualified_name: str
    name: str
    kind: Literal["namespace", "package"] = "namespace"
    layer: Literal["design", "as-built", "dependency"] = "design"
    description: str = ""

    # --- Source location ---
    refid: str = ""
    file_path: str = ""

    # --- Project context ---
    component_id: int | None = None

    model_config = {"from_attributes": True}