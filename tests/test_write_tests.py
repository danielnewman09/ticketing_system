"""Tests for the test writer — deterministic generation and prompt context."""

from backend.ticketing_agent.write_tests_prompt import build_test_context
from backend.ticketing_agent.write_tests import generate_deterministic_tests, TestFileOutput


class TestBuildTestContext:
    def test_basic_context(self):
        context = build_test_context(
            verifications=[{
                "test_name": "test_add",
                "method": "automated",
                "description": "Add two numbers",
            }],
            llr_id=1,
            llr_description="Calculator performs arithmetic",
            module_path="src.calculator.engine",
        )
        assert "LLR 1" in context
        assert "test_add" in context
        assert "src.calculator.engine" in context

    def test_full_verification(self):
        context = build_test_context(
            verifications=[{
                "test_name": "test_divide_by_zero",
                "method": "automated",
                "description": "Division by zero raises error",
                "preconditions": ["divisor == 0"],
                "actions": ["call engine.divide(10, 0)"],
                "postconditions": ["ZeroDivisionError raised"],
            }],
            llr_id=2,
            llr_description="Error handling",
        )
        assert "preconditions" in context
        assert "divisor == 0" in context
        assert "actions" in context
        assert "postconditions" in context
        assert "ZeroDivisionError raised" in context

    def test_with_skeleton_files(self):
        context = build_test_context(
            verifications=[],
            skeleton_files=["src/calculator/engine.py"],
            llr_id=1,
        )
        assert "src/calculator/engine.py" in context


class TestDeterministicTests:
    def test_generates_valid_test_file(self):
        results = generate_deterministic_tests(
            verifications=[{
                "test_name": "test_add_two_integers",
                "method": "automated",
                "description": "Add two integers",
                "preconditions": ["a=1, b=2"],
                "actions": ["call calc.add(1, 2)"],
                "postconditions": ["result == 3"],
            }],
            module_path="src.calculator.engine",
            llr_id=1,
            llr_description="Performs arithmetic",
        )
        assert len(results) == 1
        assert results[0].test_names == ["test_add_two_integers"]
        assert "import pytest" in results[0].content
        assert "def test_add_two_integers():" in results[0].content
        assert '"""LLR 1: Add two integers."""' in results[0].content
        assert "Arrange:" in results[0].content
        assert "Act" in results[0].content
        assert "Assert:" in results[0].content

    def test_empty_verifications(self):
        results = generate_deterministic_tests([])
        assert results == []

    def test_multiple_verifications(self):
        results = generate_deterministic_tests(
            verifications=[
                {
                    "test_name": "test_add",
                    "method": "automated",
                    "description": "Add",
                    "postconditions": ["result correct"],
                },
                {
                    "test_name": "test_subtract",
                    "method": "automated",
                    "description": "Subtract",
                    "postconditions": ["result correct"],
                },
            ],
            module_path="src.calc",
            llr_id=3,
        )
        assert len(results) == 1
        assert results[0].test_names == ["test_add", "test_subtract"]
        assert "def test_add():" in results[0].content
        assert "def test_subtract():" in results[0].content

    def test_generated_code_is_valid_python(self):
        results = generate_deterministic_tests(
            verifications=[{
                "test_name": "test_valid",
                "method": "automated",
                "description": "Valid test",
                "preconditions": [],
                "actions": [],
                "postconditions": ["assertTrue"],
            }],
            llr_id=1,
        )
        # Verify the generated code is syntactically valid
        compile(results[0].content, results[0].file_path, "exec")
