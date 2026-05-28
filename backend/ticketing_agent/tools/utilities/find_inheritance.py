"""find_inheritance tool: explore class inheritance hierarchies."""

from backend.ticketing_agent.tools.helpers.discovery import discover_tool_dispatch

SCHEMA = {
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


def handle(ctx, tool_input: dict) -> str:
    """Delegate to the discovery toolset."""
    return discover_tool_dispatch("find_inheritance", tool_input, ctx.toolset)
