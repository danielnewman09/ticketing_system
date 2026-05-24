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

class TestValidateVerificationQnames:
    """Test _validate_verification_qnames format validation."""

    def _make_verification(self, caller_qn="", callee_qn="", subject_qn=""):
        preconditions = []
        postconditions = []
        actions = []
        if subject_qn:
            preconditions.append(
                VerificationConditionSchema(
                    subject_qualified_name=subject_qn,
                    operator="==",
                    expected_value="true",
                )
            )
        if caller_qn or callee_qn:
            actions.append(
                VerificationActionSchema(
                    description="Test action",
                    callee_qualified_name=callee_qn,
                    caller_qualified_name=caller_qn,
                )
            )
        return VerificationSchema(
            method="automated",
            test_name="test_something",
            description="Test",
            preconditions=preconditions,
            actions=actions,
            postconditions=postconditions,
        )

    def test_valid_qnames_pass(self):
        from backend.ticketing_agent.verify.verify_llr import _validate_verification_qnames
        vs = [self._make_verification(
            caller_qn="calc::Engine",
            callee_qn="calc::Engine::calculate",
            subject_qn="calc::Engine::state",
        )]
        errors = _validate_verification_qnames(vs)
        assert errors == []

    def test_test_prefix_in_caller_flagged(self):
        from backend.ticketing_agent.verify.verify_llr import _validate_verification_qnames
        vs = [self._make_verification(caller_qn="test_division_of_valid_numbers")]
        errors = _validate_verification_qnames(vs)
        assert len(errors) == 1
        assert "test_division" in errors[0]
        assert "not a design element" in errors[0]

    def test_result_of_prefix_in_subject_flagged(self):
        from backend.ticketing_agent.verify.verify_llr import _validate_verification_qnames
        vs = [self._make_verification(subject_qn="result_of_first_call")]
        errors = _validate_verification_qnames(vs)
        assert len(errors) == 1
        assert "result_of" in errors[0]

    def test_bare_lowercase_in_caller_flagged(self):
        from backend.ticketing_agent.verify.verify_llr import _validate_verification_qnames
        vs = [self._make_verification(caller_qn="test_context")]
        errors = _validate_verification_qnames(vs)
        assert len(errors) == 1
        assert "test_context" in errors[0]

    def test_dot_separator_flagged_with_correction(self):
        from backend.ticketing_agent.verify.verify_llr import _validate_verification_qnames
        vs = [self._make_verification(subject_qn="calc.Engine.state")]
        errors = _validate_verification_qnames(vs)
        assert len(errors) == 1
        assert "Dot separator" in errors[0]
        assert "calc::Engine::state" in errors[0]

    def test_empty_caller_not_flagged(self):
        from backend.ticketing_agent.verify.verify_llr import _validate_verification_qnames
        vs = [self._make_verification(caller_qn="", callee_qn="calc::Engine::run")]
        errors = _validate_verification_qnames(vs)
        assert errors == []

    def test_multiple_errors_all_flagged(self):
        from backend.ticketing_agent.verify.verify_llr import _validate_verification_qnames
        vs = [self._make_verification(
            caller_qn="test_validate",
            subject_qn="result_of_call",
        )]
        errors = _validate_verification_qnames(vs)
        assert len(errors) == 2
