"""Tool definitions and dispatcher for the combined design+verify tool loop.

Provides six tools:
- draft_design: submit/revise the OO design draft (stores in dispatcher state)
- validate_design: validate the current draft for structural consistency
- check_class_name: look up class names in prior designs, dep APIs, and intercomponent context
- validate_qualified_names: validate qname format and existence against draft + Neo4j
- lookup_design_element: search for design elements in draft + Neo4j (excluding verification stubs)
- commit_design_and_verifications: atomically commit design + verifications (terminates loop)
"""

import json
import logging

from backend.codebase.schemas import DesignAndVerificationSchema, OODesignSchema
from backend.db.neo4j.repositories.verification import _is_valid_verification_qname
from backend.requirements.schemas import VerificationSchema

from backend.ticketing_agent.design.design_oo_tools import _validate_oo_design

log = logging.getLogger("agents.design_verify")


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------


def _commit_tool_schema() -> dict:
    """Build the JSON schema for commit_design_and_verifications.

    Customizes the verifications field to explicitly describe the LLR ID key
    format, which LLMs frequently get wrong.
    """
    schema = DesignAndVerificationSchema.model_json_schema()
    # Add a clear description to the verifications property
    if "properties" in schema and "verifications" in schema["properties"]:
        schema["properties"]["verifications"]["description"] = (
            "Map of LLR ID (integer string) to list of verification procedures. "
            "Keys MUST be LLR IDs like \"1\", \"2\" — NOT test names. "
            "Example: {\"1\": [...], \"2\": [...]}"
        )
    return schema

# ---------------------------------------------------------------------------
# Tool definitions (Anthropic format)
# ---------------------------------------------------------------------------

DRAFT_DESIGN_TOOL = {
    "name": "draft_design",
    "description": (
        "Submit or revise the current OO design draft. The design is stored "
        "in the tool loop state so that subsequent validate_qualified_names "
        "and lookup_design_element calls can check references against it. "
        "Returns validation results and a summary of the stored draft."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "design": OODesignSchema.model_json_schema(),
        },
        "required": ["design"],
    },
}

VALIDATE_DESIGN_TOOL = {
    "name": "validate_design",
    "description": (
        "Validate the current draft OO design for structural consistency. "
        "Checks for unknown association targets, missing intercomponent "
        "associations, and other issues. Uses the design currently stored "
        "via draft_design. Returns errors and warnings."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "design": OODesignSchema.model_json_schema(),
        },
        "required": ["design"],
    },
}

CHECK_CLASS_NAME_TOOL = {
    "name": "check_class_name",
    "description": (
        "Check if a class, interface, or enum name exists in the design "
        "context (prior designs, dependency APIs, intercomponent boundaries, "
        "or the current draft). Use this to verify that association targets "
        "and type references are valid. Supports partial matching."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "A class, interface, or enum name to look up. Can be a "
                    "bare name or qualified name. Supports substring matching."
                ),
            },
        },
        "required": ["name"],
    },
}

