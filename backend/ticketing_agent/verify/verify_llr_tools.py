"""Tool definitions and dispatcher for the verify_llr tool-loop agent.

Provides three tools:
- validate_qualified_names: check qname format and Neo4j existence
- lookup_design_element: fuzzy search for :Design nodes in Neo4j
- produce_verifications: commit verification procedures (terminates loop)
"""

import json
import logging

from backend.requirements.schemas import VerificationSchema

log = logging.getLogger("agents.verify")

# ---------------------------------------------------------------------------
# Tool definitions (Anthropic format)
# ---------------------------------------------------------------------------

PRODUCE_VERIFICATIONS_TOOL = {
    "name": "produce_verifications",
    "description": (
        "Return the fleshed-out verification procedures for an LLR. "
        "Call this ONLY after you are confident in your output — use "
        "validate_qualified_names and lookup_design_element to verify "
        "your references first."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "verifications": {
                "type": "array",
                "items": VerificationSchema.model_json_schema(),
            },
        },
        "required": ["verifications"],
    },
}

VALIDATE_QNAMES_TOOL = {
    "name": "validate_qualified_names",
    "description": (
        "Validate a list of qualified names against format rules and the "
        "design context. Checks for: invalid prefixes (test_, result_of_, "
        "verify_, check_), bare lowercase identifiers, dot separators (should "
        "be ::), and existence as :Design nodes in the ontology graph. "
        "Use this to verify your references before calling produce_verifications."
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

LOOKUP_DESIGN_ELEMENT_TOOL = {
    "name": "lookup_design_element",
    "description": (
        "Search for design elements in the ontology graph by name or qualified "
        "name. Returns matching :Design nodes with their qualified names, kind, "
        "description, and public members. Use this to find the correct qualified "
        "name for a class, method, or attribute before referencing it in "
        "verification conditions."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "Name or qualified name to search for. Supports "
                    "substring matching — e.g., 'Button' will find "
                    "'user_interface::Button'."
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

ALL_TOOLS = [VALIDATE_QNAMES_TOOL, LOOKUP_DESIGN_ELEMENT_TOOL, PRODUCE_VERIFICATIONS_TOOL]


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def make_verify_dispatcher(neo4j_session=None):
    """Create a tool dispatcher for the verify_llr tool loop.

    Args:
        neo4j_session: Optional Neo4j session for reference validation
            and design element lookup. If None, format validation still
            works but Neo4j checks are skipped.
    """
    def dispatch(tool_name: str, tool_input: dict) -> str:
        if tool_name == "validate_qualified_names":
            return _dispatch_validate_qnames(tool_input)
        elif tool_name == "lookup_design_element":
            return _dispatch_lookup_design_element(tool_input)
        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

    def _dispatch_validate_qnames(tool_input: dict) -> str:
        from backend.db.neo4j.repositories.verification import _is_valid_verification_qname

        qnames = tool_input.get("qualified_names", [])
        results = []
        for qn in qnames:
            result_entry = {
                "qname": qn,
                "valid": True,
                "exists": None,
                "error": None,
                "correction": None,
            }
            # Format validation
            is_valid, corrected = _is_valid_verification_qname(qn)
            if not is_valid:
                result_entry["valid"] = False
                result_entry["error"] = f"Invalid qualified name format: {qn}"
            elif corrected:
                result_entry["correction"] = corrected
            # Neo4j existence check (if session provided)
            if neo4j_session is not None and is_valid:
                resolved_qn = corrected if corrected else qn
                # For member references (e.g., "Ns::Class::method"), check the class part too
                check_names = [resolved_qn]
                parts = resolved_qn.rsplit("::", 2)
                if len(parts) >= 2:
                    # Add class-level qname as fallback
                    class_qname = "::".join(parts[:-1]) if len(parts) == 3 else resolved_qn
                    if class_qname != resolved_qn:
                        check_names.append(class_qname)

                found = False
                for candidate in check_names:
                    record = neo4j_session.run(
                        "MATCH (d:Design {qualified_name: $qn}) RETURN count(d) AS cnt",
                        {"qn": candidate},
                    ).single()
                    if record and record["cnt"] > 0:
                        found = True
                        break
                result_entry["exists"] = found
            results.append(result_entry)
        return json.dumps({"results": results})

    def _dispatch_lookup_design_element(tool_input: dict) -> str:
        name = tool_input.get("name", "")
        kind = tool_input.get("kind")
        if not name or neo4j_session is None:
            return json.dumps({"elements": []})

        from backend.db.neo4j.repositories.design import DesignRepository
        repo = DesignRepository(neo4j_session)
        # Try exact match first
        exact = repo.get_by_qualified_name(name)
        if exact:
            return json.dumps({"elements": [_format_design_node(exact)]})
        # Fuzzy search
        nodes = repo.find_nodes(kind=kind, search=name)
        # Limit to avoid overwhelming context
        elements = [_format_design_node(n) for n in nodes[:20]]
        return json.dumps({"elements": elements})

    return dispatch


def _format_design_node(node) -> dict:
    """Format a DesignNode for the tool response."""
    result = {
        "qualified_name": node.qualified_name,
        "kind": node.kind,
        "description": node.description,
    }
    if node.is_intercomponent:
        result["is_intercomponent"] = True
    return result
