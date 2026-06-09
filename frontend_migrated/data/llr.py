"""LLR CRUD and detail data — migrated backend.

Uses neomodel models (LLR, HLR, VerificationMethod) for CRUD
operations and neomodel relationship managers for COMPOSES traversal.
Node identity is via ``refid`` (UniqueIdProperty), matching the
pattern used by HLR and FileNode.

Neomodel auto-initialises its database driver on first query, so no
explicit ``_ensure_driver()`` call is needed before neomodel
operations.  For raw Cypher, ``get_session()`` handles driver
initialisation internally.

No imports from backend/ anywhere in this module.
"""

from __future__ import annotations

import logging

from typing import TypedDict

from backend_migrated.models import HLR, LLR, VerificationMethod, Condition, Action

log = logging.getLogger(__name__)


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
    id: str
    method: str
    test_name: str | None
    description: str | None
    preconditions: list[ConditionRow]
    actions: list[ActionRow]
    postconditions: list[ConditionRow]


class HLRSummary(TypedDict):
    id: str
    description: str
    component: str | None


class LLRDetail(TypedDict):
    id: str
    description: str
    hlr: HLRSummary | None
    verifications: list[VerificationDetail]
    components: list[str]
    triples: list[dict]


def fetch_llr_detail(refid: str) -> LLRDetail | None:
    """Fetch all data needed for LLR detail page."""
    raise NotImplementedError("fetch_llr_detail — requires backend_migrated data layer")


def create_llr(hlr_refid: str, description: str) -> str:
    """Create a new LLR under an HLR in Neo4j. Returns the new LLR's refid.

    Uses ``CodeGraphNode.save_new()`` to validate, construct, and persist
    the node in one call.  Creates a COMPOSES edge from the parent HLR.
    """
    hlr = HLR.nodes.get_or_none(refid=hlr_refid)
    if not hlr:
        raise ValueError(f"HLR {hlr_refid} not found")

    llr = LLR.save_new(description=description, layer="design")
    hlr.llrs.connect(llr)

    log.info("Created LLR refid=%s under HLR refid=%s", llr.refid, hlr_refid)
    return llr.refid


def update_llr(refid: str, description: str) -> bool:
    """Update an LLR's description in Neo4j. Returns True on success.

    Uses ``CodeGraphNode.update()`` to validate and persist the change.
    """
    llr = LLR.nodes.get_or_none(refid=refid)
    if not llr:
        return False

    llr.update(description=description)
    return True


def delete_llr(refid: str) -> bool:
    """Delete an LLR and its COMPOSES subtree from Neo4j. Returns True on success.

    ``CodeGraphNode.delete()`` cascades through all outgoing COMPOSES
    children (depth-first, leaves first), disconnects remaining
    relationships, then removes the node.
    """
    llr = LLR.nodes.get_or_none(refid=refid)
    if not llr:
        return False

    llr.delete()
    return True