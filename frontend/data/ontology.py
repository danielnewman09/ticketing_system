"""Ontology data, Neo4j graph queries, and node detail."""

import logging

from services.dependencies import get_neo4j

from backend.db import get_session
from backend.db.models import OntologyNode, OntologyTriple, Predicate

log = logging.getLogger(__name__)


def fetch_ontology_data():
    """Fetch all data needed for ontology page."""
    with get_session() as session:
        nodes = []
        kind_counts = {}
        for n in session.query(OntologyNode).all():
            kind_counts[n.kind] = kind_counts.get(n.kind, 0) + 1
            nodes.append({
                "name": n.name,
                "kind": n.kind,
                "qualified_name": n.qualified_name,
                "component": n.component.name if n.component else "-",
            })

        return {
            "nodes": nodes[:200],
            "kind_counts": kind_counts,
            "total_nodes": len(nodes),
            "total_triples": session.query(OntologyTriple).count(),
            "total_predicates": session.query(Predicate).count(),
        }


def fetch_ontology_graph_data(
    layer: str = "design",
    kind_filter: str | None = None,
    search: str | None = None,
    component_id: int | None = None,
    source_filter: str | None = None,
) -> dict:
    """Fetch graph from Neo4j for Cytoscape.js rendering.

    *layer* is ``"design"``, ``"codebase"``, or ``"dependency"``.
    Delegates to the unified ``fetch_graph()`` backend, which filters
    by the appropriate Neo4j labels.
    """
    try:
        from backend.db.neo4j_queries import fetch_graph
        return fetch_graph(layer, kind_filter, search, component_id, source_filter)
    except Exception:
        log.warning("Neo4j query failed — returning empty graph", exc_info=True)
        return {"nodes": [], "edges": []}


def fetch_hlr_graph_data(hlr_id: int, component_id: int | None = None) -> dict:
    """Fetch the ontology subgraph around an HLR for Cytoscape.js."""
    try:
        from backend.db.neo4j_queries import fetch_hlr_subgraph
        return fetch_hlr_subgraph(hlr_id, component_id)
    except Exception:
        log.warning("Neo4j HLR subgraph query failed — returning empty graph", exc_info=True)
        return {"nodes": [], "edges": []}


def fetch_neighbourhood_graph_data(qualified_name: str) -> dict:
    """Fetch the 1-hop neighbourhood graph with collapsed members."""
    try:
        from backend.db.neo4j_queries import fetch_neighbourhood_graph
        return fetch_neighbourhood_graph(qualified_name)
    except Exception:
        log.warning("Neo4j neighbourhood query failed", exc_info=True)
        return {"nodes": [], "edges": []}


def fetch_graph_node_detail(qualified_name: str) -> dict | None:
    """Fetch node detail from Neo4j (properties + relationships + requirements)."""
    try:
        from backend.db.neo4j_queries import fetch_node_detail
        return fetch_node_detail(qualified_name)
    except Exception:
        log.warning("Neo4j node detail query failed", exc_info=True)
        return None


def fetch_node_detail_full(node_id: int) -> dict | None:
    """Fetch ontology node by SQLite id with all properties + Neo4j relationships."""
    with get_session() as session:
        node = session.query(OntologyNode).filter_by(id=node_id).first()
        if not node:
            return None

        node_data = {
            "id": node.id,
            "name": node.name,
            "qualified_name": node.qualified_name,
            "kind": node.kind,
            "specialization": node.specialization or "",
            "visibility": node.visibility or "",
            "description": node.description or "",
            "component": node.component.name if node.component else "",
            "component_id": node.component_id,
            "type_signature": node.type_signature or "",
            "argsstring": node.argsstring or "",
            "definition": node.definition or "",
            "file_path": node.file_path or "",
            "line_number": node.line_number,
            "refid": node.refid or "",
            "source_type": node.source_type or "",
            "is_static": node.is_static,
            "is_const": node.is_const,
            "is_virtual": node.is_virtual,
            "is_abstract": node.is_abstract,
            "is_final": node.is_final,
        }

    # Fetch Neo4j relationships if available
    neo4j_data = None
    if node_data["qualified_name"]:
        neo4j_data = fetch_graph_node_detail(node_data["qualified_name"])

    return {"node": node_data, "neo4j": neo4j_data}


def resolve_node_id_by_qualified_name(qualified_name: str) -> int | None:
    """Look up the SQLite id for an ontology node by qualified_name."""
    with get_session() as session:
        node = session.query(OntologyNode).filter_by(
            qualified_name=qualified_name
        ).first()
        return node.id if node else None


def update_member_type(qualified_name: str, type_signature: str) -> bool:
    """Update type_signature on an ontology node (and sync to Neo4j)."""
    with get_session() as session:
        node = session.query(OntologyNode).filter_by(
            qualified_name=qualified_name
        ).first()
        if not node:
            return False
        node.type_signature = type_signature
    # Also update Neo4j
    try:
        with get_neo4j().session() as ns:
            ns.run(
                "MATCH (n:Design {qualified_name: $qn}) SET n.type_signature = $ts",
                {"qn": qualified_name, "ts": type_signature},
            )
    except Exception:
        log.warning("Neo4j type_signature sync failed", exc_info=True)
    return True
