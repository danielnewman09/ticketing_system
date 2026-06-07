"""Tests for design_data transforms — updated for codegraph diagram Pydantic types."""

import pytest
from codegraph.diagram import (
    ClassDiagram,
    Association,
    DiagramClassNode,
    DiagramEnumNode,
    DiagramEnumValueNode,
    DiagramInterfaceNode,
    DiagramMethodNode,
    DiagramAttributeNode,
)
from backend.design_data.transforms import class_diagram_from_oo_design, oo_design_from_class_diagram


def _sample_oo_design():
    return ClassDiagram(
        module_names=["calc"],
        classes=[
            DiagramClassNode(
                name="Calculator",
                qualified_name="calc::Calculator",
                module="calc",
                kind="class",
                layer="design",
                description="Main calculator class",
            ),
        ],
        interfaces=[
            DiagramInterfaceNode(
                name="ICalculator",
                qualified_name="calc::ICalculator",
                module="calc",
                kind="interface",
                layer="design",
                description="Calculator interface",
            ),
        ],
        enums=[
            DiagramEnumNode(
                name="Operation",
                qualified_name="calc::Operation",
                module="calc",
                kind="enum",
                layer="design",
                description="Supported operations",
            ),
        ],
        associations=[
            Association(
                subject="calc::Calculator",
                object="calc::Result",
                predicate="aggregates",
                mechanism="std::vector",
            ),
        ],
    )


class TestClassDiagramFromOODesign:
    def test_classes_preserved(self):
        oo = _sample_oo_design()
        diagram = class_diagram_from_oo_design(oo)
        assert len(diagram.classes) == 1
        assert diagram.classes[0].name == "Calculator"
        assert diagram.classes[0].qualified_name == "calc::Calculator"

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

    def test_qualified_name_set_when_missing(self):
        """class_diagram_from_oo_design sets qualified_name for nodes without one."""
        oo = ClassDiagram(
            classes=[
                DiagramClassNode(
                    name="Widget",
                    module="ui",
                    kind="class",
                    layer="design",
                ),
            ],
        )
        diagram = class_diagram_from_oo_design(oo)
        assert diagram.classes[0].qualified_name == "ui::Widget"

    def test_oo_design_from_class_diagram_passthrough(self):
        oo = _sample_oo_design()
        result = oo_design_from_class_diagram(oo)
        assert result is oo