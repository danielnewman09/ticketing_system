"""Tests for verify_llr tool dispatcher and schemas."""

import json
import pytest
from unittest.mock import MagicMock
from backend.ticketing_agent.verify.verify_llr_tools import (
    VALIDATE_QNAMES_TOOL,
    LOOKUP_DESIGN_ELEMENT_TOOL,
    PRODUCE_VERIFICATIONS_TOOL,
    ALL_TOOLS,
    make_verify_dispatcher,
)


class TestToolSchemas:
    def test_all_tools_present(self):
        assert len(ALL_TOOLS) == 3
        names = {t["name"] for t in ALL_TOOLS}
        assert names == {"validate_qualified_names", "lookup_design_element", "produce_verifications"}

    def test_validate_qnames_schema(self):
        assert VALIDATE_QNAMES_TOOL["name"] == "validate_qualified_names"
        props = VALIDATE_QNAMES_TOOL["input_schema"]["properties"]
        assert "qualified_names" in props
        assert props["qualified_names"]["type"] == "array"

    def test_lookup_design_element_schema(self):
        assert LOOKUP_DESIGN_ELEMENT_TOOL["name"] == "lookup_design_element"
        props = LOOKUP_DESIGN_ELEMENT_TOOL["input_schema"]["properties"]
        assert "name" in props
        assert "kind" in props

    def test_produce_verifications_schema(self):
        assert PRODUCE_VERIFICATIONS_TOOL["name"] == "produce_verifications"
        props = PRODUCE_VERIFICATIONS_TOOL["input_schema"]["properties"]
        assert "verifications" in props


class TestValidateQualifiedNames:
    def test_valid_qnames_pass(self):
        dispatcher = make_verify_dispatcher(neo4j_session=None)
        result = json.loads(dispatcher("validate_qualified_names", {
            "qualified_names": ["calc::Engine::run", "user_interface::Display::show"]
        }))
        assert len(result["results"]) == 2
        assert result["results"][0]["valid"] is True
        assert result["results"][1]["valid"] is True

    def test_test_prefix_flagged(self):
        dispatcher = make_verify_dispatcher(neo4j_session=None)
        result = json.loads(dispatcher("validate_qualified_names", {
            "qualified_names": ["test_validate_input"]
        }))
        assert result["results"][0]["valid"] is False
        assert "test_" in result["results"][0]["error"]

    def test_result_of_prefix_flagged(self):
        dispatcher = make_verify_dispatcher(neo4j_session=None)
        result = json.loads(dispatcher("validate_qualified_names", {
            "qualified_names": ["result_of_call"]
        }))
        assert result["results"][0]["valid"] is False

    def test_dot_separator_flagged_with_correction(self):
        dispatcher = make_verify_dispatcher(neo4j_session=None)
        result = json.loads(dispatcher("validate_qualified_names", {
            "qualified_names": ["calc.Engine.run"]
        }))
        assert result["results"][0]["valid"] is True  # auto-correctable
        assert result["results"][0]["correction"] == "calc::Engine::run"

    def test_bare_lowercase_flagged(self):
        dispatcher = make_verify_dispatcher(neo4j_session=None)
        result = json.loads(dispatcher("validate_qualified_names", {
            "qualified_names": ["somevar"]
        }))
        assert result["results"][0]["valid"] is False

    def test_empty_list(self):
        dispatcher = make_verify_dispatcher(neo4j_session=None)
        result = json.loads(dispatcher("validate_qualified_names", {
            "qualified_names": []
        }))
        assert result["results"] == []

    def test_neo4j_resolution(self):
        mock_session = MagicMock()
        # Simulate: calc::Engine::run resolves (member of class)
        # First call for "calc::Engine::run" -> count=0 (method node doesn't exist)
        # Second call for "calc::Engine" -> count=1 (class exists)
        call_count = {"n": 0}
        def mock_run(query, params):
            qn = params.get("qn", "")
            call_count["n"] += 1
            # Engine class exists, but Engine::run method doesn't
            if qn == "calc::Engine":
                return MagicMock(single=MagicMock(return_value={"cnt": 1}))
            return MagicMock(single=MagicMock(return_value={"cnt": 0}))

        mock_session.run = mock_run
        dispatcher = make_verify_dispatcher(neo4j_session=mock_session)
        result = json.loads(dispatcher("validate_qualified_names", {
            "qualified_names": ["calc::Engine::run"]
        }))
        assert result["results"][0]["exists"] is True

    def test_unknown_tool_returns_error(self):
        dispatcher = make_verify_dispatcher(neo4j_session=None)
        result = json.loads(dispatcher("unknown_tool", {}))
        assert "error" in result


class TestLookupDesignElement:
    def test_no_session_returns_empty(self):
        dispatcher = make_verify_dispatcher(neo4j_session=None)
        result = json.loads(dispatcher("lookup_design_element", {
            "name": "Calculator",
        }))
        assert result["elements"] == []

    def test_unknown_tool_returns_error_lookup(self):
        dispatcher = make_verify_dispatcher(neo4j_session=None)
        result = json.loads(dispatcher("lookup_design_element", {
            "name": "Calculator",
        }))
        # With no session, it returns empty (not error) for lookup_design_element
        assert "elements" in result
