"""Tool dispatcher infrastructure for agent tool loops."""

import json
from collections.abc import Callable


class ToolDispatcher:
    """Base class for tool dispatchers.

    Registers handler functions by tool name alongside their JSON schemas
    and dispatches calls to the appropriate handler.

    Usage::

        class MyDispatcher(ToolDispatcher):
            def __init__(self, ...):
                super().__init__()
                self.register("my_tool", MY_TOOL_SCHEMA, self._handle_my_tool)

        d = MyDispatcher(...)
        result = d.dispatch("my_tool", {"arg": "value"})
        schemas = d.all_tool_schemas  # for LLM tools parameter
    """

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[dict], str]] = {}
        self._schemas: dict[str, dict] = {}

    def register(self, name: str, schema: dict, handler: Callable[[dict], str]) -> None:
        """Register a handler and its JSON schema for a tool name."""
        if name in self._handlers:
            raise ValueError(f"Duplicate tool handler: {name}")
        self._handlers[name] = handler
        self._schemas[name] = schema

    def dispatch(self, tool_name: str, tool_input: dict) -> str:
        """Dispatch a tool call to the registered handler."""
        handler = self._handlers.get(tool_name)
        if handler is None:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
        return handler(tool_input)

    @property
    def all_tool_schemas(self) -> list[dict]:
        """Return all registered tool schemas (for LLM tools parameter)."""
        return list(self._schemas.values())
