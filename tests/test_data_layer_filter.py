"""Tests for include_dependencies filtering in fetch_ontology_graph_data."""

import pytest
from frontend.data.ontology import filter_cross_layer_elements


class TestFilterCrossLayerElements:
    def test_removes_dependency_nodes_when_disabled(self):
        nodes = [
            {"data": {"id": "a", "layer": "design", "qualified_name": "a"}},
            {"data": {"id": "b", "layer": "dependency", "qualified_name": "b", "source": "FLTK"}},
        ]
        edges = [
            {"data": {"id": "e1", "source": "a", "target": "b", "label": "USES", "is_cross_layer": "true"}},
        ]
        result_nodes, result_edges = filter_cross_layer_elements(nodes, edges)
        assert len(result_nodes) == 1
        assert result_nodes[0]["data"]["layer"] == "design"
        assert len(result_edges) == 0

    def test_removes_as_built_nodes_when_disabled(self):
        nodes = [
            {"data": {"id": "a", "layer": "design", "qualified_name": "a"}},
            {"data": {"id": "b", "layer": "as-built", "qualified_name": "b", "is_as_built": "true"}},
        ]
        edges = [
            {"data": {"id": "e1", "source": "a", "target": "b", "label": "IMPLEMENTED_BY", "is_cross_layer": "true"}},
        ]
        result_nodes, result_edges = filter_cross_layer_elements(nodes, edges)
        assert len(result_nodes) == 1
        assert len(result_edges) == 0

    def test_does_not_filter_by_default_when_not_called(self):
        """filter_cross_layer_elements is only called when include_dependencies=False.
        When True, the caller skips the filter entirely."""
        # This test documents that the function always filters when called.
        # The include_dependencies=True case simply doesn't call this function.
        nodes = [
            {"data": {"id": "a", "layer": "design", "qualified_name": "a"}},
            {"data": {"id": "b", "layer": "dependency", "qualified_name": "b"}},
            {"data": {"id": "c", "layer": "as-built", "qualified_name": "c"}},
        ]
        edges = [
            {"data": {"id": "e1", "source": "a", "target": "b", "label": "USES"}},
            {"data": {"id": "e2", "source": "a", "target": "c", "label": "IMPLEMENTED_BY"}},
        ]
        # When dependencies are included, filter is NOT called
        # So the raw data passes through unchanged
        # Here we just verify the function itself works correctly
        result_nodes, result_edges = filter_cross_layer_elements(nodes, edges)
        assert len(result_nodes) == 1  # Only design node remains
        assert len(result_edges) == 0  # No edges (both cross-layer)

    def test_keeps_design_only_edges(self):
        nodes = [
            {"data": {"id": "a", "layer": "design", "qualified_name": "a"}},
            {"data": {"id": "b", "layer": "design", "qualified_name": "b"}},
            {"data": {"id": "c", "layer": "dependency", "qualified_name": "c"}},
        ]
        edges = [
            {"data": {"id": "e1", "source": "a", "target": "b", "label": "COMPOSES"}},
            {"data": {"id": "e2", "source": "a", "target": "c", "label": "USES", "is_cross_layer": "true"}},
        ]
        result_nodes, result_edges = filter_cross_layer_elements(nodes, edges)
        assert len(result_nodes) == 2
        assert len(result_edges) == 1
        assert result_edges[0]["data"]["label"] == "COMPOSES"

    def test_empty_input(self):
        result_nodes, result_edges = filter_cross_layer_elements([], [])
        assert result_nodes == []
        assert result_edges == []