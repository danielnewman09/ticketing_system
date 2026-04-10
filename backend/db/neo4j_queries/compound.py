"""Codebase and dependency layer graph queries.

This module now delegates to the unified fetch functions in fetch.py
for consistency and maintainability.
"""
import logging
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Design ↔ dependency links
# ---------------------------------------------------------------------------

def fetch_design_dependency_links(design_qnames: list[str]) -> dict:
    """Find dependency Compounds linked to given Design nodes.

    Returns Cytoscape-format ``{"nodes": [...], "edges": [...]}``.
    
    Note: This function is not yet consolidated into fetch.py as it
    has unique logic for cross-layer relationships.
    """
    # TODO: Consolidate this into fetch.py when appropriate
    from services.dependencies import get_neo4j
    from backend.db.neo4j_queries._node_builders import _build_node
    
    if not design_qnames:
        return {"nodes": [], "edges": []}

    with get_neo4j().session() as session:
        nodes: list[dict] = []
        edges: list[dict] = []
        node_ids: set[str] = set()

        query_str = """
        UNWIND $qnames AS qn
        MATCH (d:Design {qualified_name: qn})-[r]->(dep:Compound)
        WHERE dep.source IS NOT NULL AND dep.source <> ''
        RETURN d, r, dep
        """
        params = {"qnames": design_qnames}

        log.debug(f"Query Str:\n{query_str}")
        log.debug(f"Params:\n{params}")

        # Direct relationships from Design to dependency Compounds
        result = session.run(query_str, params)

        for record in result:
            d = record["d"]
            dep = record["dep"]
            r = record["r"]

            if d.element_id not in node_ids:
                node_ids.add(d.element_id)
                nodes.append({"data": _build_node(d, "design")})

            if dep.element_id not in node_ids:
                node_ids.add(dep.element_id)
                nodes.append({"data": _build_node(dep, "dependency")})

            edges.append({
                "data": {
                    "id": r.element_id,
                    "source": d.element_id,
                    "target": dep.element_id,
                    "label": r.type,
                }
            })

        query_str = """
        UNWIND $qnames AS qn
        MATCH (d:Design {qualified_name: qn})-[r:DEPENDS_ON]->(d2:Design)
        WITH d, r, d2
        MATCH (dep:Compound {qualified_name: d2.qualified_name})
        WHERE dep.source IS NOT NULL AND dep.source <> ''
        RETURN d, r, d2, dep
        """
        params = {"qnames": design_qnames}

        log.debug(f"Query Str:\n{query_str}")
        log.debug(f"Params:\n{params}")

        # Design→Design DEPENDS_ON where target matches a dependency Compound
        result2 = session.run(query_str, params)

        for record in result2:
            d = record["d"]
            dep = record["dep"]

            if d.element_id not in node_ids:
                node_ids.add(d.element_id)
                nodes.append({"data": _build_node(d, "design")})

            if dep.element_id not in node_ids:
                node_ids.add(dep.element_id)
                nodes.append({"data": _build_node(dep, "dependency")})

            edges.append({
                "data": {
                    "id": f"dep_link_{d.element_id}_{dep.element_id}",
                    "source": d.element_id,
                    "target": dep.element_id,
                    "label": "DEPENDS_ON",
                }
            })

    return {"nodes": nodes, "edges": edges}
