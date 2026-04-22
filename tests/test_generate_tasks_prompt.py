"""Tests for backend.ticketing_agent.generate_tasks_prompt."""

from backend.ticketing_agent.generate_tasks_prompt import build_task_context


def test_build_task_context_produces_markdown():
    """Context should contain sections for classes and verifications."""
    context = build_task_context(
        classes=[
            {
                "name": "Calculator",
                "module": "calc",
                "description": "Main calculator class",
                "methods": [
                    {
                        "name": "add",
                        "parameters": ["a", "b"],
                        "return_type": "float",
                        "visibility": "public",
                    },
                ],
            },
        ],
        verifications=[
            {
                "method": "automated",
                "test_name": "test_add_two_integers",
                "description": "Verify addition works",
            },
        ],
        existing_classes=[],
    )
    assert "## OO Class Design" in context
    assert "Calculator" in context
    assert "add" in context
    assert "## Verification Methods" in context
    assert "test_add_two_integers" in context


def test_build_task_context_includes_existing():
    context = build_task_context(
        classes=[],
        verifications=[],
        existing_classes=[{"qualified_name": "calc::BaseOps"}],
    )
    assert "## Existing Classes" in context
    assert "calc::BaseOps" in context


def test_build_task_context_includes_inheritance():
    context = build_task_context(
        classes=[{
            "name": "ScientificCalc",
            "inherits_from": ["Calculator"],
            "module": "calc.scientific",
            "methods": [],
        }],
        verifications=[],
        existing_classes=[],
    )
    assert "Inherits: Calculator" in context


def test_build_task_context_includes_requirements():
    context = build_task_context(
        classes=[{
            "name": "Foo",
            "module": "m",
            "methods": [],
            "requirement_ids": ["hlr:1", "llr:3"],
        }],
        verifications=[],
        existing_classes=[],
    )
    assert "Requirements: hlr:1, llr:3" in context


def test_build_task_context_verification_details():
    context = build_task_context(
        classes=[],
        verifications=[{
            "method": "automated",
            "test_name": "test_div_zero",
            "description": "Division by zero",
            "preconditions": ["divisor != 0"],
            "actions": ["call divide(10, 0)"],
            "postconditions": ["error raised"],
        }],
        existing_classes=[],
    )
    assert "Pre-conditions" in context
    assert "divisor != 0" in context
    assert "Actions" in context
    assert "Post-conditions" in context
    assert "error raised" in context


def test_build_task_context_empty():
    context = build_task_context([], [], [])
    assert "## OO Class Design" in context
    assert "## Verification Methods" in context
