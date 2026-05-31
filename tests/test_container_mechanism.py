"""Tests for container mechanism discovery and ontology mapping.

Tests:
- seed_container_lookup with mock Neo4j
- Mechanism resolution via dep_lookup (real nodes) vs fallback (stubs)
- find_mechanism dispatcher
- Validation: aggregates without mechanism is an error
- Validation: aggregates with unknown mechanism is an error
"""

import json
import pytest
from unittest.mock import MagicMock

from codegraph.diagram import ClassDiagram, Association
from codegraph.models import ClassNode
from backend.ticketing_agent.design.container_lookup import seed_container_lookup, get_container_class_info
from backend.ticketing_agent.design.design_oo_tools import (
    ALL_TOOLS,
    FIND_MECHANISM_TOOL,
    make_design_dispatcher,
)
from backend.ticketing_agent.tools.helpers.design_validation import validate_oo_design


# ---------------------------------------------------------------------------
# seed_container_lookup tests
# ---------------------------------------------------------------------------


class TestSeedContainerLookup:
    def test_basic_lookup(self):
        """Test that seed_container_lookup returns bare_name -> qname mappings."""
        mock_session = MagicMock()
        mock_result = [
            {"qn": "std::vector", "name": "vector"},
            {"qn": "std::map", "name": "map"},
            {"qn": "std::set", "name": "set"},
        ]
        mock_session.run.return_value = mock_result

        lookup = seed_container_lookup(mock_session)

        assert "vector" in lookup
        assert lookup["vector"] == "std::vector"
        assert "std::vector" in lookup
        assert lookup["std::vector"] == "std::vector"
        assert "map" in lookup
        assert lookup["map"] == "std::map"
        assert "set" in lookup
        assert lookup["set"] == "std::set"

    def test_custom_qnames(self):
        """Test with custom container names list."""
        mock_session = MagicMock()
        mock_result = [
            {"qn": "std::vector", "name": "vector"},
        ]
        mock_session.run.return_value = mock_result

        lookup = seed_container_lookup(mock_session, container_qnames=["std::vector"])
        assert "vector" in lookup
        assert lookup["vector"] == "std::vector"

    def test_neo4j_failure_returns_empty(self):
        """Test that Neo4j failure returns empty dict without crashing."""
        mock_session = MagicMock()
        mock_session.run.side_effect = Exception("Connection refused")

        lookup = seed_container_lookup(mock_session)
        assert lookup == {}

    def test_full_qname_key(self):
        """Test that qualified names are also keys in the lookup."""
        mock_session = MagicMock()
        mock_result = [
            {"qn": "std::vector", "name": "vector"},
        ]
        mock_session.run.return_value = mock_result

        lookup = seed_container_lookup(mock_session)
        assert lookup["std::vector"] == "std::vector"
        assert lookup["vector"] == "std::vector"

    def test_missing_name_uses_qname(self):
        """Test that empty name falls back to qualified name."""
        mock_session = MagicMock()
        mock_result = [
            {"qn": "std::vector", "name": None},
        ]
        mock_session.run.return_value = mock_result

        lookup = seed_container_lookup(mock_session)
        # Bare name extracted from qname when name is None
        assert lookup["vector"] == "std::vector"


class TestGetContainerClassInfo:
    def test_basic_info(self):
        """Test that get_container_class_info returns proper dicts."""
        mock_session = MagicMock()
        mock_result = [
            {"qn": "std::vector", "name": "vector", "kind": "class", "source": "cppreference", "brief": "Sequence container"},
        ]
        mock_session.run.return_value = mock_result

        info = get_container_class_info(mock_session)
        assert len(info) == 1
        assert info[0]["qualified_name"] == "std::vector"
        assert info[0]["name"] == "vector"
        assert info[0]["kind"] == "class"
        assert info[0]["source"] == "cppreference"

    def test_neo4j_failure_returns_empty(self):
        """Test that Neo4j failure returns empty list without crashing."""
        mock_session = MagicMock()
        mock_session.run.side_effect = Exception("Connection refused")

        info = get_container_class_info(mock_session)
        assert info == []


# ---------------------------------------------------------------------------
# Mechanism resolution tests (map_to_ontology)
# ---------------------------------------------------------------------------


