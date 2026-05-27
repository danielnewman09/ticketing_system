"""Tests for map_oo_to_ontology dependency resolution."""

import pytest
from backend.codebase.schemas import (
    AssociationSchema,
    AttributeSchema,
    ClassSchema,
    DesignSchema,
    MethodSchema,
    OODesignSchema,
)
from backend.ticketing_agent.design.map_to_ontology import map_oo_to_ontology


class TestDependencyLookupInAssociations:
    """When an association targets a dependency class, the triple should
    use the dependency's qualified name from the lookup."""

    def test_association_to_dependency_resolved(self):
        oo = OODesignSchema(
            modules=["calc"],
            classes=[
                ClassSchema(
                    name="Calculator",
                    module="calc",
                    attributes=[],
                    methods=[],
                ),
            ],
            associations=[
                AssociationSchema(
                    from_class="Calculator",
                    to_class="Fl_Window",
                    kind="aggregates",
                    description="Calculator window",
                ),
            ],
        )
        dep_lookup = {"Fl_Window": "Fl_Window"}
        result = map_oo_to_ontology(
            oo, dependency_lookup=dep_lookup, component_id=1
        )
        # There should be a triple: calc::Calculator -[aggregates]-> Fl_Window
        dep_agg = [
            t for t in result.triples
            if t.predicate == "aggregates" and t.object_qualified_name == "Fl_Window"
        ]
        assert len(dep_agg) == 1
        # There should also be a dependency stub node for Fl_Window
        dep_node = [n for n in result.nodes if n.qualified_name == "Fl_Window"]
        assert len(dep_node) == 1
        assert dep_node[0].source_type == "dependency"
        assert dep_node[0].is_intercomponent is True

    def test_association_to_dependency_with_namespaced_qname(self):
        oo = OODesignSchema(
            modules=["calc"],
            classes=[
                ClassSchema(
                    name="Calculator",
                    module="calc",
                    attributes=[],
                    methods=[],
                ),
            ],
            associations=[
                AssociationSchema(
                    from_class="Calculator",
                    to_class="string",
                    kind="depends_on",
                    description="Uses strings",
                ),
            ],
        )
        dep_lookup = {"string": "std::string"}
        result = map_oo_to_ontology(
            oo, dependency_lookup=dep_lookup
        )
        dep_triples = [
            t for t in result.triples
            if t.object_qualified_name == "std::string"
        ]
        assert len(dep_triples) >= 1
        dep_node = [n for n in result.nodes if n.qualified_name == "std::string"]
        assert len(dep_node) == 1
        assert dep_node[0].source_type == "dependency"


class TestDependencyLookupInInheritance:
    """When a class inherits from a dependency class, the generalizes
    triple should use the dependency's qualified name."""

    def test_inherits_from_dependency(self):
        oo = OODesignSchema(
            modules=["ui"],
            classes=[
                ClassSchema(
                    name="MyWindow",
                    module="ui",
                    inherits_from=["Fl_Window"],
                    attributes=[],
                    methods=[],
                ),
            ],
        )
        dep_lookup = {"Fl_Window": "Fl_Window"}
        result = map_oo_to_ontology(
            oo, dependency_lookup=dep_lookup
        )
        gen_triples = [
            t for t in result.triples
            if t.predicate == "generalizes" and t.object_qualified_name == "Fl_Window"
        ]
        assert len(gen_triples) == 1
        dep_node = [n for n in result.nodes if n.qualified_name == "Fl_Window"]
        assert len(dep_node) == 1
        assert dep_node[0].source_type == "dependency"


