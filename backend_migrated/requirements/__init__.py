"""Requirements schemas and formatting — migrated from backend.requirements.

This package provides:
- JSON Schema generation from neomodel model _detail_fields (detail_schema)
- Composite Pydantic models for LLM agent I/O (DecomposedRequirementSchema)
- Formatting helpers for requirement data (format_hlr_dict, etc.)

No imports from ``backend/``.
"""

from backend_migrated.requirements.schemas import (
    DecomposedRequirementSchema,
    LowLevelRequirementSchema,
    VERIFICATION_METHODS,
    VerificationMethodType,
    VerificationMethodSchema,
    ConditionSchema,
    ActionSchema,
    detail_schema,
)
from backend_migrated.requirements.formatting import (
    format_hlr_dict,
    format_llr_dict,
    format_hlrs_for_prompt,
    format_llrs_with_verifications_for_prompt,
)

__all__ = [
    # Composite Pydantic schemas
    "DecomposedRequirementSchema",
    "LowLevelRequirementSchema",
    # Neomodel-derived JSON schemas
    "VerificationMethodSchema",
    "ConditionSchema",
    "ActionSchema",
    "detail_schema",
    # Constants
    "VERIFICATION_METHODS",
    "VerificationMethodType",
    # Formatting
    "format_hlr_dict",
    "format_llr_dict",
    "format_hlrs_for_prompt",
    "format_llrs_with_verifications_for_prompt",
]