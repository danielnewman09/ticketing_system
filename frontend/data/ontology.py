"""Ontology data, Neo4j graph queries, and node detail.

Architecture (Phase 2):
- Neo4j is the primary store for design nodes and triples.
- HLR/LLR data lives in Neo4j as full citizens with native id properties
  (no more sqlite_id bridge from Phase 1).
- Node counts and stats come from Cypher MATCH queries.
- Requirement tags come from graph_tags.py (Cypher TRACES_TO traversal).
"""

import logging

from services.dependencies import get_neo4j

log = logging.getLogger(__name__)


def fetch_ontology_data():
    """Fetch all data needed for ontology page.

    Uses Cypher for design node stats instead of SQLAlchemy queries.
    HLR/LLR counts still come from SQLite until Phase 2.
    """
    with get_neo4j().session() as session:
        # Design node stats from Neo4j
        kind_result = session.run(
            "MATCH (d:Design) RETURN d.kind AS kind, count(d) AS cnt"
        )
        kind_counts = {}
        total_nodes = 0
        for record in kind_result:
            kind = record["kind"] or "unknown"
            cnt = record["cnt"]
            kind_counts[kind] = cnt
            total_nodes += cnt

        nodes_result = session.run(
            "MATCH (d:Design) RETURN d.qualified_name AS qn, d.name AS name, "
            "d.kind AS kind, d.component_id AS cid ORDER BY d.qualified_name LIMIT 200"
        )
        # Resolve component names — still need SQLite for this in Phase 1
        component_map: dict[int, str] = {}
        try:
            from backend.db import get_session
            from backend.db.models import Component
            with get_session() as sql_session:
                for c in sql_session.query(Component).all():
                    component_map[c.id] = c.name
        except Exception:
            pass

        nodes = []
        for record in nodes_result:
            cid = record["cid"]
            nodes.append({
                "name": record["name"],
                "kind": record["kind"],
                "qualified_name": record["qn"],
                "component": component_map.get(cid, "-") if cid else "-",
            })

        # Triple and predicate counts from Neo4j
        triple_result = session.run(
            "MATCH (:Design)-[r]->(:Design) RETURN count(r) AS cnt"
        )
        triple_rec = triple_result.single()
        total_triples = triple_rec["cnt"] if triple_rec else 0

        # Count distinct relationship types as "predicates"
        pred_result = session.run(
            "MATCH (:Design)-[r]->(:Design) RETURN count(DISTINCT type(r)) AS cnt"
        )
        pred_rec = pred_result.single()
        total_predicates = pred_rec["cnt"] if pred_rec else 0

    return {
        "nodes": nodes,
        "kind_counts": kind_counts,
        "total_nodes": total_nodes,
        "total_triples": total_triples,
        "total_predicates": total_predicates,
    }


def filter_cross_layer_elements(
    nodes: list[dict], edges: list[dict]
) -> tuple[list[dict], list[dict]]:
    """Remove cross-layer nodes and edges (dependency and as-built).

    Used when include_dependencies=False to return a design-only graph.
    """
    cross_layer_ids = {
        n["data"]["id"]
        for n in nodes
        if n["data"].get("layer") in ("dependency", "as-built")
    }
    filtered_nodes = [n for n in nodes if n["data"]["id"] not in cross_layer_ids]
    filtered_edges = [
        e for e in edges
        if e["data"].get("source") not in cross_layer_ids
        and e["data"].get("target") not in cross_layer_ids
    ]
    return filtered_nodes, filtered_edges


def fetch_ontology_graph_data(
    layer: str = "design",
    kind_filter: str | None = None,
    search: str | None = None,
    component_id: int | None = None,
    source_filter: str | None = None,
    requirement_tags: str = "hlr",
    include_dependencies: bool = True,
) -> dict:
    """Fetch graph data for Cytoscape.js rendering.

    Stage 1: Neo4j topology (no requirement data).
    Stage 2: Requirement tag enrichment via Cypher TRACES_TO.

    Args:
        layer: "design", "codebase", or "dependency".
        requirement_tags: "none" for bare topology, "hlr" for HLR badges.
        include_dependencies: If False, remove dependency/as-built nodes and
            cross-layer edges from the result (design-only graph).
    """
    try:
        from backend.db.neo4j.queries import fetch_design_graph
        from backend.db.neo4j.queries import fetch_dependency_compounds
        from backend.db.neo4j.queries import fetch_codebase_compounds
        from backend.graph import format_cytoscape_graph
        from backend.requirements.services.graph_tags import enrich_with_requirement_tags

        if layer == "design":
            raw = fetch_design_graph(kind_filter, search, component_id)
        elif layer == "dependency":
            raw = fetch_dependency_compounds(search, source_filter)
        else:
            raw = fetch_codebase_compounds(search)

        formatted = format_cytoscape_graph(raw)

        # Enrich with requirement tags (design layer only)
        if layer == "design" and requirement_tags != "none":
            enrich_with_requirement_tags(formatted["nodes"], mode=requirement_tags)

        # Filter out cross-layer nodes when toggle is off
        if not include_dependencies:
            formatted["nodes"], formatted["edges"] = filter_cross_layer_elements(
                formatted["nodes"], formatted["edges"]
            )

        return formatted
    except Exception:
        log.warning("Neo4j query failed — returning empty graph", exc_info=True)
        return {"nodes": [], "edges": []}


