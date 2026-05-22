"""Design-layer graph queries returning raw dicts.

Each function returns {"nodes": [...], "edges": [...]} where:
- nodes: list of flat dicts with Neo4j properties (qualified_name, kind, name, ...)
- edges: list of {"source": str, "target": str, "type": str}

No Cytoscape formatting — that lives in backend/graph/.

Requirement traces are handled by the SQLite enrichment layer
(backend/requirements/services/graph_tags.py), not by Neo4j queries.
This module produces bare topology only; the caller enriches with tags.
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

    Returns bare topology — no requirement data. The caller enriches
    with HLR tags via enrich_with_requirement_tags().
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
        conditions.append("(n.name CONTAINS $search OR n.qualified_name CONTAINS $search)")
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
            if src and tgt and src in node_qns and tgt in node_qns:
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

        log.debug("After adding dependencies: %d raw edges, %d raw nodes", len(edges), len(nodes))

        # As-built compounds linked via IMPLEMENTED_BY
        as_built_result = session.run(
            f"""
            MATCH (s:Design)-[r:IMPLEMENTED_BY]->(c:Compound)
            WHERE {where.replace("n:", "s:").replace("n.", "s.")}
              AND (c.source IS NULL OR c.source = '')
            RETURN s.qualified_name AS src, c, type(r) AS rel_type
            """,
            params,
        )
        for record in as_built_result:
            c = record["c"]
            qn = c.get("qualified_name", "")
            if qn not in node_qns:
                node_qns.add(qn)
                d = dict(c)
                d["layer"] = "as-built"
                nodes.append(d)
            edges.append(
                {
                    "source": record["src"],
                    "target": qn,
                    "type": record["rel_type"],
                }
            )
    

        log.debug("After adding as-built: %d raw edges, %d raw nodes", len(edges), len(nodes))


    return {"nodes": nodes, "edges": edges}


def fetch_hlr_subgraph(hlr_id: int, component_id: int | None = None) -> dict:
    """Fetch design subgraph around an HLR: seed nodes + 1-hop neighbourhood.

    Uses SQLite to find seed qualified_names via the
    high_level_requirements_nodes M2M table, then fetches those nodes
    and their 1-hop design neighbours from Neo4j.

    Returns bare topology — no synthetic requirement nodes.
    The caller enriches with requirement tags via tag_direct_nodes_only().
    """
    log.info("fetch_hlr_subgraph(hlr_id=%d, component_id=%s)", hlr_id, component_id)

    from backend.db import get_session
    from backend.db.models import HighLevelRequirement

    with get_session() as session:
        hlr = session.query(HighLevelRequirement).filter_by(id=hlr_id).first()
        if not hlr:
            log.warning("HLR %d not found in SQLite", hlr_id)
            return {"nodes": [], "edges": []}
        seed_qns = {n.qualified_name for n in hlr.nodes}

    if not seed_qns:
        log.warning("HLR %d has no linked nodes in SQLite", hlr_id)
        return {"nodes": [], "edges": []}

    with get_neo4j().session() as session:
        nodes: list[dict] = []
        edges: list[dict] = []
        seen_qns: set[str] = set()

        def _add(d) -> None:
            qn = d.get("qualified_name", d.element_id if hasattr(d, "element_id") else "")
            if qn not in seen_qns:
                seen_qns.add(qn)
                nodes.append(dict(d))

        # Seed nodes
        result = session.run(
            "UNWIND $qns AS qn MATCH (d:Design {qualified_name: qn}) RETURN d",
            {"qns": list(seed_qns)},
        )
        for record in result:
            _add(record["d"])

        # Outgoing edges to other Design nodes (excluding IMPLEMENTED_BY)
        edge_out = session.run(
            """
            UNWIND $qns AS qn
            MATCH (s:Design {qualified_name: qn})-[r]->(t:Design)
            WHERE type(r) <> 'IMPLEMENTED_BY'
            RETURN s.qualified_name AS src, t.qualified_name AS tgt, type(r) AS rel_type
            """,
            {"qns": list(seed_qns)},
        )
        for record in edge_out:
            src, tgt, rel = record["src"], record["tgt"], record["rel_type"]
            edges.append({"source": src, "target": tgt, "type": rel})
            if tgt and tgt not in seen_qns:
                nb = session.run(
                    "MATCH (d:Design {qualified_name: $qn}) RETURN d",
                    {"qn": tgt},
                ).single()
                if nb:
                    _add(nb["d"])

        # Incoming edges from other Design nodes (excluding IMPLEMENTED_BY)
        edge_in = session.run(
            """
            UNWIND $qns AS qn
            MATCH (s:Design)-[r]->(t:Design {qualified_name: qn})
            WHERE type(r) <> 'IMPLEMENTED_BY'
              AND s.qualified_name <> t.qualified_name
            RETURN s.qualified_name AS src, t.qualified_name AS tgt, type(r) AS rel_type
            """,
            {"qns": list(seed_qns)},
        )
        incoming_seen: set[tuple] = set()
        for record in edge_in:
            src, tgt, rel = record["src"], record["tgt"], record["rel_type"]
            edge_key = (src, tgt, rel)
            if edge_key not in incoming_seen:
                incoming_seen.add(edge_key)
                edges.append({"source": src, "target": tgt, "type": rel})
            if src and src not in seen_qns:
                nb = session.run(
                    "MATCH (d:Design {qualified_name: $qn}) RETURN d",
                    {"qn": src},
                ).single()
                if nb:
                    _add(nb["d"])

        # Optional: expand to full component
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
                _add(record["d"])
                for item in record["rels"]:
                    if item["rel"] is not None and item["target_qn"]:
                        edges.append(
                            {
                                "source": record["d"].get("qualified_name", ""),
                                "target": item["target_qn"],
                                "type": item["rel"],
                            }
                        )

    log.debug("fetch_hlr_subgraph: %d nodes, %d edges", len(nodes), len(edges))
    return {"nodes": nodes, "edges": edges}
