"""Tests for design_data read models — updated for codegraph atomized types."""

import pytest

from codegraph.models import (
    ClassNode,
    InterfaceNode,
    EnumNode,
    UnionNode,
    ModuleNode,
    MethodNode,
    AttributeNode,
    EnumValueNode,
)
from codegraph.diagram import ClassDiagram, Association


class TestClassNode:
    def test_minimal_creation(self):
        node = ClassNode(
            name="Calculator",
            qualified_name="calc::Calculator",
            kind="class",
            layer="design",
        )
        assert node.name == "Calculator"
        assert node.qualified_name == "calc::Calculator"
        assert node.kind == "class"
        assert node.layer == "design"

    def test_all_fields(self):
        node = ClassNode(
            name="calculate",
            qualified_name="calc::Calculator",
            kind="class",
            layer="design",
            brief_description="Adds two numbers",
            is_abstract=False,
            is_final=False,
        )
        assert node.is_abstract is False
        assert node.is_final is False

    def test_dependency_layer(self):
        node = ClassNode(
            name="Fl_Button",
            qualified_name="Fl_Button",
            kind="class",
            layer="dependency",
            source="fltk",
        )
        assert node.layer == "dependency"
        assert node.source == "fltk"


class TestAttributeNode:
    def test_creation(self):
        attr = AttributeNode(
            name="result_",
            qualified_name="calc::Calculator::result_",
            kind="attribute",
            layer="design",
            type_signature="double",
            protection="private",
        )
        assert attr.type_signature == "double"
        assert attr.protection == "private"


class TestMethodNode:
    def test_creation(self):
        method = MethodNode(
            name="add",
            qualified_name="calc::Calculator::add",
            kind="method",
            layer="design",
            type_signature="double",
            argsstring="(double x, double y)",
            protection="public",
        )
        assert method.argsstring == "(double x, double y)"
        assert method.protection == "public"


class TestEnumValueNode:
    def test_creation(self):
        val = EnumValueNode(
            name="ADD",
            qualified_name="calc::Operation::ADD",
            kind="enumvalue",
            layer="design",
        )
        assert val.name == "ADD"


class TestClassNodeRelationships:
    def test_minimal(self):
        cls = ClassNode(
            name="Calculator",
            qualified_name="calc::Calculator",
            kind="class",
            layer="design",
            module="calc",
        )
        assert cls.module == "calc"
        # Relationships are neomodel managers — existence check doesn't need Neo4j
        assert hasattr(cls, 'attributes')
        assert hasattr(cls, 'methods')
        assert cls.base_classes == []

    def test_as_built_class(self):
        cls = ClassNode(
            name="Calculator",
            qualified_name="calc::Calculator",
            kind="class",
            layer="as-built",
            module="calc",
            file_path="src/calculator.hpp",
            line_number=10,
        )
        assert cls.layer == "as-built"
        assert cls.line_number == 10


class TestInterfaceNode:
    def test_creation(self):
        iface = InterfaceNode(
            name="ICalculator",
            qualified_name="calc::ICalculator",
            kind="interface",
            layer="design",
            module="calc",
            is_abstract=True,
        )
        assert iface.is_abstract is True


class TestEnumNode:
    def test_creation(self):
        enum = EnumNode(
            name="Operation",
            qualified_name="calc::Operation",
            kind="enum",
            layer="design",
            module="calc",
        )
        assert enum.name == "Operation"


class TestModuleNode:
    def test_creation(self):
        mod = ModuleNode(
            name="calc",
            qualified_name="calc",
            kind="module",
            layer="design",
        )
        assert mod.name == "calc"
        assert mod.qualified_name == "calc"


class TestAssociation:
    def test_minimal(self):
        assoc = Association(
            subject="calc::Calculator",
            predicate="aggregates",
            object="calc::Result",
        )
        assert assoc.subject == "calc::Calculator"
        assert assoc.predicate == "aggregates"
        assert assoc.mechanism == ""

    def test_with_mechanism(self):
        assoc = Association(
            subject="calc::Calculator",
            predicate="references",
            object="calc::Result",
            mechanism="std::unique_ptr",
        )
        assert assoc.mechanism == "std::unique_ptr"


