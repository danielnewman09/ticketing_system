"""Tests for format_llrs_with_verifications_for_prompt."""

from backend.requirements.formatting import format_llrs_with_verifications_for_prompt


def test_single_llr_no_verifications():
    """An LLR with no verifications formats cleanly."""
    llrs = [
        {"id": 1, "description": "The engine computes addition.", "hlr_id": 1},
    ]
    llr_verifications = {}  # no verifications for any LLR
    result = format_llrs_with_verifications_for_prompt(llrs, llr_verifications)
    assert "LLR 1: The engine computes addition." in result
    assert "Verifications" not in result


def test_single_llr_with_verification():
    """An LLR with one verification includes method, test_name, and description."""
    llrs = [
        {"id": 1, "description": "The engine computes addition.", "hlr_id": 1},
    ]
    llr_verifications = {
        1: [
            {
                "method": "automated",
                "test_name": "test_compute_returns_sum",
                "description": "Verify that 2 + 3 returns 5.",
                "preconditions": [],
                "actions": [
                    {
                        "description": "Call compute(2, 3, '+')",
                        "callee_qualified_name": "calc::Engine::compute",
                        "caller_qualified_name": "TestSuite",
                    }
                ],
                "postconditions": [
                    {
                        "subject_qualified_name": "calc::Engine::result",
                        "operator": "==",
                        "expected_value": "5",
                        "object_qualified_name": "",
                    }
                ],
            }
        ],
    }
    result = format_llrs_with_verifications_for_prompt(llrs, llr_verifications)
    assert "[automated] test_compute_returns_sum" in result
    assert "Verify that 2 + 3 returns 5." in result
    assert "TestSuite → calc::Engine::compute" in result
    assert "calc::Engine::result == 5" in result


def test_llr_with_preconditions_and_object():
    """Preconditions and object_qualified_name are formatted correctly."""
    llrs = [
        {"id": 2, "description": "Engine validates input.", "hlr_id": 1},
    ]
    llr_verifications = {
        2: [
            {
                "method": "automated",
                "test_name": "test_validate_rejects_non_numeric",
                "description": "Verify non-numeric input is rejected.",
                "preconditions": [
                    {
                        "subject_qualified_name": "calc::Engine::initialized",
                        "operator": "is_true",
                        "expected_value": "",
                        "object_qualified_name": "",
                    }
                ],
                "actions": [
                    {
                        "description": "Call validate('abc')",
                        "callee_qualified_name": "calc::Engine::validate",
                        "caller_qualified_name": "",
                    }
                ],
                "postconditions": [
                    {
                        "subject_qualified_name": "calc::Engine::errorState",
                        "operator": "==",
                        "expected_value": "INVALID_INPUT",
                        "object_qualified_name": "calc::ErrorType::INVALID_INPUT",
                    }
                ],
            }
        ],
    }
    result = format_llrs_with_verifications_for_prompt(llrs, llr_verifications)
    assert "Pre-conditions:" in result
    assert "calc::Engine::initialized is_true" in result
    assert "calc::Engine::errorState == INVALID_INPUT" in result
    assert "calc::ErrorType::INVALID_INPUT" in result


def test_empty_conditions_and_actions():
    """Verification with no preconditions, actions, or postconditions shows (none)."""
    llrs = [
        {"id": 3, "description": "Engine returns immediately.", "hlr_id": 1},
    ]
    llr_verifications = {
        3: [
            {
                "method": "inspection",
                "test_name": "test_immediate_response",
                "description": "Verify synchronous response.",
                "preconditions": [],
                "actions": [],
                "postconditions": [],
            }
        ],
    }
    result = format_llrs_with_verifications_for_prompt(llrs, llr_verifications)
    assert "[inspection] test_immediate_response" in result
    assert "(none)" in result


def test_multiple_llrs():
    """Multiple LLRs are formatted sequentially."""
    llrs = [
        {"id": 1, "description": "First LLR.", "hlr_id": 1},
        {"id": 2, "description": "Second LLR.", "hlr_id": 1},
    ]
    llr_verifications = {
        1: [
            {
                "method": "automated",
                "test_name": "test_first_llr",
                "description": "Verify first.",
                "preconditions": [],
                "actions": [],
                "postconditions": [],
            }
        ],
        2: [
            {
                "method": "automated",
                "test_name": "test_second_llr",
                "description": "Verify second.",
                "preconditions": [],
                "actions": [],
                "postconditions": [],
            }
        ],
    }
    result = format_llrs_with_verifications_for_prompt(llrs, llr_verifications)
    assert "LLR 1: First LLR." in result
    assert "LLR 2: Second LLR." in result
    assert "test_first_llr" in result
    assert "test_second_llr" in result