"""Tests for design_oo tool dispatcher and schemas."""

import json
import pytest
from backend.ticketing_agent.design.design_oo_tools import (
    VALIDATE_DESIGN_TOOL,
    CHECK_CLASS_NAME_TOOL,
    PRODUCE_OO_DESIGN_TOOL,
    ALL_TOOLS,
    make_design_dispatcher,
)
from backend.codebase.schemas import OODesignSchema


def _sample_design_dict():
    """Return a minimal valid OODesign dict."""
    return {
        "modules": ["calculation_engine"],
        "classes": [
            {
                "name": "Calculator",
                "module": "calculation_engine",
                "description": "Main calculator",
                "visibility": "public",
                "is_intercomponent": False,
                "requirement_ids": ["hlr:1"],
                "attributes": [
                    {
                        "name": "result",
                        "type_name": "double",
                        "visibility": "private",
                        "description": "Last result",
                    }
                ],
                "methods": [
                    {
                        "name": "add",
                        "description": "Add two numbers",
                        "visibility": "public",
                        "parameters": [],
                        "return_type": "double",
                    }
                ],
                "inherits_from": [],
                "realizes_interfaces": [],
            }
        ],
        "interfaces": [],
        "enums": [],
        "associations": [],
    }


def _make_dispatcher():
    """Create a dispatcher with sample context."""
    prior_class_lookup = {"Calculator": "calculation_engine::Calculator"}
    dependency_lookup = {"Fl_Window": "fltk::Fl_Window"}
    intercomponent_classes = [
        {
            "qualified_name": "user_interface::DisplayArea",
            "kind": "class",
            "description": "Display area",
            "name": "DisplayArea",
            "methods": [],
            "attributes": [],
        }
    ]
    return make_design_dispatcher(
        prior_class_lookup=prior_class_lookup,
        dependency_lookup=dependency_lookup,
        intercomponent_classes=intercomponent_classes,
    )


class TestToolSchemas:
    def test_all_tools_present(self):
        assert len(ALL_TOOLS) == 4
        names = {t["name"] for t in ALL_TOOLS}
        assert names == {"validate_design", "check_class_name", "find_mechanism", "produce_oo_design"}

    def test_validate_design_tool_schema(self):
        assert VALIDATE_DESIGN_TOOL["name"] == "validate_design"
        assert "input_schema" in VALIDATE_DESIGN_TOOL

    def test_check_class_name_tool_schema(self):
        assert CHECK_CLASS_NAME_TOOL["name"] == "check_class_name"
        props = CHECK_CLASS_NAME_TOOL["input_schema"]["properties"]
        assert "name" in props
        assert props["name"]["type"] == "string"

    def test_produce_oo_design_tool_has_schema(self):
        assert PRODUCE_OO_DESIGN_TOOL["name"] == "produce_oo_design"
        assert "input_schema" in PRODUCE_OO_DESIGN_TOOL


