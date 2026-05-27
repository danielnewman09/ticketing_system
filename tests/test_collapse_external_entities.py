"""Tests for collapse_members preserving external entity nodes with DEPENDS_ON edges.

When an aggregated class/interface/struct also has non-containment edges
(e.g. DEPENDS_ON, GENERALIZES), the node should remain visible in the
graph alongside the collapsed compartment representation.
"""

import pytest
from backend.graph.transforms import collapse_members


def _make_node(node_id: str, label: str, kind: str, layer: str = "design", **extra) -> dict:
    """Helper to build a Cytoscape node dict."""
    data = {
        "id": node_id,
        "label": label,
        "kind": kind,
        "layer": layer,
        "visibility": "public",
        "type_signature": "",
        "qualified_name": node_id,
    }
    data.update(extra)
    return {"data": data}


def _make_edge(edge_id: str, src: str, tgt: str, label: str) -> dict:
    """Helper to build a Cytoscape edge dict."""
    return {"data": {"id": edge_id, "source": src, "target": tgt, "label": label}}


class TestAggregatedEntityWithDependsOn:
    """Aggregated entity nodes (class/interface/struct) with non-containment
    edges are kept as external nodes alongside their collapsed representation."""

    def test_aggregated_class_with_depends_on_stays_visible(self):
        """Fl_Button aggregated by CalculatorWindow AND having DEPENDS_ON
        from the owner should remain visible as an external node."""
        nodes = [
            _make_node("CalcWin", "CalculatorWindow", "class"),
            _make_node("FlBtn", "Fl_Button", "class", layer="dependency", source="fltk"),
        ]
        edges = [
            _make_edge("e1", "CalcWin", "FlBtn", "AGGREGATES"),
            _make_edge("e2", "CalcWin", "FlBtn", "DEPENDS_ON"),
        ]

        out_nodes, out_edges = collapse_members(nodes, edges)

        node_ids = {n["data"]["id"] for n in out_nodes}
        # Fl_Button should still be visible
        assert "FlBtn" in node_ids
        # CalculatorWindow should still be visible
        assert "CalcWin" in node_ids
        # CalculatorWindow label should contain Fl_Button in its compartment
        calc = next(n for n in out_nodes if n["data"]["id"] == "CalcWin")
        assert "Fl_Button" in calc["data"]["label"]
        # DEPENDS_ON edge should be preserved
        edge_labels = {(e["data"]["source"], e["data"]["target"], e["data"]["label"]) for e in out_edges}
        assert ("CalcWin", "FlBtn", "DEPENDS_ON") in edge_labels

    def test_aggregated_class_with_depends_on_to_third_party(self):
        """CalculatorDisplay aggregated by CalculatorWindow with DEPENDS_ON
        to Fl_Box should keep both CalculatorDisplay and DEPENDS_ON visible."""
        nodes = [
            _make_node("CalcWin", "CalculatorWindow", "class"),
            _make_node("CalcDisp", "CalculatorDisplay", "class"),
            _make_node("FlBox", "Fl_Box", "class", layer="dependency", source="fltk"),
        ]
        edges = [
            _make_edge("e1", "CalcWin", "CalcDisp", "AGGREGATES"),
            _make_edge("e2", "CalcWin", "FlBox", "AGGREGATES"),
            _make_edge("e3", "CalcDisp", "FlBox", "DEPENDS_ON"),
        ]

        out_nodes, out_edges = collapse_members(nodes, edges)

        node_ids = {n["data"]["id"] for n in out_nodes}
        # CalculatorDisplay should remain visible (has DEPENDS_ON)
        assert "CalcDisp" in node_ids
        # Fl_Box should remain visible (target of DEPENDS_ON, also aggregated)
        assert "FlBox" in node_ids
        # CalculatorWindow should contain both in its compartment
        calc = next(n for n in out_nodes if n["data"]["id"] == "CalcWin")
        assert "CalculatorDisplay" in calc["data"]["label"]
        assert "Fl_Box" in calc["data"]["label"]
        # DEPENDS_ON edge from CalculatorDisplay to Fl_Box preserved
        edge_labels = {(e["data"]["source"], e["data"]["target"], e["data"]["label"]) for e in out_edges}
        assert ("CalcDisp", "FlBox", "DEPENDS_ON") in edge_labels

    def test_aggregated_class_with_generalizes_stays_visible(self):
        """An aggregated class with a GENERALIZES edge should remain visible."""
        nodes = [
            _make_node("MyClass", "MyClass", "class"),
            _make_node("Base", "BaseWidget", "class", layer="dependency"),
            _make_node("AggClass", "AggregatedClass", "class"),
        ]
        edges = [
            _make_edge("e1", "MyClass", "AggClass", "AGGREGATES"),
            _make_edge("e2", "AggClass", "Base", "GENERALIZES"),
        ]

        out_nodes, out_edges = collapse_members(nodes, edges)

        node_ids = {n["data"]["id"] for n in out_nodes}
        assert "AggClass" in node_ids
        assert "Base" in node_ids
        # GENERALIZES edge preserved
        edge_labels = {(e["data"]["source"], e["data"]["target"], e["data"]["label"]) for e in out_edges}
        assert ("AggClass", "Base", "GENERALIZES") in edge_labels
        # Also in owner compartment
        owner = next(n for n in out_nodes if n["data"]["id"] == "MyClass")
        assert "AggregatedClass" in owner["data"]["label"]

    def test_interface_with_depends_on_stays_visible(self):
        """An aggregated interface with external edges stays visible."""
        nodes = [
            _make_node("Owner", "Owner", "class"),
            _make_node("Iface", "ISerializable", "interface"),
            _make_node("Dep", "SomeDep", "class", layer="dependency"),
        ]
        edges = [
            _make_edge("e1", "Owner", "Iface", "AGGREGATES"),
            _make_edge("e2", "Iface", "Dep", "DEPENDS_ON"),
        ]

        out_nodes, out_edges = collapse_members(nodes, edges)

        node_ids = {n["data"]["id"] for n in out_nodes}
        assert "Iface" in node_ids

    def test_struct_with_depends_on_stays_visible(self):
        """An aggregated struct with external edges stays visible."""
        nodes = [
            _make_node("Owner", "Owner", "class"),
            _make_node("St", "DataHolder", "struct"),
            _make_node("Dep", "SomeDep", "class", layer="dependency"),
        ]
        edges = [
            _make_edge("e1", "Owner", "St", "AGGREGATES"),
            _make_edge("e2", "St", "Dep", "DEPENDS_ON"),
        ]

        out_nodes, out_edges = collapse_members(nodes, edges)

        node_ids = {n["data"]["id"] for n in out_nodes}
        assert "St" in node_ids


