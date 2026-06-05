"""Tests for DesignRepository and codebase graph primitive models."""

import pytest
from pydantic import ValidationError


class TestClassNodeModel:
    """Tests for the CompoundNode Pydantic model."""

    def test_create_minimal(self):
        from codegraph.models import ClassNode

        node = ClassNode(qualified_name="ns::Foo", name="Foo", kind="class")
        assert node.qualified_name == "ns::Foo"
        assert node.name == "Foo"
        assert node.kind == "class"
        assert node.specialization == ""
        assert node.visibility == ""
        assert node.description == ""
        assert node.layer == "design"
        assert node.implementation_status == "designed"

    def test_create_all_fields(self):
        from codegraph.models import ClassNode

        node = ClassNode(
            qualified_name="ns::Foo",
            name="Foo",
            kind="struct",
            layer="as-built",
            specialization="template_class",
            visibility="public",
            brief_description="A struct",
            refid="classns_1_1Foo_1a123",
            type_signature="int(int, int)",
            argsstring="(int x, int y)",
            definition="int Foo::calculate(int x, int y)",
            file_path="src/foo.py",
            line_number=42,
            is_static=True,
            is_const=False,
            is_virtual=False,
            is_abstract=False,
            is_final=False,
            component_id=1,
            is_intercomponent=True,
            implementation_status="implemented",
            source_file="src/foo.cpp",
            test_file="test_foo.cpp",
        )
        assert node.file_path == "src/foo.py"
        assert node.line_number == 42
        assert node.is_static is True
        assert node.component_id == 1
        assert node.layer == "as-built"
        assert node.implementation_status == "implemented"

    def test_defaults_populated(self):
        from codegraph.models import ClassNode

        node = ClassNode(qualified_name="X", name="X", kind="class")
        assert node.layer == "design"
        assert node.implementation_status == "designed"
        assert node.is_intercomponent is False


class TestDesignConstants:
    """Tests for constants (migrated to neo4j.models.constants)."""

    def test_predicate_mapping(self):
        from codegraph.constants import PREDICATE_TO_REL_TYPE
        assert PREDICATE_TO_REL_TYPE["composes"] == "COMPOSES"
        assert PREDICATE_TO_REL_TYPE["depends_on"] == "DEPENDS_ON"
        assert PREDICATE_TO_REL_TYPE["aggregates"] == "AGGREGATES"

    def test_default_predicates(self):
        from codegraph.constants import DEFAULT_PREDICATES
        assert len(DEFAULT_PREDICATES) > 0
        names = [n for n, _ in DEFAULT_PREDICATES]
        assert "composes" in names

    def test_node_kind_values(self):
        from codegraph.constants import NODE_KIND_KEYS
        assert "class" in NODE_KIND_KEYS
        assert "method" in NODE_KIND_KEYS
        assert "namespace" in NODE_KIND_KEYS


# --- Integration tests (skipped unless Neo4j is available) ---
import os
pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_NEO4J_INTEGRATION") != "1",
    reason="Set RUN_NEO4J_INTEGRATION=1 to run Neo4j integration tests",
)


class TestDesignRepositoryIntegration:
    """Integration tests for DesignRepository (require Neo4j)."""

    def test_merge_node_creates_new(self, neo4j_session):
        from codegraph.models import ClassNode
        from backend.db.neo4j.repositories.design import DesignRepository

        repo = DesignRepository(neo4j_session)
        node = ClassNode(qualified_name="test::merge", name="merge", kind="class",
                           layer="design")
        result = repo.merge_node(node)
        assert result.qualified_name == "test::merge"

    def test_merge_node_updates_existing(self, neo4j_session):
        from codegraph.models import ClassNode
        from backend.db.neo4j.repositories.design import DesignRepository

        repo = DesignRepository(neo4j_session)
        node1 = ClassNode(qualified_name="test::update", name="old", kind="class",
                            layer="design")
        repo.merge_node(node1)
        node2 = ClassNode(qualified_name="test::update", name="old", kind="class",
                            layer="design")
        result = repo.merge_node(node2)
        fetched = repo.get_by_qualified_name("test::update")
        assert fetched is not None
        assert fetched.description == "new desc"

    def test_merge_triple_creates_relationship(self, neo4j_session):
        from codegraph.models import ClassNode
        from backend.db.neo4j.repositories.design import DesignRepository

        repo = DesignRepository(neo4j_session)
        repo.merge_node(ClassNode(qualified_name="test::tripleS", name="tripleS", kind="class",
                                     layer="design"))
        repo.merge_node(ClassNode(qualified_name="test::tripleO", name="tripleO", kind="class",
                                     layer="design"))
        repo.merge_triple("test::tripleS", "depends_on", "test::tripleO")
        # Success = no exception

    def test_get_by_qualified_name(self, neo4j_session):
        from codegraph.models import ClassNode
        from backend.db.neo4j.repositories.design import DesignRepository

        repo = DesignRepository(neo4j_session)
        repo.merge_node(ClassNode(qualified_name="test::getMe", name="getMe", kind="class",
                                     layer="design"))
        fetched = repo.get_by_qualified_name("test::getMe")
        assert fetched is not None
        assert fetched.name == "getMe"

    def test_get_by_qualified_name_not_found(self, neo4j_session):
        from backend.db.neo4j.repositories.design import DesignRepository

        repo = DesignRepository(neo4j_session)
        fetched = repo.get_by_qualified_name("does::not::exist")
        assert fetched is None

    def test_find_nodes_by_kind(self, neo4j_session):
        from codegraph.models import ClassNode
        from backend.db.neo4j.repositories.design import DesignRepository

        repo = DesignRepository(neo4j_session)
        repo.merge_node(ClassNode(qualified_name="test::findMe", name="findMe", kind="class",
                                     layer="design"))
        results = repo.find_nodes(kind="class")
        assert len(results) >= 1
        names = [n.qualified_name for n in results]
        assert "test::findMe" in names

    def test_delete_node(self, neo4j_session):
        from codegraph.models import ClassNode
        from backend.db.neo4j.repositories.design import DesignRepository

        repo = DesignRepository(neo4j_session)
        repo.merge_node(ClassNode(qualified_name="test::deleteMe", name="deleteMe", kind="class",
                                     layer="design"))
        result = repo.delete_node("test::deleteMe")
        assert result is True
        assert repo.get_by_qualified_name("test::deleteMe") is None

    def test_skips_dependency_stub_in_merge(self, neo4j_session):
        from codegraph.models import ClassNode
        from backend.db.neo4j.repositories.design import DesignRepository

        repo = DesignRepository(neo4j_session)
        # Dependency-layer nodes are merged normally (no source_type skip anymore)
        node = ClassNode(qualified_name="dep::stub", name="stub", kind="class",
                           layer="dependency", is_intercomponent=True,
                           brief_description="External dependency")
        result = repo.merge_node(node)
        assert result.qualified_name == "dep::stub"

    def test_find_nodes_excludes_layers(self, neo4j_session):
        from codegraph.models import ClassNode
        from backend.db.neo4j.repositories.design import DesignRepository

        repo = DesignRepository(neo4j_session)
        repo.merge_node(ClassNode(qualified_name="test::dep1", name="dep1", kind="class",
                                     layer="dependency", is_intercomponent=True))
        repo.merge_node(ClassNode(qualified_name="test::design1", name="design1", kind="class",
                                     layer="design"))
        results = repo.find_nodes(exclude_layers=["dependency"])
        names = [n.qualified_name for n in results]
        assert "test::dep1" not in names