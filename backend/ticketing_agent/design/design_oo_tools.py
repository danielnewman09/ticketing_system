"""Tool definitions and dispatcher for the design_oo tool-loop agent.

Provides three tools:
- validate_design: check a draft design for errors
- check_class_name: look up a class name in context
- produce_oo_design: commit the final design (terminates the loop)
"""

import json
import logging

from codegraph.designs import ClassDiagram
from backend.ticketing_agent.tools.helpers.design_validation import validate_oo_design, extract_type_refs

log = logging.getLogger("agents.design")

# ---------------------------------------------------------------------------
# Tool definitions (Anthropic format)
# ---------------------------------------------------------------------------

PRODUCE_OO_DESIGN_TOOL = {
    "name": "produce_oo_design",
    "description": (
        "Return the final object-oriented class design derived from the requirements. "
        "Call this ONLY after you are confident the design is correct — use "
        "validate_design first to check for issues."
    ),
    "input_schema": ClassDiagram.model_json_schema(),
}

VALIDATE_DESIGN_TOOL = {
    "name": "validate_design",
    "description": (
        "Validate a draft OO design before committing it. Checks for unknown "
        "association targets, missing intercomponent associations, and other "
        "structural issues. Returns a list of errors and warnings. Use this "
        "to check your work before calling produce_oo_design."
    ),
    "input_schema": ClassDiagram.model_json_schema(),
}

CHECK_CLASS_NAME_TOOL = {
    "name": "check_class_name",
    "description": (
        "Check if a class, interface, or enum name exists in the design context "
        "(prior designs, dependency APIs, or intercomponent boundaries). "
        "Use this to verify that association targets and type references are "
        "valid before including them in your design. Supports partial matching."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "A class, interface, or enum name to look up. "
                    "Can be a bare name (e.g., 'Calculator') or a qualified name "
                    "(e.g., 'calculation_engine::Calculator'). Supports substring matching."
                ),
            },
        },
        "required": ["name"],
    },
}


FIND_MECHANISM_TOOL = {
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

ALL_TOOLS = [VALIDATE_DESIGN_TOOL, CHECK_CLASS_NAME_TOOL, FIND_MECHANISM_TOOL, PRODUCE_OO_DESIGN_TOOL]


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def make_design_dispatcher(
    prior_class_lookup: dict[str, str],
    dependency_lookup: dict[str, str] | None,
    intercomponent_classes: list[dict] | None,
    neo4j_session=None,
):
    """Create a tool dispatcher for the design_oo tool loop.

    Args:
        prior_class_lookup: bare_name -> qualified_name for previously designed classes.
        dependency_lookup: bare_name -> qualified_name for dependency API classes.
        intercomponent_classes: list of intercomponent class dicts with
            qualified_name, kind, name, etc.
    """
    dep_lookup = dict(dependency_lookup or {})

    def dispatch(tool_name: str, tool_input: dict) -> str:
        if tool_name == "validate_design":
            return _dispatch_validate_design(tool_input)
        elif tool_name == "check_class_name":
            return _dispatch_check_class_name(tool_input)
        elif tool_name == "find_mechanism":
            return _dispatch_find_mechanism(tool_input)
        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

    def _dispatch_validate_design(tool_input: dict) -> str:
        try:
            schema = ClassDiagram.model_validate(tool_input)
        except Exception as e:
            return json.dumps({
                "valid": False,
                "errors": [f"Invalid design format: {e}"],
                "warnings": [],
            })

        errors = validate_oo_design(
            schema,
            prior_class_lookup=prior_class_lookup,
            dependency_lookup=dep_lookup,
            intercomponent_classes=intercomponent_classes or [],
        )
        return json.dumps({
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": [],
        })

    def _dispatch_check_class_name(tool_input: dict) -> str:
        name = tool_input.get("name", "")
        if not name:
            return json.dumps({"found": False, "matches": []})

        matches = []
        name_lower = name.lower()

        # Search prior designs
        for bare, qname in prior_class_lookup.items():
            if name_lower in bare.lower() or name_lower in qname.lower():
                matches.append({
                    "qualified_name": qname,
                    "kind": "class",
                    "source": "prior_design",
                })

        # Search dependency APIs
        for bare, qname in dep_lookup.items():
            if name_lower in bare.lower() or name_lower in qname.lower():
                matches.append({
                    "qualified_name": qname,
                    "kind": "dependency",
                    "source": "dependency",
                })

        # Search intercomponent classes
        for cls in (intercomponent_classes or []):
            qname = cls.get("qualified_name", "")
            bare = qname.rsplit("::", 1)[-1] if qname else ""
            cls_name = cls.get("name", bare)
            if name_lower in cls_name.lower() or name_lower in qname.lower():
                matches.append({
                    "qualified_name": qname,
                    "kind": cls.get("kind", "class"),
                    "source": "intercomponent",
                })

        return json.dumps({
            "found": len(matches) > 0,
            "matches": matches,
        })

    def _dispatch_find_mechanism(tool_input: dict) -> str:
        query = tool_input.get("query", "")
        library = tool_input.get("library")
        if not query:
            return json.dumps({"containers": []})

        matches = []
        query_lower = query.lower()

        # Search dep_lookup (includes pre-seeded containers)
        for bare, qname in dep_lookup.items():
            if query_lower in bare.lower() or query_lower in qname.lower():
                matches.append({
                    "qualified_name": qname,
                    "name": bare,
                    "kind": "class",
                    "source": "dependency",
                    "brief": "",
                })

        # Search Neo4j if session is available
        if neo4j_session is not None:
            try:
                result = neo4j_session.run(
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
                    # Skip if already found in dep_lookup
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

    return dispatch