class TestClassDiagram:
    def test_minimal(self):
        diagram = ClassDiagram()
        assert diagram.classes == []
        assert diagram.interfaces == []
        assert diagram.enums == []
        assert diagram.associations == []

    def test_with_entities(self):
        diagram = ClassDiagram(
            module_names=["calc"],
            classes=[
                ClassNode(
                    name="Calculator",
                    qualified_name="calc::Calculator",
                    kind="class",
                    layer="design",
                    module="calc",
                ),
            ],
            interfaces=[
                InterfaceNode(
                    name="ICalculator",
                    qualified_name="calc::ICalculator",
                    kind="interface",
                    layer="design",
                    module="calc",
                ),
            ],
            enums=[
                EnumNode(
                    name="Operation",
                    qualified_name="calc::Operation",
                    kind="enum",
                    layer="design",
                    module="calc",
                ),
            ],
            associations=[
                Association(
                    subject="calc::Calculator",
                    predicate="realizes",
                    object="calc::ICalculator",
                ),
            ],
        )
        assert len(diagram.classes) == 1
        assert len(diagram.interfaces) == 1
        assert len(diagram.enums) == 1
        assert len(diagram.associations) == 1

    def test_get_entity(self):
        calc = ClassNode(
            name="Calculator",
            qualified_name="calc::Calculator",
            kind="class",
            layer="design",
            module="calc",
        )
        iface = InterfaceNode(
            name="ICalculator",
            qualified_name="calc::ICalculator",
            kind="interface",
            layer="design",
            module="calc",
        )
        diagram = ClassDiagram(
            classes=[calc],
            interfaces=[iface],
        )
        assert diagram.get_entity("calc::Calculator") is calc
        assert diagram.get_entity("calc::ICalculator") is iface
        assert diagram.get_entity("nonexistent") is None

    def test_associations_filtering(self):
        """Associations are accessible as a flat list on the diagram."""
        diagram = ClassDiagram(
            classes=[
                ClassNode(name="A", qualified_name="ns::A", kind="class", layer="design", module="ns"),
                ClassNode(name="B", qualified_name="ns::B", kind="class", layer="design", module="ns"),
            ],
            associations=[
                Association(subject="ns::A", predicate="depends_on", object="ns::B"),
                Association(subject="ns::A", predicate="aggregates", object="ns::C"),
                Association(subject="ns::B", predicate="references", object="ns::A"),
            ],
        )
        a_assocs = [a for a in diagram.associations if a.subject == "ns::A"]
        assert len(a_assocs) == 2
        predicates = {a.predicate for a in a_assocs}
        assert predicates == {"depends_on", "aggregates"}

    def test_associations_involving(self):
        diagram = ClassDiagram(
            associations=[
                Association(subject="ns::A", predicate="depends_on", object="ns::B"),
                Association(subject="ns::B", predicate="references", object="ns::A"),
                Association(subject="ns::C", predicate="aggregates", object="ns::D"),
            ],
        )
        a_involving = [
            a for a in diagram.associations
            if a.subject == "ns::A" or a.object == "ns::A"
        ]
        assert len(a_involving) == 2

    def test_classes_in_module(self):
        diagram = ClassDiagram(
            classes=[
                ClassNode(name="A", qualified_name="calc::A", kind="class", layer="design", module="calc"),
                ClassNode(name="B", qualified_name="calc::B", kind="class", layer="design", module="calc"),
                ClassNode(name="C", qualified_name="ui::Window", kind="class", layer="design", module="ui"),
            ],
        )
        calc_classes = diagram.classes_in_module("calc")
        assert len(calc_classes) == 2
        assert all(c.module == "calc" for c in calc_classes)


class TestClassDiagramToVerificationDicts:
    def test_class_context_dicts(self):
        diagram = ClassDiagram(
            module_names=["calc"],
            classes=[
                ClassNode(
                    name="Calculator",
                    qualified_name="calc::Calculator",
                    kind="class",
                    layer="design",
                    module="calc",
                    brief_description="Main calculator",
                    attributes=[
                        AttributeNode(
                            name="result_",
                            qualified_name="calc::Calculator::result_",
                            kind="attribute",
                            layer="design",
                            type_signature="double",
                            protection="private",
                        ),
                    ],
                    methods=[
                        MethodNode(
                            name="add",
                            qualified_name="calc::Calculator::add",
                            kind="method",
                            layer="design",
                            type_signature="double",
                            protection="public",
                        ),
                    ],
                ),
            ],
        )
        dicts = diagram.to_verification_dicts()
        assert len(dicts) == 1
        calc_dict = dicts[0]
        assert calc_dict["qualified_name"] == "calc::Calculator"
        assert calc_dict["kind"] == "class"
        assert len(calc_dict["attributes"]) == 1
        assert len(calc_dict["methods"]) == 1

    def test_interface_in_verification_dicts(self):
        diagram = ClassDiagram(
            interfaces=[
                InterfaceNode(
                    name="ICalc",
                    qualified_name="calc::ICalc",
                    kind="interface",
                    layer="design",
                    module="calc",
                    methods=[
                        MethodNode(
                            name="compute",
                            qualified_name="calc::ICalc::compute",
                            kind="method",
                            layer="design",
                        ),
                    ],
                ),
            ],
        )
        dicts = diagram.to_verification_dicts()
        assert len(dicts) == 1
        iface_dict = dicts[0]
        assert iface_dict["qualified_name"] == "calc::ICalc"
        assert iface_dict["kind"] == "interface"
        assert len(iface_dict["methods"]) == 1
        assert iface_dict["attributes"] == []


