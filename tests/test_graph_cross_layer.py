"""Tests for cross-layer node tagging in format_ontology_graph."""

import pytest

from backend.db.neo4j.models.graph import (
    CompoundGraph,
    GraphEdge,
    OntologyGraph,
)
from backend.db.neo4j.models.nodes import CompoundNode
from backend.graph import format_ontology_graph


def _make_compound(qn: str, name: str, kind: str = "class", layer: str = "design", **kwargs) -> CompoundGraph:
    """Build a minimal CompoundGraph for testing."""
    node = CompoundNode(qualified_name=qn, name=name, kind=kind, layer=layer, **kwargs)
    return CompoundGraph(node=node, members=[], edges_out=[], edges_in=[])


def _make_edge(src: str, tgt: str, pred: str) -> GraphEdge:
    return GraphEdge(source_qualified_name=src, target_qualified_name=tgt, predicate=pred)


class TestCrossLayerEdgeTagging:
    def test_cross_layer_edge_tagged(self):
        """Edges between nodes of different layers get is_cross_layer='true'."""
        graph = OntologyGraph(
            compounds=[
                _make_compound("calc::Foo", "Foo", layer="design"),
                _make_compound("fltk::Fl_Button", "Fl_Button", layer="dependency", source="FLTK"),
            ],
            edges=[
                _make_edge("calc::Foo", "fltk::Fl_Button", "USES"),
            ],
        )
        result = format_ontology_graph(graph)
        cross_edges = [e for e in result["edges"] if e["data"].get("is_cross_layer") == "true"]
        assert len(cross_edges) == 1
        assert cross_edges[0]["data"]["label"] == "USES"

    def test_same_layer_edge_not_tagged(self):
        """Edges between two design nodes are NOT tagged cross-layer."""
        graph = OntologyGraph(
            compounds=[
                _make_compound("calc::Foo", "Foo", layer="design"),
                _make_compound("calc::Bar", "Bar", layer="design"),
            ],
            edges=[
                _make_edge("calc::Foo", "calc::Bar", "REFERENCES"),
            ],
        )
        result = format_ontology_graph(graph)
        for e in result["edges"]:
            assert e["data"].get("is_cross_layer") != "true"

    def test_as_built_cross_layer_edge_tagged(self):
        """Edge from design to as-built node is cross-layer."""
        graph = OntologyGraph(
            compounds=[
                _make_compound("calc::Foo", "Foo", layer="design"),
                _make_compound("calc::FooImpl", "FooImpl", layer="as-built"),
            ],
            edges=[
                _make_edge("calc::Foo", "calc::FooImpl", "IMPLEMENTED_BY"),
            ],
        )
        result = format_ontology_graph(graph)
        cross_edges = [e for e in result["edges"] if e["data"].get("is_cross_layer") == "true"]
        assert len(cross_edges) == 1


class TestDependencyNodeTagging:
    def test_dependency_node_has_source(self):
        """Dependency node with source property gets has_source='true'."""
        graph = OntologyGraph(
            compounds=[
                _make_compound("fltk::Fl_Button", "Fl_Button", layer="dependency", source="FLTK"),
            ],
        )
        result = format_ontology_graph(graph)
        node = result["nodes"][0]
        assert node["data"]["has_source"] == "true"

    def test_dependency_node_without_source_no_tag(self):
        """Dependency node without source property does not get has_source."""
        graph = OntologyGraph(
            compounds=[
                _make_compound("std::vector", "vector", layer="dependency"),
            ],
        )
        result = format_ontology_graph(graph)
        node = result["nodes"][0]
        assert node["data"].get("has_source") != "true"

    def test_as_built_node_tagged(self):
        """As-built node gets is_as_built='true'."""
        graph = OntologyGraph(
            compounds=[
                _make_compound("calc::Engine", "Engine", layer="as-built"),
            ],
        )
        result = format_ontology_graph(graph)
        node = result["nodes"][0]
        assert node["data"]["is_as_built"] == "true"

    def test_design_node_no_cross_layer_tags(self):
        """Design node gets no cross-layer tags."""
        graph = OntologyGraph(
            compounds=[
                _make_compound("calc::Foo", "Foo", layer="design"),
            ],
        )
        result = format_ontology_graph(graph)
        node = result["nodes"][0]
        assert node["data"].get("has_source") is None
        assert node["data"].get("is_as_built") is None


class TestNoComposesEdges:
    """COMPOSES edges are never emitted — they are implicit in the typed model."""

    def test_no_composes_edges_in_output(self):
        """format_ontology_graph never produces COMPOSES edges."""
        graph = OntologyGraph(
            compounds=[
                _make_compound("calc::Engine", "Engine"),
                _make_compound("calc::Result", "Result"),
            ],
            edges=[
                _make_edge("calc::Engine", "calc::Result", "REFERENCES"),
            ],
        )
        result = format_ontology_graph(graph)
        edge_labels = {e["data"]["label"] for e in result["edges"]}
        assert "COMPOSES" not in edge_labels
        assert "REFERENCES" in edge_labels