class TestValidateDesignDispatcher:
    def test_valid_design_returns_no_errors(self):
        dispatcher = _make_dispatcher()
        result = json.loads(dispatcher("validate_design", _sample_design_dict()))
        assert result["valid"] is True
        assert result["errors"] == []

    def test_unknown_association_target_flagged(self):
        dispatcher = _make_dispatcher()
        design = _sample_design_dict()
        design["associations"] = [
            {
                "from_class": "Calculator",
                "to_class": "NonExistentClass",
                "kind": "depends_on",
                "description": "Missing ref",
            }
        ]
        result = json.loads(dispatcher("validate_design", design))
        assert result["valid"] is False
        assert any("NonExistentClass" in e for e in result["errors"])

    def test_missing_intercomponent_association_flagged(self):
        dispatcher = _make_dispatcher()
        design = _sample_design_dict()
        # Add attribute referencing DisplayArea but no association
        design["classes"][0]["attributes"].append(
            {
                "name": "display",
                "type_name": "DisplayArea",
                "visibility": "private",
                "description": "The display",
            }
        )
        result = json.loads(dispatcher("validate_design", design))
        assert result["valid"] is False
        assert any("intercomponent" in e.lower() or "DisplayArea" in e for e in result["errors"])

    def test_intercomponent_association_not_flagged(self):
        dispatcher = _make_dispatcher()
        design = _sample_design_dict()
        design["classes"][0]["attributes"].append(
            {
                "name": "display",
                "type_name": "DisplayArea",
                "visibility": "private",
                "description": "The display",
            }
        )
        design["associations"] = [
            {
                "from_class": "Calculator",
                "to_class": "user_interface::DisplayArea",
                "kind": "depends_on",
                "description": "Uses display",
            }
        ]
        result = json.loads(dispatcher("validate_design", design))
        assert result["valid"] is True
        assert result["errors"] == []

    def test_malformed_design_returns_format_error(self):
        dispatcher = _make_dispatcher()
        result = json.loads(dispatcher("validate_design", {"classes": "not_a_list"}))
        assert result["valid"] is False
        assert len(result["errors"]) > 0

    def test_dependency_lookup_target_not_flagged(self):
        dispatcher = _make_dispatcher()
        design = _sample_design_dict()
        design["associations"] = [
            {
                "from_class": "Calculator",
                "to_class": "Fl_Window",
                "kind": "depends_on",
                "description": "UI dependency",
            }
        ]
        result = json.loads(dispatcher("validate_design", design))
        assert result["valid"] is True
        assert result["errors"] == []


class TestCheckClassNameDispatcher:
    def test_known_prior_design_class(self):
        dispatcher = _make_dispatcher()
        result = json.loads(dispatcher("check_class_name", {"name": "Calculator"}))
        assert result["found"] is True
        assert any(m["qualified_name"] == "calculation_engine::Calculator" for m in result["matches"])

    def test_known_dependency_class(self):
        dispatcher = _make_dispatcher()
        result = json.loads(dispatcher("check_class_name", {"name": "Fl_Window"}))
        assert result["found"] is True
        assert any(m["source"] == "dependency" for m in result["matches"])

    def test_known_intercomponent_class(self):
        dispatcher = _make_dispatcher()
        result = json.loads(dispatcher("check_class_name", {"name": "DisplayArea"}))
        assert result["found"] is True
        assert any(m["source"] == "intercomponent" for m in result["matches"])

    def test_unknown_class(self):
        dispatcher = _make_dispatcher()
        result = json.loads(dispatcher("check_class_name", {"name": "NonExistent"}))
        assert result["found"] is False
        assert result["matches"] == []

    def test_partial_match(self):
        dispatcher = _make_dispatcher()
        result = json.loads(dispatcher("check_class_name", {"name": "Calc"}))
        assert result["found"] is True
        # Should find Calculator via substring match
        assert any("Calculator" in m["qualified_name"] for m in result["matches"])

    def test_unknown_tool_returns_error(self):
        dispatcher = _make_dispatcher()
        result = json.loads(dispatcher("unknown_tool", {}))
        assert "error" in result


