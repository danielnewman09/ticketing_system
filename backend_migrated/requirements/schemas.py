"""Pydantic schemas for requirements models — derived from neomodel types.

Migrated from ``backend.requirements.schemas``. The verification schemas
are now built from the neomodel model ``_detail_fields`` rather than
hand-maintained Pydantic classes, ensuring they stay in sync with the
database models automatically.

The ``DecomposedRequirementSchema`` and ``LowLevelRequirementSchema``
remain as Pydantic models because they are composite structures (an HLR
decomposition containing LLRs containing verifications containing
conditions/actions) that don't map to a single neomodel node type.
However, the leaf schemas (conditions, actions, verification methods)
are generated from the neomodel models' ``_detail_fields`` and
property types via ``detail_schema()``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator

from backend_migrated.models.verification import (
    VerificationMethod,
    Condition,
    Action,
)

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


# ---------------------------------------------------------------------------
# JSON Schema generation from neomodel _detail_fields
# ---------------------------------------------------------------------------

_NEOMODEL_TYPE_MAP = {
    "StringProperty": "string",
    "IntegerProperty": "integer",
    "FloatProperty": "number",
    "BooleanProperty": "boolean",
    "ArrayProperty": "array",
    "UniqueIdProperty": "string",
}


def _neomodel_property_schema(prop) -> dict:
    """Generate a JSON Schema fragment for a single neomodel property."""
    type_name = type(prop).__name__
    json_type = _NEOMODEL_TYPE_MAP.get(type_name, "string")

    schema: dict = {"type": json_type}

    # Add description from help_text if available
    help_text = getattr(prop, "help_text", None) or getattr(prop, "__doc__", None)
    if help_text:
        schema["description"] = help_text

    # Handle defaults
    default = getattr(prop, "default", None)
    if default is not None and default != "":
        schema["default"] = default
    elif default == "":
        schema["default"] = ""

    return schema


def detail_schema(model_class) -> dict:
    """Generate a JSON Schema dict from a neomodel model's _detail_fields.

    This produces the same shape as a Pydantic model's ``model_json_schema()``
    but derives the field names and types directly from the neomodel property
    definitions, ensuring the schema stays in sync with the database model.

    Args:
        model_class: A neomodel StructuredNode subclass with _detail_fields.

    Returns:
        A JSON Schema dict suitable for use in LLM tool definitions.
    """
    properties = {}
    required = []

    for field_name in sorted(model_class._detail_fields):
        # Find the property descriptor on the model class hierarchy
        prop = None
        for klass in reversed(model_class.__mro__):
            if field_name in vars(klass):
                candidate = vars(klass)[field_name]
                if hasattr(candidate, 'default') or hasattr(candidate, 'required'):
                    prop = candidate
                    break

        if prop is None:
            # Field not found as neomodel property — include as string
            properties[field_name] = {"type": "string"}
            continue

        properties[field_name] = _neomodel_property_schema(prop)

        # Mark required fields
        is_required = getattr(prop, 'required', False) or getattr(prop, 'required', False)
        if is_required:
            required.append(field_name)

    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
    }


# ---------------------------------------------------------------------------
# Leaf schemas — built from neomodel _detail_fields
# ---------------------------------------------------------------------------

# These replace the hand-maintained Pydantic VerificationConditionSchema,
# VerificationActionSchema, and VerificationSchema.  The JSON Schema
# fragments are generated from the neomodel models' property definitions.

ConditionSchema = detail_schema(Condition)
ActionSchema = detail_schema(Action)
VerificationMethodSchema = detail_schema(VerificationMethod)


# ---------------------------------------------------------------------------
# Composite schemas — remain as Pydantic models
# ---------------------------------------------------------------------------


class LowLevelRequirementSchema(BaseModel):
    """A single low-level requirement with its verification stubs.

    The ``verifications`` list uses field names derived from the neomodel
    VerificationMethod, Condition, and Action ``_detail_fields``.
    """
    description: str
    verifications: list[dict] = []


class DecomposedRequirementSchema(BaseModel):
    """Structured output of the HLR decomposition agent.

    Contains the HLR description and a list of low-level requirements
    with verification stubs.  Each verification stub is a flat dict
    whose field names are derived from the neomodel models'
    ``_detail_fields``.
    """
    description: str
    low_level_requirements: list[LowLevelRequirementSchema]