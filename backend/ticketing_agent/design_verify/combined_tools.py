"""Tool definitions and dispatcher for the combined design+verify tool loop.

Provides six tools:
- draft_design: submit/revise the OO design draft (stores in dispatcher state)
- validate_design: validate the current draft for structural consistency
- check_class_name: look up class names in prior designs, dep APIs, and intercomponent context
- validate_qualified_names: validate qname format and existence against draft + Neo4j
- lookup_design_element: search for design elements in draft + Neo4j (excluding verification stubs)
- draft_verifications: submit/revise verification procedures with reference validation
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
# Discovery helpers
# ---------------------------------------------------------------------------


def _slim_compound(records: list[dict]) -> list[dict]:
    """Strip heavyweight fields from get_compound results."""
    drop = {"detailed", "member_refid", "member_brief"}
    return [{k: v for k, v in r.items() if k not in drop} for r in records]


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

DRAFT_VERIFICATIONS_TOOL = {
    "name": "draft_verifications",
    "description": (
        "Submit or revise verification procedures for LLRs. Validates all "
        "qualified name references against the current design draft and "
        "design context (prior classes, dependency APIs, intercomponent). "
        "Returns a validation report showing which references resolved and "
        "which didn't, with suggestions for corrections. Use this after "
        "drafting your design to iteratively resolve verification stub "
        "references before committing."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "verifications": {
                "type": "object",
                "description": (
                    "Map of LLR ID (integer string) to list of verification "
                    "procedures. Keys MUST be LLR IDs like \"1\", \"2\" \u2014 "
                    "NOT test names."
                ),
                "additionalProperties": {
                    "type": "array",
                    "items": VerificationSchema.model_json_schema(),
                },
            },
        },
        "required": ["verifications"],
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


SEARCH_SYMBOLS_TOOL = {
    "name": "search_symbols",
    "description": (
        "Full-text search across indexed symbol names and documentation. "
        "Use this to discover dependency or project classes relevant to "
        "the requirements when designing. Supports natural-language terms "
        "(e.g. 'window create', 'font rendering'). Returns matches with "
        "qualified_name, kind, source, and relevance score."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search terms (supports Lucene syntax — AND, OR, quotes).",
            },
            "source": {
                "type": "string",
                "description": "Optional dependency name to restrict results (e.g. 'fltk', 'boost').",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results.",
                "default": 20,
            },
        },
        "required": ["query"],
    },
}

GET_COMPOUND_TOOL = {
    "name": "get_compound",
    "description": (
        "Get full details of a class, struct, or enum and its members from "
        "the indexed codebase. Use this after search_symbols identifies a "
        "compound of interest. Returns the compound metadata plus all of "
        "its members with signatures. Essential for understanding the API "
        "of a class you plan to inherit from or reference."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Exact or qualified name (e.g. 'Fl_Window', 'boost::gregorian::date').",
            },
            "source": {
                "type": "string",
                "description": "Optional dependency name filter.",
            },
        },
        "required": ["name"],
    },
}

BROWSE_NAMESPACE_TOOL = {
    "name": "browse_namespace",
    "description": (
        "List classes, free functions, and other symbols within a namespace "
        "in the indexed codebase. Returns both nested compounds and "
        "namespace-level members. Use this to explore a dependency's top-level "
        "types when you don't know exact class names."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Namespace name (e.g. 'Fl', 'boost::asio').",
            },
            "source": {
                "type": "string",
                "description": "Optional dependency name filter.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum results.",
                "default": 50,
            },
        },
        "required": ["name"],
    },
}

FIND_INHERITANCE_TOOL = {
    "name": "find_inheritance",
    "description": (
        "Explore the inheritance hierarchy of a class in the indexed codebase. "
        "Use this to understand parent classes and derived classes — if a class "
        "is relevant, its base classes may also be. Essential for determining "
        "the correct inherits_from list in your design."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Exact or qualified class name.",
            },
            "direction": {
                "type": "string",
                "enum": ["up", "down", "both"],
                "description": 'Direction: "up" (base classes), "down" (derived), or "both".',
                "default": "both",
            },
            "max_depth": {
                "type": "integer",
                "description": "Maximum inheritance depth to traverse.",
                "default": 5,
            },
        },
        "required": ["name"],
    },
}

LIST_SOURCES_TOOL = {
    "name": "list_sources",
    "description": (
        "List all indexed dependency sources and their symbol counts. "
        "Call this first to see which dependencies are available before "
        "searching for specific classes."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

ALL_TOOLS = [
    LIST_SOURCES_TOOL,
    SEARCH_SYMBOLS_TOOL,
    GET_COMPOUND_TOOL,
    BROWSE_NAMESPACE_TOOL,
    FIND_INHERITANCE_TOOL,
    DRAFT_DESIGN_TOOL,
    VALIDATE_DESIGN_TOOL,
    CHECK_CLASS_NAME_TOOL,
    FIND_MECHANISM_TOOL,
    VALIDATE_QNAMES_TOOL,
    LOOKUP_DESIGN_ELEMENT_TOOL,
    DRAFT_VERIFICATIONS_TOOL,
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
# Shared qname resolution helpers
# ---------------------------------------------------------------------------


def _qname_resolves(
    qname: str,
    draft_lookup: dict[str, dict] | None = None,
    prior_class_lookup: dict[str, str] | None = None,
    dep_lookup: dict[str, str] | None = None,
    intercomponent_classes: list[dict] | None = None,
    neo4j_session=None,
) -> bool:
    """Check whether a qualified name exists in the design context.

    Checks draft lookup, prior class lookup, dependency lookup,
    intercomponent classes, and (optionally) Neo4j persistent store.
    """
    if draft_lookup and qname in draft_lookup:
        return True
    if prior_class_lookup:
        if qname in prior_class_lookup.values():
            return True
        if qname in prior_class_lookup:
            return True
    if dep_lookup:
        if qname in dep_lookup:
            return True
        if qname in dep_lookup.values():
            return True
    if intercomponent_classes:
        ic_qnames = {c["qualified_name"] for c in intercomponent_classes}
        if qname in ic_qnames:
            return True
    if neo4j_session is not None:
        from backend.db.neo4j.repositories.design import DesignRepository
        repo = DesignRepository(neo4j_session)
        nodes = repo.find_nodes(search=qname, exclude_source_types=["verification"])
        if any(n.qualified_name == qname for n in nodes):
            return True
    return False


def _suggest_qname(
    unresolved: str,
    draft_lookup: dict[str, dict],
    prior_class_lookup: dict[str, str],
    dep_lookup: dict[str, str],
    intercomponent_classes: list[dict],
) -> str | None:
    """Find the closest matching qualified name for an unresolved reference.

    Searches by bare name, member name, and substring matching.
    Strips common stub suffixes (.output, .result, .return_value).

    Does NOT query Neo4j — only in-memory lookups for speed.
    """
    # Strip common stub suffixes
    cleaned = unresolved
    for suffix in (".output", ".result", ".return_value"):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)]

    # Strategy 1: bare name match in prior/dep lookups
    bare = cleaned.rsplit("::", 1)[-1].rsplit(".", 1)[-1]
    for name, qname in {**prior_class_lookup, **dep_lookup}.items():
        if name == bare or name.lower() == bare.lower():
            return qname

    # Strategy 2: member name match in draft
    for qname, info in draft_lookup.items():
        kind = info.get("kind", "")
        if kind in ("method", "attribute") and qname.endswith(f"::{bare}"):
            return qname

    # Strategy 3: class/interface/enum name match in draft
    for qname, info in draft_lookup.items():
        kind = info.get("kind", "")
        if kind in ("class", "interface", "enum"):
            # Match the class name (last segment after ::)
            class_name = qname.rsplit("::", 1)[-1]
            if class_name == bare or class_name.lower() == bare.lower():
                return qname

    # Strategy 4: substring match in draft and dep lookups
    cleaned_lower = cleaned.lower()
    for qname in draft_lookup:
        if cleaned_lower in qname.lower():
            return qname
    for qname in dep_lookup.values():
        if cleaned_lower in qname.lower():
            return qname

    return None


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def make_combined_dispatcher(
    prior_class_lookup: dict[str, str],
    dependency_lookup: dict[str, str] | None,
    intercomponent_classes: list[dict] | None,
    neo4j_session=None,
    toolset=None,
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
    _draft_verifications: dict[int, list[VerificationSchema]] = {}

    def dispatch(tool_name: str, tool_input: dict) -> str:
        nonlocal _draft_design, _draft_lookup

        if tool_name == "list_sources":
            return _dispatch_discovery("list_sources", tool_input)
        elif tool_name == "search_symbols":
            return _dispatch_discovery("search_symbols", tool_input)
        elif tool_name == "get_compound":
            return _dispatch_discovery("get_compound", tool_input)
        elif tool_name == "browse_namespace":
            return _dispatch_discovery("browse_namespace", tool_input)
        elif tool_name == "find_inheritance":
            return _dispatch_discovery("find_inheritance", tool_input)
        elif tool_name == "draft_design":
            return _dispatch_draft_design(tool_input)
        elif tool_name == "validate_design":
            return _dispatch_validate_design(tool_input)
        elif tool_name == "check_class_name":
            return _dispatch_check_class_name(tool_input)
        elif tool_name == "validate_qualified_names":
            return _dispatch_validate_qnames(tool_input)
        elif tool_name == "lookup_design_element":
            return _dispatch_lookup_design_element(tool_input)
        elif tool_name == "draft_verifications":
            return _dispatch_draft_verifications(tool_input)
        elif tool_name == "find_mechanism":
            return _dispatch_find_mechanism(tool_input)
        elif tool_name == "commit_design_and_verifications":
            return _dispatch_commit(tool_input, _draft_design, _draft_lookup)
        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

    # -- discovery tools (routed to doxygen_index toolset) --------------------

    _DISCOVERY_METHOD_MAP = {
        "list_sources": "list_sources",
        "search_symbols": "search_symbols",
        "get_compound": "get_compound",
        "browse_namespace": "browse_namespace",
        "find_inheritance": "find_inheritance",
    }

    _DISCOVERY_SLIM = {
        "get_compound": _slim_compound,
    }

    def _dispatch_discovery(tool_name: str, tool_input: dict) -> str:
        if toolset is None:
            return json.dumps({
                "error": "Codebase index not available. Proceed with your design using general knowledge and note the gap.",
            })
        method_name = _DISCOVERY_METHOD_MAP.get(tool_name)
        method = getattr(toolset, method_name, None) if toolset else None
        if not method:
            return json.dumps({"error": f"Discovery tool {tool_name} not available"})
        try:
            result = method(**tool_input)
            slim = _DISCOVERY_SLIM.get(tool_name)
            if slim:
                result = slim(result)
            return json.dumps(result, default=str)
        except Exception as e:
            log.warning("Discovery tool %s failed: %s", tool_name, e)
            return json.dumps({"error": str(e)})

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

        # Check for enum name collisions across components
        warnings = []
        for enum in design.enums:
            enum_qname = f"{enum.module}::{enum.name}" if enum.module else enum.name
            if enum.name in prior_class_lookup:
                existing_qname = prior_class_lookup[enum.name]
                if existing_qname != enum_qname:
                    warnings.append(
                        f"Enum '{enum.name}' already exists as '{existing_qname}' in a prior design. "
                        f"Consider referencing the existing enum or renaming yours to avoid confusion."
                    )

        # Store draft
        _draft_design = design
        _draft_lookup = _build_draft_lookup(design)

        return json.dumps({
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
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

        # Check for enum name collisions across components
        warnings = []
        for enum in design.enums:
            enum_qname = f"{enum.module}::{enum.name}" if enum.module else enum.name
            if enum.name in prior_class_lookup:
                existing_qname = prior_class_lookup[enum.name]
                if existing_qname != enum_qname:
                    warnings.append(
                        f"Enum '{enum.name}' already exists as '{existing_qname}' in a prior design. "
                        f"Consider referencing the existing enum or renaming yours to avoid confusion."
                    )

        return json.dumps({
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
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

    # -- draft_verifications ------------------------------------------------

    def _dispatch_draft_verifications(tool_input: dict) -> str:
        nonlocal _draft_verifications
        verifs_input = tool_input.get("verifications", {})
        if not verifs_input:
            return json.dumps({"valid": False, "errors": ["No verifications provided"]})

        parsed: dict[int, list[VerificationSchema]] = {}
        parse_errors = []
        for llr_id_str, v_list in verifs_input.items():
            try:
                llr_id = int(llr_id_str)
            except (ValueError, TypeError):
                parse_errors.append(f"Non-integer LLR ID key: '{llr_id_str}'")
                continue
            parsed[llr_id] = []
            for v in v_list:
                try:
                    parsed[llr_id].append(VerificationSchema.model_validate(v))
                except Exception as e:
                    parse_errors.append(f"LLR {llr_id_str}: invalid verification: {e}")

        if parse_errors:
            return json.dumps({"valid": False, "errors": parse_errors})

        # Validate all qname references
        warnings = []
        unresolved_details = []
        verification_summary = {}

        # Warn if no design draft exists
        if not _draft_design:
            warnings.append(
                "No design draft exists. Verification references cannot be "
                "validated against design elements. Call draft_design first."
            )

        for llr_id, verifs in parsed.items():
            llr_key = str(llr_id)
            resolved = 0
            total = 0
            for v in verifs:
                test_label = v.test_name or v.method
                for cond in v.preconditions + v.postconditions:
                    if cond.subject_qualified_name:
                        total += 1
                        if _qname_resolves(cond.subject_qualified_name, _draft_lookup, prior_class_lookup, dep_lookup, intercomponent_classes or [], neo4j_session):
                            resolved += 1
                        else:
                            suggestion = _suggest_qname(cond.subject_qualified_name, _draft_lookup, prior_class_lookup, dep_lookup, intercomponent_classes or [])
                            detail = {
                                "llr_id": llr_key,
                                "verification": test_label,
                                "field": "subject_qualified_name",
                                "value": cond.subject_qualified_name,
                            }
                            if suggestion:
                                detail["suggestion"] = suggestion
                            unresolved_details.append(detail)
                    if cond.object_qualified_name:
                        total += 1
                        if _qname_resolves(cond.object_qualified_name, _draft_lookup, prior_class_lookup, dep_lookup, intercomponent_classes or [], neo4j_session):
                            resolved += 1
                        else:
                            suggestion = _suggest_qname(cond.object_qualified_name, _draft_lookup, prior_class_lookup, dep_lookup, intercomponent_classes or [])
                            detail = {
                                "llr_id": llr_key,
                                "verification": test_label,
                                "field": "object_qualified_name",
                                "value": cond.object_qualified_name,
                            }
                            if suggestion:
                                detail["suggestion"] = suggestion
                            unresolved_details.append(detail)
                    # Warn about missing operator
                    if not cond.operator or cond.operator == "":
                        warnings.append(
                            f"LLR {llr_key} '{test_label}': condition on "
                            f"'{cond.subject_qualified_name}' has no operator \u2014 "
                            f"will default to '=='"
                        )
                    # Warn about expected_value that looks like a qname
                    if cond.expected_value and "::" in cond.expected_value:
                        warnings.append(
                            f"LLR {llr_key} '{test_label}': expected_value "
                            f"'{cond.expected_value}' contains '::' \u2014 if this "
                            f"references a design member, move it to "
                            f"object_qualified_name and use the display text "
                            f"as expected_value instead"
                        )
                for action in v.actions:
                    if action.callee_qualified_name:
                        total += 1
                        if _qname_resolves(action.callee_qualified_name, _draft_lookup, prior_class_lookup, dep_lookup, intercomponent_classes or [], neo4j_session):
                            resolved += 1
                        else:
                            suggestion = _suggest_qname(action.callee_qualified_name, _draft_lookup, prior_class_lookup, dep_lookup, intercomponent_classes or [])
                            detail = {
                                "llr_id": llr_key,
                                "verification": test_label,
                                "field": "callee_qualified_name",
                                "value": action.callee_qualified_name,
                            }
                            if suggestion:
                                detail["suggestion"] = suggestion
                            unresolved_details.append(detail)
                    # Warn about unqualified caller references
                    if action.caller_qualified_name and "::" not in action.caller_qualified_name:
                        warnings.append(
                            f"LLR {llr_key} '{test_label}': caller "
                            f"'{action.caller_qualified_name}' is not a "
                            f"qualified name \u2014 leave empty if the caller is "
                            f"the test harness"
                        )

            verification_summary[llr_key] = {
                "methods": len(verifs),
                "resolved_references": resolved,
                "unresolved_references": total - resolved,
            }

        # Store drafted verifications
        _draft_verifications = parsed

        errors = [
            f"Unresolved reference: '{d['value']}'"
            + (f" Did you mean '{d['suggestion']}'?" if "suggestion" in d else "")
            for d in unresolved_details
        ]

        return json.dumps({
            "valid": len(unresolved_details) == 0 and len(parse_errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "verification_summary": verification_summary,
            "unresolved_details": unresolved_details,
        })

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
            if _qname_resolves(qn, commit_lookup, prior_class_lookup, dep_lookup, intercomponent_classes or [], neo4j_session):
                continue
            suggestion = _suggest_qname(qn, commit_lookup, prior_class_lookup, dep_lookup, intercomponent_classes or [])
            error_msg = f"Unresolved reference: '{qn}' does not exist in the design context."
            if suggestion:
                error_msg += f" Did you mean '{suggestion}'?"
            errors.append(error_msg)

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