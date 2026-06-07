"""Tests for design_oo validation helpers and tool-loop integration."""

import pytest
from unittest.mock import patch
from codegraph.diagram import ClassDiagram, Association, DiagramClassNode, DiagramAttributeNode
from backend.ticketing_agent.tools.helpers.design_validation import validate_oo_design


def _make_design(associations=None, classes=None, class_attrs=None, class_methods=None):
    """Helper to create a minimal ClassDiagram for testing."""
    if classes is None:
        classes = [DiagramClassNode(
            name="TestClass",
            module="test",
            description="A test class",
            visibility="public",
            is_intercomponent=False,
            requirement_ids=[],
            attributes=class_attrs or [],
            methods=class_methods or [],
            inherits_from=[],
            realizes=[],
        )]
    return ClassDiagram(
        module_names=["test"],
        classes=classes,
        interfaces=[],
        enums=[],
        associations=associations or [],
    )


class TestValidateOODesign:
    def test_unknown_association_target_flagged(self):
        oo = _make_design(associations=[
            Association(subject="TestClass", object="PhantomClass", predicate="depends_on")
        ])
        errors = validate_oo_design(oo, prior_class_lookup={}, dependency_lookup=None, intercomponent_classes=None)
        assert any("PhantomClass" in e for e in errors)

    def test_known_intercomponent_class_not_flagged(self):
        oo = _make_design(associations=[
            Association(subject="TestClass", object="ui::Display", predicate="depends_on")
        ])
        intercomp = [{"qualified_name": "ui::Display", "kind": "class", "description": "Display", "name": "Display", "methods": [], "attributes": []}]
        errors = validate_oo_design(oo, prior_class_lookup={}, dependency_lookup=None, intercomponent_classes=intercomp)
        assert errors == []

    def test_missing_intercomponent_association_flagged(self):
        oo = _make_design(
            classes=[DiagramClassNode(
                name="TestClass", module="test",
                visibility="public", is_intercomponent=False,
                requirement_ids=[],
                attributes=[DiagramAttributeNode(
                    name="disp", type_signature="Display", visibility="private", description="display",
                )],
                methods=[],
                inherits_from=[],
                realizes=[],
            )],
        )
        intercomp = [{"qualified_name": "ui::Display", "kind": "class", "description": "Display", "name": "Display", "methods": [], "attributes": []}]
        errors = validate_oo_design(oo, prior_class_lookup={}, dependency_lookup=None, intercomponent_classes=intercomp)
        assert any("Missing intercomponent" in e for e in errors)

    def test_valid_design_no_errors(self):
        oo = _make_design()
        errors = validate_oo_design(oo, prior_class_lookup={}, dependency_lookup=None, intercomponent_classes=None)
        assert errors == []

    def test_dependency_lookup_target_not_flagged(self):
        oo = _make_design(associations=[
            Association(subject="TestClass", object="Fl_Window", predicate="depends_on")
        ])
        errors = validate_oo_design(oo, prior_class_lookup={}, dependency_lookup={"Fl_Window": "fltk::Fl_Window"}, intercomponent_classes=None)
        assert errors == []

    def test_prior_class_lookup_target_not_flagged(self):
        oo = _make_design(associations=[
            Association(subject="TestClass", object="PriorClass", predicate="depends_on")
        ])
        errors = validate_oo_design(oo, prior_class_lookup={"PriorClass": "ns::PriorClass"}, dependency_lookup=None, intercomponent_classes=None)
        assert errors == []


class TestDesignOOToolLoop:
    def test_design_oo_returns_schema_on_valid_output(self):
        """Verify design_oo function returns ClassDiagram via call_tool_loop."""
        from backend.ticketing_agent.design.design_oo import design_oo

        mock_result = {
            "module_names": ["test_ns"],
            "classes": [{
                "name": "TestClass",
                "module": "test_ns",
                "description": "A test class",
                "visibility": "public",
                "is_intercomponent": False,
                "requirement_ids": [],
                "attributes": [],
                "methods": [],
                "inherits_from": [],
                "realizes": [],
            }],
            "interfaces": [],
            "enums": [],
            "associations": [],
        }
        with patch("backend.ticketing_agent.design.design_oo.call_tool_loop", return_value=mock_result):
            result = design_oo(
                hlr={"id": 1, "description": "Test HLR"},
                llrs=[],
                prior_class_lookup={},
            )
        assert isinstance(result, ClassDiagram)
        assert result.module_names == ["test_ns"]
        assert len(result.classes) == 1
        assert result.classes[0].name == "TestClass"