class TestDisconnectedEntityValidation:
    """Test Check 4: disconnected design entities."""

    def test_single_class_design_not_flagged(self):
        """A single-class design should not be flagged as disconnected."""
        from backend.ticketing_agent.design.design_oo_tools import _validate_oo_design

        oo = OODesignSchema.model_validate(_sample_design_dict())
        errors = _validate_oo_design(oo, prior_class_lookup={}, dependency_lookup={}, intercomponent_classes=[])
        assert not any("Disconnected" in e for e in errors)

    def test_disconnected_enum_flagged(self):
        """An enum not referenced anywhere should be flagged as disconnected."""
        from backend.ticketing_agent.design.design_oo_tools import _validate_oo_design

        design = _sample_design_dict()
        design["enums"] = [
            {"name": "Operation", "module": "calculation_engine", "description": "Operations", "values": ["ADD", "SUBTRACT"]}
        ]
        oo = OODesignSchema.model_validate(design)
        errors = _validate_oo_design(oo, prior_class_lookup={}, dependency_lookup={}, intercomponent_classes=[])
        assert any("Disconnected" in e and "Operation" in e for e in errors)

    def test_enum_connected_via_attribute_type_not_flagged(self):
        """An enum used as an attribute type should not be flagged."""
        from backend.ticketing_agent.design.design_oo_tools import _validate_oo_design

        design = _sample_design_dict()
        design["enums"] = [
            {"name": "Operation", "module": "calculation_engine", "description": "Operations", "values": ["ADD", "SUBTRACT"]}
        ]
        design["classes"][0]["attributes"].append(
            {"name": "op", "type_name": "Operation", "visibility": "private", "description": "Current operation"}
        )
        oo = OODesignSchema.model_validate(design)
        errors = _validate_oo_design(oo, prior_class_lookup={}, dependency_lookup={}, intercomponent_classes=[])
        assert not any("Disconnected" in e for e in errors)

    def test_enum_connected_via_return_type_not_flagged(self):
        """An enum used as a method return type should not be flagged."""
        from backend.ticketing_agent.design.design_oo_tools import _validate_oo_design

        design = _sample_design_dict()
        design["enums"] = [
            {"name": "Operation", "module": "calculation_engine", "description": "Operations", "values": ["ADD", "SUBTRACT"]}
        ]
        design["classes"][0]["methods"].append(
            {"name": "getOperation", "description": "Get operation", "visibility": "public", "parameters": [], "return_type": "Operation"}
        )
        oo = OODesignSchema.model_validate(design)
        errors = _validate_oo_design(oo, prior_class_lookup={}, dependency_lookup={}, intercomponent_classes=[])
        assert not any("Disconnected" in e for e in errors)

    def test_enum_connected_via_association_not_flagged(self):
        """An enum connected via association should not be flagged."""
        from backend.ticketing_agent.design.design_oo_tools import _validate_oo_design

        design = _sample_design_dict()
        design["enums"] = [
            {"name": "Operation", "module": "calculation_engine", "description": "Operations", "values": ["ADD", "SUBTRACT"]}
        ]
        design["associations"] = [
            {"from_class": "Calculator", "to_class": "Operation", "kind": "depends_on", "description": "Uses operation enum"}
        ]
        oo = OODesignSchema.model_validate(design)
        errors = _validate_oo_design(oo, prior_class_lookup={}, dependency_lookup={}, intercomponent_classes=[])
        assert not any("Disconnected" in e for e in errors)

    def test_disconnected_class_flagged(self):
        """A class not referenced by any other entity should be flagged."""
        from backend.ticketing_agent.design.design_oo_tools import _validate_oo_design

        design = _sample_design_dict()
        design["classes"].append(
            {"name": "Orphan", "module": "calculation_engine", "description": "Disconnected class",
             "visibility": "public", "is_intercomponent": False, "requirement_ids": [],
             "attributes": [], "methods": [], "inherits_from": [], "realizes_interfaces": []}
        )
        oo = OODesignSchema.model_validate(design)
        errors = _validate_oo_design(oo, prior_class_lookup={}, dependency_lookup={}, intercomponent_classes=[])
        assert any("Disconnected" in e and "Orphan" in e for e in errors)

    def test_enum_connected_via_method_parameter_not_flagged(self):
        """An enum used as a method parameter type should not be flagged."""
        from backend.ticketing_agent.design.design_oo_tools import _validate_oo_design

        design = _sample_design_dict()
        design["enums"] = [
            {"name": "Operation", "module": "calculation_engine", "description": "Operations", "values": ["ADD", "SUBTRACT"]}
        ]
        design["classes"][0]["methods"].append(
            {"name": "setOperator", "description": "Set the operator", "visibility": "public", "parameters": ["Operation op"], "return_type": "void"}
        )
        oo = OODesignSchema.model_validate(design)
        errors = _validate_oo_design(oo, prior_class_lookup={}, dependency_lookup={}, intercomponent_classes=[])
        assert not any("Disconnected" in e for e in errors)
