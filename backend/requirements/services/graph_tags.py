"""Cypher-based enrichment for Cytoscape node dicts — add HLR/LLR requirement tags.

In Phase 2, HLR and LLR nodes are full Neo4j citizens with native id
properties (no more sqlite_id bridge). Tags are enriched via TRACES_TO
edges from :HLR and :LLR nodes to :Design nodes.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from neo4j import Session as Neo4jSession

log = logging.getLogger(__name__)


def enrich_with_requirement_tags(
    nodes: list[dict],
    mode: str = "none",
    session: "Neo4jSession | None" = None,
) -> list[dict]:
    """Tag design nodes with HLR/LLR badges from Neo4j requirement nodes.

    Modifies nodes in-place, adding a 'requirements' key to each node
    that is traced by one or more requirements.

    Args:
        nodes: Cytoscape-format node dicts (from Stage 1).
        mode: "none" = no tags, "hlr" = add HLR tags.
        session: Neo4j session for Cypher queries. If None, creates one.

    Returns:
        The same list (modified in-place).
    """
    if mode == "none":
        return nodes

    node_qns = [
        n["data"].get("qualified_name")
        for n in nodes
        if n["data"].get("qualified_name") and n["data"].get("source_type") != "dependency"
    ]
    if not node_qns:
        return nodes

    if session is not None:
        _enrich_via_cypher(session, node_qns, nodes)
    else:
        from services.dependencies import get_neo4j
        neo4j_conn = get_neo4j()
        with neo4j_conn.session() as sess:
            _enrich_via_cypher(sess, node_qns, nodes)

    return nodes


def _enrich_via_cypher(
    session: "Neo4jSession",
    node_qns: list[str],
    nodes: list[dict],
) -> None:
    """Run Cypher to find HLR/LLR→Design traces and tag matching nodes."""
    qn_to_reqs: dict[str, list[dict]] = {}

    result = session.run(
        """
        UNWIND $qns AS qn
        MATCH (r)-[:TRACES_TO]->(d:Design {qualified_name: qn})
        WHERE r:HLR OR r:LLR
        RETURN d.qualified_name AS qn, r.id AS req_id, r.description AS req_desc,
               CASE WHEN r:HLR THEN 'HLR' ELSE 'LLR' END AS req_type
        """,
        {"qns": node_qns},
    )
    for record in result:
        qn = record["qn"]
        qn_to_reqs.setdefault(qn, []).append({
            "id": record["req_id"],
            "type": record["req_type"],
            "description": (record["req_desc"] or "")[:80],
        })

    for node in nodes:
        d = node["data"]
        qn = d.get("qualified_name", "")
        if qn in qn_to_reqs:
            d["requirements"] = qn_to_reqs[qn]
            badges = " ".join(f"[{r['type']} {r['id']}]" for r in qn_to_reqs[qn])
            d["label"] = d.get("label", "") + "\n" + badges
            d["has_requirements"] = "true"


def tag_direct_nodes_only(
    nodes: list[dict],
    hlr_id: int,
    session: "Neo4jSession | None" = None,
) -> None:
    """Mark seed nodes in an HLR subgraph with is_hlr_highlight and requirements tag.

    Only nodes directly linked to the HLR (via TRACES_TO edges) get the
    highlight flag and tag. 1-hop neighbours remain untagged.

    Args:
        nodes: Cytoscape-format node dicts.
        hlr_id: Neo4j id of the HLR to tag for.
        session: Neo4j session. If None, creates one.
    """
    seed_qns: set[str] = set()

    def _query(sess: "Neo4jSession") -> None:
        nonlocal seed_qns
        result = sess.run(
            """
            MATCH (hlr:HLR {id: $hid})-[:TRACES_TO]->(d:Design)
            RETURN d.qualified_name AS qn
            """,
            {"hid": hlr_id},
        )
        for record in result:
            seed_qns.add(record["qn"])

    if session is not None:
        _query(session)
    else:
        from services.dependencies import get_neo4j
        with get_neo4j().session() as sess:
            _query(sess)

    if not seed_qns:
        return

    # Fetch HLR description for badge
    hlr_desc = ""
    if session is not None:
        rec = session.run(
            "MATCH (hlr:HLR {id: $hid}) RETURN hlr.description AS desc",
            {"hid": hlr_id},
        ).single()
        if rec:
            hlr_desc = (rec["desc"] or "")[:80]
    else:
        from services.dependencies import get_neo4j
        with get_neo4j().session() as sess:
            rec = sess.run(
                "MATCH (hlr:HLR {id: $hid}) RETURN hlr.description AS desc",
                {"hid": hlr_id},
            ).single()
            if rec:
                hlr_desc = (rec["desc"] or "")[:80]

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