"""Compound-layer queries returning raw dicts.

Handles codebase (no ``source`` property) and dependency (with ``source``)
compound discovery and graph retrieval.
"""

from __future__ import annotations

import logging

from services.dependencies import get_neo4j

log = logging.getLogger(__name__)


def _discover_dependency_compounds(
    session,
    search: str | None,
    source_filter: str | None,
    limit: int,
) -> set[str]:
    """Find dependency Compound element-IDs using full-text or CONTAINS search."""
    search_term = (search or "").strip()
    if not search_term:
        return set()

    # Normalise so the param is always present (None → no filter).
    effective_source = source_filter or None
    params: dict = {"query": search_term, "limit": limit, "source_filter": effective_source}

    try:
        result = session.run(
            """
            CALL db.index.fulltext.queryNodes('doc_search', $query)
            YIELD node, score
            WHERE node.source IS NOT NULL AND node.source <> ''
              AND ($source_filter IS NULL OR node.source CONTAINS $source_filter)
            WITH node, score
            ORDER BY score DESC
            LIMIT $limit
            WITH collect({node: node, score: score}) AS hits,
                 max(score) AS top_score
            UNWIND hits AS hit
            WITH hit.node AS node, hit.score AS score, top_score
            WHERE score >= top_score * 0.4
            WITH CASE
                WHEN node:Compound THEN node
                ELSE null
            END AS direct_compound, node
            OPTIONAL MATCH (owner:Compound)-[:CONTAINS]->(node)
            WHERE NOT node:Compound AND owner.source IS NOT NULL
            WITH coalesce(direct_compound, owner) AS c
            WHERE c IS NOT NULL
            RETURN DISTINCT c
        """,
            params,
        )
    except Exception:
        log.warning("Full-text index 'doc_search' unavailable, falling back to CONTAINS search")
        result = session.run(
            """
            MATCH (n)
            WHERE n.source IS NOT NULL AND n.source <> ''
              AND (n.name CONTAINS $search OR n.qualified_name CONTAINS $search)
              AND ($source_filter IS NULL OR n.source CONTAINS $source_filter)
              AND (n:Compound OR n:Member)
            WITH n LIMIT $limit
            WITH CASE WHEN n:Compound THEN n ELSE null END AS direct_compound, n
            OPTIONAL MATCH (owner:Compound)-[:CONTAINS]->(n)
            WHERE NOT n:Compound AND owner.source IS NOT NULL
            WITH coalesce(direct_compound, owner) AS c
            WHERE c IS NOT NULL
            RETURN DISTINCT c
        """,
            {
                "search": search_term,
                "limit": limit,
                "source_filter": effective_source,
            },
        )

    ids = {record["c"].element_id for record in result}
    log.debug(
        "_discover_dependency_compounds: %d compounds found for %r",
        len(ids),
        search_term,
    )
    return ids


def _discover_codebase_compounds(session, search: str | None) -> set[str]:
    """Find codebase Compound element-IDs (no ``source`` property)."""
    result = session.run(
        """
        MATCH (c:Compound)
        WHERE $search IS NULL OR c.name CONTAINS $search OR c.qualified_name CONTAINS $search
        RETURN c
        """,
        {"search": search},
    )
    ids = {record["c"].element_id for record in result if not record["c"].get("source", "")}
    log.debug("_discover_codebase_compounds: %d compounds found for %r", len(ids), search)
    return ids


def fetch_codebase_compounds(search: str | None = None) -> dict:
    """Fetch codebase compound graph as raw dicts (no source property)."""
    log.info("fetch_codebase_compounds(search=%s)", search)
    with get_neo4j().session() as session:
        compound_ids = _discover_codebase_compounds(session, search)
        if not compound_ids:
            return {"nodes": [], "edges": []}
        return _fetch_compound_raw(session, compound_ids, "codebase")


def fetch_dependency_compounds(
    search: str | None = None,
    source_filter: str | None = None,
    limit: int = 100,
) -> dict:
    """Fetch dependency compound graph as raw dicts (with source property)."""
    log.info("fetch_dependency_compounds(search=%s, source=%s)", search, source_filter)
    with get_neo4j().session() as session:
        compound_ids = _discover_dependency_compounds(session, search, source_filter, limit)
        if not compound_ids:
            return {"nodes": [], "edges": []}
        return _fetch_compound_raw(session, compound_ids, "dependency")


