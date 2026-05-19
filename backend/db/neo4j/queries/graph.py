"""Design-layer graph queries returning raw dicts.

Each function returns {"nodes": [...], "edges": [...]} where:
- nodes: list of flat dicts with Neo4j properties (qualified_name, kind, name, ...)
- edges: list of {"source": str, "target": str, "type": str}

No Cytoscape formatting — that lives in backend/graph/.
"""

from __future__ import annotations

import logging

from services.dependencies import get_neo4j

log = logging.getLogger(__name__)


def fetch_design_graph(
    kind_filter: str | None = None,
    search: str | None = None,
    component_id: int | None = None,
) -> dict:
    """Fetch design-layer nodes and edges as raw dicts.

    Returns {"nodes": [{"qualified_name", "kind", "name", ...}],
             "edges": [{"source": qn, "target": qn, "type": rel_type}]}
    """
    log.info(
        "fetch_design_graph(kind=%s, search=%s, component_id=%s)",
        kind_filter,
        search,
        component_id,
    )
    conditions = ["n:Design"]
    params: dict = {}

    if kind_filter:
        conditions.append("n.kind = $kind")
        params["kind"] = kind_filter
    if component_id is not None:
        conditions.append("n.component_id = $comp_id")
        params["comp_id"] = component_id
    if search:
        conditions.append(
            "(n.name CONTAINS $search OR n.qualified_name CONTAINS $search)"
        )
        params["search"] = search

    where = " AND ".join(conditions)

    with get_neo4j().session() as session:
        node_result = session.run(f"MATCH (n) WHERE {where} RETURN n", params)
        nodes: list[dict] = []
        node_qns: set[str] = set()
        for record in node_result:
            n = record["n"]
            qn = n.get("qualified_name", "")
            node_qns.add(qn)
            nodes.append(dict(n))

        log.debug("fetch_design_graph: %d raw nodes", len(nodes))

        edges: list[dict] = []
        edge_result = session.run(
            f"""
            MATCH (s)-[r]->(t)
            WHERE {where.replace("n:", "s:").replace("n.", "s.")}
              AND t:Design
              AND type(r) <> 'IMPLEMENTED_BY'
            RETURN s.qualified_name AS src, t.qualified_name AS tgt, type(r) AS rel_type
            """,
            params,
        )
        for record in edge_result:
            src = record["src"]
            tgt = record["tgt"]
            if src and tgt:
                if tgt not in node_qns:
                    node_qns.add(tgt)
                edges.append(
                    {
                        "source": src,
                        "target": tgt,
                        "type": record["rel_type"],
                    }
                )

        log.debug("fetch_design_graph: %d raw edges", len(edges))

        # Dependency compounds referenced by design nodes
        dep_result = session.run(
            f"""
            MATCH (s)-[r]->(dep:Compound)
            WHERE {where.replace("n:", "s:").replace("n.", "s.")}
              AND dep.source IS NOT NULL AND dep.source <> ''
            RETURN s.qualified_name AS src, dep, type(r) AS rel_type
            """,
            params,
        )
        for record in dep_result:
            dep = record["dep"]
            if dep.get("qualified_name", "") not in node_qns:
                nodes.append(dict(dep))
            edges.append(
                {
                    "source": record["src"],
                    "target": dep.get("qualified_name", ""),
                    "type": record["rel_type"],
                }
            )

        # Linked requirement nodes
        _attach_traced_requirements(session, edges, nodes)

    return {"nodes": nodes, "edges": edges}


def _attach_traced_requirements(session, edges: list[dict], nodes: list[dict]) -> None:
    """Fetch HLR/LLR nodes that trace to any design node and append them in-place."""
    node_qns = {n.get("qualified_name", "") for n in nodes}
    if not node_qns:
        return

    req_result = session.run("""
    MATCH (req)-[:TRACES_TO]->(d:Design)
    WHERE (req:HLR OR req:LLR)
      AND d.qualified_name IS NOT NULL
    RETURN req, d.qualified_name AS d_qn
    """)
    appended_ids: set[str] = set()
    for record in req_result:
        d_qn = record["d_qn"]
        if d_qn not in node_qns:
            continue
        req = record["req"]
        req_id = req.element_id
        if req_id not in appended_ids:
            appended_ids.add(req_id)
            labels = list(req.labels)
            req_type = "HLR" if "HLR" in labels else "LLR"
            nodes.append(
                {
                    "element_id": req_id,
                    "qualified_name": "",
                    "name": f"{req_type} {req.get('sqlite_id', '')}",
                    "kind": req_type,
                    "title": req.get("title", ""),
                    "layer": "requirement",
                }
            )
        edges.append(
            {
                "source": req_id,
                "target": d_qn,
                "type": "TRACES_TO",
            }
        )

    traced_count = sum(1 for e in edges if e["type"] == "TRACES_TO")
    log.debug("_attach_traced_requirements: %d requirement edges", traced_count)


def fetch_hlr_subgraph(hlr_id: int, component_id: int | None = None) -> dict:
    """Fetch the requirement neighbourhood of an HLR as raw dicts."""
    log.info("fetch_hlr_subgraph(hlr_id=%d, component_id=%s)", hlr_id, component_id)
    with get_neo4j().session() as session:
        check = session.run(
            "MATCH (h:HLR {sqlite_id: $hid}) RETURN h",
            {"hid": hlr_id},
        ).single()
        if not check:
            log.warning("HLR %d not found in Neo4j", hlr_id)
            return {"nodes": [], "edges": []}

        nodes: list[dict] = []
        edges: list[dict] = []
        seen_qns: set[str] = set()

        def _add_node(d) -> None:
            qn = d.get("qualified_name", d.element_id)
            if qn not in seen_qns:
                seen_qns.add(qn)
                nodes.append(dict(d))

        trace_result = session.run(
            """
        MATCH (h:HLR {sqlite_id: $hid})
        OPTIONAL MATCH (h)-[:TRACES_TO]->(d1:Design)
        OPTIONAL MATCH (l:LLR)-[:DECOMPOSES]->(h)
        OPTIONAL MATCH (l)-[:TRACES_TO]->(d2:Design)
        WITH collect(DISTINCT d1) + collect(DISTINCT d2) AS designs
        UNWIND designs AS d
        WITH DISTINCT d WHERE d IS NOT NULL
        RETURN d
        """,
            {"hid": hlr_id},
        )
        for record in trace_result:
            _add_node(record["d"])

        if component_id is not None:
            comp_result = session.run(
                """
            MATCH (d:Design {component_id: $cid})
            OPTIONAL MATCH (d)-[r]->(d2:Design {component_id: $cid})
            WHERE type(r) <> 'IMPLEMENTED_BY'
            RETURN d, collect({rel: type(r), target_qn: d2.qualified_name}) AS rels
            """,
                {"cid": component_id},
            )
            for record in comp_result:
                _add_node(record["d"])
                for item in record["rels"]:
                    if item["rel"] is None or not item["target_qn"]:
                        continue
                    edges.append(
                        {
                            "source": record["d"].get("qualified_name", ""),
                            "target": item["target_qn"],
                            "type": item["rel"],
                        }
                    )

    log.debug("fetch_hlr_subgraph: %d nodes, %d edges", len(nodes), len(edges))
    return {"nodes": nodes, "edges": edges}
