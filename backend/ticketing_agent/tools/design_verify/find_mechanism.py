"""find_mechanism tool: search for container/smart-pointer types in the dependency graph."""

import json
import logging

log = logging.getLogger("agents.tools.find_mechanism")

SCHEMA = {
    "name": "find_mechanism",
    "description": (
        "Search the dependency graph for container or smart-pointer types "
        "(e.g., std::vector, std::map, boost::unordered_map). "
        "Returns matching types with their qualified_name, kind, source, "
        "and brief description. Use this to discover the correct mechanism "
        "name for aggregates and references associations. Common containers "
        "(std::vector, std::map, etc.) are pre-loaded in the dependency "
        "context and available without a search."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Container or smart-pointer name to search for "
                    "(e.g., 'vector', 'unordered_map', 'shared_ptr')"
                ),
            },
            "library": {
                "type": "string",
                "description": "Optional library source to restrict search (e.g., 'cppreference', 'boost')",
            },
        },
        "required": ["query"],
    },
}


def handle(ctx, tool_input: dict) -> str:
    """Search dep_lookup and Neo4j for container/smart-pointer types."""
    query = tool_input.get("query", "")
    library = tool_input.get("library")
    if not query:
        return json.dumps({"containers": []})

    matches = []
    query_lower = query.lower()

    # Search dep_lookup (includes pre-seeded containers)
    for bare, qname in ctx.dep_lookup.items():
        if query_lower in bare.lower() or query_lower in qname.lower():
            matches.append({
                "qualified_name": qname,
                "name": bare,
                "kind": "class",
                "source": "dependency",
                "brief": "",
            })

    # Search Neo4j if session is available
    if ctx.neo4j_session is not None:
        try:
            result = ctx.neo4j_session.run(
                "MATCH (n:Compound) "
                "WHERE n.qualified_name CONTAINS $query "
                "AND n.kind IN ['class', 'struct'] "
                "AND (n.source = 'cppreference' OR n.source = 'boost' OR n.source IS NOT NULL) "
                "RETURN n.qualified_name AS qn, n.name AS name, "
                "n.kind AS kind, n.source AS source, n.brief AS brief "
                "LIMIT 20",
                query=query,
            )
            for record in result:
                qn = record["qn"]
                if any(m["qualified_name"] == qn for m in matches):
                    continue
                if library and record["source"] != library:
                    continue
                matches.append({
                    "qualified_name": qn,
                    "name": record["name"] or qn.rsplit("::", 1)[-1],
                    "kind": record["kind"] or "class",
                    "source": record["source"] or "dependency",
                    "brief": record["brief"] or "",
                })
        except Exception:
            log.warning("find_mechanism: Neo4j query failed", exc_info=True)

    # Deduplicate by qualified_name
    seen = set()
    deduped = []
    for m in matches:
        if m["qualified_name"] not in seen:
            seen.add(m["qualified_name"])
            deduped.append(m)

    return json.dumps({"containers": deduped[:20]})
