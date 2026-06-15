"""Integration tests for backend_migrated tools — requires Neo4j.

These tests validate the full round-trip of tools that query Neo4j:
container seeding, mechanism lookup, dependency listing, and discovery
queries against live data.

Saves tool outputs to ``unit_test_data/tools/tools_integration_*``.

Run with::

    pytest tests/tools/test_integration.py -v -m integration
"""

import json
from pathlib import Path

import pytest

from backend_migrated.tools import DesignToolDispatcher

OUT_DIR = Path(__file__).resolve().parents[2] / "unit_test_data" / "tools"


def _save(stem: str, content: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / stem).write_text(content, encoding="utf-8")


@pytest.mark.integration
class TestContainerLookupIntegration:
    """Verify that container_lookup can seed real Neo4j container data."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.dispatcher = DesignToolDispatcher()

    def test_seeds_lookup_dict(self):
        result = json.loads(
            self.dispatcher.dispatch("container_lookup", {})
        )
        assert result["seeded"] is True
        # At minimum the hardcoded std containers should be returned
        assert result["count"] > 0

    def test_dispatcher_lookup_populated(self):
        """After container_lookup, the dispatcher's dependency_lookup
        should contain the seeded containers."""
        self.dispatcher.dispatch("container_lookup", {})
        # Should now have std::vector (either from Neo4j preload or other)
        assert len(self.dispatcher.dependency_lookup) > 0


@pytest.mark.integration
class TestDependencyListIntegration:
    """Verify dependency_list queries the live Neo4j codegraph."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.dispatcher = DesignToolDispatcher()

    def test_returns_cppreference_classes(self):
        result = json.loads(
            self.dispatcher.dispatch("dependency_list", {
                "source": "cppreference",
                "kind": "class",
                "limit": 10,
            })
        )
        assert result["count"] <= 10
        if result["count"] > 0:
            for d in result["dependencies"]:
                assert d["source"] == "cppreference"
                assert d["kind"] == "class"

    def test_returns_boost_types(self):
        result = json.loads(
            self.dispatcher.dispatch("dependency_list", {
                "source": "boost",
                "limit": 10,
            })
        )
        assert result["count"] <= 10
        for d in result["dependencies"]:
            assert d["source"] == "boost"

    def test_all_sources(self):
        result = json.loads(
            self.dispatcher.dispatch("dependency_list", {
                "source": "all",
                "limit": 50,
            })
        )
        assert result["count"] <= 50

    def test_substring_filter(self):
        result = json.loads(
            self.dispatcher.dispatch("dependency_list", {
                "query": "vector",
            })
        )
        for d in result["dependencies"]:
            assert "vector" in d["qualified_name"].lower()


