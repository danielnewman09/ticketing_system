"""Unit tests for migrated design_oo prompt builders.

Verifies each builder produces correct markdown from codegraph-style
dicts — the same format produced by neomodel model serialization and
the design pipeline's context-gathering phase.

All generated markdown is saved to
``tests/agents/__data__/design_oo_prompt/`` for manual inspection.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend_migrated.agents.design_oo_prompt import (
    build_as_built_section,
    build_existing_classes_section,
    build_intercomponent_section,
    build_namespace_section,
)

# ---------------------------------------------------------------------------
# Artifact saving
# ---------------------------------------------------------------------------


@pytest.fixture()
def save(data_dir: Path):
    """Return a helper that writes a builder's output to the data directory."""
    def _save(group: str, name: str, output: str) -> Path:
        dest = data_dir / group / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(output)
        return dest
    return _save


# ---------------------------------------------------------------------------
# Data fixtures — codegraph-style dicts (same shape as neomodel serialize())
# ---------------------------------------------------------------------------


def _make_class_dict(
    qualified_name: str,
    *,
    kind: str = "class",
    description: str = "",
    methods: list[dict] | None = None,
    attributes: list[dict] | None = None,
    inherits_from: list[str] | None = None,
    realizes: list[str] | None = None,
    associations: list[dict] | None = None,
    relevance: str = "",
) -> dict:
    """Build a codegraph-style class/interface dict."""
    d: dict = {
        "qualified_name": qualified_name,
        "kind": kind,
        "description": description,
        "methods": methods or [],
        "attributes": attributes or [],
        "inherits_from": inherits_from or [],
        "realizes": realizes or [],
        "associations": associations or [],
    }
    if relevance:
        d["relevance"] = relevance
    return d


# ---------------------------------------------------------------------------
# build_namespace_section
# ---------------------------------------------------------------------------


class TestBuildNamespaceSection:
    def test_empty_namespace_returns_empty(self, save):
        result = build_namespace_section("")
        save("design_oo_prompt", "01_namespace_empty.md", result)
        assert result == ""

    def test_single_namespace(self, save):
        result = build_namespace_section("calculation_engine")
        save("design_oo_prompt", "02_namespace_single.md", result)
        assert "calculation_engine" in result
        assert "module" in result
        assert "MUST use" in result

    def test_with_sibling_namespaces(self, save):
        result = build_namespace_section(
            "calculation_engine",
            sibling_namespaces=["user_interface", "data_storage"],
        )
        save("design_oo_prompt", "03_namespace_siblings.md", result)
        assert "calculation_engine" in result
        assert "user_interface" in result
        assert "data_storage" in result
        assert "do NOT use as module" in result

    def test_sibling_namespaces_are_listed(self, save):
        result = build_namespace_section(
            "calc", sibling_namespaces=["ui"]
        )
        save("design_oo_prompt", "04_namespace_listed.md", result)
        assert "- ui" in result
        assert "for reference" in result


# ---------------------------------------------------------------------------
# build_as_built_section
# ---------------------------------------------------------------------------


