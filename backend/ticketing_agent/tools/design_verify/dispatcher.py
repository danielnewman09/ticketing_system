"""Combined design+verify tool dispatcher.

Creates a ToolDispatcher with all design, verification, and discovery
tools registered. Maintains in-memory draft state between tool calls.
"""

from codegraph.diagram import ClassDiagram
from backend.requirements.schemas import VerificationSchema
from backend.ticketing_agent.tools import ToolDispatcher

# Handler imports
from backend.ticketing_agent.tools.design_verify.draft_design import (
    SCHEMA as DRAFT_DESIGN_SCHEMA, handle as handle_draft_design,
)
from backend.ticketing_agent.tools.design_verify.validate_design import (
    SCHEMA as VALIDATE_DESIGN_SCHEMA, handle as handle_validate_design,
)
from backend.ticketing_agent.tools.design_verify.check_class_name import (
    SCHEMA as CHECK_CLASS_NAME_SCHEMA, handle as handle_check_class_name,
)
from backend.ticketing_agent.tools.design_verify.find_mechanism import (
    SCHEMA as FIND_MECHANISM_SCHEMA, handle as handle_find_mechanism,
)
from backend.ticketing_agent.tools.design_verify.validate_qualified_names import (
    SCHEMA as VALIDATE_QNAMES_SCHEMA, handle as handle_validate_qualified_names,
)
from backend.ticketing_agent.tools.design_verify.lookup_design_element import (
    SCHEMA as LOOKUP_DESIGN_ELEMENT_SCHEMA, handle as handle_lookup_design_element,
)
from backend.ticketing_agent.tools.design_verify.draft_verifications import (
    SCHEMA as DRAFT_VERIFICATIONS_SCHEMA, handle as handle_draft_verifications,
)
from backend.ticketing_agent.tools.design_verify.commit import (
    SCHEMA as COMMIT_SCHEMA, handle as handle_commit,
)

# Discovery handler
from backend.ticketing_agent.tools.helpers.discovery import discover_tool_dispatch

# Discovery schemas
from backend.ticketing_agent.tools.utilities.list_sources import SCHEMA as LIST_SOURCES_SCHEMA
from backend.ticketing_agent.tools.utilities.search_symbols import SCHEMA as SEARCH_SYMBOLS_SCHEMA
from backend.ticketing_agent.tools.utilities.get_compound import SCHEMA as GET_COMPOUND_SCHEMA
from backend.ticketing_agent.tools.utilities.browse_namespace import SCHEMA as BROWSE_NAMESPACE_SCHEMA
from backend.ticketing_agent.tools.utilities.find_inheritance import SCHEMA as FIND_INHERITANCE_SCHEMA


class CombinedDispatcher(ToolDispatcher):
    """Tool dispatcher for the combined design+verify agent loop.

    Maintains in-memory draft state between tool calls and provides
    access to shared context (prior classes, dependencies, Neo4j).

    Usage::

        dispatcher = CombinedDispatcher(
            prior_class_lookup=cls_lookup,
            dependency_lookup=dep_lookup,
            neo4j_session=session,
        )
        result = call_tool_loop(
            ...,
            tools=dispatcher.all_tool_schemas,
            tool_dispatcher=dispatcher.dispatch,
        )
    """

    def __init__(
        self,
        prior_class_lookup: dict[str, str],
        dependency_lookup: dict[str, str] | None = None,
        intercomponent_classes: list[dict] | None = None,
        neo4j_session=None,
        toolset=None,
    ):
        super().__init__()
        # --- Immutable context ---
        self.prior_class_lookup = prior_class_lookup
        self.dep_lookup = dict(dependency_lookup or {})
        self.intercomponent_classes = intercomponent_classes or []
        self.neo4j_session = neo4j_session
        self.toolset = toolset

        # --- Mutable draft state ---
        self.draft_design: ClassDiagram | None = None
        self.draft_lookup: dict[str, dict] = {}
        self.draft_verifications: dict[int, list[VerificationSchema]] = {}

        # --- Register all handlers ---
        self._register_design_tools()
        self._register_verification_tools()
        self._register_discovery_tools()

    def _register_design_tools(self):
        self.register("draft_design", DRAFT_DESIGN_SCHEMA,
                       lambda inp: handle_draft_design(self, inp))
        self.register("validate_design", VALIDATE_DESIGN_SCHEMA,
                       lambda inp: handle_validate_design(self, inp))
        self.register("check_class_name", CHECK_CLASS_NAME_SCHEMA,
                       lambda inp: handle_check_class_name(self, inp))
        self.register("find_mechanism", FIND_MECHANISM_SCHEMA,
                       lambda inp: handle_find_mechanism(self, inp))

    def _register_verification_tools(self):
        self.register("validate_qualified_names", VALIDATE_QNAMES_SCHEMA,
                       lambda inp: handle_validate_qualified_names(self, inp))
        self.register("lookup_design_element", LOOKUP_DESIGN_ELEMENT_SCHEMA,
                       lambda inp: handle_lookup_design_element(self, inp))
        self.register("draft_verifications", DRAFT_VERIFICATIONS_SCHEMA,
                       lambda inp: handle_draft_verifications(self, inp))
        self.register("commit_design_and_verifications", COMMIT_SCHEMA,
                       lambda inp: handle_commit(self, inp))

    def _register_discovery_tools(self):
        self.register("list_sources", LIST_SOURCES_SCHEMA,
                       lambda inp: discover_tool_dispatch("list_sources", inp, self.toolset))
        self.register("search_symbols", SEARCH_SYMBOLS_SCHEMA,
                       lambda inp: discover_tool_dispatch("search_symbols", inp, self.toolset))
        self.register("get_compound", GET_COMPOUND_SCHEMA,
                       lambda inp: discover_tool_dispatch("get_compound", inp, self.toolset))
        self.register("browse_namespace", BROWSE_NAMESPACE_SCHEMA,
                       lambda inp: discover_tool_dispatch("browse_namespace", inp, self.toolset))
        self.register("find_inheritance", FIND_INHERITANCE_SCHEMA,
                       lambda inp: discover_tool_dispatch("find_inheritance", inp, self.toolset))
