"""Tests for requirement formatting helpers and Pydantic models.

The SQLAlchemy HighLevelRequirement/LowLevelRequirement models have been
removed in Phase 2. These tests cover the replacement formatting module
and the HLRNode/LLRNode Pydantic models.
"""

import pytest

from backend.requirements.formatting import format_hlr_dict, format_hlrs_for_prompt, format_llr_dict
from backend.db.neo4j.repositories.models.requirement import HLRNode, LLRNode


# ---------------------------------------------------------------------------
# HLRNode / LLRNode Pydantic models
# ---------------------------------------------------------------------------


class TestHLRNode:
    def test_defaults(self):
        node = HLRNode(id=1, description="test")
        assert node.id == 1
        assert node.description == "test"
        assert node.component_id is None
        assert node.dependency_context is None

    def test_with_all_fields(self):
        node = HLRNode(
            id=1,
            description="The system shall perform arithmetic",
            component_id=5,
            dependency_context={"recommendation": "eigen"},
        )
        assert node.component_id == 5
        assert node.dependency_context == {"recommendation": "eigen"}

    def test_model_dump(self):
        node = HLRNode(id=1, description="test", component_id=3)
        d = node.model_dump()
        assert d["id"] == 1
        assert d["description"] == "test"
        assert d["component_id"] == 3
        assert d["dependency_context"] is None


class TestLLRNode:
    def test_defaults(self):
        node = LLRNode(id=10, high_level_requirement_id=1, description="test")
        assert node.id == 10
        assert node.description == "test"
        assert node.high_level_requirement_id == 1

    def test_model_dump(self):
        node = LLRNode(id=5, high_level_requirement_id=1, description="test")
        d = node.model_dump()
        assert d["id"] == 5
        assert d["high_level_requirement_id"] == 1


# ---------------------------------------------------------------------------
# format_hlr_dict
# ---------------------------------------------------------------------------


class TestFormatHlrDict:
    def test_basic_format(self):
        hlr = {"id": 1, "description": "The system shall be fast"}
        result = format_hlr_dict(hlr)
        assert result == "HLR 1: The system shall be fast"

    def test_with_component_name(self):
        hlr = {
            "id": 5,
            "description": "Perform arithmetic",
            "component_name": "Calculator",
        }
        result = format_hlr_dict(hlr, include_component=True)
        assert result == "HLR 5 [Component: Calculator]: Perform arithmetic"

    def test_with_component__name_dunder(self):
        hlr = {
            "id": 5,
            "description": "Perform arithmetic",
            "component__name": "Calculator",
        }
        result = format_hlr_dict(hlr, include_component=True)
        assert result == "HLR 5 [Component: Calculator]: Perform arithmetic"

    def test_component_name_takes_precedence_over_dunder(self):
        hlr = {
            "id": 5,
            "description": "Test",
            "component_name": "Primary",
            "component__name": "Secondary",
        }
        result = format_hlr_dict(hlr, include_component=True)
        assert result == "HLR 5 [Component: Primary]: Test"

    def test_no_component_name_when_include_component_false(self):
        hlr = {
            "id": 1,
            "description": "Test",
            "component_name": "Calculator",
        }
        result = format_hlr_dict(hlr, include_component=False)
        assert result == "HLR 1: Test"

    def test_missing_component_name_shows_no_component(self):
        hlr = {"id": 1, "description": "No comp"}
        result = format_hlr_dict(hlr, include_component=True)
        assert result == "HLR 1: No comp"


# ---------------------------------------------------------------------------
# format_llr_dict
# ---------------------------------------------------------------------------


class TestFormatLlrDict:
    def test_basic_format(self):
        llr = {"id": 10, "description": "Validate numeric input"}
        result = format_llr_dict(llr)
        assert result == "LLR 10: Validate numeric input"


# ---------------------------------------------------------------------------
# format_hlrs_for_prompt
# ---------------------------------------------------------------------------


class TestFormatHlrsForPrompt:
    def test_hlrs_only(self):
        hlrs = [
            {"id": 1, "description": "HLR one"},
            {"id": 2, "description": "HLR two"},
        ]
        result = format_hlrs_for_prompt(hlrs)
        assert "HLR 1: HLR one" in result
        assert "HLR 2: HLR two" in result

    def test_hlrs_with_linked_llrs(self):
        hlrs = [{"id": 1, "description": "HLR one"}]
        llrs = [
            {"id": 10, "description": "LLR for one", "hlr_id": 1},
        ]
        result = format_hlrs_for_prompt(hlrs, llrs=llrs)
        assert "HLR 1: HLR one" in result
        assert "  LLR 10: LLR for one" in result

    def test_hlrs_with_unlinked_llrs(self):
        hlrs = [{"id": 1, "description": "HLR one"}]
        llrs = [
            {"id": 10, "description": "Linked", "hlr_id": 1},
            {"id": 11, "description": "Unlinked", "hlr_id": None},
        ]
        result = format_hlrs_for_prompt(hlrs, llrs=llrs)
        assert "HLR 1: HLR one" in result
        assert "  LLR 10: Linked" in result
        assert "\nUnlinked LLRs:" in result
        assert "  LLR 11: Unlinked" in result

    def test_no_unlinked_llrs_no_separator(self):
        hlrs = [{"id": 1, "description": "HLR one"}]
        llrs = [{"id": 10, "description": "Linked", "hlr_id": 1}]
        result = format_hlrs_for_prompt(hlrs, llrs=llrs)
        assert "Unlinked LLRs" not in result

    def test_with_include_component(self):
        hlrs = [
            {"id": 1, "description": "HLR one", "component_name": "Calc"},
        ]
        result = format_hlrs_for_prompt(hlrs, include_component=True)
        assert "HLR 1 [Component: Calc]: HLR one" in result

    def test_llrs_only_no_hlrs(self):
        result = format_hlrs_for_prompt(
            [], llrs=[{"id": 5, "description": "Orphan", "hlr_id": None}]
        )
        assert "Unlinked LLRs:" in result
        assert "  LLR 5: Orphan" in result

    def test_empty_inputs(self):
        result = format_hlrs_for_prompt([])
        assert result == ""

    def test_hlrs_only_no_llrs(self):
        hlrs = [{"id": 1, "description": "HLR one"}]
        result = format_hlrs_for_prompt(hlrs)
        assert result == "HLR 1: HLR one"