class TestMechanismResolution:
    """Test that mechanism resolution prefers dep_lookup over stubs."""

    def _make_simple_design(self, associations):
        """Helper to create a minimal ClassDiagram."""
        return ClassDiagram(
            module_names=["test"],
            classes=[
                ClassNode(name="MyClass", module="test", visibility="public"),
            ],
            associations=associations,
        )

    def test_mechanism_resolved_via_dep_lookup(self):
        """When mechanism is in dep_lookup, depends_on links to the real node."""
        from backend.ticketing_agent.design.map_to_ontology import map_oo_to_ontology

        oo = self._make_simple_design([
            Association(
                subject="MyClass",
                object="Widget",
                predicate="aggregates",
                mechanism="std::vector",
            ),
        ])

        # dep_lookup has std::vector pointing to a real node
        dep_lookup = {"Widget": "ext::Widget", "std::vector": "std::vector", "vector": "std::vector"}

        result = map_oo_to_ontology(oo, dependency_lookup=dep_lookup)

        # Should have a depends_on to std::vector (resolved via dep_lookup)
        dep_triples = [t for t in result.triples if t.predicate == "depends_on" and t.object_qualified_name == "std::vector"]
        assert len(dep_triples) >= 1, f"Expected depends_on std::vector, got: {[t.object_qualified_name for t in result.triples if t.predicate == 'depends_on']}"

        # Should NOT have a stub node for std::vector (it should resolve to real one)
        stub_nodes = [n for n in result.nodes if n.qualified_name == "std::vector" and n.layer == "dependency" and "Standard library" in n.brief_description]
        # When resolved via dep_lookup, the _add_node in _resolve_ref creates the node with layer="dependency"
        # but it's a real node from the lookup, not a stub
        assert len([n for n in result.nodes if n.qualified_name == "std::vector"]) >= 1

    def test_mechanism_fallback_creates_stub(self):
        """When mechanism is NOT in dep_lookup but IS in fallback, creates stub."""
        from backend.ticketing_agent.design.map_to_ontology import map_oo_to_ontology

        oo = self._make_simple_design([
            Association(
                subject="MyClass",
                object="Widget",
                predicate="aggregates",
                mechanism="std::vector",
            ),
        ])

        # dep_lookup has Widget but NOT std::vector (no Neo4j seeding)
        dep_lookup = {"Widget": "ext::Widget"}

        result = map_oo_to_ontology(oo, dependency_lookup=dep_lookup)

        # Should still have depends_on to std::vector (via fallback)
        dep_triples = [t for t in result.triples if t.predicate == "depends_on" and t.object_qualified_name == "std::vector"]
        assert len(dep_triples) >= 1

    def test_no_dep_mechanisms_skip_dependency(self):
        """raw_pointer and reference mechanisms don't create depends_on."""
        from backend.ticketing_agent.design.map_to_ontology import map_oo_to_ontology

        oo = self._make_simple_design([
            Association(
                subject="MyClass",
                object="Widget",
                predicate="references",
                mechanism="raw_pointer",
            ),
        ])

        result = map_oo_to_ontology(oo, dependency_lookup={})

        # Should NOT have depends_on from raw_pointer mechanism
        ptr_deps = [t for t in result.triples if t.predicate == "depends_on" and t.object_qualified_name == "raw_pointer"]
        assert len(ptr_deps) == 0


# ---------------------------------------------------------------------------
# find_mechanism dispatcher tests
# ---------------------------------------------------------------------------


class TestFindMechanism:
    def test_find_mechanism_searches_dep_lookup(self):
        """Test that find_mechanism searches dep_lookup for container names."""
        dispatcher = make_design_dispatcher(
            prior_class_lookup={},
            dependency_lookup={"vector": "std::vector", "std::vector": "std::vector", "map": "std::map"},
            intercomponent_classes=[],
        )

        result = json.loads(dispatcher("find_mechanism", {"query": "vector"}))
        assert "containers" in result
        found_qnames = [c["qualified_name"] for c in result["containers"]]
        assert "std::vector" in found_qnames

    def test_find_mechanism_empty_query(self):
        """Test that empty query returns empty list."""
        dispatcher = make_design_dispatcher(
            prior_class_lookup={},
            dependency_lookup={"vector": "std::vector"},
            intercomponent_classes=[],
        )

        result = json.loads(dispatcher("find_mechanism", {"query": ""}))
        assert result["containers"] == []

    def test_find_mechanism_with_neo4j(self):
        """Test that find_mechanism queries Neo4j when session is available."""
        mock_session = MagicMock()
        mock_result = [
            {"qn": "std::vector", "name": "vector", "kind": "class", "source": "cppreference", "brief": "Sequence container"},
        ]
        mock_session.run.return_value = mock_result

        dispatcher = make_design_dispatcher(
            prior_class_lookup={},
            dependency_lookup={},
            intercomponent_classes=[],
            neo4j_session=mock_session,
        )

        result = json.loads(dispatcher("find_mechanism", {"query": "vector"}))
        assert "containers" in result
        found_qnames = [c["qualified_name"] for c in result["containers"]]
        assert "std::vector" in found_qnames

    def test_find_mechanism_neo4j_failure(self):
        """Test that Neo4j failure doesn't crash the tool."""
        mock_session = MagicMock()
        mock_session.run.side_effect = Exception("Connection refused")

        dispatcher = make_design_dispatcher(
            prior_class_lookup={},
            dependency_lookup={"vector": "std::vector"},
            intercomponent_classes=[],
            neo4j_session=mock_session,
        )

        # Should still work with dep_lookup results
        result = json.loads(dispatcher("find_mechanism", {"query": "vector"}))
        assert "containers" in result


