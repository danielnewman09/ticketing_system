"""Tests for design_oo validate-and-retry functionality."""

from backend.codebase.schemas import (
    AssociationSchema,
    AttributeSchema,
    ClassSchema,
    MethodSchema,
    OODesignSchema,
)


class TestValidateOODesign:
    """Test _validate_oo_design association validation."""

    def test_unknown_association_target_flagged(self):
        from backend.ticketing_agent.design.design_oo import _validate_oo_design
        oo = OODesignSchema(
            modules=["ui"],
            classes=[
                ClassSchema(name="CalculatorWindow", module="ui", attributes=[], methods=[]),
            ],
            associations=[
                AssociationSchema(
                    from_class="CalculatorWindow",
                    to_class="NonExistentClass",
                    kind="depends_on",
                    description="Unknown ref",
                ),
            ],
        )
        errors = _validate_oo_design(
            oo,
            prior_class_lookup={},
            dependency_lookup={},
            intercomponent_classes=[],
        )
        assert any("NonExistentClass" in e for e in errors)

    def test_known_intercomponent_class_not_flagged(self):
        from backend.ticketing_agent.design.design_oo import _validate_oo_design
        oo = OODesignSchema(
            modules=["ui"],
            classes=[
                ClassSchema(name="CalculatorWindow", module="ui", attributes=[], methods=[]),
            ],
            associations=[
                AssociationSchema(
                    from_class="CalculatorWindow",
                    to_class="calculation_engine::CalculatorEngine",
                    kind="depends_on",
                    description="Uses engine",
                ),
            ],
        )
        errors = _validate_oo_design(
            oo,
            prior_class_lookup={},
            dependency_lookup={},
            intercomponent_classes=[
                {"qualified_name": "calculation_engine::CalculatorEngine", "kind": "class"},
            ],
        )
        assert len(errors) == 0

    def test_missing_intercomponent_association_flagged(self):
        from backend.ticketing_agent.design.design_oo import _validate_oo_design
        oo = OODesignSchema(
            modules=["ui"],
            classes=[
                ClassSchema(
                    name="CalculatorWindow",
                    module="ui",
                    attributes=[
                        AttributeSchema(name="result", type_name="CalculatorResult", visibility="private", description=""),
                    ],
                    methods=[
                        MethodSchema(name="calculate", visibility="public", description="", parameters=[], return_type="CalculatorResult"),
                    ],
                ),
            ],
            associations=[],
        )
        errors = _validate_oo_design(
            oo,
            prior_class_lookup={},
            dependency_lookup={},
            intercomponent_classes=[
                {"qualified_name": "calculation_engine::CalculatorResult", "kind": "class"},
            ],
        )
        assert any("CalculatorResult" in e and "no association" in e for e in errors)

    def test_valid_design_no_errors(self):
        from backend.ticketing_agent.design.design_oo import _validate_oo_design
        oo = OODesignSchema(
            modules=["ui"],
            classes=[
                ClassSchema(name="CalculatorWindow", module="ui", attributes=[], methods=[]),
            ],
            associations=[],
        )
        errors = _validate_oo_design(
            oo,
            prior_class_lookup={},
            dependency_lookup={},
            intercomponent_classes=[],
        )
        assert len(errors) == 0

    def test_dependency_lookup_target_not_flagged(self):
        from backend.ticketing_agent.design.design_oo import _validate_oo_design
        oo = OODesignSchema(
            modules=["ui"],
            classes=[
                ClassSchema(name="CalculatorWindow", module="ui", attributes=[], methods=[]),
            ],
            associations=[
                AssociationSchema(
                    from_class="CalculatorWindow",
                    to_class="Fl_Button",
                    kind="aggregates",
                    description="Uses buttons",
                ),
            ],
        )
        errors = _validate_oo_design(
            oo,
            prior_class_lookup={},
            dependency_lookup={"Fl_Button": "Fl_Button"},
            intercomponent_classes=[],
        )
        assert len(errors) == 0

    def test_prior_class_lookup_target_not_flagged(self):
        from backend.ticketing_agent.design.design_oo import _validate_oo_design
        oo = OODesignSchema(
            modules=["ui"],
            classes=[
                ClassSchema(name="CalculatorWindow", module="ui", attributes=[], methods=[]),
            ],
            associations=[
                AssociationSchema(
                    from_class="CalculatorWindow",
                    to_class="CalculatorPanel",
                    kind="aggregates",
                    description="Contains panel",
                ),
            ],
        )
        errors = _validate_oo_design(
            oo,
            prior_class_lookup={"CalculatorPanel": "ui::CalculatorPanel"},
            dependency_lookup={},
            intercomponent_classes=[],
        )
        assert len(errors) == 0


class TestFormatDesignValidationErrors:
    """Test _format_design_validation_errors."""

    def test_format_single_error(self):
        from backend.ticketing_agent.design.design_oo import _format_design_validation_errors
        msg = _format_design_validation_errors(["Missing association to CalculatorResult"])
        assert "<issues>" in msg
        assert "CalculatorResult" in msg
        assert "correct these issues" in msg

    def test_format_multiple_errors(self):
        from backend.ticketing_agent.design.design_oo import _format_design_validation_errors
        msg = _format_design_validation_errors([
            "Missing association to CalculatorResult",
            "Unknown class UnknownClass",
        ])
        assert "1." in msg
        assert "2." in msg
        assert "CalculatorResult" in msg
        assert "UnknownClass" in msg