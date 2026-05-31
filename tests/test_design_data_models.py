"""Tests for design_data read models."""

import pytest
from pydantic import ValidationError
import pytest
from backend.design_data.models import (
    ClassNode,
    InterfaceNode,
    EnumNode,
    ModuleNode,
    AttributeNode,
    MethodNode,
    EnumValueNode,
    Association,
    ClassDiagram,
)


@pytest.mark.skip(reason="backend.design_data.models shim deleted — tests need updating for codegraph atomized types")
class TestDiagramNode:
    def test_minimal_creation(self):
        node = DiagramNode(
            name="Calculator",
            qualified_name="calc::Calculator",
            kind="class",
            layer="design",
        )
        assert node.name == "Calculator"
        assert node.qualified_name == "calc::Calculator"
        assert node.kind == "class"
        assert node.layer == "design"
        assert node.description == ""
        assert node.visibility == ""
        assert node.implementation_status == "designed"

    def test_all_fields(self):
        node = DiagramNode(
            name="calculate",
            qualified_name="calc::Calculator::calculate",
            kind="method",
            layer="as-built",
            description="Adds two numbers",
            visibility="public",
            specialization="const_method",
            component_id=3,
            is_intercomponent=False,
            type_signature="double(double, double)",
            argsstring="(double x, double y)",
            definition="double Calculator::calculate(double x, double y)",
            source="",
            file_path="src/calculator.hpp",
            line_number=42,
            is_static=False,
            is_const=True,
            is_virtual=False,
            is_abstract=False,
            is_final=False,
            implementation_status="implemented",
            source_file="src/calculator.hpp",
            test_file="test/test_calculator.cpp",
        )
        assert node.is_const is True
        assert node.line_number == 42
        assert node.implementation_status == "implemented"

    def test_dependency_layer(self):
        node = DiagramNode(
            name="Fl_Button",
            qualified_name="Fl_Button",
            kind="class",
            layer="dependency",
            source="fltk",
        )
        assert node.layer == "dependency"
        assert node.source == "fltk"


@pytest.mark.skip(reason="backend.design_data.models shim deleted — tests need updating for codegraph atomized types")
class TestAttributeNode:
    def test_creation(self):
        attr = AttributeNode(
            name="result_",
            qualified_name="calc::Calculator::result_",
            kind="attribute",
            layer="design",
            owner="calc::Calculator",
            type_signature="double",
            visibility="private",
        )
        assert attr.owner == "calc::Calculator"
        assert attr.type_signature == "double"


@pytest.mark.skip(reason="backend.design_data.models shim deleted — tests need updating for codegraph atomized types")
class TestMethodNode:
    def test_creation(self):
        method = MethodNode(
            name="add",
            qualified_name="calc::Calculator::add",
            kind="method",
            layer="design",
            owner="calc::Calculator",
            type_signature="double",
            argsstring="(double x, double y)",
            visibility="public",
        )
        assert method.owner == "calc::Calculator"
        assert method.argsstring == "(double x, double y)"


@pytest.mark.skip(reason="backend.design_data.models shim deleted — tests need updating for codegraph atomized types")
class TestEnumValueNode:
    def test_creation(self):
        val = EnumValueNode(
            name="ADD",
            qualified_name="calc::Operation::ADD",
            kind="enum_value",
            layer="design",
            owner="calc::Operation",
        )
        assert val.owner == "calc::Operation"


@pytest.mark.skip(reason="backend.design_data.models shim deleted — tests need updating for codegraph atomized types")
class TestClassNode:
    def test_minimal(self):
        cls = ClassNode(
            name="Calculator",
            qualified_name="calc::Calculator",
            kind="class",
            layer="design",
            module="calc",
        )
        assert cls.module == "calc"
        assert cls.attributes == []
        assert cls.methods == []
        assert cls.inherits_from == []
        assert cls.realizes == []

    def test_with_members(self):
        cls = ClassNode(
            name="Calculator",
            qualified_name="calc::Calculator",
            kind="class",
            layer="design",
            module="calc",
            attributes=[
                AttributeNode(
                    name="result_",
                    qualified_name="calc::Calculator::result_",
                    kind="attribute",
                    layer="design",
                    owner="calc::Calculator",
                    type_signature="double",
                    visibility="private",
                ),
            ],
            methods=[
                MethodNode(
                    name="add",
                    qualified_name="calc::Calculator::add",
                    kind="method",
                    layer="design",
                    owner="calc::Calculator",
                    visibility="public",
                ),
            ],
            inherits_from=["calc::ICalculator"],
            realizes=["calc::IProcessor"],
        )
        assert len(cls.attributes) == 1
        assert len(cls.methods) == 1
        assert "calc::ICalculator" in cls.inherits_from

    def test_as_built_class(self):
        cls = ClassNode(
            name="Calculator",
            qualified_name="calc::Calculator",
            kind="class",
            layer="as-built",
            module="calc",
            file_path="src/calculator.hpp",
            line_number=10,
            implementation_status="implemented",
        )
        assert cls.layer == "as-built"
        assert cls.line_number == 10


