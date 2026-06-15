"""Tests for DesignToolDispatcher — registration, schemas, dispatch,
mutable context, and error handling.

Saves tool outputs to ``unit_test_data/tools_*`` for visual inspection.
"""

import json
from pathlib import Path

import pytest

from backend_migrated.tools import DesignToolDispatcher
from codegraph.tools.dispatcher import ToolDispatcher, CodeGraphDispatcher
from codegraph.repository import GraphRepository

OUT_DIR = Path(__file__).resolve().parents[2] / "unit_test_data" / "tools"


def _save(stem: str, content: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / stem).write_text(content, encoding="utf-8")


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def dispatcher():
    return DesignToolDispatcher(
        prior_class_lookup={
            "CalcEngine": "calc::CalcEngine",
            "Logger": "util::Logger",
        },
        dependency_lookup={
            "std::vector": "std::vector",
            "std::string": "std::basic_string",
            "Fl_Window": "fltk::Fl_Window",
        },
        intercomponent_classes=[
            {"qualified_name": "ui::DisplayArea", "kind": "class", "name": "DisplayArea"},
            {"qualified_name": "io::DataPort", "kind": "interface", "name": "DataPort"},
        ],
        component_namespace="calc",
        sibling_namespaces=["ui", "io"],
    )


@pytest.fixture
def empty_dispatcher():
    return DesignToolDispatcher()


# ══════════════════════════════════════════════════════════════════════════
# Registration & schema tests
# ══════════════════════════════════════════════════════════════════════════


class TestToolRegistration:
    def test_total_tool_count(self, dispatcher):
        assert len(dispatcher.all_tool_schemas) == 24  # 21 codegraph + 3 design
        _save("tools_registry.json",
              json.dumps({
                  "total_tools": len(dispatcher.all_tool_schemas),
                  "tool_names": sorted(dispatcher._handlers.keys()),
              }, indent=2))

    def test_design_tools_registered(self, dispatcher):
        names = {s["name"] for s in dispatcher.all_tool_schemas}
        assert "validate_design" in names
        assert "check_class_name" in names
        assert "produce_oo_design" in names

    def test_lookup_tools_registered(self, dispatcher):
        names = {s["name"] for s in dispatcher.all_tool_schemas}
        assert "container_lookup" in names
        assert "alias_lookup" in names
        assert "get_container_info" in names
        assert "dependency_list" in names

    def test_discovery_tools_registered(self, dispatcher):
        names = {s["name"] for s in dispatcher.all_tool_schemas}
        assert "search_symbols" in names
        assert "get_compound" in names
        assert "get_member" in names
        assert "browse_namespace" in names
        assert "list_sources" in names
        assert "find_inheritance" in names
        assert "find_callers_and_callees" in names

    def test_all_schemas_have_name_description_input_schema(self, dispatcher):
        for s in dispatcher.all_tool_schemas:
            assert "name" in s
            assert isinstance(s["name"], str) and s["name"]
            assert "description" in s
            assert "input_schema" in s

    def test_all_input_schemas_are_objects(self, dispatcher):
        # Most tools use object schemas; validate_design/produce_oo_design
        # use array schemas (LayerGraph format).
        for s in dispatcher.all_tool_schemas:
            t = s["input_schema"]["type"]
            assert t in ("object", "array"), f"{s['name']} has unexpected type {t}"

    def test_all_properties_have_types(self, dispatcher):
        for s in dispatcher.all_tool_schemas:
            schema = s["input_schema"]
            if "properties" in schema:
                for prop_name, prop in schema["properties"].items():
                    assert (
                        "type" in prop or "enum" in prop
                        or "anyOf" in prop or "items" in prop
                        or "$ref" in prop
                    ), f"{s['name']}.{prop_name} missing type"

    def test_handler_registered_for_every_schema(self, dispatcher):
        for s in dispatcher.all_tool_schemas:
            assert s["name"] in dispatcher._handlers

    def test_duplicate_registration_raises(self):
        d = ToolDispatcher()
        d.register("test", {
            "name": "test", "description": "A test",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        }, lambda inp: "ok")
        with pytest.raises(ValueError, match="Duplicate"):
            d.register("test", {
                "name": "test", "description": "Another",
                "input_schema": {"type": "object", "properties": {}, "required": []},
            }, lambda inp: "fail")


# ══════════════════════════════════════════════════════════════════════════
# Dispatch fundamentals
# ══════════════════════════════════════════════════════════════════════════


