"""Tests for verify_llr_prompt FORMAT-CONTRACT content."""

from backend.ticketing_agent.verify.verify_llr_prompt import SYSTEM_PROMPT, format_structured_context


class TestVerifyPromptFormatContract:
    def test_system_prompt_contains_format_contract(self):
        assert "<FORMAT-CONTRACT" in SYSTEM_PROMPT

    def test_system_prompt_contains_qualified_name_pattern(self):
        assert "<namespace>::<ClassName>::<memberName>" in SYSTEM_PROMPT

    def test_system_prompt_contains_negative_examples(self):
        assert "✗" in SYSTEM_PROMPT
        assert "Dot separator" in SYSTEM_PROMPT or "dot separator" in SYSTEM_PROMPT

    def test_system_prompt_contains_positive_examples(self):
        assert "✓" in SYSTEM_PROMPT
        assert "CalculatorEngine" in SYSTEM_PROMPT or "CalculatorWindow" in SYSTEM_PROMPT

    def test_system_prompt_strengthens_qualified_name_guidance(self):
        """The strengthened guidance should mention 'fabricate' or 'exact match'."""
        assert "fabricate" in SYSTEM_PROMPT.lower()
        assert "exactly match" in SYSTEM_PROMPT.lower()

    def test_format_contract_has_fallback_rule(self):
        """The contract should say what to do if no match exists."""
        assert "omit the reference" in SYSTEM_PROMPT.lower() or "expected_value" in SYSTEM_PROMPT


class TestFormatStructuredContext:
    def test_empty_context(self):
        result = format_structured_context([])
        assert result == "(no design context)"

    def test_single_class_context(self):
        ctx = [
            {
                "qualified_name": "calc::Engine",
                "kind": "class",
                "description": "An engine",
                "attributes": [],
                "methods": [],
                "relationships": [],
            }
        ]
        result = format_structured_context(ctx)
        assert "calc::Engine" in result
        assert "class" in result

    def test_class_with_methods(self):
        ctx = [
            {
                "qualified_name": "calc::Engine",
                "kind": "class",
                "description": "An engine",
                "attributes": [],
                "methods": [
                    {"name": "calculate", "visibility": "public"},
                ],
                "relationships": [],
            }
        ]
        result = format_structured_context(ctx)
        assert "calculate" in result