class TestBuildAsBuiltSection:
    def test_empty_list_returns_empty(self, save):
        result = build_as_built_section([])
        save("design_oo_prompt", "05_as_built_empty.md", result)
        assert result == ""

    def test_single_class_renders_correctly(self, save):
        classes = [
            _make_class_dict(
                "calc::CalculatorEngine",
                kind="class",
                description="Core engine handling arithmetic",
                methods=[
                    {"name": "add", "visibility": "public"},
                    {"name": "validate", "visibility": "private"},
                ],
                attributes=[
                    {"name": "precision", "visibility": "private"},
                ],
                inherits_from=["calc::BaseEngine"],
                relevance="Directly relevant to calculation HLRs",
            )
        ]
        result = build_as_built_section(classes)
        save("design_oo_prompt", "06_as_built_single_class.md", result)
        save("design_oo_prompt", "06_as_built_input.json", json.dumps(classes, indent=2))
        assert "As-built project classes" in result
        assert "calc::CalculatorEngine" in result
        assert "Core engine" in result
        assert "add" in result
        # Private methods should NOT appear in public methods list
        assert "validate" not in result  # private
        # Private attributes also not shown in public attributes list
        assert "precision" not in result  # private attrs are excluded
        assert "calc::BaseEngine" in result
        # Relevance is a custom field not rendered by codegraph
        assert "Core engine" in result

    def test_private_methods_excluded_from_public_list(self, save):
        classes = [
            _make_class_dict(
                "ns::Widget",
                methods=[
                    {"name": "render", "visibility": "public"},
                    {"name": "layout", "visibility": "private"},
                    {"name": "paint", "visibility": "protected"},
                ],
            )
        ]
        result = build_as_built_section(classes)
        save("design_oo_prompt", "07_as_built_private_excluded.md", result)
        assert "render" in result
        assert "layout" not in result
        assert "paint" not in result

    def test_multiple_classes(self, save):
        classes = [
            _make_class_dict("calc::A", description="Class A"),
            _make_class_dict("calc::B", description="Class B"),
        ]
        result = build_as_built_section(classes)
        save("design_oo_prompt", "08_as_built_multiple.md", result)
        assert "calc::A" in result
        assert "calc::B" in result
        assert "Class A" in result
        assert "Class B" in result

    def test_interface_kind(self, save):
        classes = [
            _make_class_dict(
                "calc::ICompute",
                kind="interface",
                description="Compute interface",
                methods=[{"name": "compute", "visibility": "public"}],
            )
        ]
        result = build_as_built_section(classes)
        save("design_oo_prompt", "09_as_built_interface.md", result)
        assert "Interface: `calc::ICompute`" in result
        assert "compute" in result

    def test_no_methods_or_attributes(self, save):
        classes = [
            _make_class_dict("calc::Minimal", description="Just a stub")
        ]
        result = build_as_built_section(classes)
        save("design_oo_prompt", "10_as_built_minimal.md", result)
        assert "calc::Minimal" in result
        assert "Public methods" not in result
        assert "Public attributes" not in result


# ---------------------------------------------------------------------------
# build_existing_classes_section
# ---------------------------------------------------------------------------


class TestBuildExistingClassesSection:
    def test_empty_list_returns_empty(self, save):
        result = build_existing_classes_section([])
        save("design_oo_prompt", "11_existing_empty.md", result)
        assert result == ""

    def test_single_class_with_all_fields(self, save):
        classes = [
            _make_class_dict(
                "calc::Calculator",
                kind="class",
                description="Handles arithmetic",
                methods=[
                    {"name": "add", "visibility": "public"},
                    {"name": "subtract", "visibility": "public"},
                    {"name": "log", "visibility": "private"},
                ],
                attributes=[
                    {"name": "result", "visibility": "private"},
                    {"name": "cache", "visibility": "protected"},
                ],
                inherits_from=["calc::Base"],
                realizes=["calc::IArithmetic"],
                associations=[
                    {"kind": "references", "target": "calc::Log", "description": "Logs operations"},
                ],
            )
        ]
        result = build_existing_classes_section(classes)
        save("design_oo_prompt", "12_existing_full.md", result)
        save("design_oo_prompt", "12_existing_input.json", json.dumps(classes, indent=2))
        assert "Existing classes in the design" in result
        assert "calc::Calculator" in result
        assert "Handles arithmetic" in result
        # Methods grouped by visibility
        assert "public: add, subtract" in result
        assert "private: log" in result
        # Attributes grouped by visibility
        assert "private: result" in result
        assert "protected: cache" in result
        # Inherits
        assert "calc::Base" in result
        # Realizes
        assert "calc::IArithmetic" in result
        # Associations
        assert "references -> calc::Log" in result
        assert "Logs operations" in result

    def test_class_without_inherits_or_realizes(self, save):
        classes = [
            _make_class_dict("ns::Simple", description="Simple class")
        ]
        result = build_existing_classes_section(classes)
        save("design_oo_prompt", "13_existing_simple.md", result)
        assert "Inherits from" not in result
        assert "Realizes" not in result
        assert "-> " not in result  # no associations

    def test_multiple_classes_with_different_kinds(self, save):
        classes = [
            _make_class_dict("calc::Engine", kind="class", description="Engine"),
            _make_class_dict("calc::IOps", kind="interface", description="Ops interface"),
            _make_class_dict("calc::Status", kind="enum", description="Status enum"),
        ]
        result = build_existing_classes_section(classes)
        save("design_oo_prompt", "14_existing_kinds.md", result)
        assert "class: `calc::Engine`" in result
        assert "interface: `calc::IOps`" in result
        assert "enum: `calc::Status`" in result

    def test_reuse_guidance_included(self, save):
        classes = [
            _make_class_dict("calc::Old", description="Existing class")
        ]
        result = build_existing_classes_section(classes)
        save("design_oo_prompt", "15_existing_reuse.md", result)
        assert "MUST reuse" in result
        assert "extend" in result


