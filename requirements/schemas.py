"""
Pydantic schemas for requirements models.

These are the single source of truth for the structured data shapes used by
both the Django ORM models and the AI agent. If you add or rename fields on
the Django models, update these schemas to match.
"""

from typing import Literal

from pydantic import BaseModel

from requirements.models import VERIFICATION_METHODS

VerificationMethod = Literal["automated", "review", "inspection"]

# Runtime check: if someone adds a method to the Django model but forgets
# to update the Literal above, this will fail at import time.
_literal_methods = set(VerificationMethod.__args__)
_model_methods = set(VERIFICATION_METHODS)
if _literal_methods != _model_methods:
    raise RuntimeError(
        f"VerificationMethod Literal {_literal_methods} is out of sync "
        f"with VERIFICATION_METHODS {_model_methods}. Update schemas.py."
    )


class VerificationSchema(BaseModel):
    method: VerificationMethod
    confirmation: str
    test_name: str


class LowLevelRequirementSchema(BaseModel):
    description: str
    verifications: list[VerificationSchema]


class DecomposedRequirementSchema(BaseModel):
    description: str
    low_level_requirements: list[LowLevelRequirementSchema]
