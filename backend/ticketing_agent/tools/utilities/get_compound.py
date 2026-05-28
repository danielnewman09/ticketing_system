"""get_compound tool: get full details of a class, struct, or enum."""

from backend.ticketing_agent.tools.helpers.discovery import discover_tool_dispatch

SCHEMA = {
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


def handle(ctx, tool_input: dict) -> str:
    """Delegate to the discovery toolset."""
    return discover_tool_dispatch("get_compound", tool_input, ctx.toolset)
