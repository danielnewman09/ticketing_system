"""Discovery tool dispatch helpers.

Routes discovery tool calls (list_sources, search_symbols, etc.)
to a DependencyGraphTools instance (doxygen_index).
"""

import json
import logging

log = logging.getLogger("agents.tools.discovery")

# Maps our tool names -> DependencyGraphTools method names
DISCOVERY_METHOD_MAP = {
    "list_sources": "list_sources",
    "search_symbols": "search_symbols",
    "get_compound": "get_compound",
    "browse_namespace": "browse_namespace",
    "find_inheritance": "find_inheritance",
}

# Tools whose results should be slimmed down
_SLIM_FN = {}


def slim_compound(records: list[dict]) -> list[dict]:
    """Strip heavyweight fields from get_compound results."""
    drop = {"detailed", "member_refid", "member_brief"}
    return [{k: v for k, v in r.items() if k not in drop} for r in records]


_SLIM_FN["get_compound"] = slim_compound


def discover_tool_dispatch(
    tool_name: str,
    tool_input: dict,
    toolset,
) -> str:
    """Dispatch a discovery tool call to the DependencyGraphTools instance.

    Args:
        tool_name: One of the discovery tool names (list_sources, etc.).
        tool_input: Dict of tool arguments.
        toolset: A DependencyGraphTools instance, or None if unavailable.

    Returns:
        JSON string result.
    """
    if toolset is None:
        return json.dumps({
            "error": (
                "Codebase index not available. Proceed with your design "
                "using general knowledge and note the gap."
            ),
        })
    method_name = DISCOVERY_METHOD_MAP.get(tool_name)
    method = getattr(toolset, method_name, None) if toolset else None
    if not method:
        return json.dumps({"error": f"Discovery tool {tool_name} not available"})
    try:
        result = method(**tool_input)
        slim = _SLIM_FN.get(tool_name)
        if slim:
            result = slim(result)
        return json.dumps(result, default=str)
    except Exception as e:
        log.warning("Discovery tool %s failed: %s", tool_name, e)
        return json.dumps({"error": str(e)})
