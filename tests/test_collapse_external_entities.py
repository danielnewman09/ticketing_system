"""Tests for collapse_members preserving external entity nodes with non-COMPOSES edges.

When an aggregated class/interface/enum/struct also has non-containment,
non-COMPOSES edges (e.g. REFERENCES, DEPENDS_ON, GENERALIZES), the node
should remain visible in the graph.

COMPOSES is an implicit relationship (like dependency injection) and
should never appear as a visible edge in the graph.  Entity kinds
(class/interface/enum/struct) composed by non-module owners are NOT
added as line items in the owner's UML compartment — their typed
attributes (e.g. ``error_signal: CalculationError``) already convey
the reference.
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
    """Aggregated entity nodes (class/interface/enum/struct) with
    non-COMPOSES non-containment edges are kept as external nodes.
    They are NOT shown as UML compartment lines in the owner node."""

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
        # Fl_Button should still be visible (has DEPENDS_ON edge)
        assert "FlBtn" in node_ids
        # CalculatorWindow should still be visible
        assert "CalcWin" in node_ids
        # CalculatorWindow label should NOT contain Fl_Button as a compartment
        # line — entity kinds are not added to the owner's UML compartment
        calc = next(n for n in out_nodes if n["data"]["id"] == "CalcWin")
        assert "Fl_Button" not in calc["data"]["label"]
        # DEPENDS_ON edge should be preserved (not COMPOSES)
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
        # Fl_Box should remain visible (target of DEPENDS_ON, also aggregated and has DEPENDS_ON)
        assert "FlBox" in node_ids
        # Entity kinds are NOT added as compartment lines in the owner
        calc = next(n for n in out_nodes if n["data"]["id"] == "CalcWin")
        assert "CalculatorDisplay" not in calc["data"]["label"]
        assert "Fl_Box" not in calc["data"]["label"]
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
        # Entity kinds are NOT shown in owner compartment
        owner = next(n for n in out_nodes if n["data"]["id"] == "MyClass")
        assert "AggregatedClass" not in owner["data"]["label"]

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
    """Aggregated entity nodes WITHOUT non-COMPOSES non-containment edges
    should be fully collapsed (removed from the graph).  COMPOSES is
    implicit and does not justify keeping an entity visible."""

    def test_aggregated_class_no_edges_is_removed(self):
        """An aggregated class with only AGGREGATES edge from the owner
        and no other non-COMPOSES edges should be removed from the graph.
        COMPOSES/AGGREGATES are implicit relationships."""
        nodes = [
            _make_node("Owner", "Owner", "class"),
            _make_node("Agg", "InnerClass", "class"),
        ]
        edges = [
            _make_edge("e1", "Owner", "Agg", "AGGREGATES"),
        ]

        out_nodes, out_edges = collapse_members(nodes, edges)

        node_ids = {n["data"]["id"] for n in out_nodes}
        # InnerClass with only containment edge is removed
        assert "Agg" not in node_ids
        # Entity kinds are NOT added as compartment lines
        owner = next(n for n in out_nodes if n["data"]["id"] == "Owner")
        assert "InnerClass" not in owner["data"]["label"]
        # No AGGREGATES edge preserved — COMPOSES/AGGREGATES are implicit
        # (AGGREGATES to a non-external entity is removed)
        edge_labels = {(e["data"]["source"], e["data"]["target"], e["data"]["label"]) for e in out_edges}
        assert ("Owner", "Agg", "AGGREGATES") not in edge_labels

    def test_aggregated_class_only_containment_edges_is_removed(self):
        """An aggregated class with only COMPOSES/CONTAINS edges should
        be removed from the graph."""
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
        # InnerClass with only containment edges is removed
        assert "Agg" not in node_ids
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


class TestComposesImplicit:
    """COMPOSES is an implicit relationship and should never be visible
    in the graph.  Composed entity kinds are not shown as UML compartment
    lines in the owner."""

    def test_composes_entity_not_in_compartment(self):
        """COMPOSES edge to a class node should NOT add it as a line
        in the owner's UML compartment. Entity kinds are not shown
        as member lines — their typed attributes convey the reference."""
        nodes = [
            _make_node("Owner", "Owner", "class"),
            _make_node("Nested", "NestedClass", "class"),
        ]
        edges = [
            _make_edge("e1", "Owner", "Nested", "COMPOSES"),
        ]

        out_nodes, out_edges = collapse_members(nodes, edges)

        node_ids = {n["data"]["id"] for n in out_nodes}
        # Entity with only COMPOSES edges is removed (no external edges)
        assert "Nested" not in node_ids
        # No COMPOSES edge visible
        edge_labels = {(e["data"]["source"], e["data"]["target"], e["data"]["label"]) for e in out_edges}
        assert ("Owner", "Nested", "COMPOSES") not in edge_labels

    def test_composes_entity_not_visible_without_external_edges(self):
        """A composed entity with ONLY COMPOSES edges is removed from the graph.
        COMPOSES is implicit and doesn't justify keeping the entity visible."""
        nodes = [
            _make_node("Owner", "Owner", "class"),
            _make_node("Nested", "NestedClass", "class"),
        ]
        edges = [
            _make_edge("e1", "Owner", "Nested", "COMPOSES"),
        ]

        out_nodes, _ = collapse_members(nodes, edges)

        node_ids = {n["data"]["id"] for n in out_nodes}
        assert "Nested" not in node_ids

    def test_composes_plus_references_keeps_entity(self):
        """COMPOSES + REFERENCES should keep the entity visible via
        the REFERENCES edge, not via COMPOSES."""
        nodes = [
            _make_node("Owner", "Owner", "class"),
            _make_node("Nested", "NestedClass", "class"),
            _make_node("Dep", "Dep", "class", layer="dependency"),
        ]
        edges = [
            _make_edge("e1", "Owner", "Nested", "COMPOSES"),
            _make_edge("e2", "Nested", "Dep", "REFERENCES"),
        ]

        out_nodes, out_edges = collapse_members(nodes, edges)

        node_ids = {n["data"]["id"] for n in out_nodes}
        # Nested stays visible because of REFERENCES edge
        assert "Nested" in node_ids
        # REFERENCES edge is visible
        edge_labels = {(e["data"]["source"], e["data"]["target"], e["data"]["label"]) for e in out_edges}
        assert ("Nested", "Dep", "REFERENCES") in edge_labels
        # COMPOSES edge is NOT visible
        assert ("Owner", "Nested", "COMPOSES") not in edge_labels
        # Entity not shown as compartment line
        owner = next(n for n in out_nodes if n["data"]["id"] == "Owner")
        assert "NestedClass" not in owner["data"]["label"]


