"""Tests for design_tools — validate_design, check_class_name,
produce_oo_design.

Saves tool outputs to ``unit_test_data/tools/tools_*`` for visual inspection.
"""

import json
from pathlib import Path

import pytest

from backend_migrated.tools import DesignToolDispatcher

OUT_DIR = Path(__file__).resolve().parents[2] / "unit_test_data" / "tools"


def _save(stem: str, content: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / stem).write_text(content, encoding="utf-8")


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def dispatcher():
    """Dispatcher with sample prior designs, dependencies, intercomponent."""
    return DesignToolDispatcher(
        prior_class_lookup={
            "CalcEngine": "calc::CalcEngine",
            "Logger": "util::Logger",
        },
        dependency_lookup={
            "std::vector": "std::vector",
            "std::string": "std::basic_string",
        },
        intercomponent_classes=[
            {
                "qualified_name": "ui::DisplayArea",
                "kind": "class",
                "name": "DisplayArea",
            },
            {
                "qualified_name": "io::DataPort",
                "kind": "interface",
                "name": "DataPort",
            },
        ],
    )


def _sample_design():
    """Return a minimal valid design in LayerGraph format (list of CodeGraphNode dicts)."""
    return [
        {
            "type": "ClassNode",
            "name": "Calculator",
            "qualified_name": "calc::Calculator",
            "kind": "class",
            "visibility": "public",
            "brief_description": "Main calculator engine",
            "tags": ["design"],
            "base_classes": [],
            "edges": [],
            "composes": [
                {
                    "type": "AttributeNode",
                    "name": "result",
                    "qualified_name": "calc::Calculator::result",
                    "kind": "attribute",
                    "visibility": "private",
                    "type_signature": "double",
                    "brief_description": "Last computed result",
                    "tags": ["design"],
                    "edges": [],
                },
                {
                    "type": "MethodNode",
                    "name": "add",
                    "qualified_name": "calc::Calculator::add",
                    "kind": "method",
                    "visibility": "public",
                    "type_signature": "double",
                    "argsstring": "(double a, double b)",
                    "brief_description": "Add two numbers",
                    "tags": ["design"],
                    "edges": [],
                },
            ],
        },
    ]


# ══════════════════════════════════════════════════════════════════════════
# validate_design
# ══════════════════════════════════════════════════════════════════════════


