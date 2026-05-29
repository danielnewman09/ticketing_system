"""Tests for cross-layer node tagging in format_cytoscape_graph."""

import pytest
from backend.graph import format_cytoscape_graph


class TestCrossLayerEdgeTagging:
    def test_cross_layer_edge_tagged(self):
        """Edges between nodes of different layers get is_cross_layer='true'."""
        raw = {
            "nodes": [
                {"qualified_name": "calc::Foo", "name": "Foo", "kind": "class", "layer": "design"},
                {"qualified_name": "fltk::Fl_Button", "name": "Fl_Button", "kind": "class", "layer": "dependency", "source": "FLTK"},
            ],
            "edges": [
                {"source": "calc::Foo", "target": "fltk::Fl_Button", "type": "USES"},
            ],
        }
        result = format_cytoscape_graph(raw)
        cross_edges = [e for e in result["edges"] if e["data"].get("is_cross_layer") == "true"]
        assert len(cross_edges) == 1
        assert cross_edges[0]["data"]["label"] == "USES"

    def test_same_layer_edge_not_tagged(self):
        """Edges between two design nodes are NOT tagged cross-layer."""
        raw = {
            "nodes": [
                {"qualified_name": "calc::Foo", "name": "Foo", "kind": "class", "layer": "design"},
                {"qualified_name": "calc::Bar", "name": "Bar", "kind": "class", "layer": "design"},
            ],
            "edges": [
                {"source": "calc::Foo", "target": "calc::Bar", "type": "COMPOSES"},
            ],
        }
        result = format_cytoscape_graph(raw)
        for e in result["edges"]:
            assert e["data"].get("is_cross_layer") != "true"

    def test_as_built_cross_layer_edge_tagged(self):
        """Edge from design to as-built node is cross-layer."""
        raw = {
            "nodes": [
                {"qualified_name": "calc::Foo", "name": "Foo", "kind": "class", "layer": "design"},
                {"qualified_name": "calc::FooImpl", "name": "FooImpl", "kind": "class", "layer": "as-built"},
            ],
            "edges": [
                {"source": "calc::Foo", "target": "calc::FooImpl", "type": "IMPLEMENTED_BY"},
            ],
        }
        result = format_cytoscape_graph(raw)
        cross_edges = [e for e in result["edges"] if e["data"].get("is_cross_layer") == "true"]
        assert len(cross_edges) == 1


class TestDependencyNodeTagging:
    def test_dependency_node_has_source(self):
        """Dependency node with source property gets has_source='true'."""
        raw = {
            "nodes": [
                {"qualified_name": "fltk::Fl_Button", "name": "Fl_Button", "kind": "class", "layer": "dependency", "source": "FLTK"},
            ],
            "edges": [],
        }
        result = format_cytoscape_graph(raw)
        node = result["nodes"][0]
        assert node["data"]["has_source"] == "true"

    def test_dependency_node_without_source_no_tag(self):
        """Dependency node without source property does not get has_source."""
        raw = {
            "nodes": [
                {"qualified_name": "std::vector", "name": "vector", "kind": "class", "layer": "dependency"},
            ],
            "edges": [],
        }
        result = format_cytoscape_graph(raw)
        node = result["nodes"][0]
        assert node["data"].get("has_source") != "true"

    def test_as_built_node_tagged(self):
        """As-built node gets is_as_built='true'."""
        raw = {
            "nodes": [
                {"qualified_name": "calc::Engine", "name": "Engine", "kind": "class", "layer": "as-built"},
            ],
            "edges": [],
        }
        result = format_cytoscape_graph(raw)
        node = result["nodes"][0]
        assert node["data"]["is_as_built"] == "true"

    def test_design_node_no_cross_layer_tags(self):
        """Design node gets no cross-layer tags."""
        raw = {
            "nodes": [
                {"qualified_name": "calc::Foo", "name": "Foo", "kind": "class", "layer": "design"},
            ],
            "edges": [],
        }
        result = format_cytoscape_graph(raw)
        node = result["nodes"][0]
        assert node["data"].get("has_source") is None
        assert node["data"].get("is_as_built") is None


class TestComposesEdgesAlwaysRemoved:
    """COMPOSES edges should never appear in format_cytoscape_graph output."""

    def test_composes_edges_removed_in_full_pipeline(self):
        """format_cytoscape_graph removes all COMPOSES edges from output."""
        raw = {
            "nodes": [
                {"qualified_name": "calc::Engine", "name": "Engine", "kind": "class", "layer": "design"},
                {"qualified_name": "calc::Result", "name": "Result", "kind": "class", "layer": "design"},
            ],
            "edges": [
                {"source": "calc::Engine", "target": "calc::Result", "type": "COMPOSES"},
                {"source": "calc::Engine", "target": "calc::Result", "type": "REFERENCES"},
            ],
        }
        result = format_cytoscape_graph(raw)
        edge_labels = {e["data"]["label"] for e in result["edges"]}
        assert "COMPOSES" not in edge_labels
        assert "REFERENCES" in edge_labels

    def test_module_composes_removed_after_namespace_assignment(self):
        """Module COMPOSES edges used for namespace grouping are also removed."""
        raw = {
            "nodes": [
                {"qualified_name": "calc", "name": "calc", "kind": "module", "layer": "design"},
                {"qualified_name": "calc::Engine", "name": "Engine", "kind": "class", "layer": "design"},
            ],
            "edges": [
                {"source": "calc", "target": "calc::Engine", "type": "COMPOSES"},
            ],
        }
        result = format_cytoscape_graph(raw)
        edge_labels = {e["data"]["label"] for e in result["edges"]}
        assert "COMPOSES" not in edge_labels