def fetch_hlr_graph_data(
    hlr_id: int,
    component_id: int | None = None,
    requirement_tags: str = "hlr",
) -> dict:
    """Fetch the ontology subgraph around an HLR for Cytoscape.js.

    Uses Neo4j :HLR stub nodes and TRACES_TO edges to find seed nodes,
    then fetches 1-hop neighbourhood and enriches with tags.

    Args:
        requirement_tags: "none" for bare topology, "hlr" for HLR highlight + badges.
    """
    try:
        from backend.db.neo4j.queries import fetch_hlr_subgraph
        from backend.graph import format_cytoscape_graph
        from backend.requirements.services.graph_tags import tag_direct_nodes_only

        raw = fetch_hlr_subgraph(hlr_id, component_id)
        formatted = format_cytoscape_graph(raw)

        if requirement_tags != "none":
            tag_direct_nodes_only(formatted["nodes"], hlr_id)

        return formatted
    except Exception:
        log.warning("Neo4j HLR subgraph query failed — returning empty graph", exc_info=True)
        return {"nodes": [], "edges": []}


def fetch_neighbourhood_graph_data(qualified_name: str) -> dict:
    """Fetch the 1-hop neighbourhood graph with collapsed members."""
    try:
        from backend.db.neo4j.queries import fetch_neighbourhood_graph
        from backend.graph import format_cytoscape_graph

        raw = fetch_neighbourhood_graph(qualified_name)
        return format_cytoscape_graph(raw)
    except Exception:
        log.warning("Neo4j neighbourhood query failed", exc_info=True)
        return {"nodes": [], "edges": []}


def fetch_graph_node_detail(qualified_name: str) -> dict | None:
    """Fetch node detail from Neo4j (properties + relationships + members).

    Use fetch_node_detail_full() for the complete picture including
    requirement tags from TRACES_TO edges.
    """
    try:
        from backend.db.neo4j.queries import fetch_node_detail

        return fetch_node_detail(qualified_name)
    except Exception:
        log.warning("Neo4j node detail query failed", exc_info=True)
        return None


def fetch_node_detail_full(qualified_name: str) -> dict | None:
    """Fetch ontology node by qualified_name with all properties + Neo4j relationships.

    In Phase 2, requirement tags come from TRACES_TO edges on :HLR/:LLR nodes
    with native id properties (no more sqlite_id bridge).
    """
    neo4j_data = fetch_graph_node_detail(qualified_name)
    if not neo4j_data:
        return None

    props = neo4j_data.get("properties", {})
    node_data = {
        "name": props.get("name", ""),
        "qualified_name": props.get("qualified_name", ""),
        "kind": props.get("kind", ""),
        "specialization": props.get("specialization", ""),
        "visibility": props.get("visibility", ""),
        "description": props.get("description", ""),
        "component_id": props.get("component_id"),
        "type_signature": props.get("type_signature", ""),
        "argsstring": props.get("argsstring", ""),
        "definition": props.get("definition", ""),
        "file_path": props.get("file_path", ""),
        "line_number": props.get("line_number"),
        "source_type": props.get("source_type", ""),
        "is_static": props.get("is_static", False),
        "is_const": props.get("is_const", False),
        "is_virtual": props.get("is_virtual", False),
        "is_abstract": props.get("is_abstract", False),
        "is_final": props.get("is_final", False),
    }

    # Look up component name if component_id exists
    component_name = ""
    if node_data["component_id"]:
        try:
            from backend.db import get_session
            from backend.db.models import Component
            with get_session() as session:
                comp = session.query(Component).filter_by(id=node_data["component_id"]).first()
                if comp:
                    component_name = comp.name
        except Exception:
            pass
    node_data["component"] = component_name

    # Fetch requirement tags from Neo4j TRACES_TO edges
    requirements = []
    try:
        with get_neo4j().session() as ns:
            result = ns.run(
                """
                MATCH (r)-[:TRACES_TO]->(d:Design {qualified_name: $qn})
                WHERE r:HLR OR r:LLR
                RETURN labels(r) AS labels, r.id AS id, r.description AS desc
                """,
                {"qn": qualified_name},
            )
            for record in result:
                label = "HLR" if "HLR" in record["labels"] else "LLR"
                requirements.append({
                    "id": record["id"],
                    "type": label,
                    "description": (record["desc"] or "")[:80],
                })
    except Exception:
        log.warning("Failed to fetch requirement traces for %s", qualified_name, exc_info=True)

    return {"node": node_data, "neo4j": neo4j_data, "requirements": requirements}


def resolve_node_id_by_qualified_name(qualified_name: str) -> int | None:
    """Look up an identifier for an ontology node by qualified_name.

    In Phase 1, this returns a stable hash of the qualified_name since
    the SQLAlchemy id is no longer the primary key for design nodes.
    """
    # Design nodes no longer have a SQLAlchemy id — they are identified
    # by their qualified_name in Neo4j. Return a stable hash as identifier.
    import hashlib
    return int(hashlib.md5(qualified_name.encode()).hexdigest()[:8], 16)


def update_member_type(qualified_name: str, type_signature: str) -> bool:
    """Update type_signature on a design node in Neo4j (primary store)."""
    try:
        with get_neo4j().session() as ns:
            ns.run(
                "MATCH (n:Design {qualified_name: $qn}) SET n.type_signature = $ts",
                {"qn": qualified_name, "ts": type_signature},
            )
        return True
    except Exception:
        log.warning("Neo4j type_signature update failed", exc_info=True)
        return False