"""LLR CRUD and detail data — stubs.

Return types are documented via TypedDicts. All functions raise
NotImplementedError until reimplemented against the migrated backend.
No imports from backend/ anywhere in this module.
"""

from __future__ import annotations

from typing import TypedDict


class ConditionRow(TypedDict):
    subject_qualified_name: str
    operator: str
    expected_value: str


class ActionRow(TypedDict):
    order: int
    description: str
    callee_qualified_name: str | None
    caller_qualified_name: str | None


class VerificationDetail(TypedDict):
    id: int
    method: str
    test_name: str | None
    description: str | None
    preconditions: list[ConditionRow]
    actions: list[ActionRow]
    postconditions: list[ConditionRow]


class HLRSummary(TypedDict):
    id: int
    description: str
    component: str | None


class LLRDetail(TypedDict):
    id: int
    description: str
    hlr: HLRSummary | None
    verifications: list[VerificationDetail]
    components: list[str]
    triples: list[dict]  # TripleRow — import from hlr.py if needed


def fetch_llr_detail(llr_id: int) -> LLRDetail | None:
    """Fetch all data needed for LLR detail page."""
    raise NotImplementedError("fetch_llr_detail — requires backend_migrated data layer")


def create_llr(hlr_id: int, description: str) -> int:
    """Create a new LLR under an HLR in Neo4j. Returns the new LLR id."""
    raise NotImplementedError("create_llr — requires backend_migrated data layer")


def update_llr(llr_id: int, description: str) -> bool:
    """Update an LLR's description in Neo4j. Returns True on success."""
    raise NotImplementedError("update_llr — requires backend_migrated data layer")


def delete_llr(llr_id: int) -> bool:
    """Delete an LLR from Neo4j. Returns True on success."""
    raise NotImplementedError("delete_llr — requires backend_migrated data layer")