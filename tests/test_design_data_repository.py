"""Integration tests for DesignDataRepository.

Requires a running Neo4j instance. Set RUN_NEO4J_INTEGRATION=1 to run.
"""

import os
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_NEO4J_INTEGRATION") != "1",
    reason="Set RUN_NEO4J_INTEGRATION=1 to run Neo4j integration tests",
)


@pytest.fixture
def neo4j_session():
    """Provide a Neo4j session and clean up after each test."""
    from codegraph.neo4j import get_standalone_driver

    driver = get_standalone_driver()
    session = driver.session(database="neo4j")
    # Clean up before
    from backend.db.neo4j.repositories.design import DesignRepository
    DesignRepository(session).clear_design_graph()
    yield session
    # Clean up after
    DesignRepository(session).clear_design_graph()
    session.close()
    driver.close()


def _seed_design_nodes(neo4j_session):
    """Seed some codebase graph nodes for testing."""
    from backend.db.neo4j.models.nodes import CompoundNode, MemberNode
    from backend.db.neo4j.repositories.design import DesignRepository

    repo = DesignRepository(neo4j_session)

    # Create a class with members
    repo.merge_node(CompoundNode(
        name="Calculator", qualified_name="calc::Calculator", kind="class",
        description="Main calculator class", component_id=1,
    ))
    repo.merge_node(MemberNode(
        name="result_", qualified_name="calc::Calculator::result_", kind="attribute",
        type_signature="double", visibility="private",
    ))
    repo.merge_node(MemberNode(
        name="add", qualified_name="calc::Calculator::add", kind="method",
        visibility="public", type_signature="double", argsstring="(double x, double y)",
    ))
    # COMPOSES relationship
    repo.merge_triple("calc::Calculator", "composes", "calc::Calculator::result_")
    repo.merge_triple("calc::Calculator", "composes", "calc::Calculator::add")

    # Create an interface
    repo.merge_node(CompoundNode(
        name="ICalculator", qualified_name="calc::ICalculator", kind="interface",
        description="Calculator interface", component_id=1,
    ))
    repo.merge_node(MemberNode(
        name="add", qualified_name="calc::ICalculator::add", kind="method",
        visibility="public", is_virtual=True,
    ))
    repo.merge_triple("calc::ICalculator", "composes", "calc::ICalculator::add")

    # Create an enum
    repo.merge_node(CompoundNode(
        name="Operation", qualified_name="calc::Operation", kind="enum",
        description="Supported operations", component_id=1,
    ))


class TestDesignDataRepository:
    def test_get_existing_class(self, neo4j_session):
        from backend.design_data.repository import DesignDataRepository

        _seed_design_nodes(neo4j_session)
        repo = DesignDataRepository(neo4j_session)
        cls = repo.get_class("calc::Calculator")
        assert cls is not None
        assert cls.name == "Calculator"
        assert cls.qualified_name == "calc::Calculator"
        assert cls.module == "calc"

    def test_get_class_with_members(self, neo4j_session):
        from backend.design_data.repository import DesignDataRepository

        _seed_design_nodes(neo4j_session)
        repo = DesignDataRepository(neo4j_session)
        cls = repo.get_class("calc::Calculator")
        assert cls is not None
        assert len(cls.attributes) >= 1
        assert cls.attributes[0].name == "result_"
        assert len(cls.methods) >= 1
        assert cls.methods[0].name == "add"

    def test_get_nonexistent_class(self, neo4j_session):
        from backend.design_data.repository import DesignDataRepository

        repo = DesignDataRepository(neo4j_session)
        cls = repo.get_class("nonexistent::Class")
        assert cls is None

    def test_get_class_diagram_by_component(self, neo4j_session):
        from backend.design_data.repository import DesignDataRepository

        _seed_design_nodes(neo4j_session)
        repo = DesignDataRepository(neo4j_session)
        diagram = repo.get_class_diagram(component_id=1)
        assert len(diagram.classes) >= 1
        assert any(c.name == "Calculator" for c in diagram.classes)