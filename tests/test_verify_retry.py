"""Tests for verify_llr validation helpers and tool-loop integration."""

from unittest.mock import patch
from backend.requirements.schemas import VerificationSchema, VerificationConditionSchema, VerificationActionSchema
from backend.ticketing_agent.verify.verify_llr import _validate_verification_qnames, _collect_qualified_names, VerifyResult


class TestCollectQualifiedNames:
    """Test _collect_qualified_names helper."""

    def test_collects_from_preconditions(self):
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
        vs = [self._make_verification(
            caller_qn="calc::Engine",
            callee_qn="calc::Engine::calculate",
            subject_qn="calc::Engine::state",
        )]
        errors = _validate_verification_qnames(vs)
        assert errors == []

    def test_test_prefix_in_caller_flagged(self):
        vs = [self._make_verification(caller_qn="test_division_of_valid_numbers")]
        errors = _validate_verification_qnames(vs)
        assert len(errors) == 1
        assert "test_division" in errors[0]
        assert "not a design element" in errors[0]

    def test_result_of_prefix_in_subject_flagged(self):
        vs = [self._make_verification(subject_qn="result_of_first_call")]
        errors = _validate_verification_qnames(vs)
        assert len(errors) == 1
        assert "result_of" in errors[0]

    def test_bare_lowercase_in_caller_flagged(self):
        vs = [self._make_verification(caller_qn="test_context")]
        errors = _validate_verification_qnames(vs)
        assert len(errors) == 1
        assert "test_context" in errors[0]

    def test_dot_separator_flagged_with_correction(self):
        vs = [self._make_verification(subject_qn="calc.Engine.state")]
        errors = _validate_verification_qnames(vs)
        assert len(errors) == 1
        assert "Dot separator" in errors[0]
        assert "calc::Engine::state" in errors[0]

    def test_empty_caller_not_flagged(self):
        vs = [self._make_verification(caller_qn="", callee_qn="calc::Engine::run")]
        errors = _validate_verification_qnames(vs)
        assert errors == []

    def test_multiple_errors_all_flagged(self):
        vs = [self._make_verification(
            caller_qn="test_validate",
            subject_qn="result_of_call",
        )]
        errors = _validate_verification_qnames(vs)
        assert len(errors) == 2


class TestVerifyResult:
    def test_all_resolved_true(self):
        r = VerifyResult(verifications=[], resolved=["a"], unresolved=[])
        assert r.all_resolved is True

    def test_all_resolved_false(self):
        r = VerifyResult(verifications=[], resolved=["a"], unresolved=["b"])
        assert r.all_resolved is False


class TestVerifyToolLoop:
    def test_verify_returns_result_on_valid_output(self):
        """Verify that verify() returns VerifyResult via call_tool_loop."""
        from backend.ticketing_agent.verify.verify_llr import verify

        mock_result = {
            "verifications": [
                {
                    "method": "automated",
                    "test_name": "check_display",
                    "description": "Check display",
                    "preconditions": [
                        {
                            "subject_qualified_name": "ui::MainWindow::display",
                            "operator": "not_null",
                            "expected_value": "",
                        }
                    ],
                    "actions": [],
                    "postconditions": [],
                }
            ]
        }
        with patch("backend.ticketing_agent.verify.verify_llr.call_tool_loop", return_value=mock_result):
            result = verify(
                llr={"id": 1, "description": "Test LLR"},
                existing_verifications=[{"method": "automated", "test_name": "check_display", "description": "Check display"}],
                class_contexts=[],
                neo4j_session=None,
            )
        assert isinstance(result, VerifyResult)
        assert len(result.verifications) == 1
        assert result.verifications[0].test_name == "check_display"
