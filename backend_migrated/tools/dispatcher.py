"""Tool dispatcher for ``backend_migrated`` design agents.

Provides :class:`DesignToolDispatcher` — extends
:class:`codegraph.tools.dispatcher.CodeGraphDispatcher` with mutable
lookups for prior designs, dependency APIs, and intercomponent
boundaries, plus the 4 ticketing-specific design tools
(``validate_design``, ``check_class_name``,
``produce_oo_design``).

All generic codegraph tools (query, format, info, discovery, lookup)
are inherited from ``CodeGraphDispatcher``.

Usage::

    from backend_migrated.tools import DesignToolDispatcher

    d = DesignToolDispatcher(
        prior_class_lookup={"Calculator": "calc::Calculator"},
        dependency_lookup={"std::vector": "std::vector"},
    )
    schemas = d.all_tool_schemas  # 10 codegraph + 4 design = 14 tools
    result = d.dispatch("check_class_name", {"name": "Calculator"})
"""

from __future__ import annotations

from codegraph.repository import GraphRepository
from codegraph.tools.dispatcher import CodeGraphDispatcher


class DesignToolDispatcher(CodeGraphDispatcher):
    """Ticketing-specific dispatcher — inherits all codegraph tools + adds
    design validation, name checking, and mechanism lookup.

    Holds mutable lookups for prior designs, dependency APIs, and
    intercomponent boundaries that ``check_class_name``,
    ``validate_design`` and ``check_class_name`` read from (and that
    can be updated mid-session as designs are produced).

    Usage::

        d = DesignToolDispatcher(
            prior_class_lookup={"Calc": "calc::CalcEngine"},
            dependency_lookup={"std::vector": "std::vector"},
            intercomponent_classes=[
                {"qualified_name": "ui::Widget", "kind": "class", "name": "Widget"},
            ],
            component_namespace="calc",
        )
        schemas = d.all_tool_schemas
        result = d.dispatch("check_class_name", {"name": "Widget"})
    """

    def __init__(
        self,
        repo: GraphRepository | None = None,
        *,
        prior_class_lookup: dict[str, str] | None = None,
        dependency_lookup: dict[str, str] | None = None,
        intercomponent_classes: list[dict] | None = None,
        component_namespace: str = "",
        sibling_namespaces: list[str] | None = None,
    ):
        super().__init__(repo=repo)

        # ── Mutable context dictionaries (updated as designs are produced) ──
        self.prior_class_lookup: dict[str, str] = dict(prior_class_lookup or {})
        self.dependency_lookup: dict[str, str] = dict(dependency_lookup or {})
        self.intercomponent_classes: list[dict] = list(intercomponent_classes or [])
        self.component_namespace: str = component_namespace
        self.sibling_namespaces: list[str] = list(sibling_namespaces or [])

        # Register ticketing-specific design tools on top of codegraph tools
        from backend_migrated.tools.design_tools import register_all as _reg_design
        _reg_design(self)

    # ── Convenience setters ──────────────────────────────────────────────

    def add_prior_class(self, name: str, qualified_name: str) -> None:
        """Register a bare-name → qualified-name mapping for a newly
        designed class so that future ``check_class_name`` and
        ``validate_design`` calls can resolve it."""
        self.prior_class_lookup[name] = qualified_name

    def set_dependency_lookup(self, lookup: dict[str, str]) -> None:
        """Replace the dependency API lookup (name → qualified_name)."""
        self.dependency_lookup = dict(lookup)

    def set_intercomponent_classes(self, classes: list[dict]) -> None:
        """Replace the inter-component boundary class list."""
        self.intercomponent_classes = list(classes)
