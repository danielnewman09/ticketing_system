"""Unified Cypher query builder for ontology graph layers."""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Layer Configuration
# ---------------------------------------------------------------------------

LAYER_CONFIG = {
    "design": {
        "label": "Compound|Member|Namespace",
        "layer_value": "design",
        "search_fields": ["name", "qualified_name", "kind"],
        "extra_filters": ["kind", "component_id"],
        "node_var": "n",
        "default_show_all": True,
        "edge_types": ["DEPENDS_ON", "CALLS", "REFERENCES", "EXTENDS", "COMPOSES"],
    },
    "codebase": {
        "label": "Compound|Member|Namespace",
        "layer_value": "codebase",
        "search_fields": ["name", "qualified_name"],
        "extra_filters": [],
        "node_var": "c",
        "source_condition": "NOT c.source IS NOT NULL AND c.source <> ''",
        "default_show_all": True,
        "edge_types": ["INHERITS_FROM"],
    },
    "dependency": {
        "label": "Compound|Member|Namespace",
        "layer_value": "dependency",
        "search_fields": ["name", "qualified_name", "source"],
        "extra_filters": ["source"],
        "node_var": "c",
        "source_condition": "c.source IS NOT NULL AND c.source <> ''",
        "default_show_all": False,
        "edge_types": ["INHERITS_FROM"],
    },
    "requirement": {
        "label": "HLR|LLR",
        "layer_value": None,
        "search_fields": ["title", "description"],
        "extra_filters": [],
        "node_var": "req",
    },
}


def _build_where_clause(
    layer: str,
    filters: dict[str, str | int | None],
    node_var: str = "n",
) -> tuple[str, dict]:
    """Build WHERE clause for ontology graph queries.

    Args:
        layer: Layer name (design, codebase, dependency, requirement)
        filters: Filter parameters (kind, component_id, source, search)
        node_var: Neo4j node variable name

    Returns:
        Tuple of (where_clause_string, params_dict)
    """
    config = LAYER_CONFIG[layer]
    label = config["label"]
    conditions = [f"{node_var}:{label}"]
    params: dict = {}

    # Add layer filter for design/codebase/dependency
    if config.get("layer_value"):
        conditions.append(f"{node_var}.layer = $layer")
        params["layer"] = config["layer_value"]

    # Layer-specific filters
    if layer == "design":
        if filters.get("kind"):
            conditions.append(f"{node_var}.kind = $kind")
            params["kind"] = filters["kind"]
        if filters.get("component_id") is not None:
            conditions.append(f"{node_var}.component_id = $component_id")
            params["component_id"] = filters["component_id"]
    elif layer == "dependency":
        if filters.get("source_filter"):
            conditions.append(f"{node_var}.source CONTAINS $source_filter")
            params["source_filter"] = filters["source_filter"]

    # Search (case-insensitive)
    search = filters.get("search")
    if search:
        search_fields = config.get("search_fields", ["name"])
        search_conditions = [
            f"tolower({node_var}.{field}) CONTAINS tolower($search)" for field in search_fields
        ]
        conditions.append(f"({' OR '.join(search_conditions)})")
        params["search"] = search

    return " AND ".join(conditions), params


def _build_node_query(
    layer: str,
    filters: dict[str, str | int | None],
) -> tuple[str, dict]:
    """Build query to fetch nodes for a layer.

    Args:
        layer: Layer name
        filters: Filter parameters

    Returns:
        Tuple of (query_string, params_dict)
    """
    node_var = LAYER_CONFIG[layer]["node_var"]
    where_clause, params = _build_where_clause(layer, filters)
    return f"MATCH ({node_var}) WHERE {where_clause} RETURN {node_var}", params


