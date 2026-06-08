"""HLR CRUD, decomposition, and requirements dashboard data — migrated backend.

Uses neomodel objects (HLR, LLR, VerificationMethod, Component) for
requirement traversal and ``CodeGraphNode.serialize()`` for dict
production.  Cross-cutting aggregate counts (total design-graph nodes,
total triples) still use raw Cypher since they span the entire codegraph.

The COMPOSES hierarchy:

  Component → HLR → LLR → VerificationMethod

mirrors the codegraph LayerGraph composition pattern (Namespace → Class
→ Method).  Neomodel relationship managers (``.llrs.all()``,
``.component.all()``, etc.) replace raw Cypher traversal.

No imports from backend/ anywhere in this module.
"""

from __future__ import annotations

import logging

# Importing codegraph.config at module level ensures the neomodel
# database URL is configured from environment variables before any
# neomodel model is touched.
from codegraph.config import config as _neo4j_config  # noqa: F401

from backend_migrated.models import Component, HLR, LLR, VerificationMethod

log = logging.getLogger(__name__)


def _ensure_driver() -> None:
    """Ensure neomodel's database driver is initialised."""
    from codegraph.connection import _ensure_driver as _cg_ensure
    _cg_ensure()


def _get_session():
    """Return a Neo4j session context manager from the shared connection pool.

    Used only for cross-cutting aggregate counts that span the entire
    codegraph and cannot be expressed as neomodel queries on a single
    node type.
    """
    from codegraph.connection import get_session
    return get_session()


# ---------------------------------------------------------------------------
# Requirements dashboard data
# ---------------------------------------------------------------------------


def _serialize_llr(llr: LLR) -> dict:
    """Serialize an LLR node with its verification methods attached.

    Returns a dict with the LLR's serialized properties plus a
    ``methods`` key listing verification method types.
    """
    data = llr.serialize(fields="all")
    vms = llr.verification_methods.all()
    data["methods"] = [vm.method for vm in vms if vm.method]
    return data


def fetch_requirements_data() -> dict:
    """Fetch all data needed for the requirements dashboard.

    Uses neomodel objects for HLR/LLR/VM traversal and
    ``CodeGraphNode.serialize()`` for dict production.  Design-graph
    aggregate counts (total_nodes, total_triples) use raw Cypher since
    they span all code-level node types.

    Returns a dict with keys:
      hlrs              — list of serialized HLR dicts (with llrs and component)
      unlinked_llrs     — list of serialized LLR dicts with no parent HLR
      total_hlrs        — number of HLR nodes
      total_llrs        — number of LLR nodes
      total_verifications — number of VerificationMethod nodes
      total_nodes       — number of design-graph nodes (CompoundNode, MemberNode, NamespaceNode)
      total_triples     — number of design-graph edges
    """
    _ensure_driver()

    # --- HLRs and their LLRs via neomodel ---
    all_hlrs = HLR.nodes.all()
    hlr_refids: set[str] = set()
    hlrs: list[dict] = []

    for hlr in all_hlrs:
        hlr_refids.add(hlr.refid)

        # Serialize the HLR node (all fields including refid)
        hlr_data = hlr.serialize(fields="all")

        # Traverse COMPOSES → LLR children
        llr_nodes = hlr.llrs.all()
        hlr_data["llrs"] = [_serialize_llr(l) for l in llr_nodes]

        # Traverse incoming COMPOSES ← Component
        comp_nodes = hlr.component.all()
        hlr_data["component"] = comp_nodes[0].name if comp_nodes else None

        hlrs.append(hlr_data)

    # --- Unlinked LLRs (no parent HLR via COMPOSES) ---
    all_llrs = LLR.nodes.all()
    linked_refids: set[str] = set()
    for hlr in all_hlrs:
        for llr in hlr.llrs.all():
            linked_refids.add(llr.refid)

    unlinked_llrs: list[dict] = []
    for llr in all_llrs:
        if llr.refid not in linked_refids:
            unlinked_llrs.append(_serialize_llr(llr))

    # --- Aggregate counts ---
    total_verifications = len(VerificationMethod.nodes.all())

    # Design-graph counts span all code-level node types — use raw Cypher.
    with _get_session() as ns:
        total_nodes = ns.run(
            "MATCH (d) WHERE d:CompoundNode OR d:MemberNode OR d:NamespaceNode RETURN count(d) AS cnt"
        ).single()["cnt"]

        total_triples = ns.run(
            "MATCH (s)-[r]->(t) "
            "WHERE (s:CompoundNode OR s:MemberNode OR s:NamespaceNode) "
            "AND (t:CompoundNode OR t:MemberNode OR t:NamespaceNode) "
            "RETURN count(r) AS cnt"
        ).single()["cnt"]

    return {
        "hlrs": hlrs,
        "unlinked_llrs": unlinked_llrs,
        "total_hlrs": len(hlrs),
        "total_llrs": len(all_llrs),
        "total_verifications": total_verifications,
        "total_nodes": total_nodes,
        "total_triples": total_triples,
    }


# ---------------------------------------------------------------------------
# HLR detail / CRUD — still stubs (to be migrated later)
# ---------------------------------------------------------------------------


def fetch_hlr_detail(hlr_id: int) -> dict | None:
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


def decompose_hlr(hlr_id: int) -> dict:
    """Run the decomposition agent on an HLR and persist results to Neo4j."""
    raise NotImplementedError("decompose_hlr — requires backend_migrated data layer")


def design_single_hlr(hlr_id: int) -> dict:
    """Run the design agent on an HLR and persist the ontology results."""
    raise NotImplementedError("design_single_hlr — requires backend_migrated data layer")