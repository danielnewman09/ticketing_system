"""HLR CRUD, decomposition, and requirements dashboard data — migrated backend.

Uses raw Neo4j Cypher queries for HLR/LLR data aggregation (verification
method counts, design-graph statistics) via the shared codegraph connection
infrastructure.  Component names are resolved through :COMPOSES edges
(Component->HLR).  HLR/LLR neomodel models (:class:`HLR`, :class:`LLR`)
are defined in :mod:`backend_migrated.models.requirement` and registered
in the CodeGraphNode registry.  The relationship pattern is:

  Component -[:COMPOSES]-> HLR -[:COMPOSES]-> LLR

matching the codegraph LayerGraph composition pattern (Namespace > Class >
Method).  The legacy ``DECOMPOSES_INTO`` edge has been replaced by
``COMPOSES``, and ``component_id`` has been replaced by :COMPOSES edges.

No imports from backend/ anywhere in this module.
"""

from __future__ import annotations

import logging

from typing import TypedDict

# Importing codegraph.config at module level ensures the neomodel
# database URL is configured from environment variables before any
# neomodel model is touched.
from codegraph.config import config as _neo4j_config  # noqa: F401

from backend_migrated.models import Component

log = logging.getLogger(__name__)


def _ensure_driver() -> None:
    """Ensure neomodel's database driver is initialised."""
    from codegraph.connection import _ensure_driver as _cg_ensure
    _cg_ensure()


def _get_session():
    """Return a Neo4j session context manager from the shared connection pool."""
    from codegraph.connection import get_session
    return get_session()


# ---------------------------------------------------------------------------
# TypedDict contracts
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Requirements dashboard data
# ---------------------------------------------------------------------------


def _resolve_component_name_for_hlr(hlr_id: int) -> str | None:
    """Look up the Component name for an HLR via its COMPOSES relationship.

    In the migrated data model, Component nodes compose their HLRs
    via :COMPOSES edges (Component-[COMPOSES]->HLR).  This function
    queries Neo4j for the Component that composes the given HLR.
    Falls back to the legacy component_id property if no COMPOSES
    edge exists (e.g. during partial migration).
    """
    _ensure_driver()
    with _get_session() as ns:
        # Primary: follow the COMPOSES edge from Component to this HLR.
        result = ns.run(
            "MATCH (c:Component)-[:COMPOSES]->(h:HLR {id: $hid}) "
            "RETURN c.name AS name",
            {"hid": hlr_id},
        )
        record = result.single()
        if record and record["name"]:
            return record["name"]

    # Fallback: use the legacy component_id property (pre-migration data).
    # This handles HLR nodes that haven't had their COMPOSES edge created yet.
    try:
        with _get_session() as ns:
            hlr_result = ns.run(
                "MATCH (h:HLR {id: $hid}) RETURN h.component_id AS cid",
                {"hid": hlr_id},
            )
            hlr_rec = hlr_result.single()
            cid = hlr_rec["cid"] if hlr_rec else None
            if cid is None:
                return None

            # Try to find Component by neomodel uid or refid match.
            comp = Component.nodes.get_or_none(uid=cid)
            if comp is not None:
                return comp.name
            comp = Component.nodes.get_or_none(refid=str(cid))
            if comp is not None:
                return comp.name
    except Exception:
        pass
    return None


def fetch_requirements_data() -> RequirementsData:
    """Fetch all data needed for the requirements dashboard.

    Queries HLR, LLR, VerificationMethod, and design-graph node counts
    directly from Neo4j via Cypher. Component names are resolved through
    the neomodel Component model.
    """
    _ensure_driver()

    with _get_session() as ns:
        # --- HLRs and their LLRs ---
        hlr_result = ns.run("MATCH (h:HLR) RETURN h ORDER BY h.id")
        hlrs: list[HLRRow] = []
        hlr_ids: set[int] = set()

        for record in hlr_result:
            h = dict(record["h"])
            hlr_id = h["id"]
            hlr_ids.add(hlr_id)

            # Fetch LLRs for this HLR (COMPOSES edge replaces legacy DECOMPOSES_INTO)
            llr_result = ns.run(
                "MATCH (:HLR {id: $hid})-[:COMPOSES]->(l:LLR) RETURN l ORDER BY l.id",
                {"hid": hlr_id},
            )
            llrs: list[LLRRow] = []
            for llr_rec in llr_result:
                l = dict(llr_rec["l"])
                llr_id = l["id"]
                # Fetch verification methods for this LLR
                vm_result = ns.run(
                    "MATCH (:LLR {id: $lid})-[:VERIFIES]->(vm:VerificationMethod) "
                    "RETURN vm.method AS method",
                    {"lid": llr_id},
                )
                methods = [r["method"] for r in vm_result if r["method"]]
                llrs.append({"id": llr_id, "description": l["description"], "methods": methods})

            component_name = _resolve_component_name_for_hlr(hlr_id)

            hlrs.append({
                "id": hlr_id,
                "description": h["description"],
                "component": component_name,
                "llrs": llrs,
            })

        # --- Unlinked LLRs (no parent HLR) ---
        all_llr_result = ns.run("MATCH (l:LLR) RETURN l ORDER BY l.id")
        unlinked_llrs: list[LLRRow] = []
        total_llr_count = 0
        for record in all_llr_result:
            l = dict(record["l"])
            total_llr_count += 1
            parent_hlr_id = l.get("high_level_requirement_id")
            # An LLR is unlinked if its parent HLR id is not among known HLRs
            if parent_hlr_id not in hlr_ids:
                llr_id = l["id"]
                vm_result = ns.run(
                    "MATCH (:LLR {id: $lid})-[:VERIFIES]->(vm:VerificationMethod) "
                    "RETURN vm.method AS method",
                    {"lid": llr_id},
                )
                methods = [r["method"] for r in vm_result if r["method"]]
                unlinked_llrs.append({
                    "id": llr_id,
                    "description": l["description"],
                    "methods": methods,
                })

        # --- Aggregate counts ---
        total_verifications = ns.run(
            "MATCH (vm:VerificationMethod) RETURN count(vm) AS cnt"
        ).single()["cnt"]

        total_nodes = ns.run(
            "MATCH (d) WHERE d:Compound OR d:Member OR d:Namespace RETURN count(d) AS cnt"
        ).single()["cnt"]

        total_triples = ns.run(
            "MATCH (s)-[r]->(t) "
            "WHERE (s:Compound OR s:Member OR s:Namespace) "
            "AND (t:Compound OR t:Member OR t:Namespace) "
            "RETURN count(r) AS cnt"
        ).single()["cnt"]

    return {
        "hlrs": hlrs,
        "unlinked_llrs": unlinked_llrs,
        "total_hlrs": len(hlrs),
        "total_llrs": total_llr_count,
        "total_verifications": total_verifications,
        "total_nodes": total_nodes,
        "total_triples": total_triples,
    }


# ---------------------------------------------------------------------------
# HLR detail / CRUD — still stubs (to be migrated later)
# ---------------------------------------------------------------------------


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