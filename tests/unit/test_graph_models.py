"""Unit tests for graph container models."""

from codegraph.graph import (
    CompoundGraph,
    GraphEdge,
    NamespaceGraph,
    OntologyGraph,
)
from codegraph.models import ClassNode, MethodNode, NamespaceNode


class TestOntologyGraphToRaw:
    def test_empty_graph_returns_empty_dicts(self):
        graph = OntologyGraph()
        raw = graph.to_raw()
        assert raw == {"nodes": [], "edges": []}

    def test_single_compound_with_members(self):
        node = ClassNode(
            qualified_name="ns::MyClass",
            name="MyClass",
            kind="class",
            layer="design",
        )
        member = MethodNode(
            qualified_name="ns::MyClass::run",
            name="run",
            kind="method",
            layer="design",
        )
        edge = GraphEdge(
            source_qualified_name="ns::MyClass",
            target_qualified_name="ns::OtherClass",
            predicate="DEPENDS_ON",
        )
        cg = CompoundGraph(
            node=node,
            members=[member],
            edges_out=[edge],
        )
        graph = OntologyGraph(compounds=[cg])
        raw = graph.to_raw()

        assert len(raw["nodes"]) == 2
        assert len(raw["edges"]) == 1
        node_qns = {n["qualified_name"] for n in raw["nodes"]}
        assert "ns::MyClass" in node_qns
        assert "ns::MyClass::run" in node_qns
        assert raw["edges"][0]["source"] == "ns::MyClass"
        assert raw["edges"][0]["target"] == "ns::OtherClass"
        assert raw["edges"][0]["type"] == "DEPENDS_ON"

    def test_namespace_with_nested_compounds(self):
        node = ClassNode(
            qualified_name="ns::MyClass",
            name="MyClass",
            kind="class",
            layer="design",
        )
        ns_node = NamespaceNode(
            qualified_name="ns",
            name="ns",
            kind="namespace",
            layer="design",
        )
        cg = CompoundGraph(node=node)
        nsg = NamespaceGraph(node=ns_node, compounds=[cg])
        graph = OntologyGraph(namespaces=[nsg])
        raw = graph.to_raw()

        assert len(raw["nodes"]) == 2
        qns = {n["qualified_name"] for n in raw["nodes"]}
        assert "ns::MyClass" in qns
        assert "ns" in qns

    def test_nested_classes(self):
        outer = ClassNode(
            qualified_name="ns::Outer",
            name="Outer",
            kind="class",
            layer="design",
        )
        inner_node = ClassNode(
            qualified_name="ns::Outer::Inner",
            name="Inner",
            kind="class",
            layer="design",
        )
        inner = CompoundGraph(node=inner_node)
        outer_cg = CompoundGraph(node=outer, nested=[inner])
        graph = OntologyGraph(compounds=[outer_cg])
        raw = graph.to_raw()

        assert len(raw["nodes"]) == 2
        qns = {n["qualified_name"] for n in raw["nodes"]}
        assert "ns::Outer" in qns
        assert "ns::Outer::Inner" in qns

    def test_deduplicates_duplicate_nodes(self):
        node = ClassNode(
            qualified_name="ns::Shared",
            name="Shared",
            kind="class",
            layer="design",
        )
        cg1 = CompoundGraph(node=node)
        cg2 = CompoundGraph(node=node)
        graph = OntologyGraph(compounds=[cg1, cg2])
        raw = graph.to_raw()

        assert len(raw["nodes"]) == 1
        assert raw["nodes"][0]["qualified_name"] == "ns::Shared"
