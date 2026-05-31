"""Unit tests for individual tool handlers in the design_verify package."""

import json
import pytest
from unittest.mock import MagicMock

from codegraph.diagram import ClassDiagram


class MockContext:
    """Lightweight mock of CombinedDispatcher for testing individual handlers."""
    def __init__(
        self,
        prior_class_lookup=None,
        dep_lookup=None,
        intercomponent_classes=None,
        neo4j_session=None,
        toolset=None,
        draft_lookup=None,
        draft_design=None,
    ):
        self.prior_class_lookup = prior_class_lookup or {}
        self.dep_lookup = dep_lookup or {}
        self.intercomponent_classes = intercomponent_classes or []
        self.neo4j_session = neo4j_session
        self.toolset = toolset
        self.draft_lookup = draft_lookup or {}
        self.draft_design = draft_design
        self.draft_verifications = {}


class TestCheckClassName:
    def test_empty_name_returns_not_found(self):
        from backend.ticketing_agent.tools.design_verify.check_class_name import handle
        ctx = MockContext()
        result = json.loads(handle(ctx, {"name": ""}))
        assert result["found"] is False
        assert result["matches"] == []

    def test_finds_in_prior_class_lookup(self):
        from backend.ticketing_agent.tools.design_verify.check_class_name import handle
        ctx = MockContext(prior_class_lookup={"Calculator": "calc::Calculator"})
        result = json.loads(handle(ctx, {"name": "Calculator"}))
        assert result["found"] is True
        assert any(m["source"] == "prior_design" for m in result["matches"])

    def test_finds_in_dep_lookup(self):
        from backend.ticketing_agent.tools.design_verify.check_class_name import handle
        ctx = MockContext(dep_lookup={"Fl_Window": "fltk::Fl_Window"})
        result = json.loads(handle(ctx, {"name": "Fl_Window"}))
        assert result["found"] is True
        assert any(m["source"] == "dependency" for m in result["matches"])

    def test_finds_in_draft_lookup(self):
        from backend.ticketing_agent.tools.design_verify.check_class_name import handle
        ctx = MockContext(draft_lookup={
            "calc::Calculator": {"qualified_name": "calc::Calculator", "kind": "class", "description": "", "source": "draft"},
        })
        result = json.loads(handle(ctx, {"name": "Calculator"}))
        assert result["found"] is True
        assert any(m["source"] == "draft" for m in result["matches"])


class TestFindMechanism:
    def test_empty_query_returns_empty(self):
        from backend.ticketing_agent.tools.design_verify.find_mechanism import handle
        ctx = MockContext()
        result = json.loads(handle(ctx, {"query": ""}))
        assert result == {"containers": []}

    def test_finds_in_dep_lookup(self):
        from backend.ticketing_agent.tools.design_verify.find_mechanism import handle
        ctx = MockContext(dep_lookup={"vector": "std::vector"})
        result = json.loads(handle(ctx, {"query": "vector"}))
        assert len(result["containers"]) == 1
        assert result["containers"][0]["qualified_name"] == "std::vector"


class TestDraftDesign:
    def test_valid_empty_design_passes(self):
        from backend.ticketing_agent.tools.design_verify.draft_design import handle
        ctx = MockContext()
        # An empty design with no classes is technically valid
        result = json.loads(handle(ctx, {"design": {"classes": [], "interfaces": [], "enums": [], "associations": []}}))
        assert result["valid"] is True

    def test_valid_design_stores_draft(self):
        from backend.ticketing_agent.tools.design_verify.draft_design import handle
        ctx = MockContext()
        design = {
            "classes": [
                {
                    "name": "Calculator",
                    "module": "calc",
                    "description": "Calculator class",
                    "attributes": [],
                    "methods": [],
                },
            ],
            "interfaces": [],
            "enums": [],
            "associations": [],
        }
        result = json.loads(handle(ctx, {"design": design}))
        assert result["valid"] is True
        assert ctx.draft_design is not None
        assert ctx.draft_lookup != {}


class TestValidateDesign:
    def test_valid_design_passes(self):
        from backend.ticketing_agent.tools.design_verify.validate_design import handle
        ctx = MockContext()
        design = {
            "classes": [
                {
                    "name": "Calculator",
                    "module": "calc",
                    "description": "A calculator",
                    "attributes": [],
                    "methods": [],
                },
            ],
            "interfaces": [],
            "enums": [],
            "associations": [],
        }
        result = json.loads(handle(ctx, {"design": design}))
        assert result["valid"] is True

    def test_valid_empty_design_passes(self):
        from backend.ticketing_agent.tools.design_verify.validate_design import handle
        ctx = MockContext()
        # An empty design with no classes is valid
        result = json.loads(handle(ctx, {"design": {"classes": [], "interfaces": [], "enums": [], "associations": []}}))
        assert result["valid"] is True


class TestToolDispatcher:
    def test_dispatch_unknown_returns_error(self):
        from backend.ticketing_agent.tools import ToolDispatcher
        d = ToolDispatcher()
        result = json.loads(d.dispatch("nonexistent", {}))
        assert "error" in result

    def test_register_and_dispatch(self):
        from backend.ticketing_agent.tools import ToolDispatcher
        d = ToolDispatcher()
        d.register("test", {"name": "test"}, lambda inp: json.dumps({"ok": True, "input": inp}))
        result = json.loads(d.dispatch("test", {"x": 1}))
        assert result["ok"] is True
        assert result["input"] == {"x": 1}

    def test_all_tool_schemas(self):
        from backend.ticketing_agent.tools import ToolDispatcher
        d = ToolDispatcher()
        d.register("a", {"name": "a"}, lambda inp: "")
        d.register("b", {"name": "b"}, lambda inp: "")
        assert [s["name"] for s in d.all_tool_schemas] == ["a", "b"]


class TestCombinedDispatcher:
    def test_all_13_tools_registered(self):
        from backend.ticketing_agent.tools.design_verify import CombinedDispatcher
        d = CombinedDispatcher(prior_class_lookup={})
        expected = sorted([
            "list_sources", "search_symbols", "get_compound", "browse_namespace", "find_inheritance",
            "draft_design", "validate_design", "check_class_name", "find_mechanism",
            "validate_qualified_names", "lookup_design_element", "draft_verifications",
            "commit_design_and_verifications",
        ])
        names = sorted(s["name"] for s in d.all_tool_schemas)
        assert names == expected

    def test_draft_design_roundtrip(self):
        from backend.ticketing_agent.tools.design_verify import CombinedDispatcher
        d = CombinedDispatcher(prior_class_lookup={})
        design = {
            "classes": [{
                "name": "Widget",
                "module": "app",
                "description": "A widget",
                "attributes": [],
                "methods": [],
            }],
            "interfaces": [],
            "enums": [],
            "associations": [],
        }
        result = json.loads(d.dispatch("draft_design", {"design": design}))
        assert result["valid"] is True
        assert d.draft_design is not None
        assert "Widget" in str(d.draft_lookup)

    def test_unknown_tool_returns_error(self):
        from backend.ticketing_agent.tools.design_verify import CombinedDispatcher
        d = CombinedDispatcher(prior_class_lookup={})
        result = json.loads(d.dispatch("nonexistent_tool", {}))
        assert "error" in result
