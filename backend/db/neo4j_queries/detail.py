"""Single-node detail and neighbourhood queries."""

import logging
log = logging.getLogger(__name__)

from services.dependencies import get_neo4j

from backend.db.neo4j_queries._graph_transforms import _collapse_members
from backend.db.neo4j_queries._node_builders import _build_node


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _detect_layer(labels: list[str]) -> str:
    """Determine the graph layer from a Neo4j node's labels."""
    if "HLR" in labels or "LLR" in labels:
        return "requirement"
    if "Design" in labels:
        return "design"
    return "as-built"


def _fetch_members(session, qualified_names: set[str]) -> list[dict]:
    """Fetch full properties for design-intent member nodes."""
    if not qualified_names:
        return []
    result = session.run("""
    UNWIND $qns AS qn
    MATCH (m:Design {qualified_name: qn})
    RETURN m
    """, {"qns": list(qualified_names)})
    members = []
    for record in result:
        m = record["m"]
        members.append({
            "name": m.get("name", ""),
            "qualified_name": m.get("qualified_name", ""),
            "kind": m.get("kind", ""),
            "visibility": m.get("visibility", ""),
            "type_signature": m.get("type_signature", ""),
            "argsstring": m.get("argsstring", ""),
            "description": m.get("description", ""),
        })
    return sorted(members, key=lambda m: (m["kind"], m["name"]))


def _fetch_codebase_members(session, qualified_name: str) -> list[dict]:
    """Fetch members from the codebase layer (Compound -> CONTAINS -> Member)."""
    result = session.run("""
    MATCH (c:Compound {qualified_name: $qn})-[:CONTAINS]->(m:Member)
    RETURN m
    """, {"qn": qualified_name})
    members = []
    for record in result:
        m = record["m"]
        members.append({
            "name": m.get("name", ""),
            "qualified_name": m.get("qualified_name", ""),
            "kind": m.get("kind", ""),
            "visibility": m.get("visibility", ""),
            "type_signature": m.get("type", ""),
            "argsstring": m.get("argsstring", ""),
            "description": m.get("brief_description", "") or m.get("detailed_description", ""),
        })
    return sorted(members, key=lambda m: (m["kind"], m["name"]))


def _fetch_available_types(
    session,
    qualified_name: str,
    outgoing_rels: list[dict],
) -> list[str]:
    """Build a list of type names available to a class for autocomplete.

    Sources (in order of priority):
    1. Direct relationship targets (types the class "knows about").
    2. Sibling types in the same namespace.
    3. Primitive/built-in types.
    """
    types: dict[str, str] = {}  # qualified_name -> short_name

    _DESIGN_RELS = {"ASSOCIATES", "DEPENDS_ON", "AGGREGATES", "GENERALIZES", "REALIZES"}
    for r in outgoing_rels:
        if r["rel"] in _DESIGN_RELS:
            tqn = r.get("target_qn", "")
            tname = r.get("target_name", "")
            if tqn:
                types[tqn] = tname

    if "::" in qualified_name:
        ns = qualified_name.rsplit("::", 1)[0]
        result = session.run("""
        MATCH (d:Design)
        WHERE d.qualified_name STARTS WITH $prefix
          AND d.kind IN ['class', 'interface', 'enum', 'struct', 'type_alias']
          AND d.qualified_name <> $self
        RETURN d.qualified_name AS qn, d.name AS name
        """, {"prefix": ns + "::", "self": qualified_name})
        for record in result:
            qn = record["qn"]
            if qn not in types:
                types[qn] = record["name"]

    builtins = [
        "void", "bool", "int", "double", "float", "char",
        "uint8_t", "uint16_t", "uint32_t", "uint64_t",
        "int8_t", "int16_t", "int32_t", "int64_t",
        "size_t", "std::string", "std::vector", "std::map",
        "std::optional", "std::shared_ptr", "std::unique_ptr",
    ]

    completions = set()
    for qn, name in types.items():
        completions.add(qn)
        completions.add(name)
    completions.update(builtins)
    return sorted(completions)


# ---------------------------------------------------------------------------
# Public queries
# ---------------------------------------------------------------------------

