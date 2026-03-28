"""
Pydantic schemas for requirements models.

These are the single source of truth for the structured data shapes used by
both the ORM models and the AI agent.
"""

from typing import Literal

from pydantic import BaseModel

from backend.db.models.verification import VERIFICATION_METHODS

VerificationMethodType = Literal["automated", "review", "inspection"]

# Runtime check: if someone adds a method to the model but forgets
# to update the Literal above, this will fail at import time.
_literal_methods = set(VerificationMethodType.__args__)
_model_methods = set(VERIFICATION_METHODS)
if _literal_methods != _model_methods:
    raise RuntimeError(
        f"VerificationMethodType Literal {_literal_methods} is out of sync "
        f"with VERIFICATION_METHODS {_model_methods}. Update schemas.py."
    )


class VerificationConditionSchema(BaseModel):
    member_qualified_name: str
    operator: str = "=="
    expected_value: str


class VerificationActionSchema(BaseModel):
    description: str
    member_qualified_name: str = ""


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
