"""
Pydantic schemas for requirements models.

These are the single source of truth for the structured data shapes used by
the AI agent and the persistence layer.

Phase 3: Conditions use subject_qualified_name/object_qualified_name for
typed operand edges to :Design nodes. Actions use caller_qualified_name/
callee_qualified_name. The legacy member_qualified_name field is removed.
"""

from typing import Literal

from pydantic import BaseModel

VERIFICATION_METHODS = ["automated", "review", "inspection"]

VerificationMethodType = Literal["automated", "review", "inspection"]

# Runtime check: if someone adds a method to this list but forgets
# to update the Literal above (or vice versa), this will fail at import time.
_literal_methods = set(VerificationMethodType.__args__)
_model_methods = set(VERIFICATION_METHODS)
if _literal_methods != _model_methods:
    raise RuntimeError(
        f"VerificationMethodType Literal {_literal_methods} is out of sync "
        f"with VERIFICATION_METHODS {_model_methods}. Update schemas.py."
    )


class VerificationConditionSchema(BaseModel):
    subject_qualified_name: str  # references :Design node via LEFT_OPERAND edge
    operator: str = "=="
    expected_value: str
    object_qualified_name: str = ""  # optional RIGHT_OPERAND edge reference


class VerificationActionSchema(BaseModel):
    description: str
    callee_qualified_name: str = ""  # :CALLEE edge target (method being invoked)
    caller_qualified_name: str = ""  # :CALLER edge target (object performing action)


class VerificationSchema(BaseModel):
    method: VerificationMethodType
    test_name: str = ""
    description: str = ""
    preconditions: list[VerificationConditionSchema] = []
    actions: list[VerificationActionSchema] = []
    postconditions: list[VerificationConditionSchema] = []


class LowLevelRequirementSchema(BaseModel):
    description: str
    verifications: list[VerificationSchema]


class DecomposedRequirementSchema(BaseModel):
    description: str
    low_level_requirements: list[LowLevelRequirementSchema]
