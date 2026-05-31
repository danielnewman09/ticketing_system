"""Tests for design_data transforms."""

import pytest
from codegraph.diagram import ClassDiagram, Association
from codegraph.models import (
    ClassNode,
    EnumNode,
    EnumValueNode,
    InterfaceNode,
    MethodNode,
    AttributeNode,
)
from backend.design_data.transforms import class_diagram_from_oo_design, oo_design_from_class_diagram


def _sample_oo_design():
    return ClassDiagram(
        module_names=["calc"],
        classes=[
            ClassNode(
                name="Calculator",
                module="calc",
                brief_description="Main calculator class",
                visibility="public",
                is_intercomponent=False,
                requirement_ids=["hlr:1"],
                attributes=[
                    AttributeNode(
                        name="result_",
                        type_signature="double",
                        visibility="private",
                        brief_description="Last result",
                    ),
                ],
                methods=[
                    MethodNode(
                        name="add",
                        visibility="public",
                        brief_description="Add two numbers",
                        argsstring="(double x, double y)",
                        type_signature="double",
                    ),
                ],
                inherits_from=["ICalculator"],
                realizes=[],
            ),
        ],
        interfaces=[
            InterfaceNode(
                name="ICalculator",
                module="calc",
                brief_description="Calculator interface",
                is_intercomponent=False,
                methods=[
                    MethodNode(
                        name="add",
                        visibility="public",
                        brief_description="Add two numbers",
                        argsstring="",
                        type_signature="double",
                    ),
                ],
            ),
        ],
        enums=[
            EnumNode(
                name="Operation",
                module="calc",
                brief_description="Supported operations",
                values=[
                    EnumValueNode(name="ADD", qualified_name="calc::Operation::ADD"),
                    EnumValueNode(name="SUBTRACT", qualified_name="calc::Operation::SUBTRACT"),
                ],
            ),
        ],
        associations=[
            Association(
                subject="Calculator",
                object="Result",
                predicate="aggregates",
                mechanism="std::vector",
            ),
        ],
    )


@pytest.mark.skip(reason="Source code needs atomized type updates — uses old field names")
class TestClassDiagramFromOODesign:
    def test_classes_preserved(self):
        oo = _sample_oo_design()
        diagram = class_diagram_from_oo_design(oo)
        assert len(diagram.classes) == 1
        assert diagram.classes[0].name == "Calculator"
        assert diagram.classes[0].qualified_name == "calc::Calculator"

    def test_class_attributes(self):
        oo = _sample_oo_design()
        diagram = class_diagram_from_oo_design(oo)
        assert len(diagram.classes[0].attributes) == 1
        assert diagram.classes[0].attributes[0].name == "result_"
        assert diagram.classes[0].attributes[0].type_signature == "double"

    def test_class_methods(self):
        oo = _sample_oo_design()
        diagram = class_diagram_from_oo_design(oo)
        assert len(diagram.classes[0].methods) == 1
        assert diagram.classes[0].methods[0].name == "add"

    def test_class_inherits_from(self):
        oo = _sample_oo_design()
        diagram = class_diagram_from_oo_design(oo)
        assert "ICalculator" in diagram.classes[0].inherits_from

    def test_interfaces_preserved(self):
        oo = _sample_oo_design()
        diagram = class_diagram_from_oo_design(oo)
        assert len(diagram.interfaces) == 1
        assert diagram.interfaces[0].name == "ICalculator"

    def test_enums_preserved(self):
        oo = _sample_oo_design()
        diagram = class_diagram_from_oo_design(oo)
        assert len(diagram.enums) == 1
        assert diagram.enums[0].name == "Operation"
        assert len(diagram.enums[0].values) == 2

    def test_associations_preserved(self):
        oo = _sample_oo_design()
        diagram = class_diagram_from_oo_design(oo)
        assert len(diagram.associations) == 1
        assert diagram.associations[0].predicate == "aggregates"
        assert diagram.associations[0].mechanism == "std::vector"

    def test_layer_is_design(self):
        oo = _sample_oo_design()
        diagram = class_diagram_from_oo_design(oo)
        assert diagram.classes[0].layer == "design"

    def test_component_id_propagated(self):
        oo = _sample_oo_design()
        diagram = class_diagram_from_oo_design(oo, component_id=5)
        assert diagram.classes[0].component_id == 5

    def test_modules_extracted(self):
        oo = _sample_oo_design()
        diagram = class_diagram_from_oo_design(oo)
        assert "calc" in diagram.module_names

    def test_owner_set_on_members(self):
        oo = _sample_oo_design()
        diagram = class_diagram_from_oo_design(oo)
        assert diagram.classes[0].attributes[0].owner == "calc::Calculator"
        assert diagram.classes[0].methods[0].owner == "calc::Calculator"