class TestClassDiagramToDraftLookup:
    def test_lookup_with_classes_and_members(self):
        diagram = ClassDiagram(
            classes=[
                ClassNode(
                    name="Calculator",
                    qualified_name="calc::Calculator",
                    kind="class",
                    layer="design",
                    module="calc",
                    brief_description="Main calculator",
                    attributes=[
                        AttributeNode(
                            name="result_",
                            qualified_name="calc::Calculator::result_",
                            kind="attribute",
                            layer="design",
                            brief_description="Last result",
                        ),
                    ],
                    methods=[
                        MethodNode(
                            name="add",
                            qualified_name="calc::Calculator::add",
                            kind="method",
                            layer="design",
                            brief_description="Add two numbers",
                        ),
                    ],
                ),
            ],
        )
        lookup = diagram.to_draft_lookup()
        assert "calc::Calculator" in lookup
        assert lookup["calc::Calculator"]["kind"] == "class"
        assert lookup["calc::Calculator"]["source"] == "draft"
        assert "calc::Calculator::result_" in lookup
        assert lookup["calc::Calculator::result_"]["kind"] == "attribute"
        assert "calc::Calculator::add" in lookup
        assert lookup["calc::Calculator::add"]["kind"] == "method"

    def test_lookup_with_enums(self):
        diagram = ClassDiagram(
            enums=[
                EnumNode(
                    name="Operation",
                    qualified_name="calc::Operation",
                    kind="enum",
                    layer="design",
                    module="calc",
                    brief_description="Supported ops",
                ),
            ],
        )
        lookup = diagram.to_draft_lookup()
        assert "calc::Operation" in lookup
        assert lookup["calc::Operation"]["kind"] == "enum"


class TestClassDiagramToSummary:
    """Tests for ClassDiagram.to_summary()."""

    def test_summary_counts(self):
        diagram = ClassDiagram(
            module_names=["calc"],
            classes=[
                ClassNode(
                    name="Calculator",
                    qualified_name="calc::Calculator",
                    kind="class",
                    layer="design",
                    brief_description="Main calculator",
                ),
            ],
            interfaces=[
                InterfaceNode(
                    name="IComputable",
                    qualified_name="calc::IComputable",
                    kind="interface",
                    layer="design",
                    brief_description="Computable interface",
                ),
            ],
            enums=[
                EnumNode(
                    name="Op",
                    qualified_name="calc::Op",
                    kind="enum",
                    layer="design",
                    brief_description="Operation types",
                ),
            ],
            associations=[
                Association(
                    subject="calc::Calculator",
                    predicate="aggregates",
                    object="calc::Op",
                ),
            ],
        )
        summary = diagram.to_summary()
        assert summary["classes"] == 1
        assert summary["interfaces"] == 1
        assert summary["enums"] == 1
        assert summary["attributes"] == 0  # No pre-saved attributes
        assert summary["methods"] == 0  # No pre-saved methods

    def test_empty_summary(self):
        diagram = ClassDiagram()
        summary = diagram.to_summary()
        assert summary["classes"] == 0
        assert summary["interfaces"] == 0
        assert summary["enums"] == 0
        assert summary["attributes"] == 0
        assert summary["methods"] == 0


class TestClassDiagramToClassLookup:
    """Tests for ClassDiagram.to_class_lookup()."""

    def test_lookup_with_classes(self):
        diagram = ClassDiagram(
            classes=[
                ClassNode(
                    name="Calculator",
                    qualified_name="calc::Calculator",
                    kind="class",
                    layer="design",
                    module="calc",
                ),
            ],
            interfaces=[
                InterfaceNode(
                    name="IComputable",
                    qualified_name="calc::IComputable",
                    kind="interface",
                    layer="design",
                    module="calc",
                ),
            ],
            enums=[
                EnumNode(
                    name="Op",
                    qualified_name="calc::Op",
                    kind="enum",
                    layer="design",
                    module="calc",
                ),
            ],
        )
        lookup = diagram.to_class_lookup()
        assert lookup["Calculator"] == "calc::Calculator"
        assert lookup["IComputable"] == "calc::IComputable"
        assert lookup["Op"] == "calc::Op"

    def test_empty_lookup(self):
        diagram = ClassDiagram()
        lookup = diagram.to_class_lookup()
        assert lookup == {}
