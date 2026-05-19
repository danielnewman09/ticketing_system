"""Tests for backend/requirements/services/graph_tags.py"""

import pytest
from backend.requirements.services.graph_tags import (
    enrich_with_requirement_tags,
    tag_direct_nodes_only,
)
from backend.db.models.ontology import OntologyNode
from backend.db.models.requirements import HighLevelRequirement, LowLevelRequirement


class TestEnrichWithRequirementTags:
    def test_mode_none_returns_nodes_unchanged(self):
        nodes = [{"id": "n1", "qualified_name": "ns::Foo"}]
        result = enrich_with_requirement_tags(nodes, mode="none")
        assert result == nodes
        assert "requirements" not in result[0]

    def test_mode_hlr_tags_nodes_with_matching_requirements(self, seeded_session):
        hlr = seeded_session.query(HighLevelRequirement).first()
        node = OntologyNode(kind="class", name="Foo", qualified_name="calc::Foo")
        seeded_session.add(node)
        seeded_session.flush()
        hlr.nodes.append(node)
        seeded_session.flush()

        nodes = [{"id": "calc::Foo", "qualified_name": "calc::Foo", "kind": "class", "name": "Foo"}]
        result = enrich_with_requirement_tags(nodes, mode="hlr", session=seeded_session)

        assert len(result) == 1
        assert len(result[0]["requirements"]) == 1
        assert result[0]["requirements"][0]["type"] == "HLR"
        assert result[0]["requirements"][0]["id"] == hlr.id

    def test_mode_hlr_skips_nodes_without_requirements(self, seeded_session):
        nodes = [{"id": "n1", "qualified_name": "ns::NoReq", "kind": "class", "name": "NoReq"}]
        result = enrich_with_requirement_tags(nodes, mode="hlr", session=seeded_session)
        assert "requirements" not in result[0]

    def test_mode_hlr_handles_multiple_hlrs_on_same_node(self, seeded_session):
        comp = seeded_session.query(HighLevelRequirement).first().component
        hlr1 = HighLevelRequirement(description="First HLR", component=comp)
        hlr2 = HighLevelRequirement(description="Second HLR", component=comp)
        seeded_session.add_all([hlr1, hlr2])
        seeded_session.flush()

        node = OntologyNode(kind="class", name="MultiReq", qualified_name="calc::MultiReq")
        seeded_session.add(node)
        seeded_session.flush()

        hlr1.nodes.append(node)
        hlr2.nodes.append(node)
        seeded_session.flush()

        nodes = [{"id": "calc::MultiReq", "qualified_name": "calc::MultiReq", "kind": "class", "name": "MultiReq"}]
        result = enrich_with_requirement_tags(nodes, mode="hlr", session=seeded_session)

        assert len(result[0]["requirements"]) == 2

    def test_mode_hlr_empty_graph_returns_empty(self):
        result = enrich_with_requirement_tags([], mode="hlr")
        assert result == []


class TestTagDirectNodesOnly:
    def test_marks_seed_nodes_with_highlight(self, seeded_session):
        hlr = seeded_session.query(HighLevelRequirement).first()
        node = OntologyNode(kind="class", name="Foo", qualified_name="calc::Foo")
        seeded_session.add(node)
        seeded_session.flush()
        hlr.nodes.append(node)
        seeded_session.flush()

        nodes = [
            {"id": "calc::Foo", "qualified_name": "calc::Foo", "kind": "class", "name": "Foo"},
            {"id": "calc::Bar", "qualified_name": "calc::Bar", "kind": "class", "name": "Bar"},
        ]
        tag_direct_nodes_only(nodes, hlr.id, session=seeded_session)

        assert nodes[0].get("is_hlr_highlight") == "true"
        assert len(nodes[0].get("requirements", [])) == 1
        assert nodes[1].get("is_hlr_highlight", "") == ""

    def test_hlr_not_found_does_nothing(self, seeded_session):
        nodes = [{"id": "n1", "qualified_name": "ns::X"}]
        tag_direct_nodes_only(nodes, hlr_id=99999, session=seeded_session)
        assert nodes[0].get("is_hlr_highlight", "") == ""

    def test_only_direct_nodes_tagged(self, seeded_session):
        hlr = seeded_session.query(HighLevelRequirement).first()
        direct_node = OntologyNode(kind="class", name="Direct", qualified_name="calc::Direct")
        neighbour_node = OntologyNode(kind="class", name="Neighbour", qualified_name="calc::Neighbour")
        seeded_session.add_all([direct_node, neighbour_node])
        seeded_session.flush()
        hlr.nodes.append(direct_node)
        seeded_session.flush()

        nodes = [
            {"id": "calc::Direct", "qualified_name": "calc::Direct", "kind": "class", "name": "Direct"},
            {"id": "calc::Neighbour", "qualified_name": "calc::Neighbour", "kind": "class", "name": "Neighbour"},
        ]
        tag_direct_nodes_only(nodes, hlr.id, session=seeded_session)

        assert nodes[0]["is_hlr_highlight"] == "true"
        assert len(nodes[0]["requirements"]) == 1
        assert nodes[1].get("is_hlr_highlight", "") == ""
        assert "requirements" not in nodes[1]
