"""Tests for design_oo_prompt contract and anti-pattern content."""

from backend.ticketing_agent.design.design_oo_prompt import (
    SYSTEM_PROMPT,
    build_intercomponent_section,
)


class TestIntercomponentSection:
    def test_intercomponent_section_contains_contract(self):
        classes = [
            {
                "qualified_name": "calculation_engine::CalculatorResult",
                "kind": "class",
                "description": "Result wrapper",
                "component_name": "calculation_engine",
                "methods": [{"name": "get_value", "visibility": "public"}],
            }
        ]
        section = build_intercomponent_section(classes)
        assert "<CONTRACT>" in section
        assert "</CONTRACT>" in section
        assert "MUST create associations" in section

    def test_intercomponent_section_contains_example(self):
        classes = [
            {
                "qualified_name": "calculation_engine::CalculatorResult",
                "kind": "class",
                "description": "Result wrapper",
                "component_name": "calculation_engine",
                "methods": [{"name": "get_value", "visibility": "public"}],
            }
        ]
        section = build_intercomponent_section(classes)
        assert "Example" in section
        assert "depends_on" in section
        assert "from_class" in section

    def test_intercomponent_section_does_not_say_do_not_include(self):
        """The old discouraging text should be removed."""
        classes = [
            {
                "qualified_name": "calc::Result",
                "kind": "class",
                "description": "Result",
                "component_name": "calc",
                "methods": [],
            }
        ]
        section = build_intercomponent_section(classes)
        assert "Do NOT include them in your output" not in section

    def test_empty_classes_returns_empty(self):
        section = build_intercomponent_section([])
        assert section == ""


class TestSystemPromptContract:
    def test_system_prompt_contains_association_contract(self):
        assert "<CONTRACT>" in SYSTEM_PROMPT

    def test_system_prompt_intercomponent_contract_mentions_disconnected(self):
        """The contract should mention disconnected components."""
        assert "disconnected" in SYSTEM_PROMPT.lower()