"""Single-node detail and neighbourhood queries returning raw dicts.

Requirements are sourced from Neo4j :HLR/:LLR stubs via TRACES_TO
edges (Phase 1). The caller enriches node detail with requirement
data from these graph relationships.
"""

from __future__ import annotations

import logging

from services.dependencies import get_neo4j

log = logging.getLogger(__name__)


def _detect_layer(labels: list[str]) -> str:
    if "Design" in labels:
        return "design"
    return "as-built"


def _fetch_members(session, qualified_names: set[str]) -> list[dict]:
    """Fetch full properties for design-intent member nodes."""
    if not qualified_names:
        return []
    result = session.run(
        """
    UNWIND $qns AS qn
    MATCH (m:Design {qualified_name: qn})
    RETURN m
    """,
        {"qns": list(qualified_names)},
    )
    members = [dict(record["m"]) for record in result]
    members.sort(key=lambda m: (m.get("kind", ""), m.get("name", "")))
    log.debug("_fetch_members: %d members for %d qns", len(members), len(qualified_names))
    return members


def _fetch_codebase_members(session, qualified_name: str) -> list[dict]:
    """Fetch members from the codebase layer (Compound -> CONTAINS -> Member)."""
    result = session.run(
        """
    MATCH (c:Compound {qualified_name: $qn})-[:CONTAINS]->(m:Member)
    RETURN m
    """,
        {"qn": qualified_name},
    )
    members = [dict(record["m"]) for record in result]
    members.sort(key=lambda m: (m.get("kind", ""), m.get("name", "")))
    log.debug("_fetch_codebase_members: %d members for %s", len(members), qualified_name)
    return members


def _fetch_available_types(
    session,
    qualified_name: str,
    outgoing_rels: list[dict],
) -> list[str]:
    """Build a list of type names available to a class (for autocomplete)."""
    types: dict[str, str] = {}

    _DESIGN_RELS = {"ASSOCIATES", "DEPENDS_ON", "AGGREGATES", "GENERALIZES", "REALIZES"}
    for r in outgoing_rels:
        if r.get("type") in _DESIGN_RELS:
            tqn = r.get("target_qn", "")
            tname = r.get("target_name", "")
            if tqn:
                types[tqn] = tname

    if "::" in qualified_name:
        ns = qualified_name.rsplit("::", 1)[0]
        result = session.run(
            """
        MATCH (d:Design)
        WHERE d.qualified_name STARTS WITH $prefix
          AND d.kind IN ['class', 'interface', 'enum', 'struct', 'type_alias']
          AND d.qualified_name <> $self
        RETURN d.qualified_name AS qn, d.name AS name
        """,
            {"prefix": ns + "::", "self": qualified_name},
        )
        for record in result:
            qn = record["qn"]
            if qn not in types:
                types[qn] = record["name"]

    builtins = [
        "void",
        "bool",
        "int",
        "double",
        "float",
        "char",
        "uint8_t",
        "uint16_t",
        "uint32_t",
        "uint64_t",
        "int8_t",
        "int16_t",
        "int32_t",
        "int64_t",
        "size_t",
        "std::string",
        "std::vector",
        "std::map",
        "std::optional",
        "std::shared_ptr",
        "std::unique_ptr",
    ]

    completions: set[str] = set()
    for qn, name in types.items():
        completions.add(qn)
        completions.add(name)
    completions.update(builtins)
    return sorted(completions)