# ---------------------------------------------------------------------------
# build_intercomponent_section
# ---------------------------------------------------------------------------


class TestBuildIntercomponentSection:
    def test_empty_list_returns_empty(self, save):
        result = build_intercomponent_section([])
        save("design_oo_prompt", "16_intercomponent_empty.md", result)
        assert result == ""

    def test_single_interface_renders_with_component(self, save):
        classes = [
            {
                "qualified_name": "ui::Display",
                "kind": "class",
                "description": "Renders output",
                "component_name": "user_interface",
                "methods": [
                    {"name": "show", "visibility": "public"},
                    {"name": "clear", "visibility": "public"},
                ],
            }
        ]
        result = build_intercomponent_section(classes)
        save("design_oo_prompt", "17_intercomponent_single.md", result)
        save("design_oo_prompt", "17_intercomponent_input.json", json.dumps(classes, indent=2))
        assert "Cross-component interfaces" in result
        assert "ui::Display" in result
        assert "user_interface" in result
        assert "show" in result
        assert "clear" in result
        assert "CONTRACT" in result
        assert "MUST create associations" in result
        assert "do not redesign" in result.lower()

    def test_example_association_guidance(self, save):
        classes = [
            {
                "qualified_name": "ui::Display",
                "kind": "class",
                "description": "Renders output",
                "component_name": "user_interface",
                "methods": [],
            }
        ]
        result = build_intercomponent_section(classes)
        save("design_oo_prompt", "18_intercomponent_example.md", result)
        assert "Example: cross-component association" in result
        assert "ui::Display" in result
        assert "depends_on" in result

    def test_private_methods_not_shown(self, save):
        classes = [
            {
                "qualified_name": "ns::Service",
                "kind": "interface",
                "component_name": "other",
                "methods": [
                    {"name": "serve", "visibility": "public"},
                    {"name": "_internal", "visibility": "private"},
                ],
            }
        ]
        result = build_intercomponent_section(classes)
        save("design_oo_prompt", "19_intercomponent_private.md", result)
        assert "serve" in result
        assert "_internal" not in result

    def test_multiple_components(self, save):
        classes = [
            {
                "qualified_name": "a::One",
                "kind": "class",
                "component_name": "comp_a",
                "methods": [],
            },
            {
                "qualified_name": "b::Two",
                "kind": "interface",
                "component_name": "comp_b",
                "methods": [],
            },
        ]
        result = build_intercomponent_section(classes)
        save("design_oo_prompt", "20_intercomponent_multiple.md", result)
        assert "a::One" in result
        assert "comp_a" in result
        assert "b::Two" in result
        assert "comp_b" in result
