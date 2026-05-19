"""
Tests for Pydantic schemas in backend.requirements.schemas.

Covers: VerificationConditionSchema, VerificationActionSchema,
VerificationSchema, LowLevelRequirementSchema,
DecomposedRequirementSchema, and the VerificationMethodType literal.
"""

import pytest
from pydantic import ValidationError

from backend.requirements.schemas import (
    DecomposedRequirementSchema,
    LowLevelRequirementSchema,
    VerificationActionSchema,
    VerificationConditionSchema,
    VerificationMethodType,
    VerificationSchema,
)


# ---------------------------------------------------------------------------
# VerificationConditionSchema
# ---------------------------------------------------------------------------

class TestVerificationConditionSchema:
    def test_minimal(self):
        vc = VerificationConditionSchema(
            member_qualified_name="Calculator::result", expected_value="OK"
        )
        assert vc.member_qualified_name == "Calculator::result"
        assert vc.operator == "=="  # default
        assert vc.expected_value == "OK"

    def test_custom_operator(self):
        vc = VerificationConditionSchema(
            member_qualified_name="Calculator::count",
            operator=">=",
            expected_value="0",
        )
        assert vc.operator == ">="

    def test_missing_required_field(self):
        with pytest.raises(ValidationError):
            VerificationConditionSchema(member_qualified_name="X")  # no expected_value

    def test_missing_member(self):
        with pytest.raises(ValidationError):
            VerificationConditionSchema(expected_value="OK")  # no member_qualified_name


# ---------------------------------------------------------------------------
# VerificationActionSchema
# ---------------------------------------------------------------------------

class TestVerificationActionSchema:
    def test_minimal(self):
        va = VerificationActionSchema(description="Call add(2, 3)")
        assert va.description == "Call add(2, 3)"
        assert va.member_qualified_name == ""  # default

    def test_all_fields(self):
        va = VerificationActionSchema(
            description="Invoke the add method with valid operands",
            member_qualified_name="Calculator::add",
        )
        assert va.member_qualified_name == "Calculator::add"

    def test_description_required(self):
        with pytest.raises(ValidationError):
            VerificationActionSchema()  # missing description


# ---------------------------------------------------------------------------
# VerificationSchema
# ---------------------------------------------------------------------------

class TestVerificationSchema:
    def test_minimal(self):
        vs = VerificationSchema(method="automated")
        assert vs.test_name == ""
        assert vs.description == ""
        assert vs.preconditions == []
        assert vs.actions == []
        assert vs.postconditions == []

    def test_all_method_types(self):
        for method in ("automated", "review", "inspection"):
            vs = VerificationSchema(method=method)
            assert vs.method == method

    def test_invalid_method(self):
        with pytest.raises(ValidationError):
            VerificationSchema(method="invalid")

    def test_full_schema(self):
        vs = VerificationSchema(
            method="automated",
            test_name="test_addition",
            description="Verify addition works",
            preconditions=[
                VerificationConditionSchema(
                    member_qualified_name="Calc::status", expected_value="READY"
                )
            ],
            actions=[
                VerificationActionSchema(
                    description="Call add(2,3)",
                    member_qualified_name="Calc::add",
                )
            ],
            postconditions=[
                VerificationConditionSchema(
                    member_qualified_name="Calc::result", expected_value="5"
                )
            ],
        )
        assert vs.method == "automated"
        assert vs.test_name == "test_addition"
        assert len(vs.preconditions) == 1
        assert len(vs.actions) == 1
        assert len(vs.postconditions) == 1
        assert vs.preconditions[0].operator == "=="

    def test_round_trip(self):
        vs = VerificationSchema(
            method="review",
            description="Manually review design",
            actions=[VerificationActionSchema(description="Check diagram")],
        )
        data = vs.model_dump()
        restored = VerificationSchema.model_validate(data)
        assert restored.method == "review"
        assert len(restored.actions) == 1

    def test_json_round_trip(self):
        vs = VerificationSchema(
            method="inspection",
            test_name="inspect_wiring",
            preconditions=[
                VerificationConditionSchema(
                    member_qualified_name="A::ready", expected_value="true"
                )
            ],
        )
        json_str = vs.model_dump_json()
        restored = VerificationSchema.model_validate_json(json_str)
        assert restored.method == "inspection"
        assert len(restored.preconditions) == 1


# ---------------------------------------------------------------------------
# LowLevelRequirementSchema
# ---------------------------------------------------------------------------