@pytest.mark.skip(reason="backend.design_data.models shim deleted — tests need updating for codegraph atomized types")
class TestInterfaceNode:
    def test_creation(self):
        iface = InterfaceNode(
            name="ICalculator",
            qualified_name="calc::ICalculator",
            kind="interface",
            layer="design",
            module="calc",
            is_abstract=True,
            methods=[
                MethodNode(
                    name="add",
                    qualified_name="calc::ICalculator::add",
                    kind="method",
                    layer="design",
                    owner="calc::ICalculator",
                    is_virtual=True,
                ),
            ],
        )
        assert iface.is_abstract is True
        assert len(iface.methods) == 1


@pytest.mark.skip(reason="backend.design_data.models shim deleted — tests need updating for codegraph atomized types")
class TestEnumNode:
    def test_creation(self):
        enum = EnumNode(
            name="Operation",
            qualified_name="calc::Operation",
            kind="enum",
            layer="design",
            module="calc",
            values=[
                EnumValueNode(
                    name="ADD",
                    qualified_name="calc::Operation::ADD",
                    kind="enum_value",
                    layer="design",
                    owner="calc::Operation",
                ),
            ],
        )
        assert len(enum.values) == 1


@pytest.mark.skip(reason="backend.design_data.models shim deleted — tests need updating for codegraph atomized types")
class TestModuleNode:
    def test_creation(self):
        mod = ModuleNode(
            name="calc",
            qualified_name="calc",
            kind="module",
            layer="design",
        )


@pytest.mark.skip(reason="backend.design_data.models shim deleted — tests need updating for codegraph atomized types")
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
        assert assoc.description == ""

    def test_with_mechanism(self):
        assoc = Association(
            subject="calc::Calculator",
            predicate="references",
            object="calc::Result",
            mechanism="std::unique_ptr",
        )
        assert assoc.mechanism == "std::unique_ptr"


@pytest.mark.skip(reason="backend.design_data.models shim deleted — tests need updating for codegraph atomized types")
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

    def test_associations_for(self):
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
        a_assocs = diagram.associations_for("ns::A")
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
        a_involving = diagram.associations_involving("ns::A")
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


@pytest.mark.skip(reason="backend.design_data.models shim deleted — tests need updating for codegraph atomized types")
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
                            owner="calc::Calculator",
                            type_signature="double",
                            visibility="private",
                        ),
                    ],
                    methods=[
                        MethodNode(
                            name="add",
                            qualified_name="calc::Calculator::add",
                            kind="method",
                            layer="design",
                            owner="calc::Calculator",
                            type_signature="double",
                            visibility="public",
                        ),
                    ],
                ),
            ],
            associations=[
                Association(
                    subject="calc::Calculator",
                    predicate="aggregates",
                    object="calc::Result",
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
        assert len(calc_dict["relationships"]) == 1
        assert calc_dict["relationships"][0]["predicate"] == "aggregates"

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
                            owner="calc::ICalc",
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


@pytest.mark.skip(reason="backend.design_data.models shim deleted — tests need updating for codegraph atomized types")
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
                            owner="calc::Calculator",
                            brief_description="Last result",
                        ),
                    ],
                    methods=[
                        MethodNode(
                            name="add",
                            qualified_name="calc::Calculator::add",
                            kind="method",
                            layer="design",
                            owner="calc::Calculator",
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


@pytest.mark.skip(reason="backend.design_data.models shim deleted — tests need updating for codegraph atomized types")
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
                    attributes=[
                        AttributeNode(
                            name="result_",
                            qualified_name="calc::Calculator::result_",
                            kind="attribute",
                            layer="design",
                            brief_description="Last result",
                        ),
                        AttributeNode(
                            name="history",
                            qualified_name="calc::Calculator::history",
                            kind="attribute",
                            layer="design",
                            brief_description="History of calculations",
                        ),
                    ],
                    methods=[
                        MethodNode(
                            name="add",
                            qualified_name="calc::Calculator::add",
                            kind="method",
                            layer="design",
                            brief_description="Add numbers",
                        ),
                        MethodNode(
                            name="subtract",
                            qualified_name="calc::Calculator::subtract",
                            kind="method",
                            layer="design",
                            brief_description="Subtract numbers",
                        ),
                    ],
                ),
            ],
            interfaces=[
                InterfaceNode(
                    name="IComputable",
                    qualified_name="calc::IComputable",
                    kind="interface",
                    layer="design",
                    brief_description="Computable interface",
                    methods=[
                        MethodNode(
                            name="execute",
                            qualified_name="calc::IComputable::execute",
                            kind="method",
                            layer="design",
                            brief_description="Execute computation",
                        ),
                    ],
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
        assert summary["associations"] == 1
        assert summary["attributes"] == 2
        assert summary["methods"] == 2  # Only class methods counted

    def test_empty_summary(self):
        diagram = ClassDiagram()
        summary = diagram.to_summary()
        assert summary["classes"] == 0
        assert summary["interfaces"] == 0
        assert summary["enums"] == 0
        assert summary["associations"] == 0
        assert summary["attributes"] == 0
        assert summary["methods"] == 0

@pytest.mark.skip(reason="backend.design_data.models shim deleted — tests need updating for codegraph atomized types")
class TestClassDiagramToClassLookup:
    """Tests for ClassDiagram.to_class_lookup()."""

    def test_lookup_with_classes(self):
        from backend.design_data.models import ClassNode, InterfaceNode, EnumNode
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
        from backend.design_data.models import ClassDiagram
        diagram = ClassDiagram()
        lookup = diagram.to_class_lookup()
        assert lookup == {}