class TestRealWorldScenario:
    """Test the full CalculatorWindow scenario from the user's description."""

    def test_calculator_window_scenario(self):
        """Matches the real data in the system:
        CalculatorWindow AGGREGATES fl_button objects (Compound),
        also has DEPENDS_ON to them. The fl_button should appear
        as an external node with the DEPENDS_ON edge visible, but
        NOT as a compartment line in CalculatorWindow.
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

        # CalculatorWindow should NOT show entity kinds as compartment lines
        calc_win = next(n for n in out_nodes if n["data"]["id"] == "ui::CalcWin")
        assert "CalculatorDisplay" not in calc_win["data"]["label"]
        assert "CalculatorController" not in calc_win["data"]["label"]
        assert "Fl_Button" not in calc_win["data"]["label"]
        assert "Fl_Box" not in calc_win["data"]["label"]

        # Dependency nodes with DEPENDS_ON edges should remain visible
        assert "Fl_Btn" in node_ids
        assert "Fl_RBtn" in node_ids
        assert "Fl_Box" in node_ids
        assert "Fl_Group" in node_ids

        # CalculatorDisplay should remain visible (has DEPENDS_ON to Fl_Box)
        assert "ui::CalcDisp" in node_ids

        # CalculatorController has only AGGREGATES edges → removed
        # (entity with only containment, no non-containment external edges)
        assert "ui::CalcCtrl" not in node_ids

        # DEPENDS_ON edges should be visible
        edge_triples = {
            (e["data"]["source"], e["data"]["target"], e["data"]["label"])
            for e in out_edges
        }
        assert ("ui::CalcWin", "Fl_Btn", "DEPENDS_ON") in edge_triples
        assert ("ui::CalcWin", "Fl_RBtn", "DEPENDS_ON") in edge_triples
        assert ("ui::CalcWin", "Fl_Group", "DEPENDS_ON") in edge_triples
        assert ("ui::CalcDisp", "Fl_Box", "DEPENDS_ON") in edge_triples

        # AGGREGATES edges should NOT be visible for entities without
        # non-containment external edges
        assert ("ui::CalcWin", "ui::CalcCtrl", "AGGREGATES") not in edge_triples


class TestComposedEnumNotInCompartment:
    """When a class composes an enum, the enum is NOT added as a
    compartment line in the owner's UML label.  The enum should only
    remain visible as a separate node if it has non-COMPOSES external
    edges (REFERENCES, DEPENDS_ON, etc.)."""

    def test_class_composes_enum_not_in_compartment(self):
        """Enum composed by CalculationResult should NOT appear as a line
        in CalculationResult's compartment. With only COMPOSES edges
        and no external references, the enum is removed from the graph."""
        nodes = [
            _make_node("CalcResult", "CalculationResult", "class"),
            _make_node("ErrorType", "ErrorType", "enum"),
        ]
        edges = [
            _make_edge("e1", "CalcResult", "ErrorType", "COMPOSES"),
        ]

        out_nodes, out_edges = collapse_members(nodes, edges)

        node_ids = {n["data"]["id"] for n in out_nodes}
        # Enum with only COMPOSES edge is removed from the graph
        assert "ErrorType" not in node_ids
        assert "CalcResult" in node_ids

        # No COMPOSES edge visible
        edge_labels = {
            (e["data"]["source"], e["data"]["target"], e["data"]["label"])
            for e in out_edges
        }
        assert ("CalcResult", "ErrorType", "COMPOSES") not in edge_labels

        # Enum NOT shown as compartment line in owner
        owner = next(n for n in out_nodes if n["data"]["id"] == "CalcResult")
        assert "ErrorType" not in owner["data"]["label"]

    def test_class_composes_enum_with_references_stays_visible(self):
        """Enum composed by a class AND having REFERENCES edge should
        stay visible (via external_entity_ids) but NOT appear as a
        compartment line."""
        nodes = [
            _make_node("CalcResult", "CalculationResult", "class"),
            _make_node("ErrorType", "CalculationError", "enum"),
            _make_node("Ext", "ExternalDep", "class"),
        ]
        edges = [
            _make_edge("e1", "CalcResult", "ErrorType", "COMPOSES"),
            _make_edge("e2", "CalcResult", "ErrorType", "REFERENCES"),
        ]

        out_nodes, out_edges = collapse_members(nodes, edges)

        node_ids = {n["data"]["id"] for n in out_nodes}
        # Enum stays visible because of REFERENCES edge
        assert "ErrorType" in node_ids
        # REFERENCES edge visible
        edge_labels = {
            (e["data"]["source"], e["data"]["target"], e["data"]["label"])
            for e in out_edges
        }
        assert ("CalcResult", "ErrorType", "REFERENCES") in edge_labels
        # COMPOSES edge NOT visible
        assert ("CalcResult", "ErrorType", "COMPOSES") not in edge_labels
        # Enum NOT shown as compartment line
        owner = next(n for n in out_nodes if n["data"]["id"] == "CalcResult")
        assert "CalculationError" not in owner["data"]["label"]

    def test_class_composes_enum_with_enum_values(self):
        """An enum with its own enum_values, composed by a class without
        external edges — the enum and its values are all removed from
        the graph."""
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
        # Enum with only COMPOSES edges is removed
        assert "ErrorType" not in node_ids
        # Enum values are also collapsed (they belong to the removed enum)
        assert "ev1" not in node_ids
        assert "ev2" not in node_ids

    def test_class_composes_enum_with_enum_values_and_references(self):
        """An enum with enum_values, composed by a class, and also
        having REFERENCES should stay visible with values collapsed
        into it."""
        nodes = [
            _make_node("CalcResult", "CalculationResult", "class"),
            _make_node("ErrorType", "CalculationError", "enum"),
            _make_node("ev1", "MALFORMED_STRING", "enum_value"),
            _make_node("ev2", "NULL_INPUT", "enum_value"),
        ]
        edges = [
            _make_edge("e1", "CalcResult", "ErrorType", "COMPOSES"),
            _make_edge("e2", "CalcResult", "ErrorType", "REFERENCES"),
            _make_edge("e3", "ErrorType", "ev1", "COMPOSES"),
            _make_edge("e4", "ErrorType", "ev2", "COMPOSES"),
        ]

        out_nodes, out_edges = collapse_members(nodes, edges)

        node_ids = {n["data"]["id"] for n in out_nodes}
        # Enum stays visible (REFERENCES edge)
        assert "ErrorType" in node_ids
        # Enum values are collapsed into the enum
        assert "ev1" not in node_ids
        assert "ev2" not in node_ids
        # Enum values ARE shown in the enum's label
        enum_node = next(n for n in out_nodes if n["data"]["id"] == "ErrorType")
        assert "MALFORMED_STRING" in enum_node["data"]["label"]
        assert "NULL_INPUT" in enum_node["data"]["label"]
        # REFERENCES edge visible
        edge_labels = {
            (e["data"]["source"], e["data"]["target"], e["data"]["label"])
            for e in out_edges
        }
        assert ("CalcResult", "ErrorType", "REFERENCES") in edge_labels
        # COMPOSES edge NOT visible
        assert ("CalcResult", "ErrorType", "COMPOSES") not in edge_labels
        # Entity NOT shown as compartment line in owner
        owner = next(n for n in out_nodes if n["data"]["id"] == "CalcResult")
        assert "CalculationError" not in owner["data"]["label"]

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
        node_ids = {n["data"]["id"] for n in out_nodes}
        assert "ErrorType" in node_ids  # Not collapsed at all — module isn't an owner kind
        assert "mod" in node_ids

    def test_class_composes_interface_without_external_edges(self):
        """An interface composed by a class with no other edges should be
        removed from the graph (COMPOSES is implicit)."""
        nodes = [
            _make_node("Owner", "Owner", "class"),
            _make_node("Iface", "IHandler", "interface"),
        ]
        edges = [
            _make_edge("e1", "Owner", "Iface", "COMPOSES"),
        ]

        out_nodes, out_edges = collapse_members(nodes, edges)

        node_ids = {n["data"]["id"] for n in out_nodes}
        # Interface with only COMPOSES edge is removed
        assert "Iface" not in node_ids
        # No COMPOSES edge visible
        edge_labels = {(e["data"]["source"], e["data"]["target"], e["data"]["label"]) for e in out_edges}
        assert ("Owner", "Iface", "COMPOSES") not in edge_labels

    def test_class_composes_interface_with_references_stays_visible(self):
        """An interface composed by a class AND having REFERENCES should
        stay visible (via external_entity_ids) but NOT appear as a
        compartment line."""
        nodes = [
            _make_node("Owner", "Owner", "class"),
            _make_node("Iface", "IHandler", "interface"),
            _make_node("Dep", "ExternalDep", "class"),
        ]
        edges = [
            _make_edge("e1", "Owner", "Iface", "COMPOSES"),
            _make_edge("e2", "Iface", "Dep", "REFERENCES"),
        ]

        out_nodes, out_edges = collapse_members(nodes, edges)

        node_ids = {n["data"]["id"] for n in out_nodes}
        assert "Iface" in node_ids
        # REFERENCES edge visible
        edge_labels = {(e["data"]["source"], e["data"]["target"], e["data"]["label"]) for e in out_edges}
        assert ("Iface", "Dep", "REFERENCES") in edge_labels
        # COMPOSES edge NOT visible
        assert ("Owner", "Iface", "COMPOSES") not in edge_labels


class TestComposesEdgeRemoval:
    """Verify that COMPOSES edges are never visible in the graph output,
    even for scenarios where other edge types are preserved."""

    def test_no_composes_edges_in_output(self):
        """After collapse_members, no COMPOSES edges should appear in
        the output edges list."""
        nodes = [
            _make_node("Owner", "Owner", "class"),
            _make_node("Attr", "some_attr", "attribute"),
            _make_node("Entity", "SomeEntity", "class"),
            _make_node("Dep", "Dep", "class"),
        ]
        edges = [
            _make_edge("e1", "Owner", "Attr", "COMPOSES"),
            _make_edge("e2", "Owner", "Entity", "COMPOSES"),
            _make_edge("e3", "Entity", "Dep", "REFERENCES"),
        ]

        out_nodes, out_edges = collapse_members(nodes, edges)

        edge_labels = {e["data"]["label"] for e in out_edges}
        assert "COMPOSES" not in edge_labels
        # REFERENCES should still be present
        assert "REFERENCES" in edge_labels

    def test_composes_between_two_entities_removed(self):
        """COMPOSES edge between two entity nodes is never shown."""
        nodes = [
            _make_node("A", "ClassA", "class"),
            _make_node("B", "ClassB", "class"),
        ]
        edges = [
            _make_edge("e1", "A", "B", "COMPOSES"),
        ]

        out_nodes, out_edges = collapse_members(nodes, edges)

        edge_labels = {e["data"]["label"] for e in out_edges}
        assert "COMPOSES" not in edge_labels