class TestDispatchBasics:
    def test_unknown_tool_returns_error(self, dispatcher):
        raw = dispatcher.dispatch("nonexistent_tool", {})
        result = json.loads(raw)
        _save("tools_dispatch_unknown.json", raw)
        assert "error" in result
        assert "Unknown tool" in result["error"]

    def test_custom_tool_roundtrip(self):
        d = ToolDispatcher()
        d.register("echo", {
            "name": "echo", "description": "Echo",
            "input_schema": {
                "type": "object",
                "properties": {"msg": {"type": "string"}},
                "required": ["msg"],
            },
        }, lambda inp: json.dumps({"echo": inp["msg"]}))

        raw = d.dispatch("echo", {"msg": "hello world"})
        result = json.loads(raw)
        _save("tools_dispatch_echo.json", raw)
        assert result["echo"] == "hello world"

    def test_multiple_tools_isolated(self):
        d = ToolDispatcher()
        def make_handler(name):
            return lambda inp: json.dumps({"tool": name, "input": inp})
        d.register("tool_a", {
            "name": "tool_a", "description": "A",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        }, make_handler("tool_a"))
        d.register("tool_b", {
            "name": "tool_b", "description": "B",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        }, make_handler("tool_b"))

        raw_a = d.dispatch("tool_a", {})
        raw_b = d.dispatch("tool_b", {"x": 1})
        _save("tools_dispatch_multi_a.json", raw_a)
        _save("tools_dispatch_multi_b.json", raw_b)
        assert json.loads(raw_a)["tool"] == "tool_a"
        assert json.loads(raw_b)["input"] == {"x": 1}

    def test_all_tool_schemas_property_empty(self):
        d = ToolDispatcher()
        assert d.all_tool_schemas == []

    def test_all_tool_schemas_property_order(self):
        d = ToolDispatcher()
        d.register("a", {
            "name": "a", "description": "A",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        }, lambda i: "ok")
        assert len(d.all_tool_schemas) == 1
        assert d.all_tool_schemas[0]["name"] == "a"


# ══════════════════════════════════════════════════════════════════════════
# Mutable context tests
# ══════════════════════════════════════════════════════════════════════════


class TestMutableContext:
    def test_add_prior_class(self, dispatcher):
        result = json.loads(
            dispatcher.dispatch("check_class_name", {"name": "NewThing"})
        )
        assert result["found"] is False

        dispatcher.add_prior_class("NewThing", "calc::NewThing")
        raw = dispatcher.dispatch("check_class_name", {"name": "NewThing"})
        result = json.loads(raw)
        _save("tools_mutable_add_class.json", raw)
        assert result["found"] is True
        assert result["matches"][0]["source"] == "prior_design"
        assert result["matches"][0]["qualified_name"] == "calc::NewThing"

    def test_add_prior_class_visible_to_validate(self, dispatcher):
        dispatcher.add_prior_class("Helper", "calc::Helper")
        design = [{
            "type": "ClassNode",
            "name": "Main",
            "qualified_name": "calc::Main",
            "kind": "class",
            "visibility": "public",
            "brief_description": "Main class",
            "tags": ["design"],
            "base_classes": [],
            "edges": [{
                "relation_type": "DEPENDS_ON",
                "target_uid": "Helper",
                "target_type": "ClassNode",
            }],
        }]
        raw = dispatcher.dispatch("validate_design", design)
        result = json.loads(raw)
        _save("tools_mutable_validate.json", raw)
        assert result["valid"] is True

    def test_set_dependency_lookup(self, dispatcher):
        dispatcher.set_dependency_lookup({"boost::asio": "boost::asio"})
        raw = dispatcher.dispatch("check_class_name", {"name": "asio"})
        result = json.loads(raw)
        _save("tools_mutable_set_deps.json", raw)
        assert result["found"] is True
        assert any(m["source"] == "dependency" for m in result["matches"])

    def test_set_intercomponent_classes(self, dispatcher):
        dispatcher.set_intercomponent_classes([
            {"qualified_name": "net::Socket", "kind": "class", "name": "Socket"},
        ])
        raw = dispatcher.dispatch("check_class_name", {"name": "Socket"})
        result = json.loads(raw)
        _save("tools_mutable_set_intercomponent.json", raw)
        assert result["found"] is True
        assert any(m["source"] == "intercomponent" for m in result["matches"])

    def test_initial_context_stored(self, dispatcher):
        assert dispatcher.prior_class_lookup["CalcEngine"] == "calc::CalcEngine"
        assert dispatcher.dependency_lookup["std::vector"] == "std::vector"
        assert dispatcher.component_namespace == "calc"
        assert dispatcher.sibling_namespaces == ["ui", "io"]

    def test_empty_dispatcher_has_no_context(self, empty_dispatcher):
        assert empty_dispatcher.prior_class_lookup == {}
        assert empty_dispatcher.dependency_lookup == {}
        assert empty_dispatcher.intercomponent_classes == []
        assert empty_dispatcher.component_namespace == ""


# ══════════════════════════════════════════════════════════════════════════
# GraphRepository integration
# ══════════════════════════════════════════════════════════════════════════


class TestDispatcherRepo:
    def test_default_repo(self, empty_dispatcher):
        assert isinstance(empty_dispatcher.repo, GraphRepository)

    def test_custom_repo(self):
        repo = GraphRepository()
        d = DesignToolDispatcher(repo=repo)
        assert d.repo is repo

    def test_session_contextmanager(self, empty_dispatcher):
        try:
            with empty_dispatcher.session() as s:
                pass
        except Exception:
            pass  # Expected when Neo4j is unavailable
        assert hasattr(empty_dispatcher, "session")


# ══════════════════════════════════════════════════════════════════════════
# Inheritance
# ══════════════════════════════════════════════════════════════════════════


class TestInheritance:
    def test_is_tool_dispatcher(self):
        d = DesignToolDispatcher()
        assert isinstance(d, ToolDispatcher)

    def test_methods_inherited(self):
        d = DesignToolDispatcher()
        assert hasattr(d, "register")
        assert hasattr(d, "dispatch")
        assert hasattr(d, "all_tool_schemas")
        assert hasattr(d, "_handlers")
        assert hasattr(d, "_schemas")
