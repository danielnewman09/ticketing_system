"""Tool dispatchers for ``backend_migrated`` agents.

Provides three dispatcher classes:

- :class:`DesignToolDispatcher` — extends
  :class:`codegraph.tools.dispatcher.CodeGraphDispatcher` with mutable
  lookups for prior designs, dependency APIs, and intercomponent
  boundaries, plus design tools (``validate_design``, ``check_class_name``,
  ``produce_oo_design``).  Inherits the full codegraph tool suite.

- :class:`VerificationDispatcher` — extends the base
  :class:`ToolDispatcher` with verification-resolution tools
  (``draft_verifications``, ``commit_design_and_verifications``).
  Holds a reference to the :class:`DesignToolDispatcher` for access
  to the design draft and context lookups.  Does **not** inherit
  codegraph tools — the agent can use those via the design dispatcher.

- :class:`RequirementsDispatcher` — extends the base
  :class:`ToolDispatcher` with requirements-retrieval tools
  (``get_requirement_hierarchy``, ``get_llr_details``, etc.).

Usage::

    from backend_migrated.tools.dispatcher import (
        DesignToolDispatcher,
        VerificationDispatcher,
        RequirementsDispatcher,
    )

    # Design + verification agent (single tool loop)
    design_disp = DesignToolDispatcher(
        prior_class_lookup={"Thermostat": "climate::Thermostat"},
    )
    verif_disp = VerificationDispatcher(design_dispatcher=design_disp)

    # Composite dispatch for the tool loop
    def dispatch(name, inp):
        if name in verif_disp._handlers:
            return verif_disp.dispatch(name, inp)
        return design_disp.dispatch(name, inp)

    tools = design_disp.all_tool_schemas + verif_disp.all_tool_schemas
    result = call_tool_loop(..., tools=tools, final_tool_name="commit_design_and_verifications", ...)

    # Requirements agent (standalone)
    req_disp = RequirementsDispatcher()
"""

from __future__ import annotations

from contextlib import contextmanager

from codegraph.repository import GraphRepository
from codegraph.tools.dispatcher import CodeGraphDispatcher, ToolDispatcher
from codegraph.connection import get_session


class DesignToolDispatcher(CodeGraphDispatcher):
    """Design-agent dispatcher — inherits all codegraph tools + adds
    design validation, name checking, and design storage.

    Holds mutable lookups for prior designs, dependency APIs, and
    intercomponent boundaries.  The ``produce_oo_design`` tool stores
    the design on ``self.design_draft`` so that the
    :class:`VerificationDispatcher` can validate qname references
    against it.

    Usage::

        d = DesignToolDispatcher(
            prior_class_lookup={"Thermostat": "climate::Thermostat"},
            dependency_lookup={"std::vector": "std::vector"},
            intercomponent_classes=[
                {"qualified_name": "ui::Widget", "kind": "class", "name": "Widget"},
            ],
            component_namespace="climate",
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

        # ── Mutable draft state ──
        self.design_draft: list[dict] | None = None

        # Register design-specific tools on top of codegraph tools
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


class VerificationDispatcher(ToolDispatcher):
    """Verification-resolution dispatcher — resolve notional verification
    stubs to qualified design names.

    Extends the base :class:`ToolDispatcher` with just two tools:

    - ``draft_verifications`` — submit resolved verification procedures,
      validate qname references against the design draft + context, and
      return unresolved references with suggestions.
    - ``commit_design_and_verifications`` — terminal tool that validates
      everything and returns the final design + verifications.

    Holds a reference to the :class:`DesignToolDispatcher` for access
    to ``design_draft``, ``prior_class_lookup``,
    ``dependency_lookup``, and ``intercomponent_classes``.

    Usage::

        design_disp = DesignToolDispatcher(prior_class_lookup={...})
        verif_disp = VerificationDispatcher(design_dispatcher=design_disp)
    """

    def __init__(self, design_dispatcher: DesignToolDispatcher):
        super().__init__()
        self._design_dispatcher = design_dispatcher

        # Register verification tools
        from backend_migrated.tools.verification_tools import register_all as _reg_verif
        _reg_verif(self)

    # ── Delegate access to the design dispatcher's context ────────────────

    @property
    def design_draft(self) -> list[dict] | None:
        """The design stored by ``produce_oo_design``."""
        return self._design_dispatcher.design_draft

    @property
    def prior_class_lookup(self) -> dict[str, str]:
        """Bare-name → qualified-name from prior designs."""
        return self._design_dispatcher.prior_class_lookup

    @property
    def dependency_lookup(self) -> dict[str, str]:
        """Bare-name → qualified-name for dependency API classes."""
        return self._design_dispatcher.dependency_lookup

    @property
    def intercomponent_classes(self) -> list[dict]:
        """Inter-component boundary classes."""
        return self._design_dispatcher.intercomponent_classes

    @property
    def draft_verifications(self) -> dict[str, list[dict]] | None:
        """Verification procedures stored by ``draft_verifications``."""
        return getattr(self, "_draft_verifications", None)

    @draft_verifications.setter
    def draft_verifications(self, value: dict[str, list[dict]] | None) -> None:
        self._draft_verifications = value


class RequirementsDispatcher(ToolDispatcher):
    """Requirements-agent dispatcher — lightweight base + only
    requirements-retrieval tools.

    Extends the base :class:`ToolDispatcher` without inheriting the
    full codegraph tool suite.  Adds a ``session()`` context manager
    for Neo4j Cypher queries used by the ``list_requirements`` tool.

    Provides tools for:

    - ``get_requirement_hierarchy`` — full HLR → LLR → Verification tree
    - ``get_llr_details`` — single LLR with verification methods
    - ``search_requirements`` — keyword search across HLR/LLR descriptions
    - ``list_requirements`` — list HLRs with optional component/layer filter
    - ``get_requirement_traces`` — COMPOSES edges from requirement to design nodes

    Usage::

        r = RequirementsDispatcher()
        schemas = r.all_tool_schemas   # only the 5 requirements tools
        result = r.dispatch("get_requirement_hierarchy", {"refid": "abc123"})
    """

    def __init__(self) -> None:
        super().__init__()

        # Register requirements-retrieval tools (no codegraph tools)
        from backend_migrated.tools.requirements_tools import register_all as _reg_requirements
        _reg_requirements(self)

    @contextmanager
    def session(self):
        """Yield a Neo4j driver session."""
        with get_session() as session:
            yield session