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
    LAYER_CONFIG,
    _build_compound_discovery_query,
    _build_component_query,
    _build_composes_query,
    _build_edge_query,
    _build_hlr_subgraph_query,
    _build_inheritance_query,
    _build_member_query,
    _build_node_query,
    _build_where_clause,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------




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
    log.debug(f"Query Str:\n{query_str}")
    log.debug(f"Params:\n{params}")

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
    log.debug(f"Query Str:\n{query_str}")
    log.debug(f"Params:\n{params}")

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


def _discover_compounds(
    session,
    layer: str,
    search: str | None,
    source_filter: str | None,
    kind_filter: str | None,
    component_id: int | None,
    limit: int,
) -> set[str]:
    """Find Compound element-IDs using full-text search with CONTAINS fallback.
    
    Unified discovery for all layers (design, codebase, dependency).
    """
    query_str, params = _build_compound_discovery_query(
        layer, search, source_filter, kind_filter, component_id, limit
    )
    log.debug(f"Query Str:\n{query_str}")
    log.debug(f"Params:\n{params}")

    try:
        result = session.run(query_str, params)
    except Exception as e:
        log.warning(
            f"Full-text index 'doc_search' unavailable for {layer}, falling back to CONTAINS search: {e}"
        )
        # Fallback: simple CONTAINS search based on layer
        config = LAYER_CONFIG[layer]
        search_term = (search or "").strip()
        
        if layer == "dependency" and not search_term:
            return set()
        
        # Build MATCH and WHERE clauses properly
        where_conditions = []
        fallback_params = {}
        
        # Use layer property for filtering (consistent with full-text search)
        if layer == "codebase":
            where_conditions.append("c.layer = 'codebase'")
        elif layer == "dependency":
            where_conditions.append("c.layer = 'dependency'")
        elif layer == "design":
            where_conditions.append("c.layer = 'design'")
        
        # Search filter
        if search_term:
            where_conditions.append(
                "(c.name CONTAINS $search OR c.qualified_name CONTAINS $search)"
            )
            fallback_params["search"] = search_term
        
        # Additional filters
        if source_filter and layer == "dependency":
            where_conditions.append("c.source CONTAINS $source_filter")
            fallback_params["source_filter"] = source_filter
        
        if kind_filter and layer == "design":
            where_conditions.append("c.kind = $kind")
            fallback_params["kind"] = kind_filter
        
        if component_id is not None and layer == "design":
            where_conditions.append("c.component_id = $component_id")
            fallback_params["component_id"] = component_id
        
        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
        
        log.debug(f"Fallback query: MATCH (c:Compound) WHERE {where_clause} RETURN c")
        
        try:
            result = session.run(f"""
                MATCH (c:Compound)
                WHERE {where_clause}
                RETURN c
            """, fallback_params)
        except Exception as e2:
            log.error(f"Fallback query failed: {e2}")
            return set()

    return {record["c"].element_id for record in result}


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