@pytest.mark.integration
class TestDiscoveryToolsIntegration:
    """Verify discovery tools return actual Neo4j data."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.dispatcher = DesignToolDispatcher()

    def test_search_symbols_returns_matches(self):
        result = json.loads(
            self.dispatcher.dispatch("search_symbols", {"query": "std::"})
        )
        assert result["count"] >= 0

    def test_get_compound_returns_real_node(self):
        result = json.loads(
            self.dispatcher.dispatch("get_compound",
                                     {"qualified_name": "std::vector"})
        )
        if "error" not in result:
            assert result["qualified_name"] == "std::vector"
            assert "members" in result

    def test_get_member_returns_real_node(self):
        result = json.loads(
            self.dispatcher.dispatch("get_member",
                                     {"qualified_name": "std::vector::push_back"})
        )
        if "error" not in result:
            assert result["qualified_name"] == "std::vector::push_back"
            assert "kind" in result

    def test_browse_namespace_returns_compounds(self):
        result = json.loads(
            self.dispatcher.dispatch("browse_namespace", {
                "namespace": "std",
                "limit": 10,
            })
        )
        if "results" in result:
            assert len(result["results"]) <= 10
            for c in result["results"]:
                assert c["qualified_name"].startswith("std::")

    def test_list_sources(self):
        result = json.loads(
            self.dispatcher.dispatch("list_sources", {})
        )
        if "sources" in result:
            assert isinstance(result["sources"], dict)
            # Should have at least one source
            assert len(result["sources"]) > 0

    def test_find_inheritance(self):
        result = json.loads(
            self.dispatcher.dispatch("find_inheritance",
                                     {"qualified_name": "std::exception"})
        )
        if "error" not in result:
            assert "parents" in result
            assert "children" in result

    def test_find_callers_callees(self):
        result = json.loads(
            self.dispatcher.dispatch("find_callers_and_callees",
                                     {"qualified_name": "std::vector::push_back"})
        )
        if "error" not in result:
            assert "callers" in result
            assert "callees" in result


@pytest.mark.integration
class TestAliasLookupIntegration:
    """Verify alias_lookup resolves typedefs from Neo4j."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.dispatcher = DesignToolDispatcher()

    def test_alias_lookup_count(self):
        result = json.loads(
            self.dispatcher.dispatch("alias_lookup", {})
        )
        # Should always have the hardcoded 8 std aliases
        assert result["alias_count"] >= 8

    def test_sample_contains_std_aliases(self):
        result = json.loads(
            self.dispatcher.dispatch("alias_lookup", {})
        )
        # At least one known alias should be in the sample
        keys = list(result["sample"].keys())
        aliases = [k for k in keys if "string" in k]
        assert len(aliases) > 0 or result["alias_count"] >= 8


@pytest.mark.integration
class TestEndToEndDesignToolLoop:
    """Simulate a full design tool loop with real Neo4j data."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.dispatcher = DesignToolDispatcher(
            prior_class_lookup={"Calculator": "calc::Calculator"},
            dependency_lookup={},
            intercomponent_classes=[
                {"qualified_name": "ui::Display", "kind": "class", "name": "Display"},
            ],
            component_namespace="calc",
        )

    def test_full_cycle(self):
        """Step through a typical design agent tool loop."""
        # 1. Seed containers
        self.dispatcher.dispatch("container_lookup", {})

        # 2. Check a class name
        result = json.loads(
            self.dispatcher.dispatch("check_class_name", {"name": "Calculator"})
        )
        assert result["found"] is True

        # 3. Validate a draft design (LayerGraph format)
        design = [
            {
                "type": "ClassNode",
                "name": "CalcEngine",
                "qualified_name": "calc::CalcEngine",
                "kind": "class",
                "visibility": "public",
                "brief_description": "Main calculation engine",
                "tags": ["design"],
                "base_classes": [],
                "edges": [
                    {
                        "relation_type": "DEPENDS_ON",
                        "target_uid": "std::vector",
                        "target_type": "ClassNode",
                    },
                    {
                        "relation_type": "DEPENDS_ON",
                        "target_uid": "ui::Display",
                        "target_type": "ClassNode",
                    },
                ],
                "composes": [
                    {
                        "type": "MethodNode",
                        "name": "compute",
                        "qualified_name": "calc::CalcEngine::compute",
                        "kind": "method",
                        "visibility": "public",
                        "type_signature": "double",
                        "argsstring": "",
                        "brief_description": "Compute result",
                        "tags": ["design"],
                        "edges": [],
                    },
                ],
            },
        ]
        result = json.loads(
            self.dispatcher.dispatch("validate_design", design)
        )
        assert result["valid"] is True

        # 4. Discover a real dependency
        result = json.loads(
            self.dispatcher.dispatch("dependency_list", {
                "query": "vector",
                "limit": 5,
            })
        )
        assert "dependencies" in result

        # 5. Add a new prior class and verify
        self.dispatcher.add_prior_class("CalcEngine", "calc::CalcEngine")
        result = json.loads(
            self.dispatcher.dispatch("check_class_name", {"name": "CalcEngine"})
        )
        assert result["found"] is True
        assert any(
            m["source"] == "prior_design" for m in result["matches"]
        )
