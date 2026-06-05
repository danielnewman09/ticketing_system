"""Integration tests for graph query methods on DesignRepository.

Requires a running Neo4j instance.
"""

import os

import pytest
from backend.db.neo4j.repositories.design import DesignRepository
from codegraph.models import ClassNode, MethodNode

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_NEO4J_INTEGRATION") != "1",
    reason="Set RUN_NEO4J_INTEGRATION=1 to run Neo4j integration tests",
)


@pytest.fixture
def neo4j_session():
    """Provide a Neo4j session and clean up after each test."""
    from neomodel import db

    session = db.driver.session()
    repo = DesignRepository(session)
    repo.clear_design_graph()
    yield session
    repo.clear_design_graph()
    session.close()


class TestGetCompoundGraph:
    def test_returns_none_for_missing_compound(self, neo4j_session):
        repo = DesignRepository(neo4j_session)
        assert repo.get_compound_graph("does_not::exist") is None

    def test_returns_compound_with_members(self, neo4j_session):
        repo = DesignRepository(neo4j_session)
        # Create test data
        node = ClassNode(
            qualified_name="test_graph::TestClass",
            name="TestClass",
            kind="class",
            layer="design",
        )
        repo.merge_node(node)
        member = MethodNode(
            qualified_name="test_graph::TestClass::do_thing",
            name="do_thing",
            kind="method",
            layer="design",
        )
        repo.merge_node(member)
        repo.merge_triple("test_graph::TestClass", "composes",
                          "test_graph::TestClass::do_thing")

        cg = repo.get_compound_graph("test_graph::TestClass", layer="design")
        assert cg is not None
        assert cg.node.name == "TestClass"
        assert cg.node.kind == "class"
        assert len(cg.members) == 1
        assert cg.members[0].name == "do_thing"
        assert cg.members[0].kind == "method"