VALIDATE_QNAMES_TOOL = {
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

LOOKUP_DESIGN_ELEMENT_TOOL = {
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

COMMIT_TOOL = {
    "name": "commit_design_and_verifications",
    "description": (
        "Commit the final OO design and all verification procedures. This "
        "terminates the agent loop. Validates that all qualified names "
        "reference real design elements and that the design is structurally "
        "sound. If there are errors, returns them for the agent to fix "
        "before retrying."
    ),
    "input_schema": _commit_tool_schema(),
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

ALL_TOOLS = [
    DRAFT_DESIGN_TOOL,
    VALIDATE_DESIGN_TOOL,
    CHECK_CLASS_NAME_TOOL,
    FIND_MECHANISM_TOOL,
    VALIDATE_QNAMES_TOOL,
    LOOKUP_DESIGN_ELEMENT_TOOL,
    COMMIT_TOOL,
]


# ---------------------------------------------------------------------------
# Draft-state helpers
# ---------------------------------------------------------------------------


def _build_draft_lookup(design: OODesignSchema) -> dict[str, dict]:
    """Build a lookup dict from a draft OODesignSchema.

    Returns qualified_name -> {kind, description, source: 'draft'} for all
    classes, interfaces, enums, their attributes, and methods.
    """
    lookup: dict[str, dict] = {}

    for cls in design.classes:
        qname = f"{cls.module}::{cls.name}" if cls.module else cls.name
        lookup[qname] = {
            "qualified_name": qname,
            "kind": "class",
            "description": cls.description,
            "source": "draft",
        }
        for attr in cls.attributes:
            attr_qname = f"{qname}::{attr.name}"
            lookup[attr_qname] = {
                "qualified_name": attr_qname,
                "kind": "attribute",
                "description": attr.description,
                "source": "draft",
            }
        for method in cls.methods:
            method_qname = f"{qname}::{method.name}"
            lookup[method_qname] = {
                "qualified_name": method_qname,
                "kind": "method",
                "description": method.description,
                "source": "draft",
            }

    for iface in design.interfaces:
        qname = f"{iface.module}::{iface.name}" if iface.module else iface.name
        lookup[qname] = {
            "qualified_name": qname,
            "kind": "interface",
            "description": iface.description,
            "source": "draft",
        }
        for method in iface.methods:
            method_qname = f"{qname}::{method.name}"
            lookup[method_qname] = {
                "qualified_name": method_qname,
                "kind": "method",
                "description": method.description,
                "source": "draft",
            }

    for enum in design.enums:
        qname = f"{enum.module}::{enum.name}" if enum.module else enum.name
        lookup[qname] = {
            "qualified_name": qname,
            "kind": "enum",
            "description": enum.description,
            "source": "draft",
        }

    return lookup


def _draft_summary(design: OODesignSchema) -> dict:
    """Return a summary dict of the draft design for tool responses."""
    total_attrs = sum(len(cls.attributes) for cls in design.classes)
    total_methods = sum(len(cls.methods) for cls in design.classes)
    return {
        "classes": len(design.classes),
        "interfaces": len(design.interfaces),
        "enums": len(design.enums),
        "associations": len(design.associations),
        "attributes": total_attrs,
        "methods": total_methods,
    }


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def make_combined_dispatcher(
    prior_class_lookup: dict[str, str],
    dependency_lookup: dict[str, str] | None,
    intercomponent_classes: list[dict] | None,
    neo4j_session=None,
):
    """Create a tool dispatcher for the combined design+verify tool loop.

    Maintains in-memory draft state between tool calls.

    Args:
        prior_class_lookup: bare_name -> qualified_name for previously designed classes.
        dependency_lookup: bare_name -> qualified_name for dependency API classes.
        intercomponent_classes: list of intercomponent class dicts.
        neo4j_session: Optional Neo4j session for persistent design lookups.
    """
    dep_lookup = dict(dependency_lookup or {})
    _draft_design: OODesignSchema | None = None
    _draft_lookup: dict[str, dict] = {}

    def dispatch(tool_name: str, tool_input: dict) -> str:
        nonlocal _draft_design, _draft_lookup

        if tool_name == "draft_design":
            return _dispatch_draft_design(tool_input)
        elif tool_name == "validate_design":
            return _dispatch_validate_design(tool_input)
        elif tool_name == "check_class_name":
            return _dispatch_check_class_name(tool_input)
        elif tool_name == "validate_qualified_names":
            return _dispatch_validate_qnames(tool_input)
        elif tool_name == "lookup_design_element":
            return _dispatch_lookup_design_element(tool_input)
        elif tool_name == "find_mechanism":
            return _dispatch_find_mechanism(tool_input)
        elif tool_name == "commit_design_and_verifications":
            return _dispatch_commit(tool_input, _draft_design, _draft_lookup)
        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

    # -- draft_design --------------------------------------------------------

    def _dispatch_draft_design(tool_input: dict) -> str:
        nonlocal _draft_design, _draft_lookup
        try:
            design = OODesignSchema.model_validate(tool_input.get("design", tool_input))
        except Exception as e:
            return json.dumps({"valid": False, "errors": [f"Invalid design format: {e}"], "draft_summary": {}})

        # Validate the draft
        errors = _validate_oo_design(
            design,
            prior_class_lookup=prior_class_lookup,
            dependency_lookup=dep_lookup,
            intercomponent_classes=intercomponent_classes or [],
        )

        # Store draft
        _draft_design = design
        _draft_lookup = _build_draft_lookup(design)

        return json.dumps({
            "valid": len(errors) == 0,
            "errors": errors,
            "draft_summary": _draft_summary(design),
        })

    # -- validate_design -----------------------------------------------------

    def _dispatch_validate_design(tool_input: dict) -> str:
        try:
            design = OODesignSchema.model_validate(tool_input.get("design", tool_input))
        except Exception as e:
            return json.dumps({"valid": False, "errors": [f"Invalid design format: {e}"], "warnings": []})

        errors = _validate_oo_design(
            design,
            prior_class_lookup=prior_class_lookup,
            dependency_lookup=dep_lookup,
            intercomponent_classes=intercomponent_classes or [],
        )
        return json.dumps({
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": [],
        })

    # -- check_class_name ----------------------------------------------------

    def _dispatch_check_class_name(tool_input: dict) -> str:
        name = tool_input.get("name", "")
        if not name:
            return json.dumps({"found": False, "matches": []})

        matches = []
        name_lower = name.lower()

        # Search draft
        if _draft_lookup:
            for qname, info in _draft_lookup.items():
                if name_lower in qname.lower() or name_lower in info.get("description", "").lower():
                    matches.append({
                        "qualified_name": qname,
                        "kind": info["kind"],
                        "source": "draft",
                    })

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

        return json.dumps({"found": len(matches) > 0, "matches": matches})

    # -- validate_qualified_names --------------------------------------------

    def _dispatch_validate_qnames(tool_input: dict) -> str:
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
            found_in_draft = resolved_qn in _draft_lookup
            if found_in_draft:
                result_entry["exists"] = True
                result_entry["source"] = "draft"
            elif neo4j_session is not None:
                # Check Neo4j (excluding verification stubs)
                from backend.db.neo4j.repositories.design import DesignRepository
                repo = DesignRepository(neo4j_session)
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

    # -- lookup_design_element -----------------------------------------------

    def _dispatch_lookup_design_element(tool_input: dict) -> str:
        name = tool_input.get("name", "")
        kind = tool_input.get("kind")
        if not name:
            return json.dumps({"elements": []})

        elements = []
        name_lower = name.lower()

        # Search draft
        if _draft_lookup:
            for qname, info in _draft_lookup.items():
                if name_lower in qname.lower() or name_lower in info.get("description", "").lower():
                    if kind and info.get("kind") != kind:
                        continue
                    elements.append(info.copy())

        # Search Neo4j (excluding verification stubs)
        if neo4j_session is not None:
            from backend.db.neo4j.repositories.design import DesignRepository
            repo = DesignRepository(neo4j_session)
            nodes = repo.find_nodes(
                search=name,
                kind=kind if kind in ("class", "interface", "enum") else None,
                exclude_source_types=["verification"],
            )
            for node in nodes[:20]:
                # Skip if already found in draft (draft takes priority)
                if node.qualified_name in _draft_lookup:
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

    # -- find_mechanism -------------------------------------------------------

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

    # -- commit_design_and_verifications --------------------------------------

    def _dispatch_commit(tool_input: dict, draft, draft_lookup) -> str:
        try:
            schema = DesignAndVerificationSchema.model_validate(tool_input)
        except Exception as e:
            return json.dumps({"committed": False, "errors": [f"Invalid input format: {e}"]})

        errors = []

        # 1. Design validation
        design_errors = _validate_oo_design(
            schema.oo_design,
            prior_class_lookup=prior_class_lookup,
            dependency_lookup=dep_lookup,
            intercomponent_classes=intercomponent_classes or [],
        )
        errors.extend(design_errors)

        # 2. Qname validation across all verifications
        all_qnames = set()
        for llr_id, verifs in schema.verifications.items():
            for v in verifs:
                for cond in v.preconditions + v.postconditions:
                    if cond.subject_qualified_name:
                        all_qnames.add(cond.subject_qualified_name)
                    if cond.object_qualified_name:
                        # object_qualified_name must be a valid qname or empty
                        is_valid, _ = _is_valid_verification_qname(cond.object_qualified_name)
                        if not is_valid:
                            errors.append(
                                f"LLR {llr_id}: Invalid object_qualified_name "
                                f"in condition: '{cond.object_qualified_name}'. "
                                f"Use expected_value for literal values."
                            )
                for action in v.actions:
                    if action.caller_qualified_name:
                        all_qnames.add(action.caller_qualified_name)
                    if action.callee_qualified_name:
                        all_qnames.add(action.callee_qualified_name)

        # 3. Existence check for all referenced qnames
        # Build lookup from the committed design (use schema.oo_design, not draft)
        commit_lookup = _build_draft_lookup(schema.oo_design)
        for qn in all_qnames:
            if qn in commit_lookup:
                continue
            # Check prior designs
            if qn in prior_class_lookup.values():
                continue
            if qn in prior_class_lookup:
                continue
            if qn in dep_lookup:
                continue
            if qn in dep_lookup.values():
                continue
            if intercomponent_classes:
                ic_qnames = {c["qualified_name"] for c in intercomponent_classes}
                if qn in ic_qnames:
                    continue
            # Check Neo4j
            if neo4j_session is not None:
                from backend.db.neo4j.repositories.design import DesignRepository
                repo = DesignRepository(neo4j_session)
                nodes = repo.find_nodes(search=qn, exclude_source_types=["verification"])
                if any(n.qualified_name == qn for n in nodes):
                    continue
            errors.append(f"Unresolved reference: '{qn}' does not exist in the design context or prior designs.")

        if errors:
            return json.dumps({"committed": False, "errors": errors})

        return json.dumps({
            "committed": True,
            "oo_design": schema.oo_design.model_dump(),
            "verifications": {
                str(k): [v.model_dump() for v in vs] for k, vs in schema.verifications.items()
            },
        })

    return dispatch