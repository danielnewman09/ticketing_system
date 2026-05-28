"""validate_qualified_names tool: validate qname format and existence."""

import json

from backend.db.neo4j.repositories.verification import _is_valid_verification_qname
from backend.ticketing_agent.tools.helpers.qname import qname_resolves

SCHEMA = {
    "name": "validate_qualified_names",
    "description": (
        "Validate a list of qualified names against format rules and the "
        "design context (draft + persistent). Checks for: invalid prefixes, "
        "bare lowercase identifiers, dot separators, and existence. Use this "
        "to verify your references before calling commit_design_and_verifications."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "qualified_names": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of qualified names to validate.",
            },
        },
        "required": ["qualified_names"],
    },
}


def handle(ctx, tool_input: dict) -> str:
    """Validate qualified name format and existence against draft + Neo4j."""
    qnames = tool_input.get("qualified_names", [])
    results = []
    for qn in qnames:
        result_entry = {
            "qname": qn,
            "valid": True,
            "exists": None,
            "source": None,
            "error": None,
            "correction": None,
        }

        # Format validation
        is_valid, corrected = _is_valid_verification_qname(qn)
        if not is_valid:
            result_entry["valid"] = False
            result_entry["error"] = f"Invalid qualified name format: {qn}"
            results.append(result_entry)
            continue
        elif corrected:
            result_entry["correction"] = corrected

        resolved_qn = corrected if corrected else qn

        # Check draft first
        found_in_draft = resolved_qn in ctx.draft_lookup
        if found_in_draft:
            result_entry["exists"] = True
            result_entry["source"] = "draft"
        elif ctx.neo4j_session is not None:
            from backend.db.neo4j.repositories.design import DesignRepository

            repo = DesignRepository(ctx.neo4j_session)
            nodes = repo.find_nodes(search=resolved_qn, exclude_source_types=["verification"])
            found = any(n.qualified_name == resolved_qn for n in nodes)
            # Also check parent class for member references
            if not found and "::" in resolved_qn:
                parts = resolved_qn.rsplit("::", 2)
                if len(parts) >= 2:
                    class_qname = "::".join(parts[:-1]) if len(parts) == 3 else resolved_qn
                    found = any(n.qualified_name == class_qname for n in nodes)
            result_entry["exists"] = found
            result_entry["source"] = "persistent" if found else None
        else:
            result_entry["exists"] = found_in_draft
            result_entry["source"] = "draft" if found_in_draft else None

        results.append(result_entry)
    return json.dumps({"results": results})