class TestLowLevelRequirementSchema:
    def test_minimal(self):
        llr = LowLevelRequirementSchema(
            description="System shall add two numbers",
            verifications=[VerificationSchema(method="automated")],
        )
        assert llr.description == "System shall add two numbers"
        assert len(llr.verifications) == 1
        assert llr.verifications[0].method == "automated"

    def test_multiple_verifications(self):
        llr = LowLevelRequirementSchema(
            description="Robust addition",
            verifications=[
                VerificationSchema(method="automated", test_name="test_add"),
                VerificationSchema(method="review", description="Design review"),
            ],
        )
        assert len(llr.verifications) == 2

    def test_empty_verifications(self):
        llr = LowLevelRequirementSchema(
            description="No verifications yet", verifications=[]
        )
        assert llr.verifications == []

    def test_missing_description(self):
        with pytest.raises(ValidationError):
            LowLevelRequirementSchema(verifications=[])

    def test_round_trip(self):
        llr = LowLevelRequirementSchema(
            description="Subtraction works",
            verifications=[
                VerificationSchema(
                    method="automated",
                    test_name="test_subtract",
                    actions=[
                        VerificationActionSchema(description="Call subtract(5,3)")
                    ],
                )
            ],
        )
        data = llr.model_dump()
        restored = LowLevelRequirementSchema.model_validate(data)
        assert restored.description == "Subtraction works"
        assert len(restored.verifications) == 1
        assert restored.verifications[0].actions[0].description == "Call subtract(5,3)"


# ---------------------------------------------------------------------------
# DecomposedRequirementSchema
# ---------------------------------------------------------------------------

class TestDecomposedRequirementSchema:
    def test_minimal(self):
        dr = DecomposedRequirementSchema(
            description="HLR: calculator operations",
            low_level_requirements=[],
        )
        assert dr.description == "HLR: calculator operations"
        assert dr.low_level_requirements == []

    def test_with_llrs(self):
        dr = DecomposedRequirementSchema(
            description="Calculator shall perform arithmetic",
            low_level_requirements=[
                LowLevelRequirementSchema(
                    description="Addition",
                    verifications=[VerificationSchema(method="automated")],
                ),
                LowLevelRequirementSchema(
                    description="Subtraction",
                    verifications=[VerificationSchema(method="review")],
                ),
            ],
        )
        assert len(dr.low_level_requirements) == 2

    def test_round_trip(self):
        dr = DecomposedRequirementSchema(
            description="Calculator",
            low_level_requirements=[
                LowLevelRequirementSchema(
                    description="Div",
                    verifications=[
                        VerificationSchema(
                            method="automated",
                            test_name="test_div",
                            preconditions=[
                                VerificationConditionSchema(
                                    member_qualified_name="Calc::ready",
                                    expected_value="true",
                                )
                            ],
                        )
                    ],
                )
            ],
        )
        data = dr.model_dump()
        restored = DecomposedRequirementSchema.model_validate(data)
        assert restored.description == "Calculator"
        assert len(restored.low_level_requirements) == 1
        assert restored.low_level_requirements[0].verifications[0].test_name == "test_div"

    def test_json_round_trip(self):
        dr = DecomposedRequirementSchema(
            description="Math ops",
            low_level_requirements=[
                LowLevelRequirementSchema(
                    description="Mult",
                    verifications=[VerificationSchema(method="inspection")],
                )
            ],
        )
        json_str = dr.model_dump_json()
        restored = DecomposedRequirementSchema.model_validate_json(json_str)
        assert restored.low_level_requirements[0].description == "Mult"


# ---------------------------------------------------------------------------
# VerificationMethodType literal
# ---------------------------------------------------------------------------

class TestVerificationMethodTypeLiteral:
    def test_literal_matches_model_constant(self):
        """VerificationMethodType must stay in sync with VERIFICATION_METHODS."""
        from backend.db.models.verification import VERIFICATION_METHODS
        literal_methods = set(VerificationMethodType.__args__)
        model_methods = set(VERIFICATION_METHODS)
        assert literal_methods == model_methods, (
            f"VerificationMethodType {literal_methods} out of sync "
            f"with VERIFICATION_METHODS {model_methods}"
        )

    def test_all_methods_are_valid(self):
        for method in VerificationMethodType.__args__:
            vs = VerificationSchema(method=method)
            assert vs.method == method