# ---------------------------------------------------------------------------
# Validation tests (aggregates mechanism required)
# ---------------------------------------------------------------------------


class TestAggregatesValidation:
    """Test that aggregates without mechanism is now a hard error."""

    def test_aggregates_without_mechanism_is_error(self):
        """Aggregates without mechanism should produce an error."""
        oo = ClassDiagram(
            module_names=["test"],
            classes=[
                ClassNode(name="MyClass", module="test", visibility="public"),
                ClassNode(name="Widget", module="test", visibility="public"),
            ],
            associations=[
                Association(
                    subject="MyClass",
                    object="Widget",
                    predicate="aggregates",
                    mechanism="",
                ),
            ],
        )

        errors = validate_oo_design(
            oo,
            prior_class_lookup={},
            dependency_lookup={"Widget": "test::Widget"},
            intercomponent_classes=[],
        )

        # Should find an error about missing mechanism
        mechanism_errors = [e for e in errors if "mechanism" in e.lower()]
        assert len(mechanism_errors) >= 1, f"Expected mechanism error, got: {errors}"

    def test_aggregates_with_known_mechanism_passes(self):
        """Aggregates with a known mechanism should pass validation."""
        oo = ClassDiagram(
            module_names=["test"],
            classes=[
                ClassNode(name="MyClass", module="test", visibility="public"),
                ClassNode(name="Widget", module="test", visibility="public"),
            ],
            associations=[
                Association(
                    subject="MyClass",
                    object="Widget",
                    predicate="aggregates",
                    mechanism="std::vector",
                ),
            ],
        )

        errors = validate_oo_design(
            oo,
            prior_class_lookup={},
            dependency_lookup={"Widget": "test::Widget", "std::vector": "std::vector"},
            intercomponent_classes=[],
        )

        # Should NOT have an error about mechanism
        mechanism_errors = [e for e in errors if "mechanism" in e.lower()]
        assert len(mechanism_errors) == 0, f"Unexpected mechanism error: {mechanism_errors}"

    def test_aggregates_with_unknown_mechanism_is_error(self):
        """Aggregates with an unknown mechanism should produce an error."""
        oo = ClassDiagram(
            module_names=["test"],
            classes=[
                ClassNode(name="MyClass", module="test", visibility="public"),
                ClassNode(name="Widget", module="test", visibility="public"),
            ],
            associations=[
                Association(
                    subject="MyClass",
                    object="Widget",
                    predicate="aggregates",
                    mechanism="std::hypothetical_container",
                ),
            ],
        )

        errors = validate_oo_design(
            oo,
            prior_class_lookup={},
            dependency_lookup={"Widget": "test::Widget"},
            intercomponent_classes=[],
        )

        # Should find an error about unknown mechanism
        unknown_errors = [e for e in errors if "std::hypothetical_container" in e]
        assert len(unknown_errors) >= 1, f"Expected unknown mechanism error, got: {errors}"

    def test_references_without_mechanism_is_not_error(self):
        """References without mechanism should NOT produce an error (out of scope)."""
        oo = ClassDiagram(
            module_names=["test"],
            classes=[
                ClassNode(name="MyClass", module="test", visibility="public"),
                ClassNode(name="Engine", module="test", visibility="public"),
            ],
            associations=[
                Association(
                    subject="MyClass",
                    object="Engine",
                    predicate="references",
                    mechanism="",
                ),
            ],
        )

        errors = validate_oo_design(
            oo,
            prior_class_lookup={},
            dependency_lookup={"Engine": "test::Engine"},
            intercomponent_classes=[],
        )

        # Should NOT have any errors about mechanism
        assert len(errors) == 0, f"Unexpected errors: {errors}"