def _fetch_compound_raw(session, compound_ids: set[str], layer: str) -> dict:
    """Fetch compounds and their members as raw dicts.

    *compound_ids* is the seed set from discovery.  The inheritance query
    may expand it (adding base/derived Compound IDs), and the expanded
    set is then used to fetch compounds + members.
    """
    nodes: list[dict] = []
    edges: list[dict] = []

    # Copy so the caller's set is never mutated.
    expanded_ids: set[str] = set(compound_ids)

    # Inheritance edges
    result = session.run(
        """
        UNWIND $cids AS cid
        MATCH (c:Compound) WHERE elementId(c) = cid
        OPTIONAL MATCH (c)-[r1:INHERITS_FROM]->(base:Compound)
        OPTIONAL MATCH (derived:Compound)-[r2:INHERITS_FROM]->(c)
        RETURN c, r1, base, r2, derived
    """,
        {"cids": list(expanded_ids)},
    )

    for record in result:
        expanded_ids.add(record["c"].element_id)
        for role, rel_key in [("base", "r1"), ("derived", "r2")]:
            n = record[role]
            r = record[rel_key]
            if r is not None:
                expanded_ids.add(n.element_id)
                edges.append(
                    {
                        "source": (
                            record["c"].get("qualified_name", record["c"].element_id)
                            if role == "base"
                            else n.get("qualified_name", n.element_id)
                        ),
                        "target": (
                            n.get("qualified_name", n.element_id)
                            if role == "base"
                            else record["c"].get("qualified_name", record["c"].element_id)
                        ),
                        "type": "INHERITS_FROM",
                    }
                )

    # Compounds + members (using the expanded set that now includes
    # base/derived compounds discovered from inheritance).
    result2 = session.run(
        """
        UNWIND $cids AS cid
        MATCH (c:Compound) WHERE elementId(c) = cid
        OPTIONAL MATCH (c)-[r:CONTAINS]->(m:Member)
        RETURN c, r, m
    """,
        {"cids": list(expanded_ids)},
    )

    seen_node_ids: set[str] = set()
    for record in result2:
        c = record["c"]
        if c.element_id not in seen_node_ids:
            seen_node_ids.add(c.element_id)
            d = dict(c)
            d["layer"] = layer
            nodes.append(d)
        m = record["m"]
        r = record["r"]
        if m is not None and m.element_id not in seen_node_ids:
            seen_node_ids.add(m.element_id)
            d = dict(m)
            d["layer"] = layer
            nodes.append(d)
        if r is not None and m is not None:
            edges.append(
                {
                    "source": c.get("qualified_name", c.element_id),
                    "target": m.get("qualified_name", m.element_id),
                    "type": "CONTAINS",
                }
            )

    log.debug("_fetch_compound_raw(%s): %d nodes, %d edges", layer, len(nodes), len(edges))
    return {"nodes": nodes, "edges": edges}


def fetch_design_dependency_links(design_qnames: list[str]) -> dict:
    """Find dependency Compounds linked to given Design nodes as raw dicts."""
    log.info("fetch_design_dependency_links(%d qnames)", len(design_qnames))
    if not design_qnames:
        return {"nodes": [], "edges": []}

    with get_neo4j().session() as session:
        nodes: list[dict] = []
        edges: list[dict] = []
        seen_qns: set[str] = set()

        def _add(d: dict) -> None:
            qn = d.get("qualified_name", d.element_id)
            if qn not in seen_qns:
                seen_qns.add(qn)
                nodes.append(dict(d))

        result = session.run(
            """
        UNWIND $qnames AS qn
        MATCH (d:Design {qualified_name: qn})-[r]->(dep:Compound)
        WHERE dep.source IS NOT NULL AND dep.source <> ''
        RETURN d, dep, type(r) AS rel_type
        """,
            {"qnames": design_qnames},
        )
        for record in result:
            _add(record["d"])
            _add(record["dep"])
            edges.append(
                {
                    "source": record["d"].get("qualified_name", ""),
                    "target": record["dep"].get("qualified_name", ""),
                    "type": record["rel_type"],
                }
            )

        result2 = session.run(
            """
        UNWIND $qnames AS qn
        MATCH (d:Design {qualified_name: qn})-[r:DEPENDS_ON]->(d2:Design)
        WITH d, r, d2
        MATCH (dep:Compound {qualified_name: d2.qualified_name})
        WHERE dep.source IS NOT NULL AND dep.source <> ''
        RETURN d, dep, type(r) AS rel_type
        """,
            {"qnames": design_qnames},
        )
        for record in result2:
            _add(record["d"])
            _add(record["dep"])
            edges.append(
                {
                    "source": record["d"].get("qualified_name", ""),
                    "target": record["dep"].get("qualified_name", ""),
                    "type": record["rel_type"],
                }
            )

    return {"nodes": nodes, "edges": edges}