class TestDependsOnFromTypeSignatures:
    """When an attribute or method return type references a dependency class,
    a depends_on triple should be synthesized from the design class."""

    def test_attribute_type_references_dependency(self):
        oo = OODesignSchema(
            modules=["ui"],
            classes=[
                ClassSchema(
                    name="Calculator",
                    module="ui",
                    attributes=[
                        AttributeSchema(
                            name="display",
                            type_name="Fl_Output",
                            visibility="private",
                            description="The display",
                        ),
                    ],
                    methods=[],
                ),
            ],
        )
        dep_lookup = {"Fl_Output": "Fl_Output"}
        result = map_oo_to_ontology(
            oo, dependency_lookup=dep_lookup
        )
        dep_triples = [
            t for t in result.triples
            if t.predicate == "depends_on"
            and t.subject_qualified_name == "ui::Calculator"
            and t.object_qualified_name == "Fl_Output"
        ]
        assert len(dep_triples) == 1
        dep_node = [n for n in result.nodes if n.qualified_name == "Fl_Output"]
        assert len(dep_node) == 1
        assert dep_node[0].source_type == "dependency"

    def test_pointer_type_still_resolves(self):
        """Fl_Output* should still resolve Fl_Output."""
        oo = OODesignSchema(
            modules=["ui"],
            classes=[
                ClassSchema(
                    name="Calculator",
                    module="ui",
                    attributes=[
                        AttributeSchema(
                            name="display",
                            type_name="Fl_Output*",
                            visibility="private",
                            description="Pointer to display",
                        ),
                    ],
                    methods=[],
                ),
            ],
        )
        dep_lookup = {"Fl_Output": "Fl_Output"}
        result = map_oo_to_ontology(
            oo, dependency_lookup=dep_lookup
        )
        dep_triples = [
            t for t in result.triples
            if t.predicate == "depends_on"
            and t.object_qualified_name == "Fl_Output"
        ]
        assert len(dep_triples) == 1

    def test_no_depends_on_for_design_internal_classes(self):
        """If the type name matches a design class, no depends_on should be created."""
        oo = OODesignSchema(
            modules=["calc"],
            classes=[
                ClassSchema(
                    name="Calculator",
                    module="calc",
                    attributes=[
                        AttributeSchema(
                            name="result",
                            type_name="CalculationResult",
                            visibility="private",
                            description="The result",
                        ),
                    ],
                    methods=[],
                ),
                ClassSchema(
                    name="CalculationResult",
                    module="calc",
                    attributes=[],
                    methods=[],
                ),
            ],
        )
        dep_lookup = {}
        result = map_oo_to_ontology(
            oo, dependency_lookup=dep_lookup
        )
        dep_triples = [
            t for t in result.triples if t.predicate == "depends_on"
        ]
        assert len(dep_triples) == 0