class TestAttributesStillCollapsed:
    """Attributes, methods, and enum_values are always fully collapsed
    regardless of edges — they are NOT entity kinds."""

    def test_attribute_fully_collapsed_even_with_edge(self):
        """Attributes (non-entity kind) are always collapsed, even if
        they technically appear as edge endpoints."""
        nodes = [
            _make_node("Owner", "Owner", "class"),
            _make_node("attr1", "some_attr", "attribute"),
            _make_node("Dep", "Dep", "class"),
        ]
        edges = [
            _make_edge("e1", "Owner", "attr1", "COMPOSES"),
            _make_edge("e2", "Owner", "Dep", "DEPENDS_ON"),
        ]

        out_nodes, _ = collapse_members(nodes, edges)

        node_ids = {n["data"]["id"] for n in out_nodes}
        # Attribute should be removed (fully collapsed)
        assert "attr1" not in node_ids
        # Owner should contain attribute in label
        owner = next(n for n in out_nodes if n["data"]["id"] == "Owner")
        assert "some_attr" in owner["data"]["label"]

    def test_method_fully_collapsed(self):
        """Methods are always fully collapsed."""
        nodes = [
            _make_node("Owner", "Owner", "class"),
            _make_node("m1", "do_stuff", "method"),
        ]
        edges = [
            _make_edge("e1", "Owner", "m1", "COMPOSES"),
        ]

        out_nodes, _ = collapse_members(nodes, edges)

        node_ids = {n["data"]["id"] for n in out_nodes}
        assert "m1" not in node_ids

    def test_enum_value_fully_collapsed(self):
        """Enum values are always fully collapsed."""
        nodes = [
            _make_node("Owner", "MyEnum", "enum"),
            _make_node("ev1", "VALUE_A", "enum_value"),
        ]
        edges = [
            _make_edge("e1", "Owner", "ev1", "COMPOSES"),
        ]

        out_nodes, _ = collapse_members(nodes, edges)

        node_ids = {n["data"]["id"] for n in out_nodes}
        assert "ev1" not in node_ids