def fetch_neighbourhood_graph(qualified_name: str) -> dict:
    """Fetch the 1-hop neighbourhood of a Design node as raw dicts."""
    log.info("fetch_neighbourhood_graph(qn=%s)", qualified_name)
    with get_neo4j().session() as session:
        result = session.run(
            """
        MATCH (center {qualified_name: $qn})
        OPTIONAL MATCH (center)-[r_out]->(target)
        OPTIONAL MATCH (source)-[r_in]->(center)
        RETURN center,
               collect(DISTINCT {type: type(r_out), target: target}) AS outs,
               collect(DISTINCT {type: type(r_in), source: source}) AS ins
        """,
            {"qn": qualified_name},
        )

        record = result.single()
        if not record:
            log.warning("Neighbourhood: %s not found", qualified_name)
            return {"nodes": [], "edges": []}

        nodes: list[dict] = []
        edges: list[dict] = []
        seen_ids: set[str] = set()

        def _add(n, extra: dict | None = None) -> None:
            if n is None or n.element_id in seen_ids:
                return
            seen_ids.add(n.element_id)
            d = dict(n)
            if extra:
                d.update(extra)
            nodes.append(d)

        center = record["center"]
        _add(center, {"is_center": "true"})

        for item in record["outs"]:
            r, t = item.get("type"), item.get("target")
            if r is None or t is None:
                continue
            _add(t, {"layer": _detect_layer(list(t.labels))})
            edges.append(
                {
                    "source": center.get("qualified_name", center.element_id),
                    "target": t.get("qualified_name", t.element_id),
                    "type": r,
                }
            )

        for item in record["ins"]:
            r, s = item.get("type"), item.get("source")
            if r is None or s is None:
                continue
            _add(s, {"layer": _detect_layer(list(s.labels))})
            edges.append(
                {
                    "source": s.get("qualified_name", s.element_id),
                    "target": center.get("qualified_name", center.element_id),
                    "type": r,
                }
            )

    log.debug("fetch_neighbourhood_graph: %d nodes, %d edges", len(nodes), len(edges))
    return {"nodes": nodes, "edges": edges}


def fetch_node_detail(qualified_name: str) -> dict | None:
    """Fetch full node properties + relationships + members as raw dicts.

    Requirement traces come from TRACES_TO edges on :HLR/:LLR stubs.
    The caller enriches node detail with requirement data from those
    graph relationships.
    """
    log.info("fetch_node_detail(qn=%s)", qualified_name)
    with get_neo4j().session() as session:
        result = session.run(
            """
        MATCH (n {qualified_name: $qn})
        OPTIONAL MATCH (n)-[r_out]->(target)
        OPTIONAL MATCH (source)-[r_in]->(n)
        RETURN n,
               collect(DISTINCT {rel: type(r_out), target_qn: target.qualified_name, target_name: target.name, target_labels: labels(target)}) AS outgoing,
               collect(DISTINCT {rel: type(r_in), source_qn: source.qualified_name, source_name: source.name, source_labels: labels(source)}) AS incoming
        """,
            {"qn": qualified_name},
        )

        record = result.single()
        if not record:
            log.warning("fetch_node_detail: %s not found", qualified_name)
            return None

        n = record["n"]
        props = dict(n)

        outgoing = [r for r in record["outgoing"] if r["rel"] is not None]
        incoming = [r for r in record["incoming"] if r["rel"] is not None]

        relationships_in = []
        for r in incoming:
            relationships_in.append(r)

        implemented_by = []
        relationships_out = []
        member_qns: set[str] = set()
        for r in outgoing:
            if r["rel"] == "IMPLEMENTED_BY":
                implemented_by.append(
                    {
                        "qualified_name": r.get("target_qn", ""),
                        "name": r.get("target_name", ""),
                        "labels": r.get("target_labels", []),
                    }
                )
            elif r["rel"] == "COMPOSES":
                member_qns.add(r.get("target_qn", ""))
            else:
                relationships_out.append(r)

        members = _fetch_members(session, member_qns) if member_qns else []
        codebase_members = _fetch_codebase_members(session, qualified_name)
        available_types = _fetch_available_types(session, qualified_name, relationships_out)

        return {
            "properties": props,
            "outgoing": relationships_out,
            "incoming": relationships_in,
            "implemented_by": implemented_by,
            "members": members,
            "codebase_members": codebase_members,
            "available_types": available_types,
        }
