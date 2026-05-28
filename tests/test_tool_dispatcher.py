"""Tests for ToolDispatcher base class."""

import json


def test_register_and_dispatch():
    """Register a handler and dispatch to it."""
    from backend.ticketing_agent.tools import ToolDispatcher

    dispatcher = ToolDispatcher()

    def my_handler(tool_input: dict) -> str:
        return json.dumps({"result": tool_input["value"] * 2})

    dispatcher.register("my_tool", {"name": "my_tool"}, my_handler)

    result = dispatcher.dispatch("my_tool", {"value": 5})
    assert json.loads(result) == {"result": 10}


def test_dispatch_unknown_tool():
    """Dispatching an unknown tool returns an error JSON."""
    from backend.ticketing_agent.tools import ToolDispatcher

    dispatcher = ToolDispatcher()

    result = dispatcher.dispatch("nonexistent", {})
    parsed = json.loads(result)
    assert parsed["error"] == "Unknown tool: nonexistent"


def test_all_tool_schemas():
    """all_tool_schemas returns schemas in registration order."""
    from backend.ticketing_agent.tools import ToolDispatcher

    dispatcher = ToolDispatcher()

    schema_a = {"name": "tool_a", "description": "A"}
    schema_b = {"name": "tool_b", "description": "B"}
    dispatcher.register("tool_a", schema_a, lambda inp: "")
    dispatcher.register("tool_b", schema_b, lambda inp: "")

    schemas = dispatcher.all_tool_schemas
    assert schemas == [schema_a, schema_b]


def test_duplicate_registration_raises():
    """Registering the same tool name twice raises ValueError."""
    from backend.ticketing_agent.tools import ToolDispatcher

    dispatcher = ToolDispatcher()
    dispatcher.register("tool_a", {}, lambda inp: "")

    try:
        dispatcher.register("tool_a", {}, lambda inp: "")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Duplicate tool handler: tool_a" in str(e)
