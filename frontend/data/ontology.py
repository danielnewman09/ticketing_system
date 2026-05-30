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


def _label_match_direct(alias: str = "n") -> str:
    """Build label-match clause without import from repository (avoid circular)."""
    return f"({alias}:Compound OR {alias}:Member OR {alias}:Namespace)"


def fetch_ontology_data():
    """Fetch all data needed for ontology page via DesignRepository."""
    from backend.db.neo4j.repositories.design import DesignRepository

    with get_neo4j().session() as session:
        repo = DesignRepository(session)
        stats = repo.get_graph_stats()

        # Resolve component names (still needs SQLite)
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
        for n in stats.get("nodes", []):
            cid = n.get("component_id")
            nodes.append({
                "name": n["name"],
                "kind": n["kind"],
                "qualified_name": n["qualified_name"],
                "component": component_map.get(cid, "-") if cid else "-",
            })

    return {
        "nodes": nodes,
        "kind_counts": stats["kind_counts"],
        "total_nodes": stats["total_nodes"],
        "total_triples": stats["total_edges"],
        "total_predicates": stats["total_predicates"],
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
        from backend.db.neo4j.repositories.design import DesignRepository
        from backend.graph import format_cytoscape_graph
        from backend.requirements.services.graph_tags import enrich_with_requirement_tags

        with get_neo4j().session() as session:
            repo = DesignRepository(session)
            graph = repo.get_ontology_graph(
                layer=layer,
                kind_filter=kind_filter,
                search=search,
                component_id=component_id,
            )
            raw = graph.to_raw()

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
        from backend.db.neo4j.repositories.design import DesignRepository
        from backend.graph import format_cytoscape_graph
        from backend.requirements.services.graph_tags import tag_direct_nodes_only

        with get_neo4j().session() as session:
            repo = DesignRepository(session)
            graph = repo.get_hlr_subgraph(hlr_id, component_id)
            raw = graph.to_raw()

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
        from backend.db.neo4j.repositories.design import DesignRepository
        from backend.graph import format_cytoscape_graph

        with get_neo4j().session() as session:
            repo = DesignRepository(session)
            graph = repo.get_neighbourhood_graph(qualified_name)
            raw = graph.to_raw()

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
        from backend.db.neo4j.repositories.design import DesignRepository

        with get_neo4j().session() as session:
            repo = DesignRepository(session)
            cg = repo.get_compound_graph(qualified_name)

        if cg is None:
            return None

        # Convert CompoundGraph to the dict shape expected by the frontend
        return {
            "properties": cg.node.model_dump(),
            "outgoing": [
                {"rel": e.predicate, "target_qn": e.target_qualified_name,
                 "target_name": "", "target_labels": ["Compound"]}
                for e in cg.edges_out
            ],
            "incoming": [
                {"rel": e.predicate, "source_qn": e.source_qualified_name,
                 "source_name": "", "source_labels": ["Compound"]}
                for e in cg.edges_in
            ],
            "implemented_by": [],
            "members": [m.model_dump() for m in cg.members],
            "codebase_members": [],
            "available_types": [],
        }
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
            label_clause = _label_match_direct("d")
            result = ns.run(
                f"""
                MATCH (r)-[:TRACES_TO]->(d {{qualified_name: $qn}})
                WHERE (r:HLR OR r:LLR) AND ({label_clause})
                RETURN labels(r) AS labels, r.id AS id,
                       r.description AS desc
                """,
                {"qn": qualified_name},
            )
            for record in result:
                label_type = "HLR" if "HLR" in record["labels"] else "LLR"
                requirements.append({
                    "id": record["id"],
                    "type": label_type,
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
    """Update type_signature on a design member node in Neo4j (primary store)."""
    try:
        with get_neo4j().session() as ns:
            ns.run(
                "MATCH (n:Member {qualified_name: $qn}) SET n.type_signature = $ts",
                {"qn": qualified_name, "ts": type_signature},
            )
        return True
    except Exception:
        log.warning("Neo4j type_signature update failed", exc_info=True)
        return False