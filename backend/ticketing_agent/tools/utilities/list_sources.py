"""list_sources tool: list indexed dependency sources."""

from backend.ticketing_agent.tools.helpers.discovery import discover_tool_dispatch

SCHEMA = {
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


def handle(ctx, tool_input: dict) -> str:
    """Delegate to the discovery toolset."""
    return discover_tool_dispatch("list_sources", tool_input, ctx.toolset)