def fetch_neighbourhood_graph(qualified_name: str) -> dict:
    """Fetch the 1-hop neighbourhood of a Design node with collapsed members.

    Returns Cytoscape-format ``{"nodes": [...], "edges": [...]}``.
    """
    with get_neo4j().session() as session:
        result = session.run("""
        MATCH (center {qualified_name: $qn})
        OPTIONAL MATCH (center)-[r_out]->(target)
        OPTIONAL MATCH (source)-[r_in]->(center)
        RETURN center,
               collect(DISTINCT {rel: r_out, target: target}) AS outs,
               collect(DISTINCT {rel: r_in, source: source}) AS ins
        """, {"qn": qualified_name})

        record = result.single()
        if not record:
            return {"nodes": [], "edges": []}

        nodes: list[dict] = []
        edges: list[dict] = []
        node_ids: set[str] = set()

        def _add(n, extra_data: dict | None = None) -> None:
            if n is None or n.element_id in node_ids:
                return
            node_ids.add(n.element_id)
            layer = _detect_layer(list(n.labels))
            d = _build_node(n, layer)
            if extra_data:
                d.update(extra_data)
            nodes.append({"data": d})

        center = record["center"]
        _add(center, {"is_center": "true"})

        for item in record["outs"]:
            r = item["rel"]
            t = item["target"]
            if r is None or t is None:
                continue
            _add(t, {"layer": _detect_layer(list(t.labels))})
            edges.append({"data": {
                "id": r.element_id,
                "source": center.element_id,
                "target": t.element_id,
                "label": r.type,
            }})

        for item in record["ins"]:
            r = item["rel"]
            s = item["source"]
            if r is None or s is None:
                continue
            _add(s, {"layer": _detect_layer(list(s.labels))})
            edges.append({"data": {
                "id": r.element_id,
                "source": s.element_id,
                "target": center.element_id,
                "label": r.type,
            }})

    nodes, edges = _collapse_members(nodes, edges)
    return {"nodes": nodes, "edges": edges}


def fetch_node_detail(qualified_name: str) -> dict | None:
    """Fetch full node properties + relationships + traced requirements + members."""
    with get_neo4j().session() as session:
        query_str = """
        MATCH (n {qualified_name: $qn})
        OPTIONAL MATCH (n)-[r_out]->(target)
        OPTIONAL MATCH (source)-[r_in]->(n)
        RETURN n,
               collect(DISTINCT {rel: type(r_out), target_qn: target.qualified_name, target_name: target.name, target_labels: labels(target)}) AS outgoing,
               collect(DISTINCT {rel: type(r_in), source_qn: source.qualified_name, source_name: source.name, source_labels: labels(source)}) AS incoming
        """

        log.debug("Query str:\n{query_str}")

        result = session.run(query_str, {"qn": qualified_name})

        record = result.single()
        if not record:
            return None

        n = record["n"]
        props = dict(n)

        outgoing = [r for r in record["outgoing"] if r["rel"] is not None]
        incoming = [r for r in record["incoming"] if r["rel"] is not None]

        # Extract traced requirements from incoming
        requirements = []
        relationships_in = []
        for r in incoming:
            labels = r.get("source_labels", [])
            if "HLR" in labels or "LLR" in labels:
                req_type = "HLR" if "HLR" in labels else "LLR"
                requirements.append({
                    "type": req_type,
                    "name": r.get("source_name", ""),
                    "relationship": r["rel"],
                })
            else:
                relationships_in.append(r)

        # Extract IMPLEMENTED_BY and COMPOSES members from outgoing
        implemented_by = []
        relationships_out = []
        member_qns: set[str] = set()
        for r in outgoing:
            if r["rel"] == "IMPLEMENTED_BY":
                implemented_by.append({
                    "qualified_name": r.get("target_qn", ""),
                    "name": r.get("target_name", ""),
                    "labels": r.get("target_labels", []),
                })
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
            "requirements": requirements,
            "implemented_by": implemented_by,
            "members": members,
            "codebase_members": codebase_members,
            "available_types": available_types,
        }
