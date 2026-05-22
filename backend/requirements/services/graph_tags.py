"""SQLite enrichment for Cytoscape node dicts — add HLR requirement tags.

This module is Stage 2 of the two-stage graph pipeline:
Stage 1 (Neo4j) produces bare topology; Stage 2 (SQLite) tags nodes
with requirement metadata. The two stages never import from each other.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


def enrich_with_requirement_tags(
    nodes: list[dict],
    mode: str = "none",
    session: "Session | None" = None,
) -> list[dict]:
    """Tag design nodes with HLR badges from SQLite.

    Modifies nodes in-place, adding a 'requirements' key to each node
    that is traced by one or more HLRs.

    Args:
        nodes: Cytoscape-format node dicts (from Stage 1).
        mode: "none" = no tags, "hlr" = add HLR tags.
        session: Optional SQLAlchemy session. If None, creates one via get_session().

    Returns:
        The same list (modified in-place).
    """
    if mode == "none":
        return nodes

    node_qns = {n["data"].get("qualified_name") for n in nodes if n["data"].get("qualified_name")}
    # Skip dependency stubs — they are cross-references, not design intent
    dependency_qns = {
        n["data"]["qualified_name"]
        for n in nodes
        if n["data"].get("qualified_name") and n["data"].get("source_type") == "dependency"
    }
    if not node_qns:
        return nodes

    from backend.db.models import HighLevelRequirement

    qn_to_reqs: dict[str, list[dict]] = {}

    def _query(session: "Session") -> None:
        for hlr in session.query(HighLevelRequirement).all():
            for node in hlr.nodes:
                if node.qualified_name in node_qns:
                    qn_to_reqs.setdefault(node.qualified_name, []).append({
                        "id": hlr.id,
                        "type": "HLR",
                        "description": hlr.description[:80],
                    })

    if session is not None:
        _query(session)
    else:
        from backend.db import get_session
        with get_session() as sess:
            _query(sess)

    for node in nodes:
        d = node["data"]
        qn = d.get("qualified_name", "")
        if qn in qn_to_reqs:
            d["requirements"] = qn_to_reqs[qn]
            badges = " ".join(f"[{r['type']} {r['id']}]" for r in qn_to_reqs[qn])
            d["label"] = d["label"] + "\n" + badges
            d["has_requirements"] = "true"

    return nodes


def tag_direct_nodes_only(
    nodes: list[dict],
    hlr_id: int,
    session: "Session | None" = None,
) -> None:
    """Mark seed nodes in an HLR subgraph with is_hlr_highlight and requirements tag.

    Only nodes directly linked to the HLR (via the M2M table) get the
    highlight flag and tag. 1-hop neighbours remain untagged.

    Args:
        nodes: Cytoscape-format node dicts.
        hlr_id: Database ID of the HLR to tag for.
        session: Optional SQLAlchemy session. If None, creates one via get_session().
    """
    from backend.db.models import HighLevelRequirement

    seed_qns: set[str] = set()
    hlr_desc: str = ""

    def _query(session: "Session") -> None:
        nonlocal seed_qns, hlr_desc
        hlr = session.query(HighLevelRequirement).filter_by(id=hlr_id).first()
        if not hlr:
            log.warning("tag_direct_nodes_only: HLR %d not found", hlr_id)
            return
        seed_qns = {n.qualified_name for n in hlr.nodes}
        hlr_desc = hlr.description[:80]

    if session is not None:
        _query(session)
    else:
        from backend.db import get_session
        with get_session() as sess:
            _query(sess)

    if not seed_qns:
        return

    for node in nodes:
        d = node["data"]
        qn = d.get("qualified_name", "")
        if qn in seed_qns:
            d["is_hlr_highlight"] = "true"
            d.setdefault("requirements", []).append({
                "id": hlr_id,
                "type": "HLR",
                "description": hlr_desc,
            })
            badge = f"[HLR {hlr_id}]"
            d["label"] = d.get("label", "") + "\n" + badge
            d["has_requirements"] = "true"
