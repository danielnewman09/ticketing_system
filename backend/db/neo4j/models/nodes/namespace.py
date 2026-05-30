"""NamespaceNode — :Namespace in Neo4j.

Namespaces group compounds into modules. They form a hierarchy via
COMPOSES edges (e.g. `std` COMPOSES `std::chrono`).

Ticketing-system extensions (file_path, component_id) are added on top
of the ``codegraph`` base model.
"""

from __future__ import annotations

from codegraph.nodes import NamespaceNode as BaseNamespaceNode


class NamespaceNode(BaseNamespaceNode):
    """A namespace entity in the codebase graph (:Namespace in Neo4j).

    Inherits core fields from ``codegraph.nodes.NamespaceNode`` and adds
    ticketing-system-specific fields for project context.
    """

    # --- Ticketing-system extensions ---
    file_path: str = ""
    component_id: int | None = None
