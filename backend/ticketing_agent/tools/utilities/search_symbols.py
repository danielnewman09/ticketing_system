"""search_symbols tool: full-text search across indexed symbol names."""

from backend.ticketing_agent.tools.helpers.discovery import discover_tool_dispatch

SCHEMA = {
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


def handle(ctx, tool_input: dict) -> str:
    """Delegate to the discovery toolset."""
    return discover_tool_dispatch("search_symbols", tool_input, ctx.toolset)
