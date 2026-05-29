"""Tests for build_alias_lookup in container_lookup."""

from unittest.mock import MagicMock

import pytest


class TestBuildAliasLookup:
    def test_returns_std_string_alias(self):
        from backend.ticketing_agent.design.container_lookup import build_alias_lookup
        mock_session = MagicMock()
        # Simulate that Neo4j has no type_alias members for std::string
        mock_session.run.return_value = []
        result = build_alias_lookup(mock_session)
        # Fallback map should include std::string → std::basic_string
        assert result.get("std::string") == "std::basic_string"
        assert result.get("std::wstring") == "std::basic_string"
        assert result.get("std::string_view") == "std::basic_string_view"

    def test_neo4j_aliases_merge_with_fallback(self):
        from backend.ticketing_agent.design.container_lookup import build_alias_lookup
        mock_session = MagicMock()
        # Simulate Neo4j returning a type_alias for std::string
        mock_session.run.return_value = [
            {"alias_name": "std::string", "qualified_name": "std::basic_string"},
        ]
        result = build_alias_lookup(mock_session)
        # Neo4j result should be present
        assert result.get("std::string") == "std::basic_string"
        # Fallback should still be present for wstring
        assert result.get("std::wstring") == "std::basic_string"

    def test_direct_names_not_in_alias_map(self):
        from backend.ticketing_agent.design.container_lookup import build_alias_lookup
        mock_session = MagicMock()
        mock_session.run.return_value = []
        result = build_alias_lookup(mock_session)
        # std::vector is not an alias — it IS std::vector
        assert "std::vector" not in result