def _build_edge_query(
    layer: str,
    filters: dict[str, str | int | None],
    edge_types: list[str] | None = None,
    exclude_types: list[str] | None = None,
) -> tuple[str, dict]:
    """Build query to fetch edges for a layer.

    Args:
        layer: Layer name
        filters: Filter parameters
        edge_types: Specific edge types to include (optional)
        exclude_types: Edge types to exclude (optional)

    Returns:
        Tuple of (query_string, params_dict)
    """
    node_var = LAYER_CONFIG[layer]["node_var"]
    where_clause, params = _build_where_clause(layer, filters)

    # Build edge type conditions
    edge_conditions = []
    if edge_types:
        edge_conditions.append(f"r.type IN $edge_types")
        params["edge_types"] = edge_types
    if exclude_types:
        edge_conditions.append(f"NOT r.type IN $exclude_types")
        params["exclude_types"] = exclude_types

    if edge_conditions:
        edge_filter = " AND " + " AND ".join(edge_conditions)
    else:
        edge_filter = ""

    # Replace node_var with word boundaries to avoid mangling field names
    import re
    where_clause_target = re.sub(r'\b' + re.escape(node_var) + r'\b', 't', where_clause)
    where_clause_source = re.sub(r'\b' + re.escape(node_var) + r'\b', 's', where_clause)

    query = f"""
    MATCH (s)-[r]->(t)
    WHERE {where_clause_source}
      AND {where_clause_target}
      {edge_filter}
    RETURN s, r, t
    """
    return query, params


def _build_composes_query(node_ids: list[str], layer: str = "design") -> tuple[str, dict]:
    """Build query to fetch COMPOSES edges for specific nodes.
    
    Args:
        node_ids: Element IDs of nodes to fetch COMPOSES edges for
        layer: Layer name (design or dependency)
    
    Returns:
        Tuple of (query_string, params_dict)
    """
    config = LAYER_CONFIG[layer]
    label = config["label"]
    query = f"""
    UNWIND $node_ids AS nid
    MATCH (s:{label}) WHERE elementId(s) = nid
    OPTIONAL MATCH (s)-[r:COMPOSES]->(m:{label})
    RETURN s, r, m
    """
    params = {"node_ids": node_ids}
    return query, params


def _build_compound_discovery_query(
    layer: str,
    search: str | None,
    source_filter: str | None,
    kind_filter: str | None,
    component_id: int | None,
    limit: int,
) -> tuple[str, dict]:
    """Build query to discover Compounds using full-text search.
    
    Behavior by layer:
    - design: Returns all design nodes if no search, filtered by kind/component_id
    - codebase: Returns all codebase compounds if no search
    - dependency: Returns empty if no search, otherwise full-text search
    
    Uses full-text search with CONTAINS fallback.
    """
    config = LAYER_CONFIG[layer]
    default_show_all = config.get("default_show_all", True)
    
    # For dependency layer with no search term and default_show_all=False, return empty
    if layer == "dependency" and not search and not default_show_all:
        return "MATCH (c:Compound) WHERE false RETURN c", {}
    
    # Build source condition based on layer
    if layer == "codebase":
        source_condition = "node.layer = 'codebase'"
    elif layer == "dependency":
        source_condition = "node.layer = 'dependency'"
    else:  # design
        source_condition = "node.layer = 'design'"
    
    # Design layer with filters - use simple MATCH query
    if layer == "design" and (kind_filter or component_id or not search):
        conditions = []
        params = {}
        conditions.append(f"c:{config['label']}")
        conditions.append("c.layer = 'design'")
        if kind_filter:
            conditions.append("c.kind = $kind")
            params["kind"] = kind_filter
        if component_id is not None:
            conditions.append("c.component_id = $component_id")
            params["component_id"] = component_id
        if search:
            conditions.append(
                "(tolower(c.name) CONTAINS tolower($search) OR tolower(c.qualified_name) CONTAINS tolower($search))"
            )
            params["search"] = search
        where_clause = " AND ".join(conditions)
        return f"MATCH (c:Compound) WHERE {where_clause} RETURN c", params
    
    # Full-text search for all layers
    search_term = (search or "").strip()
    
    # For empty search terms, use simple MATCH instead of full-text
    if not search_term and layer != "design":
        conditions = []
        params = {}
        conditions.append(f"c:{config['label']}")
        
        if layer == "codebase":
            conditions.append("NOT c.source IS NOT NULL AND c.source <> ''")
        elif layer == "dependency":
            conditions.append("c.source IS NOT NULL AND c.source <> ''")
        
        if source_filter:
            conditions.append("c.source CONTAINS $source_filter")
            params["source_filter"] = source_filter
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        return f"MATCH (c:Compound) WHERE {where_clause} RETURN c", params
    
    params = {"query": search_term if search_term else "*", "limit": limit}
    if source_filter:
        params["source_filter"] = source_filter
    
    # Build additional WHERE conditions for source filter
    source_filter_clause = ""
    if source_filter:
        source_filter_clause = "AND node.source CONTAINS $source_filter"
    
    query = f"""
    CALL db.index.fulltext.queryNodes('doc_search', $query) YIELD node, score
    WHERE {source_condition}
      {source_filter_clause}
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
    WHERE {source_condition}
    WITH coalesce(direct_compound, owner) AS c
    WHERE c IS NOT NULL
    RETURN DISTINCT c
    """
    return query, params