class TestAggregatedEntityNoExternalEdges:
    """Aggregated entity nodes WITHOUT non-containment edges
    should be fully collapsed (removed from node list)."""

    def test_aggregated_class_no_edges_keeps_visible(self):
        """An aggregated class from a non-module owner stays visible
        (entity-to-entity composition relationship)."""
        nodes = [
            _make_node("Owner", "Owner", "class"),
            _make_node("Agg", "InnerClass", "class"),
        ]
        edges = [
            _make_edge("e1", "Owner", "Agg", "AGGREGATES"),
        ]

        out_nodes, out_edges = collapse_members(nodes, edges)

        node_ids = {n["data"]["id"] for n in out_nodes}
        assert "Agg" in node_ids
        # Shown in compartment
        owner = next(n for n in out_nodes if n["data"]["id"] == "Owner")
        assert "InnerClass" in owner["data"]["label"]

    def test_aggregated_class_only_containment_edges_keeps_visible(self):
        """An aggregated class with only COMPOSES/CONTAINS edges
        from its owner stays visible."""
        nodes = [
            _make_node("Owner", "Owner", "class"),
            _make_node("Agg", "InnerClass", "class"),
            _make_node("m1", "inner_method", "method"),
        ]
        edges = [
            _make_edge("e1", "Owner", "Agg", "AGGREGATES"),
            _make_edge("e2", "Agg", "m1", "COMPOSES"),
        ]

        out_nodes, _ = collapse_members(nodes, edges)

        node_ids = {n["data"]["id"] for n in out_nodes}
        assert "Agg" in node_ids
        assert "m1" not in node_ids  # method still fully collapsed


class TestDuplicateEdgeDedup:
    """When the owner already has a DEPENDS_ON to the same target
    as an aggregated entity, deduplication should work correctly."""

    def test_owner_and_aggregate_same_depends_on_target(self):
        """If both the owner and its aggregated class have DEPENDS_ON
        to the same target, only one edge should appear (deduped)."""
        nodes = [
            _make_node("Owner", "Owner", "class"),
            _make_node("Agg", "InnerClass", "class"),
            _make_node("Dep", "Dependency", "class", layer="dependency"),
        ]
        edges = [
            _make_edge("e1", "Owner", "Agg", "AGGREGATES"),
            _make_edge("e2", "Owner", "Dep", "DEPENDS_ON"),
            _make_edge("e3", "Agg", "Dep", "DEPENDS_ON"),
        ]

        out_nodes, out_edges = collapse_members(nodes, edges)

        # Both Owner and InnerClass visible
        node_ids = {n["data"]["id"] for n in out_nodes}
        assert "Owner" in node_ids
        assert "Agg" in node_ids  # has DEPENDS_ON edge
        assert "Dep" in node_ids

        dep_edges = [
            e for e in out_edges
            if e["data"]["label"] == "DEPENDS_ON" and e["data"]["target"] == "Dep"
        ]
        # Owner → Dep and Agg → Dep should both appear (different sources)
        dep_sources = {e["data"]["source"] for e in dep_edges}
        assert "Owner" in dep_sources
        assert "Agg" in dep_sources


