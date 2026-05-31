"""Tests for mechanism field and references association kind."""

import pytest
from codegraph.diagram import ClassDiagram, Association
from codegraph.models import ClassNode
from backend.ticketing_agent.design.map_to_ontology import map_oo_to_ontology


@pytest.mark.skip(reason="map_oo_to_ontology needs refactoring for atomized types")
class TestMechanismInference:
    """When an aggregates/references association has a mechanism field,
    the appropriate container/smart-ptr dependency should be inferred."""

    def test_aggregates_mechanism_infers_container_dep(self):
        """aggregates with mechanism=std::vector should infer depends_on std::vector."""
        oo = ClassDiagram(
            module_names=["ui"],
            classes=[
                ClassNode(
                    name="CalculatorWindow",
                    module="ui",
                    attributes=[],
                    methods=[],
                ),
            ],
            associations=[
                Association(
                    subject="CalculatorWindow",
                    object="Fl_Button",
                    predicate="aggregates",
                    mechanism="std::vector",
                ),
            ],
        )
        dep_lookup = {"Fl_Button": "Fl_Button"}
        result = map_oo_to_ontology(
            oo, dependency_lookup=dep_lookup, component_id=1
        )

        # Should create depends_on to std::vector
        container_deps = [
            t for t in result.triples
            if t.predicate == "depends_on"
            and t.object_qualified_name == "std::vector"
        ]
        assert len(container_deps) == 1
        assert container_deps[0].subject_qualified_name == "ui::CalculatorWindow"

        # Should also create a node for std::vector
        vector_nodes = [n for n in result.nodes if n.qualified_name == "std::vector"]
        assert len(vector_nodes) == 1
        assert vector_nodes[0].layer == "dependency"

    def test_references_mechanism_unique_ptr_dep(self):
        """references with mechanism=std::unique_ptr should infer depends_on std::unique_ptr."""
        oo = ClassDiagram(
            module_names=["ui"],
            classes=[
                ClassNode(
                    name="CalculatorWindow",
                    module="ui",
                    attributes=[],
                    methods=[],
                ),
            ],
            associations=[
                Association(
                    subject="CalculatorWindow",
                    object="CalculatorEngine",
                    predicate="references",
                    mechanism="std::unique_ptr",
                ),
            ],
        )
        dep_lookup = {"CalculatorEngine": "calculation_engine::CalculatorEngine"}
        result = map_oo_to_ontology(
            oo, dependency_lookup=dep_lookup, component_id=1
        )

        # Should have a REFERENCES triple with mechanism
        ref_triples = [
            t for t in result.triples
            if t.predicate == "references"
            and t.subject_qualified_name == "ui::CalculatorWindow"
        ]
        assert len(ref_triples) == 1
        assert ref_triples[0].mechanism == "std::unique_ptr"

        # Should infer depends_on to std::unique_ptr
        ptr_deps = [
            t for t in result.triples
            if t.predicate == "depends_on"
            and t.object_qualified_name == "std::unique_ptr"
        ]
        assert len(ptr_deps) == 1

        # Should also infer depends_on to the target dependency
        target_deps = [
            t for t in result.triples
            if t.predicate == "depends_on"
            and t.object_qualified_name == "calculation_engine::CalculatorEngine"
        ]
        assert len(target_deps) == 1

    def test_references_raw_pointer_no_container_dep(self):
        """references with mechanism=raw_pointer should NOT add container dependency."""
        oo = ClassDiagram(
            module_names=["ui"],
            classes=[
                ClassNode(
                    name="CalculatorWindow",
                    module="ui",
                    attributes=[],
                    methods=[],
                ),
            ],
            associations=[
                Association(
                    subject="CalculatorWindow",
                    object="Fl_Widget",
                    predicate="references",
                    mechanism="raw_pointer",
                ),
            ],
        )
        dep_lookup = {"Fl_Widget": "Fl_Widget"}
        result = map_oo_to_ontology(
            oo, dependency_lookup=dep_lookup, component_id=1
        )

        # Should infer depends_on to Fl_Widget (the target)
        widget_deps = [
            t for t in result.triples
            if t.predicate == "depends_on"
            and t.object_qualified_name == "Fl_Widget"
        ]
        assert len(widget_deps) == 1

        # Should NOT add std:: dependency for raw_pointer
        stdlib_deps = [
            t for t in result.triples
            if t.predicate == "depends_on"
            and t.object_qualified_name.startswith("std::")
        ]
        assert len(stdlib_deps) == 0, "raw_pointer should not add container dependencies"

    def test_aggregates_mechanism_on_triple(self):
        """The mechanism field should be stored on the triple."""
        oo = ClassDiagram(
            module_names=["ui"],
            classes=[
                ClassNode(
                    name="CalculatorWindow",
                    module="ui",
                    attributes=[],
                    methods=[],
                ),
            ],
            associations=[
                Association(
                    subject="CalculatorWindow",
                    object="Fl_Button",
                    predicate="aggregates",
                    mechanism="std::vector",
                ),
            ],
        )
        dep_lookup = {"Fl_Button": "Fl_Button"}
        result = map_oo_to_ontology(
            oo, dependency_lookup=dep_lookup, component_id=1
        )

        agg_triples = [
            t for t in result.triples
            if t.predicate == "aggregates"
        ]
        assert len(agg_triples) == 1
        assert agg_triples[0].mechanism == "std::vector"

    def test_mechanism_shared_ptr(self):
        """references with mechanism=std::shared_ptr should infer depends_on std::shared_ptr."""
        oo = ClassDiagram(
            module_names=["ui"],
            classes=[
                ClassNode(
                    name="CalculatorWindow",
                    module="ui",
                    attributes=[],
                    methods=[],
                ),
            ],
            associations=[
                Association(
                    subject="CalculatorWindow",
                    object="SharedWidget",
                    predicate="references",
                    mechanism="std::shared_ptr",
                ),
            ],
        )
        dep_lookup = {"SharedWidget": "SharedWidget"}
        result = map_oo_to_ontology(
            oo, dependency_lookup=dep_lookup, component_id=1
        )

        ptr_deps = [
            t for t in result.triples
            if t.predicate == "depends_on"
            and t.object_qualified_name == "std::shared_ptr"
        ]
        assert len(ptr_deps) == 1

    def test_mechanism_duplicate_container_dep(self):
        """Two associations with the same container type should not duplicate."""
        oo = ClassDiagram(
            module_names=["ui"],
            classes=[
                ClassNode(
                    name="CalculatorWindow",
                    module="ui",
                    attributes=[],
                    methods=[],
                ),
            ],
            associations=[
                Association(
                    subject="CalculatorWindow",
                    object="Fl_Button",
                    predicate="aggregates",
                    mechanism="std::vector",
                ),
                Association(
                    subject="CalculatorWindow",
                    object="Fl_Box",
                    predicate="aggregates",
                    mechanism="std::vector",
                ),
            ],
        )
        dep_lookup = {"Fl_Button": "Fl_Button", "Fl_Box": "Fl_Box"}
        result = map_oo_to_ontology(
            oo, dependency_lookup=dep_lookup, component_id=1
        )

        vector_deps = [
            t for t in result.triples
            if t.predicate == "depends_on"
            and t.object_qualified_name == "std::vector"
        ]
        assert len(vector_deps) == 1, "Should not duplicate std::vector depends_on"

    def test_kinds_other_than_aggregates_references_ignore_mechanism(self):
        """Associates/depends_on/invokes should not use mechanism field."""
        oo = ClassDiagram(
            module_names=["ui"],
            classes=[
                ClassNode(
                    name="CalculatorWindow",
                    module="ui",
                    attributes=[],
                    methods=[],
                ),
            ],
            associations=[
                Association(
                    subject="CalculatorWindow",
                    object="Logger",
                    predicate="invokes",
                    mechanism="std::shared_ptr",
                ),
            ],
        )
        dep_lookup = {"Logger": "Logger"}
        result = map_oo_to_ontology(
            oo, dependency_lookup=dep_lookup, component_id=1
        )

        # invokes should not infer std::shared_ptr dependency
        ptr_deps = [
            t for t in result.triples
            if t.predicate == "depends_on"
            and t.object_qualified_name == "std::shared_ptr"
        ]
        assert len(ptr_deps) == 0

        # Mechanism should NOT be stored on invokes triple
        invokes_triples = [
            t for t in result.triples
            if t.predicate == "invokes"
        ]
        assert len(invokes_triples) == 1
        assert invokes_triples[0].mechanism == ""