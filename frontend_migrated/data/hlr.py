"""HLR CRUD, decomposition, and requirements dashboard data — stubs.

Return types are documented via TypedDicts. All functions raise
NotImplementedError until reimplemented against the migrated backend.
No imports from backend/ anywhere in this module.
"""

from __future__ import annotations

from typing import TypedDict


class LLRRow(TypedDict):
    id: int
    description: str
    methods: list[str]


class HLRRow(TypedDict):
    id: int
    description: str
    component: str | None
    llrs: list[LLRRow]


class RequirementsData(TypedDict):
    hlrs: list[HLRRow]
    unlinked_llrs: list[LLRRow]
    total_hlrs: int
    total_llrs: int
    total_verifications: int
    total_nodes: int
    total_triples: int


class TripleRow(TypedDict):
    subject: str
    predicate: str
    object: str


class HLRDetail(TypedDict):
    id: int
    description: str
    component: str | None
    component_id: int | None
    llrs: list[LLRRow]
    triples: list[TripleRow]


class DecompositionResult(TypedDict):
    llrs_created: int
    verifications_created: int


def fetch_requirements_data() -> RequirementsData:
    """Fetch all data needed for the requirements dashboard."""
    raise NotImplementedError("fetch_requirements_data — requires backend_migrated data layer")


def fetch_hlr_detail(hlr_id: int) -> HLRDetail | None:
    """Fetch all data needed for HLR detail page."""
    raise NotImplementedError("fetch_hlr_detail — requires backend_migrated data layer")


def create_hlr(description: str, component_id: int | None = None) -> int:
    """Create a new HLR in Neo4j. Returns the new HLR id."""
    raise NotImplementedError("create_hlr — requires backend_migrated data layer")


def update_hlr(hlr_id: int, description: str, component_id: int | None = None) -> bool:
    """Update an HLR's description and component in Neo4j. Returns True on success."""
    raise NotImplementedError("update_hlr — requires backend_migrated data layer")


def delete_hlr(hlr_id: int) -> bool:
    """Delete an HLR and its child LLRs from Neo4j. Returns True on success."""
    raise NotImplementedError("delete_hlr — requires backend_migrated data layer")


def decompose_hlr(hlr_id: int) -> DecompositionResult:
    """Run the decomposition agent on an HLR and persist results to Neo4j."""
    raise NotImplementedError("decompose_hlr — requires backend_migrated data layer")


def design_single_hlr(hlr_id: int) -> dict:
    """Run the design agent on an HLR and persist the ontology results."""
    raise NotImplementedError("design_single_hlr — requires backend_migrated data layer")