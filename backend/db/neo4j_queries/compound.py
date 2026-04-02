"""Codebase and dependency layer graph queries."""

from __future__ import annotations

import logging

from services.dependencies import get_neo4j

from backend.db.neo4j_queries._graph_transforms import (
    _assign_namespace_parents,
    _collapse_members,
)
from backend.db.neo4j_queries._node_builders import (
    _make_compound_node,
    _make_dependency_node,
    _make_node_data,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Compound discovery
# ---------------------------------------------------------------------------

def _discover_dependency_compounds(
    session,
    search: str | None,
    source_filter: str | None,
    limit: int,
) -> set[str]:
    """Find dependency Compound element-IDs using full-text search.

    Falls back to CONTAINS-based search when the ``doc_search`` index is
    unavailable.
    """
    search_term = (search or "").strip()
    if not search_term:
        return set()

    source_clause = "AND node.source CONTAINS $source_filter" if source_filter else ""
    params: dict = {"query": search_term, "limit": limit}
    if source_filter:
        params["source_filter"] = source_filter

    try:
        query_str = f"""
            CALL db.index.fulltext.queryNodes('doc_search', $query)
            YIELD node, score
            WHERE node.source IS NOT NULL AND node.source <> ''
              {source_clause}
            WITH node, score
            ORDER BY score DESC
            LIMIT $limit
            WITH collect({{node: node, score: score}}) AS hits,
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
        """
        result = session.run(query_str, params)
    except Exception:
        log.warning(
            "Full-text index 'doc_search' unavailable, falling back to CONTAINS search"
        )
        fallback_where = (
            "n.source IS NOT NULL AND n.source <> '' "
            "AND (n.name CONTAINS $search OR n.qualified_name CONTAINS $search)"
        )
        if source_filter:
            fallback_where += " AND n.source CONTAINS $source_filter"
        result = session.run(f"""
            MATCH (n) WHERE ({fallback_where}) AND (n:Compound OR n:Member)
            WITH n LIMIT $limit
            WITH CASE WHEN n:Compound THEN n ELSE null END AS direct_compound, n
            OPTIONAL MATCH (owner:Compound)-[:CONTAINS]->(n)
            WHERE NOT n:Compound AND owner.source IS NOT NULL
            WITH coalesce(direct_compound, owner) AS c
            WHERE c IS NOT NULL
            RETURN DISTINCT c
        """, {
            "search": search_term,
            "limit": limit,
            "source_filter": source_filter,
        })

    return {record["c"].element_id for record in result}


def _discover_codebase_compounds(
    session,
    search: str | None,
) -> set[str]:
    """Find codebase Compound element-IDs (no ``source`` property)."""
    conditions: list[str] = []
    params: dict = {}
    if search:
        conditions.append(
            "(c.name CONTAINS $search OR c.qualified_name CONTAINS $search)"
        )
        params["search"] = search

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    result = session.run(
        f"MATCH (c:Compound) {where_clause} RETURN c", params,
    )
    return {
        record["c"].element_id
        for record in result
        if not record["c"].get("source", "")
    }


# ---------------------------------------------------------------------------
# Compound-layer pipeline
# ---------------------------------------------------------------------------

def _fetch_compound_layer(
    layer: str,
    search: str | None,
    source_filter: str | None,
    limit: int,
) -> dict:
    """Fetch graph for compound-based layers (codebase / dependency).

    Pipeline:
      1. Discover root Compound IDs (method varies by layer).
      2. Fetch inheritance edges (1 hop up/down).
      3. Fetch all Compounds with their CONTAINS -> Member edges.
      4. Collapse members + assign namespace parents.
    """
    with get_neo4j().session() as session:
        if layer == "dependency":
            compound_ids = _discover_dependency_compounds(session, search, source_filter, limit)
        else:
            compound_ids = _discover_codebase_compounds(session, search)

        if not compound_ids:
            return {"nodes": [], "edges": []}

        nodes: list[dict] = []
        edges: list[dict] = []
        node_ids: set[str] = set()
        edge_ids: set[str] = set()

        # --- Inheritance edges (1 up, 1 down) ---
        result = session.run("""
            UNWIND $cids AS cid
            MATCH (c:Compound) WHERE elementId(c) = cid
            OPTIONAL MATCH (c)-[r1:INHERITS_FROM]->(base:Compound)
            OPTIONAL MATCH (derived:Compound)-[r2:INHERITS_FROM]->(c)
            RETURN c, r1, base, r2, derived
        """, {"cids": list(compound_ids)})

        for record in result:
            compound_ids.add(record["c"].element_id)
            for role, rel in [("base", "r1"), ("derived", "r2")]:
                n = record[role]
                r = record[rel]
                if n is not None:
                    compound_ids.add(n.element_id)
                if r is not None and r.element_id not in edge_ids:
                    edge_ids.add(r.element_id)
                    src = record["c"].element_id if role == "base" else n.element_id
                    tgt = n.element_id if role == "base" else record["c"].element_id
                    edges.append({
                        "data": {
                            "id": r.element_id,
                            "source": src,
                            "target": tgt,
                            "label": "INHERITS_FROM",
                        }
                    })

        # --- Compounds + Members ---
        result2 = session.run("""
            UNWIND $cids AS cid
            MATCH (c:Compound) WHERE elementId(c) = cid
            OPTIONAL MATCH (c)-[r:CONTAINS]->(m:Member)
            RETURN c, r, m
        """, {"cids": list(compound_ids)})

        for record in result2:
            c = record["c"]
            if c.element_id not in node_ids:
                node_ids.add(c.element_id)
                nodes.append({"data": _make_compound_node(c, layer)})

            m = record["m"]
            r = record["r"]
            if m is not None and m.element_id not in node_ids:
                node_ids.add(m.element_id)
                nodes.append({"data": _make_compound_node(m, layer)})
            if r is not None and m is not None:
                edges.append({
                    "data": {
                        "id": r.element_id,
                        "source": c.element_id,
                        "target": m.element_id,
                        "label": "CONTAINS",
                    }
                })

    nodes, edges = _collapse_members(nodes, edges)
    nodes, edges = _assign_namespace_parents(nodes, edges)
    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# Design ↔ dependency links
# ---------------------------------------------------------------------------

def fetch_design_dependency_links(design_qnames: list[str]) -> dict:
    """Find dependency Compounds linked to given Design nodes.

    Returns Cytoscape-format ``{"nodes": [...], "edges": [...]}``.
    """
    if not design_qnames:
        return {"nodes": [], "edges": []}

    with get_neo4j().session() as session:
        nodes: list[dict] = []
        edges: list[dict] = []
        node_ids: set[str] = set()

        # Direct relationships from Design to dependency Compounds
        result = session.run("""
        UNWIND $qnames AS qn
        MATCH (d:Design {qualified_name: qn})-[r]->(dep:Compound)
        WHERE dep.source IS NOT NULL AND dep.source <> ''
        RETURN d, r, dep
        """, {"qnames": design_qnames})

        for record in result:
            d = record["d"]
            dep = record["dep"]
            r = record["r"]

            if d.element_id not in node_ids:
                node_ids.add(d.element_id)
                nodes.append({"data": _make_node_data(d)})

            if dep.element_id not in node_ids:
                node_ids.add(dep.element_id)
                nodes.append({"data": _make_dependency_node(dep)})

            edges.append({
                "data": {
                    "id": r.element_id,
                    "source": d.element_id,
                    "target": dep.element_id,
                    "label": r.type,
                }
            })

        # Design→Design DEPENDS_ON where target matches a dependency Compound
        result2 = session.run("""
        UNWIND $qnames AS qn
        MATCH (d:Design {qualified_name: qn})-[r:DEPENDS_ON]->(d2:Design)
        WITH d, r, d2
        MATCH (dep:Compound {qualified_name: d2.qualified_name})
        WHERE dep.source IS NOT NULL AND dep.source <> ''
        RETURN d, r, d2, dep
        """, {"qnames": design_qnames})

        for record in result2:
            d = record["d"]
            dep = record["dep"]

            if d.element_id not in node_ids:
                node_ids.add(d.element_id)
                nodes.append({"data": _make_node_data(d)})

            if dep.element_id not in node_ids:
                node_ids.add(dep.element_id)
                nodes.append({"data": _make_dependency_node(dep)})

            edges.append({
                "data": {
                    "id": f"dep_link_{d.element_id}_{dep.element_id}",
                    "source": d.element_id,
                    "target": dep.element_id,
                    "label": "DEPENDS_ON",
                }
            })

    return {"nodes": nodes, "edges": edges}