class TestValidateDesign:
    def test_valid_design_no_errors(self, dispatcher):
        design = _sample_design()
        raw = dispatcher.dispatch("validate_design", design)
        result = json.loads(raw)
        _save("tools_validate_valid.json", raw)
        assert result["valid"] is True
        assert result["errors"] == []
        assert isinstance(result["warnings"], list)

    def test_known_edge_target_not_flagged(self, dispatcher):
        """Edges targeting classes defined in the same design should not be flagged."""
        design = [
            {
                "type": "ClassNode",
                "name": "Helper",
                "qualified_name": "calc::Helper",
                "kind": "class",
                "visibility": "public",
                "brief_description": "Helper utility",
                "tags": ["design"],
                "base_classes": [],
                "edges": [],
            },
            {
                "type": "ClassNode",
                "name": "Main",
                "qualified_name": "calc::Main",
                "kind": "class",
                "visibility": "public",
                "brief_description": "Main class",
                "tags": ["design"],
                "base_classes": [],
                "edges": [
                    {
                        "relation_type": "DEPENDS_ON",
                        "target_uid": "calc::Helper",
                        "target_type": "ClassNode",
                    },
                ],
            },
        ]
        result = json.loads(dispatcher.dispatch("validate_design", design))
        assert result["valid"] is True

    def test_intercomponent_edge_not_flagged(self, dispatcher):
        design = _sample_design()
        design[0]["edges"].append({
            "relation_type": "DEPENDS_ON",
            "target_uid": "ui::DisplayArea",
            "target_type": "ClassNode",
        })
        result = json.loads(dispatcher.dispatch("validate_design", design))
        assert result["valid"] is True

    def test_dependency_edge_not_flagged(self, dispatcher):
        design = _sample_design()
        design[0]["edges"].append({
            "relation_type": "DEPENDS_ON",
            "target_uid": "std::vector",
            "target_type": "ClassNode",
        })
        result = json.loads(dispatcher.dispatch("validate_design", design))
        assert result["valid"] is True

    def test_prior_design_edge_not_flagged(self, dispatcher):
        design = _sample_design()
        design[0]["edges"].append({
            "relation_type": "DEPENDS_ON",
            "target_uid": "calc::CalcEngine",
            "target_type": "ClassNode",
        })
        result = json.loads(dispatcher.dispatch("validate_design", design))
        assert result["valid"] is True

    def test_unknown_edge_target_flagged(self, dispatcher):
        design = _sample_design()
        design[0]["edges"].append({
            "relation_type": "DEPENDS_ON",
            "target_uid": "NonExistentClass",
            "target_type": "ClassNode",
        })
        raw = dispatcher.dispatch("validate_design", design)
        result = json.loads(raw)
        _save("tools_validate_unknown_target.json", raw)
        assert result["valid"] is False
        assert any("NonExistentClass" in e for e in result["errors"])

    def test_missing_intercomponent_reference_warns(self, dispatcher):
        design = _sample_design()
        raw = dispatcher.dispatch("validate_design", design)
        result = json.loads(raw)
        _save("tools_validate_intercomponent_warn.json", raw)
        assert any(
            "DisplayArea" in w or "DataPort" in w
            for w in result["warnings"]
        )

    def test_intercomponent_reference_in_type_sig_suppresses_warning(self, dispatcher):
        design = _sample_design()
        design[0]["composes"].append({
            "type": "AttributeNode",
            "name": "display",
            "qualified_name": "calc::Calculator::display",
            "kind": "attribute",
            "visibility": "private",
            "type_signature": "ui::DisplayArea*",
            "brief_description": "Display reference",
            "tags": ["design"],
            "edges": [],
        })
        result = json.loads(dispatcher.dispatch("validate_design", design))
        assert not any("DisplayArea" in w for w in result["warnings"])

    def test_duplicate_qualified_names_flagged(self, dispatcher):
        design = _sample_design()
        design.append(design[0].copy())  # Same qualified_name appears twice
        raw = dispatcher.dispatch("validate_design", design)
        result = json.loads(raw)
        _save("tools_validate_duplicate.json", raw)
        assert result["valid"] is False
        assert any(
            "duplicate" in e.lower() or "Duplicate" in e
            for e in result["errors"]
        )

    def test_empty_design_valid(self, dispatcher):
        """A single minimal node is valid."""
        design = [{
            "type": "ClassNode",
            "name": "Foo",
            "qualified_name": "calc::Foo",
            "kind": "class",
            "visibility": "public",
            "brief_description": "Minimal",
            "tags": ["design"],
            "base_classes": [],
            "edges": [],
        }]
        result = json.loads(dispatcher.dispatch("validate_design", design))
        assert result["valid"] is True

    def test_interface_kind_accepted(self, dispatcher):
        design = _sample_design()
        design.append({
            "type": "InterfaceNode",
            "name": "ICalc",
            "qualified_name": "calc::ICalc",
            "kind": "interface",
            "visibility": "public",
            "brief_description": "Calculator interface",
            "tags": ["design"],
            "edges": [],
        })
        result = json.loads(dispatcher.dispatch("validate_design", design))
        assert result["valid"] is True

    def test_enum_kind_accepted(self, dispatcher):
        design = _sample_design()
        design.append({
            "type": "EnumNode",
            "name": "Op",
            "qualified_name": "calc::Op",
            "kind": "enum",
            "visibility": "public",
            "brief_description": "Operation enum",
            "tags": ["design"],
            "edges": [],
            "composes": [
                {
                    "type": "EnumValueNode",
                    "name": "ADD",
                    "qualified_name": "calc::Op::ADD",
                    "kind": "enumvalue",
                    "visibility": "public",
                    "brief_description": "Addition",
                    "tags": ["design"],
                    "edges": [],
                },
            ],
        })
        result = json.loads(dispatcher.dispatch("validate_design", design))
        assert result["valid"] is True

    def test_inherits_from_edge(self, dispatcher):
        """INHERITS_FROM edge between two nodes in the design."""
        design = _sample_design()
        design.append({
            "type": "ClassNode",
            "name": "Base",
            "qualified_name": "calc::Base",
            "kind": "class",
            "visibility": "public",
            "brief_description": "Base class",
            "tags": ["design"],
            "base_classes": [],
            "edges": [],
        })
        design[0]["edges"].append({
            "relation_type": "INHERITS_FROM",
            "target_uid": "calc::Base",
            "target_type": "ClassNode",
        })
        result = json.loads(dispatcher.dispatch("validate_design", design))
        assert result["valid"] is True


