"""Design-layer graph queries returning raw dicts.

Each function returns {"nodes": [...], "edges": [...]} where:
- nodes: list of flat dicts with Neo4j properties (qualified_name, kind, name, ...)
- edges: list of {"source": str, "target": str, "type": str}

No Cytoscape formatting — that lives in backend/graph/.

Requirement traces (HLR/LLR → Design) are sourced from **SQLite**, not
Neo4j.  Requirements are relational data and belong in SQLite; only the
design-intent and codebase layers live in Neo4j.
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

    # Requirement traces come from SQLite, not Neo4j.
    _attach_traced_requirements(nodes, edges)

    return {"nodes": nodes, "edges": edges}


def _attach_traced_requirements(nodes: list[dict], edges: list[dict]) -> None:
    """Attach HLR/LLR requirement nodes to the graph using SQLite data.

    Reads the HLR/LLR → OntologyTriple associations from SQLite, then
    adds synthetic requirement nodes and TRACES_TO edges for any design
    nodes already present in the graph.
    """
    node_qns = {n.get("qualified_name", "") for n in nodes if n.get("qualified_name")}
    if not node_qns:
        return

    from backend.db import get_session
    from backend.db.models import HighLevelRequirement, LowLevelRequirement

    appended: set[str] = set()  # track (req_type, req_id) already added

    with get_session() as session:
        for hlr in session.query(HighLevelRequirement).all():
            req_key = f"hlr:{hlr.id}"
            linked_qns: set[str] = set()
            for triple in hlr.triples:
                subj_qn = triple.subject.qualified_name
                obj_qn = triple.object.qualified_name
                if subj_qn in node_qns:
                    linked_qns.add(subj_qn)
                if obj_qn in node_qns:
                    linked_qns.add(obj_qn)
            if linked_qns and req_key not in appended:
                appended.add(req_key)
                nodes.append(
                    {
                        "element_id": req_key,
                        "qualified_name": "",
                        "name": f"HLR {hlr.id}",
                        "kind": "HLR",
                        "title": hlr.description[:200] if hlr.description else "",
                        "layer": "requirement",
                    }
                )
            for qn in linked_qns:
                edges.append(
                    {
                        "source": req_key,
                        "target": qn,
                        "type": "TRACES_TO",
                    }
                )

        for llr in session.query(LowLevelRequirement).all():
            req_key = f"llr:{llr.id}"
            linked_qns: set[str] = set()
            for triple in llr.triples:
                subj_qn = triple.subject.qualified_name
                obj_qn = triple.object.qualified_name
                if subj_qn in node_qns:
                    linked_qns.add(subj_qn)
                if obj_qn in node_qns:
                    linked_qns.add(obj_qn)
            if linked_qns and req_key not in appended:
                appended.add(req_key)
                nodes.append(
                    {
                        "element_id": req_key,
                        "qualified_name": "",
                        "name": f"LLR {llr.id}",
                        "kind": "LLR",
                        "title": llr.description[:200] if llr.description else "",
                        "layer": "requirement",
                    }
                )
            for qn in linked_qns:
                edges.append(
                    {
                        "source": req_key,
                        "target": qn,
                        "type": "TRACES_TO",
                    }
                )

    traced_count = sum(1 for e in edges if e["type"] == "TRACES_TO")
    log.debug("_attach_traced_requirements: %d requirement edges from SQLite", traced_count)


def fetch_hlr_subgraph(hlr_id: int, component_id: int | None = None) -> dict:
    """Fetch the requirement neighbourhood of an HLR as raw dicts.

    Starts from SQLite to find the HLR's linked triples, then fetches
    the corresponding Design nodes from Neo4j.
    """
    log.info("fetch_hlr_subgraph(hlr_id=%d, component_id=%s)", hlr_id, component_id)

    from backend.db import get_session
    from backend.db.models import HighLevelRequirement

    # Collect qualified_names of all design nodes linked to this HLR
    design_qns: set[str] = set()
    with get_session() as session:
        hlr = session.query(HighLevelRequirement).filter_by(id=hlr_id).first()
        if not hlr:
            log.warning("HLR %d not found in SQLite", hlr_id)
            return {"nodes": [], "edges": []}
        for triple in hlr.triples:
            if triple.subject.qualified_name:
                design_qns.add(triple.subject.qualified_name)
            if triple.object.qualified_name:
                design_qns.add(triple.object.qualified_name)
        # Also include LLR triples
        for llr in hlr.low_level_requirements:
            for triple in llr.triples:
                if triple.subject.qualified_name:
                    design_qns.add(triple.subject.qualified_name)
                if triple.object.qualified_name:
                    design_qns.add(triple.object.qualified_name)

    if not design_qns:
        log.warning("HLR %d has no linked triples in SQLite", hlr_id)
        return {"nodes": [], "edges": []}

    # Fetch the design nodes and their intra-component edges from Neo4j
    with get_neo4j().session() as session:
        nodes: list[dict] = []
        edges: list[dict] = []
        seen_qns: set[str] = set()

        def _add_node(d) -> None:
            qn = d.get("qualified_name", d.element_id)
            if qn not in seen_qns:
                seen_qns.add(qn)
                nodes.append(dict(d))

        # Fetch the seed design nodes
        if design_qns:
            result = session.run(
                """
                UNWIND $qns AS qn
                MATCH (d:Design {qualified_name: qn})
                RETURN d
                """,
                {"qns": list(design_qns)},
            )
            for record in result:
                _add_node(record["d"])

        # If component_id given, also fetch all nodes in that component
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

    # Add requirement nodes from SQLite (same logic as _attach_traced_requirements)
    _attach_traced_requirements(nodes, edges)

    log.debug("fetch_hlr_subgraph: %d nodes, %d edges", len(nodes), len(edges))
    return {"nodes": nodes, "edges": edges}