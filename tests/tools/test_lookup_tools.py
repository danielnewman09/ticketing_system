"""Tests for lookup_tools — container_lookup, alias_lookup,
get_container_info, dependency_list.

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
    """Dispatcher with default dependency lookup."""
    return CodeGraphDispatcher()


@pytest.fixture
def dispatcher_with_deps():
    """Dispatcher with pre-seeded dependency lookup (via DesignToolDispatcher)."""
    from backend_migrated.tools import DesignToolDispatcher
    return DesignToolDispatcher(
        dependency_lookup={
            "std::vector": "std::vector",
            "std::map": "std::map",
        },
    )


# ══════════════════════════════════════════════════════════════════════════
# container_lookup
# ══════════════════════════════════════════════════════════════════════════


class TestContainerLookup:
    def test_seeds_dispatcher_lookup(self, dispatcher):
        raw = dispatcher.dispatch("container_lookup", {})
        result = json.loads(raw)
        _save("tools_container_lookup.json", raw)
        assert "seeded" in result
        assert "containers" in result
        assert isinstance(result["count"], int)

    def test_custom_container_names(self, dispatcher):
        raw = dispatcher.dispatch("container_lookup", {
            "container_names": ["std::vector", "std::map"],
        })
        result = json.loads(raw)
        _save("tools_container_lookup_custom.json", raw)
        assert result["seeded"] is True

    def test_result_structure(self, dispatcher):
        raw = dispatcher.dispatch("container_lookup", {})
        result = json.loads(raw)
        _save("tools_container_lookup_structure.json", raw)
        for c in result["containers"]:
            assert "qualified_name" in c
            assert "name" in c


# ══════════════════════════════════════════════════════════════════════════
# alias_lookup
# ══════════════════════════════════════════════════════════════════════════


class TestAliasLookup:
    def test_returns_alias_count(self, dispatcher):
        raw = dispatcher.dispatch("alias_lookup", {})
        result = json.loads(raw)
        _save("tools_alias_lookup.json", raw)
        assert "alias_count" in result
        assert isinstance(result["alias_count"], int)

    def test_returns_sample(self, dispatcher):
        raw = dispatcher.dispatch("alias_lookup", {})
        result = json.loads(raw)
        _save("tools_alias_lookup_sample.json", raw)
        assert "sample" in result
        assert isinstance(result["sample"], dict)

    def test_hardcoded_aliases_included(self, dispatcher):
        raw = dispatcher.dispatch("alias_lookup", {})
        result = json.loads(raw)
        _save("tools_alias_lookup_hardcoded.json", raw)
        assert result["alias_count"] >= 8


# ══════════════════════════════════════════════════════════════════════════
# get_container_info
# ══════════════════════════════════════════════════════════════════════════


class TestGetContainerInfo:
    def test_returns_containers_list(self, dispatcher):
        raw = dispatcher.dispatch("get_container_info", {})
        result = json.loads(raw)
        _save("tools_get_container_info.json", raw)
        assert "containers" in result
        assert isinstance(result["containers"], list)

    def test_custom_container_names(self, dispatcher):
        raw = dispatcher.dispatch("get_container_info", {
            "container_names": ["std::vector"],
        })
        result = json.loads(raw)
        _save("tools_get_container_info_custom.json", raw)
        assert isinstance(result["containers"], list)

    def test_result_fields(self, dispatcher):
        raw = dispatcher.dispatch("get_container_info", {})
        result = json.loads(raw)
        _save("tools_get_container_info_fields.json", raw)
        for c in result["containers"]:
            assert "qualified_name" in c
            assert "name" in c
            assert "kind" in c
            assert "source" in c
            assert "description" in c


# ══════════════════════════════════════════════════════════════════════════
# dependency_list
# ══════════════════════════════════════════════════════════════════════════


class TestDependencyList:
    def test_returns_dependencies_list(self, dispatcher):
        raw = dispatcher.dispatch("dependency_list", {})
        result = json.loads(raw)
        _save("tools_dependency_list.json", raw)
        assert "dependencies" in result
        assert "count" in result
        assert isinstance(result["dependencies"], list)
        assert isinstance(result["count"], int)

    def test_filter_by_source(self, dispatcher):
        raw = dispatcher.dispatch("dependency_list", {"source": "cppreference"})
        result = json.loads(raw)
        _save("tools_dependency_list_source.json", raw)
        assert "dependencies" in result

    def test_filter_by_kind(self, dispatcher):
        raw = dispatcher.dispatch("dependency_list", {"kind": "class"})
        result = json.loads(raw)
        _save("tools_dependency_list_kind.json", raw)
        assert "dependencies" in result

    def test_filter_by_query(self, dispatcher):
        raw = dispatcher.dispatch("dependency_list", {"query": "vector"})
        result = json.loads(raw)
        _save("tools_dependency_list_query.json", raw)
        assert "dependencies" in result

    def test_limit_param(self, dispatcher):
        raw = dispatcher.dispatch("dependency_list", {"limit": 5})
        result = json.loads(raw)
        _save("tools_dependency_list_limit.json", raw)
        assert len(result["dependencies"]) <= 5

    def test_result_fields(self, dispatcher):
        raw = dispatcher.dispatch("dependency_list", {})
        result = json.loads(raw)
        _save("tools_dependency_list_fields.json", raw)
        for d in result["dependencies"]:
            assert "qualified_name" in d
            assert "name" in d
            assert "kind" in d
            assert "source" in d
            assert "description" in d
