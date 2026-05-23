"""
Pydantic schemas for requirements models.

These are the single source of truth for the structured data shapes used by
the AI agent and the persistence layer.

Phase 3: VERIFICATION_METHODS is defined here (not imported from the
deleted SQLAlchemy model). The schema now includes qualified_name reference
fields (subject_qualified_name, object_qualified_name, caller_qualified_name,
callee_qualified_name) alongside legacy member_qualified_name. The repository
uses subject_qualified_name/caller_qualified_name when present, falling back
to member_qualified_name for backward compatibility.
"""

from typing import Literal

from pydantic import BaseModel

# Self-contained list — no longer imported from the deleted SQLAlchemy model.
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
    member_qualified_name: str  # legacy — used as fallback for subject_qualified_name
    operator: str = "=="
    expected_value: str
    subject_qualified_name: str = ""  # Phase 3: references :Design node via LEFT_OPERAND edge
    object_qualified_name: str = ""  # Phase 3: optional RIGHT_OPERAND edge reference


class VerificationActionSchema(BaseModel):
    description: str
    member_qualified_name: str = ""  # legacy — used as fallback for callee_qualified_name
    caller_qualified_name: str = ""  # Phase 3: :CALLER edge target (object performing action)
    callee_qualified_name: str = ""  # Phase 3: :CALLEE edge target (method being invoked)


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
