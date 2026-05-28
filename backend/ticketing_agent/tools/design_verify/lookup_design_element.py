"""lookup_design_element tool: search for design elements in draft + Neo4j."""

import json

SCHEMA = {
    "name": "lookup_design_element",
    "description": (
        "Search for design elements in the current draft and persistent "
        "ontology graph by name or qualified name. Returns matching elements "
        "with their qualified names, kind, description, and source (draft or "
        "persistent). Use this to find the correct qualified name for a class, "
        "method, or attribute before referencing it in conditions."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "Name or qualified name to search for. Supports "
                    "substring matching."
                ),
            },
            "kind": {
                "type": "string",
                "description": "Optional kind filter: 'class', 'interface', 'enum', 'method', 'attribute'.",
            },
        },
        "required": ["name"],
    },
}


def handle(ctx, tool_input: dict) -> str:
    """Search draft and Neo4j (excluding verification stubs) for matching elements."""
    name = tool_input.get("name", "")
    kind = tool_input.get("kind")
    if not name:
        return json.dumps({"elements": []})

    elements = []
    name_lower = name.lower()

    # Search draft
    if ctx.draft_lookup:
        for qname, info in ctx.draft_lookup.items():
            if name_lower in qname.lower() or name_lower in info.get("description", "").lower():
                if kind and info.get("kind") != kind:
                    continue
                elements.append(info.copy())

    # Search Neo4j (excluding verification stubs)
    if ctx.neo4j_session is not None:
        from backend.db.neo4j.repositories.design import DesignRepository

        repo = DesignRepository(ctx.neo4j_session)
        nodes = repo.find_nodes(
            search=name,
            kind=kind if kind in ("class", "interface", "enum") else None,
            exclude_source_types=["verification"],
        )
        for node in nodes[:20]:
            # Skip if already found in draft (draft takes priority)
            if node.qualified_name in ctx.draft_lookup:
                continue
            elements.append({
                "qualified_name": node.qualified_name,
                "kind": node.kind,
                "description": node.description or "",
                "source": "persistent",
                **({"is_intercomponent": True} if node.is_intercomponent else {}),
            })

    # Deduplicate by qualified name and limit
    seen = set()
    deduped = []
    for e in elements:
        qn = e["qualified_name"]
        if qn not in seen:
            seen.add(qn)
            deduped.append(e)
    return json.dumps({"elements": deduped[:20]})
