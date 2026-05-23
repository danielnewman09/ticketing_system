"""Pydantic models for verification nodes in Neo4j.

Replaces SQLAlchemy VerificationMethod, VerificationCondition,
and VerificationAction models. Conditions and Actions are promoted
from table rows to full nodes with typed operand edges to :Design nodes.

Node labels and edge types:
  :VerificationMethod  -- linked to :LLR via (:LLR)-[:VERIFIES]->(:VerificationMethod)
  :Condition           -- linked via (:VerificationMethod)-[:HAS_CONDITION]->(:Condition)
  :Action              -- linked via (:VerificationMethod)-[:HAS_ACTION]->(:Action)

Typed operand edges:
  (:Condition)-[:LEFT_OPERAND]->(:Design)   -- subject of the assertion
  (:Condition)-[:RIGHT_OPERAND]->(:Design)  -- object/reference value
  (:Action)-[:CALLER]->(:Design)            -- the object performing the action
  (:Action)-[:CALLEE]->(:Design)            -- the method being invoked
"""

from __future__ import annotations

from pydantic import BaseModel


class VerificationMethodNode(BaseModel):
    """A verification method node in Neo4j.

    Stored as :VerificationMethod nodes linked to :LLR via :VERIFIES edges.
    Replaces the SQLAlchemy VerificationMethod model.
    """

    id: int
    llr_id: int
    method: str
    test_name: str = ""
    description: str = ""

    model_config = {"from_attributes": True}


class ConditionNode(BaseModel):
    """A pre/post-condition node in Neo4j.

    Stored as :Condition nodes linked to :VerificationMethod via
    :HAS_CONDITION edges. Linked to :Design nodes via :LEFT_OPERAND
    (subject) and :RIGHT_OPERAND (object) edges.

    The `subject_qualified_name` and `object_qualified_name` fields
    hold the qualified names used to create :LEFT_OPERAND/:RIGHT_OPERAND
    edges. They also serve as a fallback when the referenced :Design
    node does not exist yet.
    """

    id: int
    verification_method_id: int
    phase: str  # "pre" or "post"
    order: int = 0
    subject_qualified_name: str = ""
    operator: str = "=="
    expected_value: str = ""
    object_qualified_name: str = ""

    model_config = {"from_attributes": True}


class ActionNode(BaseModel):
    """An action step node in Neo4j.

    Stored as :Action nodes linked to :VerificationMethod via :HAS_ACTION
    edges. Linked to :Design nodes via :CALLER and :CALLEE edges.

    The `caller_qualified_name` and `callee_qualified_name` fields hold
    the qualified names used to create :CALLER/:CALLEE edges.
    """

    id: int
    verification_method_id: int
    order: int = 0
    description: str = ""
    caller_qualified_name: str = ""
    callee_qualified_name: str = ""

    model_config = {"from_attributes": True}