# ══════════════════════════════════════════════════════════════════════════
# check_class_name
# ══════════════════════════════════════════════════════════════════════════


class TestCheckClassName:
    def test_prior_design_match(self, dispatcher):
        raw = dispatcher.dispatch("check_class_name", {"name": "CalcEngine"})
        result = json.loads(raw)
        _save("tools_check_name_prior.json", raw)
        assert result["found"] is True
        assert any(
            m["qualified_name"] == "calc::CalcEngine"
            and m["source"] == "prior_design"
            for m in result["matches"]
        )

    def test_dependency_match(self, dispatcher):
        raw = dispatcher.dispatch("check_class_name", {"name": "std::vector"})
        result = json.loads(raw)
        _save("tools_check_name_dependency.json", raw)
        assert result["found"] is True
        assert any(m["source"] == "dependency" for m in result["matches"])

    def test_intercomponent_match(self, dispatcher):
        raw = dispatcher.dispatch("check_class_name", {"name": "DisplayArea"})
        result = json.loads(raw)
        _save("tools_check_name_intercomponent.json", raw)
        assert result["found"] is True
        assert any(
            m["qualified_name"] == "ui::DisplayArea"
            and m["source"] == "intercomponent"
            for m in result["matches"]
        )

    def test_intercomponent_match_by_qname(self, dispatcher):
        raw = dispatcher.dispatch("check_class_name", {"name": "ui::DisplayArea"})
        result = json.loads(raw)
        _save("tools_check_name_intercomponent_qn.json", raw)
        assert any(m["source"] == "intercomponent" for m in result["matches"])

    def test_unknown_name(self, dispatcher):
        raw = dispatcher.dispatch("check_class_name", {"name": "NonExistent"})
        result = json.loads(raw)
        _save("tools_check_name_unknown.json", raw)
        assert result["found"] is False
        assert result["matches"] == []

    def test_partial_substring_match(self, dispatcher):
        raw = dispatcher.dispatch("check_class_name", {"name": "Calc"})
        result = json.loads(raw)
        _save("tools_check_name_partial.json", raw)
        assert result["found"] is True
        assert any(
            "CalcEngine" in m["qualified_name"] for m in result["matches"]
        )

    def test_case_insensitive_match(self, dispatcher):
        raw = dispatcher.dispatch("check_class_name", {"name": "calcengine"})
        result = json.loads(raw)
        _save("tools_check_name_case.json", raw)
        assert any(
            "CalcEngine" in m["qualified_name"] for m in result["matches"]
        )

    def test_empty_name(self, dispatcher):
        result = json.loads(dispatcher.dispatch("check_class_name", {"name": ""}))
        assert result["found"] is False
        assert result["matches"] == []

    def test_multiple_matches_across_sources(self, dispatcher):
        dispatcher.set_intercomponent_classes([
            {"qualified_name": "other::Logger", "kind": "class", "name": "Logger"},
        ])
        raw = dispatcher.dispatch("check_class_name", {"name": "Logger"})
        result = json.loads(raw)
        _save("tools_check_name_multi_source.json", raw)
        assert result["found"] is True
        sources = {m["source"] for m in result["matches"]}
        assert "prior_design" in sources
        assert "intercomponent" in sources

    def test_all_match_fields_present(self, dispatcher):
        raw = dispatcher.dispatch("check_class_name", {"name": "CalcEngine"})
        result = json.loads(raw)
        _save("tools_check_name_fields.json", raw)
        for m in result["matches"]:
            assert "qualified_name" in m
            assert "kind" in m
            assert "source" in m


# ══════════════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════════════
# produce_oo_design
# ══════════════════════════════════════════════════════════════════════════


class TestProduceOODesign:
    def test_returns_terminal_status(self, dispatcher):
        raw = dispatcher.dispatch("produce_oo_design", _sample_design())
        result = json.loads(raw)
        _save("tools_produce_oo_design.json", raw)
        assert result["status"] == "terminal_tool"

    def test_accepts_any_input(self, dispatcher):
        result = json.loads(dispatcher.dispatch("produce_oo_design", []))
        assert result["status"] == "terminal_tool"
