"""Requirements-retrieval tools — fetch HLR/LLR hierarchies and
verification details from Neo4j via the codegraph API.

Each tool has a ``SCHEMA`` dict and a ``handle_*(ctx, tool_input)``
function registered by ``register_all(dispatcher)`` on a
:class:`RequirementsDispatcher`.

Uses neomodel ORM for HLR/LLR/VerificationMethod/Condition/Action
queries and the dispatcher's ``session()`` context manager for raw
Cypher when needed.

Tool overview
~~~~~~~~~~~~~

- **get_requirement_hierarchy** — fetch a full HLR → LLR → Verification
  tree by HLR refid.  Returns a nested JSON structure with all LLRs,
  verification methods, conditions (pre/post), and actions.

- **get_llr_details** — fetch a single LLR with its verification methods,
  conditions, and actions by LLR refid.

- **search_requirements** — search HLRs/LLRs by keyword in their
  ``description`` field.  Returns matching requirement summaries.

- **list_requirements** — list all HLRs (optionally filtered by
  component), returning summary dicts suitable for agent context.

- **get_requirement_traces** — for a given HLR or LLR refid, return
  all COMPOSES edges pointing to design-graph nodes (classes, methods,
  namespaces).  Useful for understanding which code implements a
  requirement.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend_migrated.tools.dispatcher import RequirementsDispatcher  # noqa: F811

log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# Internal helpers
# ══════════════════════════════════════════════════════════════════════════

def _get_expected_value_from_edge(cond) -> str:
    """Traverse the RIGHT_OPERAND edge to get the expected value.

    The ``expected_value`` string property has been removed from
    Condition nodes.  Instead, the right-hand side of the assertion is
    a ``RIGHT_OPERAND`` edge pointing to either a ``LiteralNode``
    (for primitive values) or a scaffold node (for enum values /
    notional references).

    For ``LiteralNode`` targets, returns the ``value`` property.
    For other targets (AttributeNode, ClassNode), returns the
    ``qualified_name``.
    """
    targets = cond.right_operand.all()
    if not targets:
        return ""
    target = targets[0]
    # LiteralNode has a 'value' property
    val = getattr(target, "value", None)
    if val is not None:
        return val
    # Fall back to qualified_name for scaffold nodes
    return getattr(target, "qualified_name", "")


def _serialize_hlr_brief(hlr) -> dict:
    """Serialize an HLR neomodel node to a brief dict (no children)."""
    return {
        "refid": hlr.refid,
        "name": hlr.name or "",
        "description": hlr.description,
        "layer": hlr.layer,
        "tags": list(hlr.tags) if hlr.tags else [],
    }


def _serialize_llr_brief(llr) -> dict:
    """Serialize an LLR neomodel node to a brief dict (no children)."""
    return {
        "refid": llr.refid,
        "name": llr.name or "",
        "description": llr.description,
        "layer": llr.layer,
        "tags": list(llr.tags) if llr.tags else [],
    }


def _serialize_verification(vm) -> dict:
    """Serialize a VerificationMethod neomodel node with its conditions and actions."""
    result = {
        "refid": vm.refid,
        "name": vm.name or "",
        "method": vm.method,
        "test_name": vm.test_name or "",
        "description": vm.description or "",
        "layer": vm.layer,
    }

    # Collect conditions grouped by phase
    conditions = vm.conditions.all()
    pre_conditions = []
    post_conditions = []
    for cond in sorted(conditions, key=lambda c: c.order):
        # Traverse LEFT_OPERAND / RIGHT_OPERAND edges to get the target
        # qualified names — the string properties have been removed in
        # favor of typed edges to scaffold/design nodes.
        left_targets = cond.left_operand.all()
        right_targets = cond.right_operand.all()
        cond_dict = {
            "refid": cond.refid,
            "name": cond.name or "",
            "phase": cond.phase,
            "order": cond.order,
            "operator": cond.operator,
            # expected_value is now a transient attr — traverse the
            # RIGHT_OPERAND edge to get the value from the target node.
            # LiteralNodes carry .value; scaffold nodes use .qualified_name.
            "expected_value": _get_expected_value_from_edge(cond),
            "subject_qualified_name": left_targets[0].qualified_name if left_targets else "",
            "object_qualified_name": right_targets[0].qualified_name if right_targets else "",
            "description": cond.description or "",
        }
        if cond.phase == "pre":
            pre_conditions.append(cond_dict)
        else:
            post_conditions.append(cond_dict)

    result["preconditions"] = pre_conditions
    result["postconditions"] = post_conditions

    # Collect actions sorted by order
    actions = vm.actions.all()
    result["actions"] = [
        {
            "refid": action.refid,
            "name": action.name or "",
            "order": action.order,
            "description": action.description or "",
            # Traverse CALLEE / CALLER edges to get the target
            # qualified names — the string properties have been removed.
            "caller_qualified_name": action.caller.all()[0].qualified_name if action.caller.all() else "",
            "callee_qualified_name": action.callee.all()[0].qualified_name if action.callee.all() else "",
        }
        for action in sorted(actions, key=lambda a: a.order)
    ]

    return result


def _serialize_llr_with_verifications(llr) -> dict:
    """Serialize an LLR with its verification methods (full depth)."""
    result = _serialize_llr_brief(llr)
    verification_methods = llr.verification_methods.all()
    result["verification_methods"] = [
        _serialize_verification(vm) for vm in verification_methods
    ]
    return result


def _serialize_hlr_with_hierarchy(hlr) -> dict:
    """Serialize an HLR with its full LLR → Verification hierarchy."""
    result = _serialize_hlr_brief(hlr)

    # Component membership
    comp_nodes = hlr.component.all()
    if comp_nodes:
        comp = comp_nodes[0]
        result["component"] = {
            "name": comp.name or "",
            "namespace": getattr(comp, "namespace", "") or "",
            "description": getattr(comp, "description", "") or "",
        }
    else:
        result["component"] = None

    # LLRs with verifications
    llr_nodes = hlr.llrs.all()
    result["llrs"] = [
        _serialize_llr_with_verifications(llr) for llr in llr_nodes
    ]

    return result


def _serialize_design_links(node) -> list[dict]:
    """Collect all COMPOSES edges from a requirement node to design nodes.

    Walks the ``design_compounds`` manager and returns a flat list of
    link dicts showing which design-graph nodes this requirement composes.
    """
    links = []
    for target in node.design_compounds.all():
        links.append({
            "target_qualified_name": target.qualified_name,
            "target_name": target.name or "",
            "target_kind": getattr(target, "kind", type(target).__name__),
            "target_type": type(target).__name__,
        })
    return links


# ══════════════════════════════════════════════════════════════════════════
# Tool schemas
# ══════════════════════════════════════════════════════════════════════════

GET_REQUIREMENT_HIERARCHY_SCHEMA = {
    "name": "get_requirement_hierarchy",
    "description": (
        "Retrieve the full hierarchy of a high-level requirement (HLR) "
        "by its refid. Returns the HLR, its component, all child LLRs, "
        "and each LLR's verification methods with preconditions, actions, "
        "and postconditions. Use this to deeply inspect a requirement and "
        "its complete verification plan."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "refid": {
                "type": "string",
                "description": (
                    "The refid (hex UUID) of the HLR to retrieve. "
                    "Use list_requirements or search_requirements to find "
                    "refids if you don't know them."
                ),
            },
        },
        "required": ["refid"],
    },
}


GET_LLR_DETAILS_SCHEMA = {
    "name": "get_llr_details",
    "description": (
        "Retrieve a single low-level requirement (LLR) with its verification "
        "methods, conditions, and actions by LLR refid. Use this when you "
        "need to inspect one specific LLR in detail without loading the "
        "entire HLR hierarchy."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "refid": {
                "type": "string",
                "description": "The refid (hex UUID) of the LLR to retrieve.",
            },
        },
        "required": ["refid"],
    },
}


SEARCH_REQUIREMENTS_SCHEMA = {
    "name": "search_requirements",
    "description": (
        "Search HLRs and LLRs by a keyword or phrase in their description "
        "field. Returns matching requirement summaries (refid, description, "
        "layer, tags). Useful for discovering requirements by concept or "
        "feature area."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Search text — matched case-insensitively against "
                    "requirement descriptions."
                ),
            },
            "scope": {
                "type": "string",
                "enum": ["hlr", "llr", "both"],
                "default": "both",
                "description": (
                    "Which requirement types to search: 'hlr' for "
                    "high-level only, 'llr' for low-level only, "
                    "'both' for all."
                ),
            },
            "limit": {
                "type": "integer",
                "default": 20,
                "description": "Maximum number of results to return.",
            },
        },
        "required": ["query"],
    },
}


LIST_REQUIREMENTS_SCHEMA = {
    "name": "list_requirements",
    "description": (
        "List all high-level requirements (HLRs), optionally filtered by "
        "component. Returns summary dicts with refid, name, description, "
        "layer, tags, and component info. Use this as a starting point to "
        "discover what HLRs exist before drilling into a specific one with "
        "get_requirement_hierarchy."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "component_name": {
                "type": "string",
                "description": (
                    "Optional component name to filter by. Only HLRs "
                    "belonging to this component are returned."
                ),
            },
            "layer": {
                "type": "string",
                "enum": ["design", "as-built"],
                "description": (
                    "Optional layer filter: 'design' or 'as-built'. "
                    "If omitted, returns HLRs from all layers."
                ),
            },
        },
        "required": [],
    },
}


GET_REQUIREMENT_TRACES_SCHEMA = {
    "name": "get_requirement_traces",
    "description": (
        "Retrieve all COMPOSES edges from an HLR or LLR to design-graph "
        "nodes (classes, interfaces, enums). Shows which design elements "
        "this requirement composes — i.e., which classes implement or "
        "satisfy the requirement. Returns the requirement's refid and "
        "a list of composed design nodes with their qualified names and kinds."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "refid": {
                "type": "string",
                "description": (
                    "The refid (hex UUID) of the HLR or LLR whose "
                    "traceability links to retrieve."
                ),
            },
        },
        "required": ["refid"],
    },
}


# ══════════════════════════════════════════════════════════════════════════
# Handlers
# ══════════════════════════════════════════════════════════════════════════

def handle_get_requirement_hierarchy(
    ctx: RequirementsDispatcher, tool_input: dict,
) -> str:
    """Fetch the full HLR → LLR → Verification hierarchy by refid."""
    from backend_migrated.models.requirement import HLR

    refid = tool_input.get("refid", "")
    if not refid:
        return json.dumps({"error": "refid is required"})

    hlr = HLR.nodes.get_or_none(refid=refid)
    if hlr is None:
        return json.dumps({"error": f"HLR with refid '{refid}' not found"})

    try:
        result = _serialize_hlr_with_hierarchy(hlr)
        return json.dumps(result, indent=2)
    except Exception as exc:
        log.exception("Failed to serialize HLR hierarchy for %s", refid)
        return json.dumps({"error": f"Serialization error: {exc}"})


def handle_get_llr_details(
    ctx: RequirementsDispatcher, tool_input: dict,
) -> str:
    """Fetch a single LLR with its verification methods by refid."""
    from backend_migrated.models.requirement import LLR

    refid = tool_input.get("refid", "")
    if not refid:
        return json.dumps({"error": "refid is required"})

    llr = LLR.nodes.get_or_none(refid=refid)
    if llr is None:
        return json.dumps({"error": f"LLR with refid '{refid}' not found"})

    try:
        result = _serialize_llr_with_verifications(llr)

        # Also include the parent HLR refid
        parent_hlrs = llr.hlr.all()
        if parent_hlrs:
            result["hlr_refid"] = parent_hlrs[0].refid

        return json.dumps(result, indent=2)
    except Exception as exc:
        log.exception("Failed to serialize LLR details for %s", refid)
        return json.dumps({"error": f"Serialization error: {exc}"})


def handle_search_requirements(
    ctx: RequirementsDispatcher, tool_input: dict,
) -> str:
    """Search HLRs and/or LLRs by description keyword."""
    from backend_migrated.models.requirement import HLR, LLR

    query = tool_input.get("query", "")
    scope = tool_input.get("scope", "both")
    limit = int(tool_input.get("limit", 20))

    if not query:
        return json.dumps({"error": "query is required", "results": []})

    query_lower = query.lower()
    results: list[dict] = []

    try:
        if scope in ("hlr", "both"):
            for hlr in HLR.nodes.all():
                if query_lower in (hlr.description or "").lower():
                    results.append({
                        "type": "HLR",
                        **_serialize_hlr_brief(hlr),
                    })
                    if len(results) >= limit:
                        break

        if scope in ("llr", "both") and len(results) < limit:
            for llr in LLR.nodes.all():
                if query_lower in (llr.description or "").lower():
                    results.append({
                        "type": "LLR",
                        **_serialize_llr_brief(llr),
                    })
                    if len(results) >= limit:
                        break

    except Exception as exc:
        log.exception("Failed to search requirements for query '%s'", query)
        return json.dumps({"error": f"Search error: {exc}", "results": []})

    return json.dumps({
        "query": query,
        "scope": scope,
        "count": len(results),
        "results": results,
    })


def handle_list_requirements(
    ctx: RequirementsDispatcher, tool_input: dict,
) -> str:
    """List all HLRs, optionally filtered by component and layer."""
    from backend_migrated.models.requirement import HLR

    component_name = tool_input.get("component_name")
    layer = tool_input.get("layer")

    results: list[dict] = []

    try:
        # Use Cypher for efficient filtering when component_name is given
        if component_name:
            with ctx.session() as session:
                cypher = (
                    "MATCH (c:Component)-[:COMPOSES]->(h:HLR) "
                    "WHERE c.name = $component_name "
                )
                params: dict = {"component_name": component_name}

                if layer:
                    cypher += "AND h.layer = $layer "
                    params["layer"] = layer

                cypher += "RETURN h.refid AS refid"

                for record in session.run(cypher, params):
                    refid = record["refid"]
                    if refid:
                        hlr = HLR.nodes.get_or_none(refid=refid)
                        if hlr:
                            results.append(_serialize_hlr_brief(hlr))
        else:
            # No component filter — load all HLRs via neomodel
            all_hlrs = HLR.nodes.all()
            if layer:
                all_hlrs = [h for h in all_hlrs if h.layer == layer]
            results = [_serialize_hlr_brief(h) for h in all_hlrs]

    except Exception as exc:
        log.exception("Failed to list requirements")
        return json.dumps({"error": f"List error: {exc}", "results": []})

    return json.dumps({
        "count": len(results),
        "hlrs": results,
    })


def handle_get_requirement_traces(
    ctx: RequirementsDispatcher, tool_input: dict,
) -> str:
    """Retrieve all COMPOSES edges from an HLR or LLR to design nodes."""
    from backend_migrated.models.requirement import HLR, LLR

    refid = tool_input.get("refid", "")
    if not refid:
        return json.dumps({"error": "refid is required"})

    # Try HLR first, then LLR
    node = HLR.nodes.get_or_none(refid=refid)
    req_type = "HLR"

    if node is None:
        node = LLR.nodes.get_or_none(refid=refid)
        req_type = "LLR"

    if node is None:
        return json.dumps({
            "error": f"No HLR or LLR found with refid '{refid}'",
        })

    try:
        design_links = _serialize_design_links(node)
        return json.dumps({
            "refid": refid,
            "type": req_type,
            "description": node.description,
            "design_links": design_links,
        }, indent=2)
    except Exception as exc:
        log.exception("Failed to serialize design links for refid '%s'", refid)
        return json.dumps({"error": f"Serialization error: {exc}"})


# ══════════════════════════════════════════════════════════════════════════
# Registration
# ══════════════════════════════════════════════════════════════════════════

def register_all(dispatcher: RequirementsDispatcher) -> None:
    """Register all requirements tools on a :class:`RequirementsDispatcher`."""
    disp = dispatcher
    disp.register(
        "get_requirement_hierarchy", GET_REQUIREMENT_HIERARCHY_SCHEMA,
        lambda inp: handle_get_requirement_hierarchy(disp, inp),
    )
    disp.register(
        "get_llr_details", GET_LLR_DETAILS_SCHEMA,
        lambda inp: handle_get_llr_details(disp, inp),
    )
    disp.register(
        "search_requirements", SEARCH_REQUIREMENTS_SCHEMA,
        lambda inp: handle_search_requirements(disp, inp),
    )
    disp.register(
        "list_requirements", LIST_REQUIREMENTS_SCHEMA,
        lambda inp: handle_list_requirements(disp, inp),
    )
    disp.register(
        "get_requirement_traces", GET_REQUIREMENT_TRACES_SCHEMA,
        lambda inp: handle_get_requirement_traces(disp, inp),
    )