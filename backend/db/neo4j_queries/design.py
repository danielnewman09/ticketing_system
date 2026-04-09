"""Design-layer graph queries."""

import logging

from services.dependencies import get_neo4j

from backend.db.neo4j_queries._graph_transforms import (
    _assign_namespace_parents,
    _collapse_members,
)
from backend.db.neo4j_queries._node_builders import _build_node

log = logging.getLogger(__name__)

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

    req_result = session.run("""
    MATCH (req)-[:TRACES_TO]->(d:Design)
    WHERE (req:HLR OR req:LLR)
      AND d.qualified_name IS NOT NULL
    RETURN DISTINCT req, d
    """)
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


def fetch_design_graph(
    kind_filter: str | None = None,
    search: str | None = None,
    component_id: int | None = None,
) -> dict:
    """Fetch design-layer graph in Cytoscape.js format.

    Returns ``{"nodes": [...], "edges": [...]}``.
    """
    log.info("Getting Design Graph")
    conditions = ["n:Design"]
    params: dict = {}

    if kind_filter:
        conditions.append("n.kind = $kind")
        params["kind"] = kind_filter
    if component_id is not None:
        conditions.append("n.component_id = $comp_id")
        params["comp_id"] = component_id
    if search:
        conditions.append("(n.name CONTAINS $search OR n.qualified_name CONTAINS $search)")
        params["search"] = search

    where = " AND ".join(conditions)

    with get_neo4j().session() as session:
        # Nodes
        query_str = f"MATCH (n) WHERE {where} RETURN n"
        node_result = session.run(
            query_str,
            params,
        )

        log.debug(f"Query Str:\n{query_str}")
        log.debug(f"Params:\n{params}")

        nodes: list[dict] = []
        node_ids: set[str] = set()
        for record in node_result:
            n = record["n"]
            node_ids.add(n.element_id)
            nodes.append({"data": _build_node(n, "design")})

        query_str = f"""
            MATCH (s)-[r]->(t)
            WHERE {where.replace('n:', 's:').replace('n.', 's.')}
              AND t:Design
              AND type(r) <> 'IMPLEMENTED_BY'
            RETURN s, r, t
            """
        
        log.debug(f"Query Str:\n{query_str}")
        log.debug(f"Params:\n{params}")

        # Edges between matched nodes
        edge_result = session.run(
            query_str,
            params,
        )
        edges: list[dict] = []
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
        
        log.debug(f"Edges:\n{edges}")

        # Dependency compounds referenced by design nodes
        dep_result = session.run(
            f"""
            MATCH (s)-[r]->(dep:Compound)
            WHERE {where.replace('n:', 's:').replace('n.', 's.')}
              AND dep.source IS NOT NULL AND dep.source <> ''
            RETURN s, r, dep
            """,
            params,
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

        # Linked requirement nodes
        _fetch_traced_requirements(session, node_ids, nodes, edges)

    nodes, edges = _collapse_members(nodes, edges)
    nodes, edges = _assign_namespace_parents(nodes, edges)
    return {"nodes": nodes, "edges": edges}


def fetch_hlr_subgraph(hlr_id: int, component_id: int | None = None) -> dict:
    """Fetch the requirement neighbourhood of an HLR in Cytoscape.js format.

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
        
        query_str = """
        MATCH (h:HLR {sqlite_id: $hid})
        OPTIONAL MATCH (h)-[:TRACES_TO]->(d1:Design)
        OPTIONAL MATCH (l:LLR)-[:DECOMPOSES]->(h)
        OPTIONAL MATCH (l)-[:TRACES_TO]->(d2:Design)
        WITH collect(DISTINCT d1) + collect(DISTINCT d2) AS designs
        UNWIND designs AS d
        WITH DISTINCT d WHERE d IS NOT NULL
        RETURN d
        """

        log.debug("Query Str:\n{query_str}")

        # 2. Design nodes traced from HLR/LLRs
        trace_result = session.run(query_str, {"hid": hlr_id})
        for record in trace_result:
            d = record["d"]
            _add_node(d.element_id, _build_node(d, "design"))

        # 3. Component design nodes + their inter-relationships
        if component_id is not None:
            comp_result = session.run("""
            MATCH (d:Design {component_id: $cid})
            OPTIONAL MATCH (d)-[r]->(d2:Design {component_id: $cid})
            WHERE type(r) <> 'IMPLEMENTED_BY'
            RETURN d, collect({rel: r, target: d2}) AS rels
            """, {"cid": component_id})
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