def _build_inheritance_query(compound_ids: list[str]) -> tuple[str, dict]:
    """Build query to fetch inheritance edges (1 hop up/down)."""
    query = """
    UNWIND $cids AS cid
    MATCH (c:Compound) WHERE elementId(c) = cid
    OPTIONAL MATCH (c)-[r1:INHERITS_FROM]->(base:Compound)
    OPTIONAL MATCH (derived:Compound)-[r2:INHERITS_FROM]->(c)
    RETURN c, r1, base, r2, derived
    """
    params = {"cids": compound_ids}
    return query, params


def _build_member_query(container_ids: list[str], container_label: str = "Compound", member_label: str = "Member", rel_type: str = "CONTAINS") -> tuple[str, dict]:
    """Build query to fetch container->member containment edges.
    
    Args:
        container_ids: Element IDs of container nodes
        container_label: Neo4j label for containers (e.g., "Compound" or "Design")
        member_label: Neo4j label for members (e.g., "Member" or "Design")
        rel_type: Relationship type (e.g., "CONTAINS" or "COMPOSES")
    """
    query = f"""
    UNWIND $cids AS cid
    MATCH (c:{container_label}) WHERE elementId(c) = cid
    OPTIONAL MATCH (c)-[r:{rel_type}]->(m:{member_label})
    RETURN c, r, m
    """
    params = {"cids": container_ids}
    return query, params


def _build_traces_query(node_ids: list[str]) -> tuple[str, dict]:
    """Build query to fetch HLR/LLR nodes that trace to design nodes."""
    query = """
    UNWIND $ids AS id
    MATCH (req)-[:TRACES_TO]->(d:Design)
    WHERE (req:HLR OR req:LLR)
      AND elementId(d) IN $ids
    RETURN DISTINCT req, d
    """
    params = {"ids": node_ids}
    return query, params


def _build_hlr_subgraph_query(hlr_id: int) -> tuple[str, dict]:
    """Build query to fetch HLR neighbourhood."""
    query = """
    MATCH (h:HLR {sqlite_id: $hid})
    OPTIONAL MATCH (h)-[:TRACES_TO]->(d1:Design)
    OPTIONAL MATCH (l:LLR)-[:DECOMPOSES]->(h)
    OPTIONAL MATCH (l)-[:TRACES_TO]->(d2:Design)
    WITH collect(DISTINCT d1) + collect(DISTINCT d2) AS designs
    UNWIND designs AS d
    WITH DISTINCT d WHERE d IS NOT NULL
    RETURN d
    """
    params = {"hid": hlr_id}
    return query, params


def _build_component_query(component_id: int) -> tuple[str, dict]:
    """Build query to fetch component design nodes."""
    query = """
    MATCH (d:Design {component_id: $cid})
    OPTIONAL MATCH (d)-[r]->(d2:Design {component_id: $cid})
    WHERE type(r) <> 'IMPLEMENTED_BY'
    RETURN d, collect({rel: r, target: d2}) AS rels
    """
    params = {"cid": component_id}
    return query, params


def _build_dependency_link_query(design_qnames: list[str]) -> tuple[str, dict]:
    """Build query to fetch Design->Dependency links."""
    query = """
    UNWIND $qnames AS qn
    MATCH (d:Design {qualified_name: qn})-[r]->(dep:Compound)
    WHERE dep.source IS NOT NULL AND dep.source <> ''
    RETURN d, r, dep
    """
    params = {"qnames": design_qnames}
    return query, params


def _build_design_dependency_match_query(design_qnames: list[str]) -> tuple[str, dict]:
    """Build query to fetch Design->Design DEPENDS_ON where target matches dependency."""
    query = """
    UNWIND $qnames AS qn
    MATCH (d:Design {qualified_name: qn})-[r:DEPENDS_ON]->(d2:Design)
    WITH d, r, d2
    MATCH (dep:Compound {qualified_name: d2.qualified_name})
    WHERE dep.source IS NOT NULL AND dep.source <> ''
    RETURN d, r, d2, dep
    """
    params = {"qnames": design_qnames}
    return query, params