class TestAggregatesInfersDependsOn:
    """When a design class aggregates an external dependency class,
    a depends_on triple should be inferred even if the design agent
    didn't explicitly include one."""

    def test_aggregates_dependency_infers_depends_on(self):
        """aggregates to a dependency class should auto-add depends_on."""
        oo = OODesignSchema(
            modules=["ui"],
            classes=[
                ClassSchema(
                    name="CalculatorWindow",
                    module="ui",
                    attributes=[],
                    methods=[],
                ),
            ],
            associations=[
                AssociationSchema(
                    from_class="CalculatorWindow",
                    to_class="Fl_Button",
                    kind="aggregates",
                    description="Button widget",
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
            and t.subject_qualified_name == "ui::CalculatorWindow"
            and t.object_qualified_name == "Fl_Button"
        ]
        assert len(agg_triples) == 1

        dep_triples = [
            t for t in result.triples
            if t.predicate == "depends_on"
            and t.subject_qualified_name == "ui::CalculatorWindow"
            and t.object_qualified_name == "Fl_Button"
        ]
        assert len(dep_triples) == 1, (
            f"Expected 1 inferred depends_on triple, got {dep_triples}. "
            f"All triples: {[(t.predicate, t.subject_qualified_name, t.object_qualified_name) for t in result.triples]}"
        )

    def test_aggregates_dependency_no_duplicate_depends_on(self):
        """If the agent already provided depends_on, don't duplicate it."""
        oo = OODesignSchema(
            modules=["ui"],
            classes=[
                ClassSchema(
                    name="CalculatorWindow",
                    module="ui",
                    attributes=[],
                    methods=[],
                ),
            ],
            associations=[
                AssociationSchema(
                    from_class="CalculatorWindow",
                    to_class="Fl_Button",
                    kind="aggregates",
                    description="Button widget",
                ),
                AssociationSchema(
                    from_class="CalculatorWindow",
                    to_class="Fl_Button",
                    kind="depends_on",
                    description="Uses Fl_Button",
                ),
            ],
        )
        dep_lookup = {"Fl_Button": "Fl_Button"}
        result = map_oo_to_ontology(
            oo, dependency_lookup=dep_lookup, component_id=1
        )

        dep_triples = [
            t for t in result.triples
            if t.predicate == "depends_on"
            and t.subject_qualified_name == "ui::CalculatorWindow"
            and t.object_qualified_name == "Fl_Button"
        ]
        assert len(dep_triples) == 1, (
            f"Expected exactly 1 depends_on triple (no duplicates), got {len(dep_triples)}"
        )

    def test_aggregates_design_class_no_depends_on_inferred(self):
        """Aggregating a design-internal class should NOT infer depends_on."""
        oo = OODesignSchema(
            modules=["ui"],
            classes=[
                ClassSchema(
                    name="CalculatorWindow",
                    module="ui",
                    attributes=[],
                    methods=[],
                ),
                ClassSchema(
                    name="CalculatorDisplay",
                    module="ui",
                    attributes=[],
                    methods=[],
                ),
            ],
            associations=[
                AssociationSchema(
                    from_class="CalculatorWindow",
                    to_class="CalculatorDisplay",
                    kind="aggregates",
                    description="Display component",
                ),
            ],
        )
        dep_lookup = {}
        result = map_oo_to_ontology(
            oo, dependency_lookup=dep_lookup, component_id=1
        )

        dep_triples = [
            t for t in result.triples
            if t.predicate == "depends_on"
        ]
        assert len(dep_triples) == 0, (
            f"No depends_on should be inferred for design-internal aggregates, "
            f"got {dep_triples}"
        )

    def test_aggregates_multiple_dependencies(self):
        """Multiple aggregates to different dependencies should each infer depends_on."""
        oo = OODesignSchema(
            modules=["ui"],
            classes=[
                ClassSchema(
                    name="CalculatorWindow",
                    module="ui",
                    attributes=[],
                    methods=[],
                ),
            ],
            associations=[
                AssociationSchema(
                    from_class="CalculatorWindow",
                    to_class="Fl_Button",
                    kind="aggregates",
                    description="Button",
                ),
                AssociationSchema(
                    from_class="CalculatorWindow",
                    to_class="Fl_Box",
                    kind="aggregates",
                    description="Box",
                ),
            ],
        )
        dep_lookup = {"Fl_Button": "Fl_Button", "Fl_Box": "Fl_Box"}
        result = map_oo_to_ontology(
            oo, dependency_lookup=dep_lookup, component_id=1
        )

        dep_triples = [
            t for t in result.triples
            if t.predicate == "depends_on"
            and t.subject_qualified_name == "ui::CalculatorWindow"
        ]
        dep_targets = {t.object_qualified_name for t in dep_triples}
        assert "Fl_Button" in dep_targets
        assert "Fl_Box" in dep_targets


class TestNoDependencyLookup:
    """Without a dependency_lookup, behavior should be unchanged."""

    def test_association_to_unknown_name_uses_bare_name(self):
        oo = OODesignSchema(
            modules=["calc"],
            classes=[
                ClassSchema(name="Calculator", module="calc", attributes=[], methods=[]),
            ],
            associations=[
                AssociationSchema(
                    from_class="Calculator",
                    to_class="RandomThing",
                    kind="associates",
                    description="Something",
                ),
            ],
        )
        result = map_oo_to_ontology(oo)
        # Triple uses bare name (no resolution)
        assoc_triples = [
            t for t in result.triples
            if t.predicate == "associates" and t.object_qualified_name == "RandomThing"
        ]
        assert len(assoc_triples) == 1
        # No dependency stub node
        random_nodes = [n for n in result.nodes if n.qualified_name == "RandomThing"]
        assert len(random_nodes) == 0

class TestAssociationSchemaKinds:
    """AssociationSchema.kind should accept composes and returns."""

    def test_composes_association(self):
        assoc = AssociationSchema(
            from_class="CalculatorResult",
            to_class="ErrorType",
            kind="composes",
            description="ErrorType member variable",
        )
        assert assoc.kind == "composes"

    def test_returns_association(self):
        assoc = AssociationSchema(
            from_class="CalculatorEngine",
            to_class="CalculationResult",
            kind="returns",
            description="Returns calculation result",
        )
        assert assoc.kind == "returns"
