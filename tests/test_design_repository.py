"""Tests for DesignRepository and design Pydantic models."""

import pytest
from pydantic import ValidationError


class TestDesignNodeModel:
    """Tests for the DesignNode Pydantic model."""

    def test_create_minimal(self):
        from backend.db.neo4j.repositories.models.design import DesignNode

        node = DesignNode(qualified_name="ns::Foo", name="Foo", kind="class")
        assert node.qualified_name == "ns::Foo"
        assert node.name == "Foo"
        assert node.kind == "class"
        assert node.specialization == ""
        assert node.visibility == ""
        assert node.description == ""
        assert node.implementation_status == "designed"

    def test_create_all_fields(self):
        from backend.db.neo4j.repositories.models.design import DesignNode

        node = DesignNode(
            qualified_name="ns::Foo",
            name="Foo",
            kind="method",
            specialization="staticmethod",
            visibility="public",
            description="A method",
            refid="classns_1_1Foo_1a123",
            source_type="member",
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
            is_intercomponent=False,
            implementation_status="implemented",
            source_file="src/foo.py",
            test_file="test_foo.py",
        )
        assert node.file_path == "src/foo.py"
        assert node.line_number == 42
        assert node.is_static is True
        assert node.component_id == 1
        assert node.implementation_status == "implemented"

    def test_defaults_populated(self):
        from backend.db.neo4j.repositories.models.design import DesignNode

        node = DesignNode(qualified_name="X", name="X", kind="class")
        assert node.specialization == ""
        assert node.source_type == ""
        assert node.type_signature == ""
        assert node.file_path == ""
        assert node.line_number is None
        assert node.component_id is None
        assert node.is_static is False
        assert node.implementation_status == "designed"
        assert node.source_file == ""
        assert node.test_file == ""


class TestDesignConstants:
    """Tests for constants moved from ontology models."""

    def test_predicate_mapping(self):
        from backend.db.neo4j.repositories.constants import PREDICATE_TO_REL_TYPE

        assert PREDICATE_TO_REL_TYPE["composes"] == "COMPOSES"
        assert PREDICATE_TO_REL_TYPE["depends_on"] == "DEPENDS_ON"
        assert len(PREDICATE_TO_REL_TYPE) == 7

    def test_default_predicates(self):
        from backend.db.neo4j.repositories.constants import DEFAULT_PREDICATES

        names = {name for name, _ in DEFAULT_PREDICATES}
        assert "composes" in names
        assert "depends_on" in names

    def test_node_kind_values(self):
        from backend.db.neo4j.repositories.constants import NODE_KIND_VALUES

        assert "class" in NODE_KIND_VALUES
        assert "method" in NODE_KIND_VALUES
        assert len(NODE_KIND_VALUES) == 11


import os

# Integration tests require a running Neo4j instance.
# Set RUN_NEO4J_INTEGRATION=1 to enable them.
_integration_skip = pytest.mark.skipif(
    os.environ.get("RUN_NEO4J_INTEGRATION") != "1",
    reason="Set RUN_NEO4J_INTEGRATION=1 to run Neo4j integration tests",
)