class TestComposesNotAffected:
    """COMPOSES edges (attributes/methods) should not trigger
    the external-entity preservation logic."""

    def test_composes_keeps_entity_visible(self):
        """COMPOSES edge to a class node should keep it visible as an
        external node (entity-to-entity composition)."""
        nodes = [
            _make_node("Owner", "Owner", "class"),
            _make_node("Nested", "NestedClass", "class"),
        ]
        edges = [
            _make_edge("e1", "Owner", "Nested", "COMPOSES"),
        ]

        out_nodes, _ = collapse_members(nodes, edges)

        node_ids = {n["data"]["id"] for n in out_nodes}
        assert "Nested" in node_ids

    def test_composes_plus_depends_on_keeps_entity(self):
        """COMPOSES + DEPENDS_ON should still keep the entity visible."""
        nodes = [
            _make_node("Owner", "Owner", "class"),
            _make_node("Nested", "NestedClass", "class"),
            _make_node("Dep", "Dep", "class", layer="dependency"),
        ]
        edges = [
            _make_edge("e1", "Owner", "Nested", "COMPOSES"),
            _make_edge("e2", "Nested", "Dep", "DEPENDS_ON"),
        ]

        out_nodes, _ = collapse_members(nodes, edges)

        node_ids = {n["data"]["id"] for n in out_nodes}
        assert "Nested" in node_ids


class TestRealWorldScenario:
    """Test the full CalculatorWindow scenario from the user's description."""

    def test_calculator_window_scenario(self):
        """Matches the real data in the system:
        CalculatorWindow AGGREGATES fl_button objects (Compound),
        also has DEPENDS_ON to them. The fl_button should appear
        both in the collapsed compartment AND as an external node
        with the DEPENDS_ON edge visible.
        """
        nodes = [
            _make_node("ui::CalcWin", "CalculatorWindow", "class"),
            _make_node("ui::CalcDisp", "CalculatorDisplay", "class"),
            _make_node("ui::CalcCtrl", "CalculatorController", "class"),
            _make_node("Fl_Btn", "Fl_Button", "class", layer="dependency", source="fltk"),
            _make_node("Fl_RBtn", "Fl_Return_Button", "class", layer="dependency", source="fltk"),
            _make_node("Fl_Box", "Fl_Box", "class", layer="dependency", source="fltk"),
            _make_node("Fl_Group", "Fl_Group", "class", layer="dependency", source="fltk"),
        ]
        edges = [
            # Aggregates
            _make_edge("e1", "ui::CalcWin", "ui::CalcDisp", "AGGREGATES"),
            _make_edge("e2", "ui::CalcWin", "ui::CalcCtrl", "AGGREGATES"),
            _make_edge("e3", "ui::CalcWin", "Fl_Btn", "AGGREGATES"),
            _make_edge("e4", "ui::CalcWin", "Fl_RBtn", "AGGREGATES"),
            _make_edge("e5", "ui::CalcWin", "Fl_Box", "AGGREGATES"),
            _make_edge("e6", "ui::CalcWin", "Fl_Group", "AGGREGATES"),
            # Depends_on
            _make_edge("e7", "ui::CalcWin", "Fl_Btn", "DEPENDS_ON"),
            _make_edge("e8", "ui::CalcWin", "Fl_RBtn", "DEPENDS_ON"),
            _make_edge("e9", "ui::CalcWin", "Fl_Group", "DEPENDS_ON"),
            _make_edge("e10", "ui::CalcDisp", "Fl_Box", "DEPENDS_ON"),
        ]

        out_nodes, out_edges = collapse_members(nodes, edges)

        node_ids = {n["data"]["id"] for n in out_nodes}

        # CalculatorWindow should show aggregated items in its compartment
        calc_win = next(n for n in out_nodes if n["data"]["id"] == "ui::CalcWin")
        assert "CalculatorDisplay" in calc_win["data"]["label"]
        assert "CalculatorController" in calc_win["data"]["label"]
        assert "Fl_Button" in calc_win["data"]["label"]
        assert "Fl_Box" in calc_win["data"]["label"]

        # All dependency nodes should remain visible (they have DEPENDS_ON edges)
        assert "Fl_Btn" in node_ids
        assert "Fl_RBtn" in node_ids
        assert "Fl_Box" in node_ids
        assert "Fl_Group" in node_ids

        # CalculatorDisplay should remain visible (has DEPENDS_ON to Fl_Box)
        assert "ui::CalcDisp" in node_ids

        # DEPENDS_ON edges should be visible
        edge_triples = {
            (e["data"]["source"], e["data"]["target"], e["data"]["label"])
            for e in out_edges
        }
        assert ("ui::CalcWin", "Fl_Btn", "DEPENDS_ON") in edge_triples
        assert ("ui::CalcWin", "Fl_RBtn", "DEPENDS_ON") in edge_triples
        assert ("ui::CalcWin", "Fl_Group", "DEPENDS_ON") in edge_triples
        assert ("ui::CalcDisp", "Fl_Box", "DEPENDS_ON") in edge_triples

