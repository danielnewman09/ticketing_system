"""Tests for verify_llr validate-and-retry integration."""

from backend.requirements.schemas import VerificationSchema, VerificationConditionSchema, VerificationActionSchema


class TestCollectQualifiedNames:
    """Test _collect_qualified_names helper."""

    def test_collects_from_preconditions(self):
        from backend.ticketing_agent.verify.verify_llr import _collect_qualified_names
        vs = [
            VerificationSchema(
                method="automated",
                test_name="test_add",
                description="Test add",
                preconditions=[
                    VerificationConditionSchema(subject_qualified_name="calc::Engine::precision", operator="==", expected_value="2"),
                ],
                actions=[],
                postconditions=[],
            ),
        ]
        qnames = _collect_qualified_names(vs)
        assert "calc::Engine::precision" in qnames

    def test_collects_from_actions(self):
        from backend.ticketing_agent.verify.verify_llr import _collect_qualified_names
        vs = [
            VerificationSchema(
                method="automated",
                test_name="test_add",
                description="Test add",
                preconditions=[],
                actions=[
                    VerificationActionSchema(description="Call add", callee_qualified_name="calc::Engine::add"),
                ],
                postconditions=[],
            ),
        ]
        qnames = _collect_qualified_names(vs)
        assert "calc::Engine::add" in qnames

    def test_collects_from_postconditions(self):
        from backend.ticketing_agent.verify.verify_llr import _collect_qualified_names
        vs = [
            VerificationSchema(
                method="automated",
                test_name="test_add",
                description="Test add",
                preconditions=[],
                actions=[],
                postconditions=[
                    VerificationConditionSchema(subject_qualified_name="calc::Engine::result", operator="==", expected_value="5"),
                ],
            ),
        ]
        qnames = _collect_qualified_names(vs)
        assert "calc::Engine::result" in qnames


class TestFormatVerificationValidationErrors:
    """Test _format_verification_validation_errors helper."""

    def test_format_single_error(self):
        from backend.ticketing_agent.verify.verify_llr import _format_verification_validation_errors
        msg = _format_verification_validation_errors([
            "user_interface::CalculatorWindow.equalsButton — dot separator, use ::",
        ])
        assert "<issues>" in msg
        assert "CalculatorWindow.equalsButton" in msg
        assert "corrected" in msg.lower() or "correct these" in msg.lower()

    def test_format_multiple_errors(self):
        from backend.ticketing_agent.verify.verify_llr import _format_verification_validation_errors
        msg = _format_verification_validation_errors([
            "user_interface::CalculatorWindow.equalsButton",
            "result_of_first_call",
        ])
        assert "<issues>" in msg
        assert "CalculatorWindow.equalsButton" in msg
        assert "result_of_first_call" in msg