@_integration_skip
class TestDesignRepositoryIntegration:
    """Integration tests for DesignRepository against a live Neo4j."""

    @pytest.fixture(autouse=True)
    def cleanup(self):
        from backend.db.neo4j.connection import get_standalone_driver
        driver = get_standalone_driver()
        with driver.session(database="neo4j") as session:
            yield
            session.run("MATCH (n:Design) DETACH DELETE n")
            session.run("MATCH (n:HLR) DETACH DELETE n")
            session.run("MATCH (n:LLR) DETACH DELETE n")
        driver.close()

    def test_merge_node_creates_new(self):
        from backend.db.neo4j.repositories.design import DesignRepository
        from backend.db.neo4j.repositories.models import DesignNode
        from backend.db.neo4j.connection import get_standalone_driver

        driver = get_standalone_driver()
        with driver.session(database="neo4j") as session:
            repo = DesignRepository(session)
            node = DesignNode(qualified_name="calc::Calculator", name="Calculator", kind="class")
            result = repo.merge_node(node)
            assert result.qualified_name == "calc::Calculator"

            record = session.run(
                "MATCH (d:Design {qualified_name: $qn}) RETURN d",
                {"qn": "calc::Calculator"},
            ).single()
            assert record is not None
            assert dict(record["d"])["kind"] == "class"
        driver.close()

    def test_merge_node_updates_existing(self):
        from backend.db.neo4j.repositories.design import DesignRepository
        from backend.db.neo4j.repositories.models import DesignNode
        from backend.db.neo4j.connection import get_standalone_driver

        driver = get_standalone_driver()
        with driver.session(database="neo4j") as session:
            repo = DesignRepository(session)
            node = DesignNode(qualified_name="calc::Calculator", name="Calculator", kind="class")
            repo.merge_node(node)
            node.description = "Updated description"
            repo.merge_node(node)

            record = session.run(
                "MATCH (d:Design {qualified_name: $qn}) RETURN d.description AS desc",
                {"qn": "calc::Calculator"},
            ).single()
            assert record["desc"] == "Updated description"
        driver.close()

    def test_merge_triple_creates_relationship(self):
        from backend.db.neo4j.repositories.design import DesignRepository
        from backend.db.neo4j.repositories.models import DesignNode
        from backend.db.neo4j.connection import get_standalone_driver

        driver = get_standalone_driver()
        with driver.session(database="neo4j") as session:
            repo = DesignRepository(session)
            parent = DesignNode(qualified_name="calc::Calculator", name="Calculator", kind="class")
            child = DesignNode(qualified_name="calc::Calculator.display", name="display", kind="attribute")
            repo.merge_node(parent)
            repo.merge_node(child)
            repo.merge_triple("calc::Calculator", "composes", "calc::Calculator.display")

            record = session.run(
                "MATCH (s:Design {qualified_name: $sqn})-[r:COMPOSES]->(o:Design {qualified_name: $oqn}) RETURN type(r) AS rel_type",
                {"sqn": "calc::Calculator", "oqn": "calc::Calculator.display"},
            ).single()
            assert record is not None
            assert record["rel_type"] == "COMPOSES"
        driver.close()

    def test_get_by_qualified_name(self):
        from backend.db.neo4j.repositories.design import DesignRepository
        from backend.db.neo4j.repositories.models import DesignNode
        from backend.db.neo4j.connection import get_standalone_driver

        driver = get_standalone_driver()
        with driver.session(database="neo4j") as session:
            repo = DesignRepository(session)
            node = DesignNode(qualified_name="calc::Calculator", name="Calculator", kind="class", description="A calculator")
            repo.merge_node(node)
            result = repo.get_by_qualified_name("calc::Calculator")
            assert result is not None
            assert result.name == "Calculator"
            assert result.description == "A calculator"
        driver.close()

    def test_get_by_qualified_name_not_found(self):
        from backend.db.neo4j.repositories.design import DesignRepository
        from backend.db.neo4j.connection import get_standalone_driver

        driver = get_standalone_driver()
        with driver.session(database="neo4j") as session:
            repo = DesignRepository(session)
            result = repo.get_by_qualified_name("nonexistent::Node")
            assert result is None
        driver.close()

    def test_find_nodes_by_kind(self):
        from backend.db.neo4j.repositories.design import DesignRepository
        from backend.db.neo4j.repositories.models import DesignNode
        from backend.db.neo4j.connection import get_standalone_driver

        driver = get_standalone_driver()
        with driver.session(database="neo4j") as session:
            repo = DesignRepository(session)
            repo.merge_node(DesignNode(qualified_name="ns::Foo", name="Foo", kind="class"))
            repo.merge_node(DesignNode(qualified_name="ns::bar", name="bar", kind="method"))
            repo.merge_node(DesignNode(qualified_name="ns::Baz", name="Baz", kind="class"))

            classes = repo.find_nodes(kind="class")
            assert len(classes) == 2
            assert all(n.kind == "class" for n in classes)
        driver.close()

    def test_delete_node(self):
        from backend.db.neo4j.repositories.design import DesignRepository
        from backend.db.neo4j.repositories.models import DesignNode
        from backend.db.neo4j.connection import get_standalone_driver

        driver = get_standalone_driver()
        with driver.session(database="neo4j") as session:
            repo = DesignRepository(session)
            repo.merge_node(DesignNode(qualified_name="ns::ToDelete", name="ToDelete", kind="class"))
            result = repo.delete_node("ns::ToDelete")
            assert result is True

            verify = repo.get_by_qualified_name("ns::ToDelete")
            assert verify is None
        driver.close()

    def test_skips_dependency_stub_in_merge(self):
        from backend.db.neo4j.repositories.design import DesignRepository
        from backend.db.neo4j.repositories.models import DesignNode
        from backend.db.neo4j.connection import get_standalone_driver

        driver = get_standalone_driver()
        with driver.session(database="neo4j") as session:
            repo = DesignRepository(session)
            node = DesignNode(
                qualified_name="Fl_Button",
                name="Fl_Button",
                kind="class",
                source_type="dependency",
            )
            repo.merge_node(node)

            record = session.run(
                "MATCH (d:Design {qualified_name: $qn}) RETURN d",
                {"qn": "Fl_Button"},
            ).single()
            assert record is None, "Dependency stub should not be created as Design node"
        driver.close()