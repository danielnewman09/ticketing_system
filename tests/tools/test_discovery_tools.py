"""Tests for discovery_tools — search_symbols, get_compound, get_member,
browse_namespace, list_sources, find_inheritance, find_callers_and_callees.

Saves tool outputs to ``unit_test_data/tools_*`` for visual inspection.
"""

import json
from pathlib import Path

import pytest

from codegraph.tools import CodeGraphDispatcher

OUT_DIR = Path(__file__).resolve().parents[2] / "unit_test_data" / "tools"


def _save(stem: str, content: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / stem).write_text(content, encoding="utf-8")


@pytest.fixture
def dispatcher():
    return CodeGraphDispatcher()


# ══════════════════════════════════════════════════════════════════════════
# search_symbols
# ══════════════════════════════════════════════════════════════════════════


class TestSearchSymbols:
    def test_returns_results_and_count(self, dispatcher):
        raw = dispatcher.dispatch("search_symbols", {"query": "vector"})
        result = json.loads(raw)
        _save("tools_search_symbols.json", raw)
        assert "results" in result
        assert "count" in result
        assert isinstance(result["results"], list)
        assert isinstance(result["count"], int)

    def test_optional_source_filter(self, dispatcher):
        raw = dispatcher.dispatch("search_symbols", {
            "query": "vector", "source": "cppreference",
        })
        result = json.loads(raw)
        _save("tools_search_symbols_source.json", raw)
        assert "results" in result

    def test_optional_kind_filter(self, dispatcher):
        raw = dispatcher.dispatch("search_symbols", {
            "query": "vector", "kind": "class",
        })
        result = json.loads(raw)
        _save("tools_search_symbols_kind.json", raw)
        assert "results" in result

    def test_custom_limit(self, dispatcher):
        raw = dispatcher.dispatch("search_symbols", {"query": "a", "limit": 5})
        result = json.loads(raw)
        _save("tools_search_symbols_limit.json", raw)
        assert len(result["results"]) <= 5

    def test_empty_query_returns_gracefully(self, dispatcher):
        raw = dispatcher.dispatch("search_symbols", {"query": ""})
        result = json.loads(raw)
        _save("tools_search_symbols_empty.json", raw)
        assert "results" in result


# ══════════════════════════════════════════════════════════════════════════
# get_compound
# ══════════════════════════════════════════════════════════════════════════


class TestGetCompound:
    def test_missing_qname_returns_error(self, dispatcher):
        raw = dispatcher.dispatch("get_compound", {})
        result = json.loads(raw)
        _save("tools_get_compound_error.json", raw)
        assert "error" in result

    def test_returns_structured_result(self, dispatcher):
        raw = dispatcher.dispatch("get_compound", {"qualified_name": "std::vector"})
        result = json.loads(raw)
        _save("tools_get_compound.json", raw)
        assert isinstance(result, dict)

    def test_result_or_error_has_keys(self, dispatcher):
        raw = dispatcher.dispatch("get_compound",
                                  {"qualified_name": "nonexistent::Foo"})
        result = json.loads(raw)
        _save("tools_get_compound_missing.json", raw)
        assert "error" in result or "qualified_name" in result


# ══════════════════════════════════════════════════════════════════════════
# get_member
# ══════════════════════════════════════════════════════════════════════════


class TestGetMember:
    def test_missing_qname_returns_error(self, dispatcher):
        raw = dispatcher.dispatch("get_member", {})
        result = json.loads(raw)
        _save("tools_get_member_error.json", raw)
        assert "error" in result

    def test_returns_structured_result(self, dispatcher):
        raw = dispatcher.dispatch("get_member",
                                  {"qualified_name": "std::vector::push_back"})
        result = json.loads(raw)
        _save("tools_get_member.json", raw)
        assert isinstance(result, dict)
        assert "error" in result or "qualified_name" in result


# ══════════════════════════════════════════════════════════════════════════
# browse_namespace
# ══════════════════════════════════════════════════════════════════════════


