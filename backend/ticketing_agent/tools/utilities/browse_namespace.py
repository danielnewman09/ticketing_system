"""browse_namespace tool: list classes and symbols within a namespace."""

from backend.ticketing_agent.tools.helpers.discovery import discover_tool_dispatch

SCHEMA = {
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


def handle(ctx, tool_input: dict) -> str:
    """Delegate to the discovery toolset."""
    return discover_tool_dispatch("browse_namespace", tool_input, ctx.toolset)
