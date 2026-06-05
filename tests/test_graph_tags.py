"""Tests for Cypher-based requirement tag enrichment."""

import os
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_NEO4J_INTEGRATION") != "1",
    reason="Set RUN_NEO4J_INTEGRATION=1 to run Neo4j integration tests",
)


@pytest.fixture
def neo4j_session():
    """Provide a Neo4j session and clean up Design/HLR/LLR nodes after each test."""
    from neomodel import db

    session = db.driver.session()
    yield session
    from backend.db.neo4j.repositories.design import DesignRepository
    DesignRepository(session).clear_design_graph()
    session.run("MATCH (n:HLR) DETACH DELETE n")
    session.run("MATCH (n:LLR) DETACH DELETE n")
    session.close()


class TestEnrichWithRequirementTagsCypher:
    def test_mode_none_returns_nodes_unchanged(self):
        from backend.requirements.services.graph_tags import enrich_with_requirement_tags

        nodes = [{"data": {"id": "n1", "qualified_name": "ns::Foo"}}]
        result = enrich_with_requirement_tags(nodes, mode="none")
        assert result == nodes
        assert "requirements" not in result[0]["data"]

    def test_tags_design_nodes_with_hlr_badges(self, neo4j_session):
        from codegraph.models import ClassNode
        from backend.db.neo4j.repositories.design import DesignRepository
        from backend.db.neo4j.repositories.requirement import RequirementRepository
        from backend.requirements.services.graph_tags import enrich_with_requirement_tags

        design_repo = DesignRepository(neo4j_session)
        design_repo.merge_node(ClassNode(qualified_name="calc::Foo", name="Foo", kind="class"))

        req_repo = RequirementRepository(neo4j_session)
        hlr = req_repo.create_hlr(description="The system shall calculate")
        req_repo.trace_to_design(hlr_id=hlr.id, design_qualified_name="calc::Foo")

        nodes = [
            {"data": {"id": "calc::Foo", "qualified_name": "calc::Foo", "kind": "class", "name": "Foo", "label": "Foo"}},
            {"data": {"id": "calc::Bar", "qualified_name": "calc::Bar", "kind": "class", "name": "Bar", "label": "Bar"}},
        ]

        enrich_with_requirement_tags(nodes, mode="hlr", session=neo4j_session)

        assert len(nodes[0]["data"]["requirements"]) == 1
        assert nodes[0]["data"]["requirements"][0]["type"] == "HLR"
        assert nodes[0]["data"]["requirements"][0]["id"] == hlr.id
        assert "requirements" not in nodes[1]["data"]

    def test_skips_dependency_stubs(self, neo4j_session):
        from backend.requirements.services.graph_tags import enrich_with_requirement_tags

        nodes = [
            {"data": {"id": "dep1", "qualified_name": "Fl_Button", "source_type": "dependency", "name": "Fl_Button", "label": "Fl_Button"}},
        ]
        result = enrich_with_requirement_tags(nodes, mode="hlr", session=neo4j_session)
        assert "requirements" not in result[0]["data"]

    def test_mode_hlr_empty_graph_returns_empty(self):
        from backend.requirements.services.graph_tags import enrich_with_requirement_tags

        result = enrich_with_requirement_tags([], mode="hlr")
        assert result == []


class TestTagDirectNodesOnlyCypher:
    def test_marks_seed_nodes_with_highlight(self, neo4j_session):
        from codegraph.models import ClassNode
        from backend.db.neo4j.repositories.design import DesignRepository
        from backend.db.neo4j.repositories.requirement import RequirementRepository
        from backend.requirements.services.graph_tags import tag_direct_nodes_only

        design_repo = DesignRepository(neo4j_session)
        design_repo.merge_node(ClassNode(qualified_name="calc::Direct", name="Direct", kind="class"))
        design_repo.merge_node(ClassNode(qualified_name="calc::Neighbour", name="Neighbour", kind="class"))

        req_repo = RequirementRepository(neo4j_session)
        hlr = req_repo.create_hlr(description="A requirement")
        req_repo.trace_to_design(hlr_id=hlr.id, design_qualified_name="calc::Direct")

        nodes = [
            {"data": {"id": "calc::Direct", "qualified_name": "calc::Direct", "kind": "class", "name": "Direct", "label": "Direct"}},
            {"data": {"id": "calc::Neighbour", "qualified_name": "calc::Neighbour", "kind": "class", "name": "Neighbour", "label": "Neighbour"}},
        ]
        tag_direct_nodes_only(nodes, hlr_id=hlr.id, session=neo4j_session)

        assert nodes[0]["data"]["is_hlr_highlight"] == "true"
        assert len(nodes[0]["data"]["requirements"]) == 1
        assert nodes[0]["data"]["requirements"][0]["id"] == hlr.id
        assert nodes[1]["data"].get("is_hlr_highlight", "") == ""

    def test_hlr_not_found_does_nothing(self, neo4j_session):
        from backend.requirements.services.graph_tags import tag_direct_nodes_only

        nodes = [{"data": {"id": "n1", "qualified_name": "ns::X", "label": "X"}}]
        tag_direct_nodes_only(nodes, hlr_id=99999, session=neo4j_session)
        assert nodes[0]["data"].get("is_hlr_highlight", "") == ""