class TestBrowseNamespace:
    def test_missing_namespace_returns_error(self, dispatcher):
        raw = dispatcher.dispatch("browse_namespace", {})
        result = json.loads(raw)
        _save("tools_browse_namespace_error.json", raw)
        assert "error" in result

    def test_returns_results_and_count(self, dispatcher):
        raw = dispatcher.dispatch("browse_namespace", {"namespace": "std"})
        result = json.loads(raw)
        _save("tools_browse_namespace.json", raw)
        if "error" not in result:
            assert "results" in result
            assert "count" in result

    def test_custom_limit(self, dispatcher):
        raw = dispatcher.dispatch("browse_namespace", {
            "namespace": "std", "limit": 5,
        })
        result = json.loads(raw)
        _save("tools_browse_namespace_limit.json", raw)
        if "results" in result:
            assert len(result["results"]) <= 5


# ══════════════════════════════════════════════════════════════════════════
# list_sources
# ══════════════════════════════════════════════════════════════════════════


class TestListSources:
    def test_no_input_required(self, dispatcher):
        raw = dispatcher.dispatch("list_sources", {})
        result = json.loads(raw)
        _save("tools_list_sources.json", raw)
        assert isinstance(result, dict)
        assert "sources" in result or "error" in result

    def test_sources_is_dict(self, dispatcher):
        raw = dispatcher.dispatch("list_sources", {})
        result = json.loads(raw)
        _save("tools_list_sources_dict.json", raw)
        if "sources" in result:
            assert isinstance(result["sources"], dict)


# ══════════════════════════════════════════════════════════════════════════
# find_inheritance
# ══════════════════════════════════════════════════════════════════════════


class TestFindInheritance:
    def test_missing_qname_returns_error(self, dispatcher):
        raw = dispatcher.dispatch("find_inheritance", {})
        result = json.loads(raw)
        _save("tools_find_inheritance_error.json", raw)
        assert "error" in result

    def test_returns_parents_and_children(self, dispatcher):
        raw = dispatcher.dispatch("find_inheritance",
                                  {"qualified_name": "std::exception"})
        result = json.loads(raw)
        _save("tools_find_inheritance.json", raw)
        if "error" not in result:
            assert "parents" in result
            assert "children" in result
            assert isinstance(result["parents"], list)
            assert isinstance(result["children"], list)


# ══════════════════════════════════════════════════════════════════════════
# find_callers_and_callees
# ══════════════════════════════════════════════════════════════════════════


class TestFindCallersAndCallees:
    def test_missing_qname_returns_error(self, dispatcher):
        raw = dispatcher.dispatch("find_callers_and_callees", {})
        result = json.loads(raw)
        _save("tools_find_callers_callees_error.json", raw)
        assert "error" in result

    def test_returns_callers_and_callees(self, dispatcher):
        raw = dispatcher.dispatch("find_callers_and_callees",
                                  {"qualified_name": "std::vector::push_back"})
        result = json.loads(raw)
        _save("tools_find_callers_callees.json", raw)
        if "error" not in result:
            assert "callees" in result
            assert "callers" in result
            assert isinstance(result["callees"], list)
            assert isinstance(result["callers"], list)


# ══════════════════════════════════════════════════════════════════════════
# Error recovery — all tools must return valid JSON without Neo4j
# ══════════════════════════════════════════════════════════════════════════


class TestDiscoveryErrorRecovery:
    TOOLS_AND_INPUTS = [
        ("search_symbols", {"query": "test"}),
        ("get_compound", {"qualified_name": "test::Foo"}),
        ("get_member", {"qualified_name": "test::Foo::bar"}),
        ("browse_namespace", {"namespace": "test"}),
        ("list_sources", {}),
        ("find_inheritance", {"qualified_name": "test::Foo"}),
        ("find_callers_and_callees", {"qualified_name": "test::Foo::bar"}),
    ]

    @pytest.mark.parametrize("tool_name,tool_input", TOOLS_AND_INPUTS)
    def test_tool_returns_valid_json(self, dispatcher, tool_name, tool_input):
        raw = dispatcher.dispatch(tool_name, tool_input)
        parsed = json.loads(raw)
        _save(f"tools_error_recovery_{tool_name}.json", raw)
        assert isinstance(parsed, dict)

    @pytest.mark.parametrize("tool_name,tool_input", TOOLS_AND_INPUTS)
    def test_tool_has_expected_structure(self, dispatcher, tool_name, tool_input):
        raw = dispatcher.dispatch(tool_name, tool_input)
        result = json.loads(raw)
        _save(f"tools_error_recovery_{tool_name}_struct.json", raw)
        assert isinstance(result, dict)
        assert len(result) > 0
