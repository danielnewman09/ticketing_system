"""Unified graph fetch functions for ontology layers."""

from __future__ import annotations

import logging

from services.dependencies import get_neo4j

from backend.db.neo4j_queries._graph_transforms import (
    _assign_namespace_parents,
    _collapse_members,
)
from backend.db.neo4j_queries._node_builders import _build_node
from backend.db.neo4j_queries._query_builder import (
    _build_compound_discovery_query,
    _build_component_query,
    _build_edge_query,
    _build_hlr_subgraph_query,
    _build_inheritance_query,
    _build_member_query,
    _build_node_query,
    _build_traces_query,
    _build_where_clause,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _fetch_traced_requirements(
    session,
    node_ids: set[str],
    nodes: list[dict],
    edges: list[dict],
) -> None:
    """Fetch HLR/LLR nodes that trace to any design node in *node_ids*.

    Appends requirement nodes and TRACES_TO edges to the provided lists
    in-place.
    """
    if not node_ids:
        return

    query_str, params = _build_traces_query(list(node_ids))
    req_result = session.run(query_str, params)
    
    for record in req_result:
        req = record["req"]
        d = record["d"]
        if d.element_id not in node_ids:
            continue
        if req.element_id not in node_ids:
            node_ids.add(req.element_id)
            labels = list(req.labels)
            req_type = "HLR" if "HLR" in labels else "LLR"
            nodes.append({
                "data": {
                    "id": req.element_id,
                    "label": f"{req_type} {req.get('sqlite_id', '')}",
                    "qualified_name": "",
                    "kind": req_type,
                    "description": req.get("title", ""),
                    "layer": "requirement",
                },
            })
        edges.append({
            "data": {
                "id": f"traces_{req.element_id}_{d.element_id}",
                "source": req.element_id,
                "target": d.element_id,
                "label": "TRACES_TO",
            },
        })


def _fetch_inheritance_edges(
    session,
    compound_ids: set[str],
    edges: list[dict],
    edge_ids: set[str],
) -> None:
    """Fetch inheritance edges (1 hop up/down) for compounds."""
    if not compound_ids:
        return

    query_str, params = _build_inheritance_query(list(compound_ids))
    result = session.run(query_str, params)

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


def _fetch_compound_members(
    session,
    compound_ids: set[str],
    nodes: list[dict],
    edges: list[dict],
    node_ids: set[str],
    layer: str = "codebase",
) -> None:
    """Fetch Compound->Member CONTAINS edges."""
    if not compound_ids:
        return

    query_str, params = _build_member_query(list(compound_ids))
    result = session.run(query_str, params)

    for record in result:
        c = record["c"]
        if c.element_id not in node_ids:
            node_ids.add(c.element_id)
            nodes.append({"data": _build_node(c, layer)})

        m = record["m"]
        r = record["r"]
        if m is not None and m.element_id not in node_ids:
            node_ids.add(m.element_id)
            nodes.append({"data": _build_node(m, layer)})
        if r is not None and m is not None:
            edges.append({
                "data": {
                    "id": r.element_id,
                    "source": c.element_id,
                    "target": m.element_id,
                    "label": "CONTAINS",
                }
            })


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
    query_str, params = _build_compound_discovery_query(
        "dependency", search, source_filter, limit
    )
    log.debug(f"Query Str:\n{query_str}")
    log.debug(f"Params:\n{params}")

    try:
        result = session.run(query_str, params)
    except Exception:
        log.warning(
            "Full-text index 'doc_search' unavailable, falling back to CONTAINS search"
        )
        # Fallback: simple CONTAINS search
        search_term = (search or "").strip()
        fallback_where = (
            "c.source IS NOT NULL AND c.source <> '' "
            "AND (c.name CONTAINS $search OR c.qualified_name CONTAINS $search)"
        )
        if source_filter:
            fallback_where += " AND c.source CONTAINS $source_filter"
        result = session.run(f"""
            MATCH (c:Compound) WHERE {fallback_where}
            RETURN c
        """, {
            "search": search_term,
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
# Unified fetch function
# ---------------------------------------------------------------------------

def fetch_graph_layer(
    layer: str,
    kind_filter: str | None = None,
    search: str | None = None,
    component_id: int | None = None,
    source_filter: str | None = None,
    limit: int = 100,
) -> dict:
    """Fetch graph data for a specific layer.

    Unified entry point for all ontology graph layers.

    Args:
        layer: One of "design", "codebase", or "dependency"
        kind_filter: Filter by kind (e.g., "class", "function")
        search: Search term for node names
        component_id: Filter by component ID
        source_filter: Filter dependency sources
        limit: Maximum results for search

    Returns:
        Cytoscape.js format {"nodes": [...], "edges": [...]}
    """
    log.info(f"Fetching graph layer: {layer}")
    
    if layer == "design":
        return _fetch_design_layer(kind_filter, search, component_id)
    elif layer == "codebase":
        return _fetch_codebase_layer(search)
    elif layer == "dependency":
        return _fetch_dependency_layer(search, source_filter, limit)
    else:
        log.error(f"Unknown layer: {layer}")
        return {"nodes": [], "edges": []}


def _fetch_design_layer(
    kind_filter: str | None,
    search: str | None,
    component_id: int | None,
) -> dict:
    """Fetch design layer graph."""
    filters = {
        "kind": kind_filter,
        "component_id": component_id,
        "search": search,
    }

    with get_neo4j().session() as session:
        nodes: list[dict] = []
        edges: list[dict] = []
        node_ids: set[str] = set()

        # Fetch nodes
        query_str, params = _build_node_query("design", filters)
        log.debug(f"Query Str:\n{query_str}")
        log.debug(f"Params:\n{params}")

        node_result = session.run(query_str, params)
        for record in node_result:
            n = record["n"]
            node_ids.add(n.element_id)
            nodes.append({"data": _build_node(n, "design")})

        # Fetch edges between matched nodes
        edge_query_str, params = _build_edge_query(
            "design",
            filters,
            exclude_types=["IMPLEMENTED_BY"],
        )
        log.debug(f"Query Str:\n{edge_query_str}")
        log.debug(f"Params:\n{params}")

        edge_result = session.run(edge_query_str, params)
        for record in edge_result:
            s = record["s"]
            t = record["t"]
            r = record["r"]
            if t.element_id not in node_ids:
                node_ids.add(t.element_id)
                nodes.append({"data": _build_node(t, "design")})
            edges.append({
                "data": {
                    "id": r.element_id,
                    "source": s.element_id,
                    "target": t.element_id,
                    "label": r.type,
                },
            })

        # Fetch COMPOSES edges (Compound -> Member) for member collapsing
        if node_ids:
            member_result = session.run(
                """
                MATCH (s)-[r:COMPOSES]->(m)
                WHERE elementId(s) IN $node_ids
                  AND (m:Compound OR m:Member OR m:Namespace)
                RETURN s, r, m
                """,
                {"node_ids": list(node_ids)},
            )
            for record in member_result:
                s = record["s"]
                m = record["m"]
                r = record["r"]
                if m.element_id not in node_ids:
                    node_ids.add(m.element_id)
                    nodes.append({"data": _build_node(m, "design")})
                edges.append({
                    "data": {
                        "id": r.element_id,
                        "source": s.element_id,
                        "target": m.element_id,
                        "label": r.type,
                    },
                })

        # Fetch dependency compounds referenced by design nodes
        if node_ids:
            dep_result = session.run(
                """
                MATCH (s)-[r]->(dep:Compound)
                WHERE elementId(s) IN $node_ids
                  AND (s:Compound OR s:Member OR s:Namespace)
                  AND dep.layer = "dependency"
                RETURN s, r, dep
                """,
                {"node_ids": list(node_ids)},
            )
        else:
            dep_result = []
        for record in dep_result:
            s = record["s"]
            dep = record["dep"]
            r = record["r"]
            if dep.element_id not in node_ids:
                node_ids.add(dep.element_id)
                nodes.append({"data": _build_node(dep, "dependency")})
            edges.append({
                "data": {
                    "id": r.element_id,
                    "source": s.element_id,
                    "target": dep.element_id,
                    "label": r.type,
                },
            })

        # Fetch linked requirement nodes
        _fetch_traced_requirements(session, node_ids, nodes, edges)

    nodes, edges = _collapse_members(nodes, edges)
    nodes, edges = _assign_namespace_parents(nodes, edges)
    return {"nodes": nodes, "edges": edges}


def _fetch_codebase_layer(search: str | None) -> dict:
    """Fetch codebase layer graph."""
    with get_neo4j().session() as session:
        # Discover root compounds
        compound_ids = _discover_codebase_compounds(session, search)
        
        if not compound_ids:
            return {"nodes": [], "edges": []}

        nodes: list[dict] = []
        edges: list[dict] = []
        node_ids: set[str] = set()
        edge_ids: set[str] = set()

        # Fetch inheritance edges
        _fetch_inheritance_edges(session, compound_ids, edges, edge_ids)

        # Fetch compounds and members
        _fetch_compound_members(session, compound_ids, nodes, edges, node_ids)

    nodes, edges = _collapse_members(nodes, edges)
    nodes, edges = _assign_namespace_parents(nodes, edges)
    return {"nodes": nodes, "edges": edges}


def _fetch_dependency_layer(
    search: str | None,
    source_filter: str | None,
    limit: int,
) -> dict:
    """Fetch dependency layer graph."""
    with get_neo4j().session() as session:
        # Discover root compounds
        compound_ids = _discover_dependency_compounds(
            session, search, source_filter, limit
        )
        
        if not compound_ids:
            return {"nodes": [], "edges": []}

        nodes: list[dict] = []
        edges: list[dict] = []
        node_ids: set[str] = set()
        edge_ids: set[str] = set()

        # Fetch inheritance edges
        _fetch_inheritance_edges(session, compound_ids, edges, edge_ids)

        # Fetch compounds and members
        _fetch_compound_members(session, compound_ids, nodes, edges, node_ids, layer="dependency")

    nodes, edges = _collapse_members(nodes, edges)
    nodes, edges = _assign_namespace_parents(nodes, edges)
    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# HLR subgraph fetch
# ---------------------------------------------------------------------------

def fetch_hlr_graph_layer(hlr_id: int, component_id: int | None = None) -> dict:
    """Fetch the requirement neighbourhood of an HLR.

    Includes: the HLR node, its LLRs, any TRACES_TO design nodes, the
    component's design nodes and their inter-relationships.
    """
    with get_neo4j().session() as session:
        nodes: list[dict] = []
        edges: list[dict] = []
        node_ids: set[str] = set()

        def _add_node(element_id: str, data: dict) -> None:
            if element_id not in node_ids:
                node_ids.add(element_id)
                nodes.append({"data": {**data, "id": element_id}})

        # 1. Verify HLR exists
        check = session.run(
            "MATCH (h:HLR {sqlite_id: $hid}) RETURN h", {"hid": hlr_id},
        ).single()
        if not check:
            return {"nodes": [], "edges": []}
        
        # 2. Design nodes traced from HLR/LLRs
        query_str, params = _build_hlr_subgraph_query(hlr_id)
        log.debug(f"Query Str:\n{query_str}")
        trace_result = session.run(query_str, params)
        for record in trace_result:
            d = record["d"]
            _add_node(d.element_id, _build_node(d, "design"))

        # 3. Component design nodes + their inter-relationships
        if component_id is not None:
            query_str, params = _build_component_query(component_id)
            comp_result = session.run(query_str, params)
            for record in comp_result:
                d = record["d"]
                _add_node(d.element_id, _build_node(d, "design"))
                for item in record["rels"]:
                    r = item["rel"]
                    t = item["target"]
                    if r is None or t is None:
                        continue
                    _add_node(t.element_id, _build_node(t, "design"))
                    edges.append({"data": {
                        "id": r.element_id,
                        "source": d.element_id,
                        "target": t.element_id,
                        "label": r.type,
                    }})

    nodes, edges = _collapse_members(nodes, edges)
    nodes, edges = _assign_namespace_parents(nodes, edges)
    return {"nodes": nodes, "edges": edges}