class TestComposedEnumDualVisibility:
    """When a class composes an enum (entity-to-entity composition), the
    enum should stay visible as a separate node AND appear in the
    class's UML compartment."""

    def test_class_composes_enum_stays_visible(self):
        """ErrorType composed by CalculationResult should remain as a
        separate enum node with the COMPOSES edge visible."""
        nodes = [
            _make_node("CalcResult", "CalculationResult", "class"),
            _make_node("ErrorType", "ErrorType", "enum"),
        ]
        edges = [
            _make_edge("e1", "CalcResult", "ErrorType", "COMPOSES"),
        ]

        out_nodes, out_edges = collapse_members(nodes, edges)

        node_ids = {n["data"]["id"] for n in out_nodes}
        assert "ErrorType" in node_ids, "Enum should remain visible as separate node"
        assert "CalcResult" in node_ids

        # COMPOSES edge should be visible
        edge_labels = {
            (e["data"]["source"], e["data"]["target"], e["data"]["label"])
            for e in out_edges
        }
        assert ("CalcResult", "ErrorType", "COMPOSES") in edge_labels

    def test_class_composes_enum_with_enum_values(self):
        """An enum with its own enum_values, composed by a class, should
        keep the enum visible with values collapsed into it."""
        nodes = [
            _make_node("CalcResult", "CalculationResult", "class"),
            _make_node("ErrorType", "ErrorType", "enum"),
            _make_node("ev1", "MALFORMED_STRING", "enum_value"),
            _make_node("ev2", "NULL_INPUT", "enum_value"),
        ]
        edges = [
            _make_edge("e1", "CalcResult", "ErrorType", "COMPOSES"),
            _make_edge("e2", "ErrorType", "ev1", "COMPOSES"),
            _make_edge("e3", "ErrorType", "ev2", "COMPOSES"),
        ]

        out_nodes, out_edges = collapse_members(nodes, edges)

        node_ids = {n["data"]["id"] for n in out_nodes}
        # Enum stays visible
        assert "ErrorType" in node_ids
        # Enum values are collapsed into the enum
        assert "ev1" not in node_ids
        assert "ev2" not in node_ids

    def test_module_composes_enum_uses_parent_not_external(self):
        """A module composes an enum (namespace containment) — this should
        use the parent field mechanism, NOT keep it as a separate node via
        entity-composition preservation. Module is NOT in _OWNER_KINDS, so
        collapse_members doesn't touch module→enum edges at all. The enum
        stays visible simply because it's not being collapsed."""
        nodes = [
            _make_node("mod", "calc_engine", "module"),
            _make_node("ErrorType", "ErrorType", "enum"),
        ]
        edges = [
            _make_edge("e1", "mod", "ErrorType", "COMPOSES"),
        ]

        out_nodes, out_edges = collapse_members(nodes, edges)

        # Module is NOT in _OWNER_KINDS so the module→enum COMPOSES doesn't
        # trigger collapse at all. The enum stays visible by default.
        # The entity-composition preservation logic only applies when a
        # non-module owner (class/interface/struct) composes an entity kind.
        node_ids = {n["data"]["id"] for n in out_nodes}
        assert "ErrorType" in node_ids  # Not collapsed at all — module isn't an owner kind
        assert "mod" in node_ids

    def test_class_composes_interface_stays_visible(self):
        """Previously only classes with DEPENDS_ON stayed visible.
        Now COMPOSES also triggers dual visibility for entity kinds."""
        nodes = [
            _make_node("Owner", "Owner", "class"),
            _make_node("Iface", "IHandler", "interface"),
        ]
        edges = [
            _make_edge("e1", "Owner", "Iface", "COMPOSES"),
        ]

        out_nodes, out_edges = collapse_members(nodes, edges)

        node_ids = {n["data"]["id"] for n in out_nodes}
        assert "Iface" in node_ids