def _fetch_compound_graph(
    session,
    layer: str,
    search: str | None,
    source_filter: str | None,
    kind_filter: str | None,
    component_id: int | None,
    limit: int,
    edge_types: list[str] | None,
    include_composes: bool,
    fetch_cross_layer_deps: bool,
) -> dict:
    """Unified graph fetching for all layers using compound discovery.
    
    Args:
        session: Neo4j session
        layer: Layer name (design, codebase, dependency)
        search: Search term
        source_filter: Source filter (dependency only)
        kind_filter: Kind filter (design only)
        component_id: Component ID filter (design only)
        limit: Maximum results
        edge_types: Edge types to include (None for all)
        include_composes: Whether to fetch COMPOSES edges
        fetch_cross_layer_deps: Whether to fetch cross-layer dependencies
        
    Returns:
        Cytoscape.js format {"nodes": [...], "edges": [...]}
    """
    # 1. Discover compounds
    compound_ids = _discover_compounds(
        session, layer, search, source_filter, kind_filter, component_id, limit
    )
    
    if not compound_ids:
        return {"nodes": [], "edges": []}
    
    nodes: list[dict] = []
    edges: list[dict] = []
    node_ids: set[str] = set()
    
    # 2. Fetch nodes and members
    _fetch_compound_members(session, compound_ids, nodes, edges, node_ids, layer=layer)
    
    # 3. Fetch inheritance edges
    _fetch_inheritance_edges(session, compound_ids, edges, set())
    
    # 4. Fetch COMPOSES edges if requested
    if include_composes and node_ids:
        composes_query, params = _build_composes_query(list(node_ids), layer)
        log.debug(f"Query Str:\n{composes_query}")
        log.debug(f"Params:\n{params}")
        try:
            composes_result = session.run(composes_query, params)
            for record in composes_result:
                s = record["s"]
                m = record["m"]
                r = record["r"]
                if m is not None and m.element_id not in node_ids:
                    node_ids.add(m.element_id)
                    nodes.append({"data": _build_node(m, layer)})
                if r is not None and m is not None:
                    edges.append({
                        "data": {
                            "id": r.element_id,
                            "source": s.element_id,
                            "target": m.element_id,
                            "label": r.type,
                        }
                    })
        except Exception as e:
            log.warning(f"COMPOSES query failed for {layer}: {e}")
    
    # 5. Fetch cross-layer dependencies if requested (design only)
    if fetch_cross_layer_deps and node_ids:
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
    
    # 6. Filter out edges with missing nodes
    valid_node_ids = {node["data"]["id"] for node in nodes}
    filtered_edges = []
    for edge in edges:
        if edge["data"]["source"] in valid_node_ids and edge["data"]["target"] in valid_node_ids:
            filtered_edges.append(edge)
        else:
            log.debug(f"Removing edge {edge['data']['id']} with missing node: "
                     f"source={edge['data']['source']}, target={edge['data']['target']}")
    edges = filtered_edges
    
    # 7. Apply transforms
    nodes, edges = _collapse_members(nodes, edges)
    nodes, edges = _assign_namespace_parents(nodes, edges)
    
    # 8. Log warning if truncated
    if len(compound_ids) == limit:
        log.warning(f"Layer {layer} results may be truncated: limit={limit}")
    
    return {"nodes": nodes, "edges": edges}


def _fetch_design_layer(
    kind_filter: str | None,
    search: str | None,
    component_id: int | None,
) -> dict:
    """Fetch design layer graph."""
    with get_neo4j().session() as session:
        return _fetch_compound_graph(
            session=session,
            layer="design",
            search=search,
            source_filter=None,
            kind_filter=kind_filter,
            component_id=component_id,
            limit=100,
            edge_types=None,  # All edges for design
            include_composes=True,
            fetch_cross_layer_deps=True,
        )


def _fetch_codebase_layer(search: str | None) -> dict:
    """Fetch codebase layer graph."""
    with get_neo4j().session() as session:
        return _fetch_compound_graph(
            session=session,
            layer="codebase",
            search=search,
            source_filter=None,
            kind_filter=None,
            component_id=None,
            limit=100,
            edge_types=["INHERITS_FROM"],
            include_composes=True,
            fetch_cross_layer_deps=False,
        )


def _fetch_dependency_layer(
    search: str | None,
    source_filter: str | None,
    limit: int,
) -> dict:
    """Fetch dependency layer graph."""
    with get_neo4j().session() as session:
        return _fetch_compound_graph(
            session=session,
            layer="dependency",
            search=search,
            source_filter=source_filter,
            kind_filter=None,
            component_id=None,
            limit=limit,
            edge_types=["INHERITS_FROM"],
            include_composes=True,
            fetch_cross_layer_deps=False,
        )


# ---------------------------------------------------------------------------
# HLR subgraph fetch
# ---------------------------------------------------------------------------

def fetch_hlr_subgraph(hlr_id: int, component_id: int | None = None) -> dict:
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
