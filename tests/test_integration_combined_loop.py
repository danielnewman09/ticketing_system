"""Integration test for the combined design+verify loop."""

import json
import pytest
from unittest.mock import patch, MagicMock

from codegraph.diagram import ClassDiagram
from backend.requirements.schemas import VerificationSchema, VerificationConditionSchema, VerificationActionSchema
from backend.ticketing_agent.design_verify.combined_loop import design_and_verify
from backend.ticketing_agent.tools.design_verify import CombinedDispatcher


def _minimal_design_dict():
    return {
        "modules": ["calculation_engine"],
        "classes": [
            {
                "name": "Calculator",
                "module": "calculation_engine",
                "description": "Main calculator",
                "visibility": "public",
                "is_intercomponent": False,
                "requirement_ids": [],
                "attributes": [],
                "methods": [
                    {
                        "name": "add",
                        "description": "Add two numbers",
                        "visibility": "public",
                        "parameters": ["double a", "double b"],
                        "return_type": "double",
                    }
                ],
                "inherits_from": [],
                "realizes_interfaces": [],
            }
        ],
        "interfaces": [],
        "enums": [],
        "associations": [],
    }


def _minimal_verification_dict():
    return {
        "method": "automated",
        "test_name": "test_add",
        "description": "Test addition",
        "preconditions": [
            {
                "subject_qualified_name": "calculation_engine::Calculator",
                "operator": "not_null",
                "expected_value": "exists",
            }
        ],
        "actions": [
            {
                "description": "Call add",
                "callee_qualified_name": "calculation_engine::Calculator::add",
            }
        ],
        "postconditions": [],
    }


def test_combined_loop_commits_valid_design_and_verifications():
    """The combined loop can commit a valid design + verification pair."""
    from backend.ticketing_agent.tools.design_verify import CombinedDispatcher

    hlr = {"id": 1, "description": "The calculator performs addition."}
    llrs = [{"id": 1, "description": "The engine shall add two numbers."}]

    # Simulate a tool loop where the agent first drafts a design, then commits
    dispatcher = CombinedDispatcher(
        prior_class_lookup={},
        dependency_lookup=None,
        intercomponent_classes=None,
        neo4j_session=None,
    )

    # Step 1: Draft the design
    draft_result = json.loads(dispatcher.dispatch("draft_design", {"design": _minimal_design_dict()}))
    assert draft_result["valid"] is True

    # Step 2: Commit with verification
    commit_result = json.loads(dispatcher.dispatch(
        "commit_design_and_verifications",
        {
            "oo_design": _minimal_design_dict(),
            "verifications": {"1": [_minimal_verification_dict()]},
        },
    ))
    assert commit_result["committed"] is True


def test_combined_loop_rejects_unresolved_references():
    """Commit rejects when verifications reference non-existent design elements."""
    from backend.ticketing_agent.tools.design_verify import CombinedDispatcher

    dispatcher = CombinedDispatcher(
        prior_class_lookup={},
        dependency_lookup=None,
        intercomponent_classes=None,
        neo4j_session=None,
    )

    # Draft a design without the referenced class
    dispatcher.dispatch("draft_design", {"design": _minimal_design_dict()})

    # Try to commit with a verification referencing a non-existent class
    bad_verification = _minimal_verification_dict()
    bad_verification["preconditions"][0]["subject_qualified_name"] = "nonexistent::GhostClass"

    commit_result = json.loads(dispatcher.dispatch(
        "commit_design_and_verifications",
        {
            "oo_design": _minimal_design_dict(),
            "verifications": {"1": [bad_verification]},
        },
    ))
    assert commit_result["committed"] is False
    assert any("GhostClass" in e for e in commit_result["errors"])


def test_commit_tool_uses_string_llr_ids():
    """Commit result always uses string LLR ID keys."""
    from backend.ticketing_agent.tools.design_verify import CombinedDispatcher

    dispatcher = CombinedDispatcher(
        prior_class_lookup={},
        dependency_lookup=None,
        intercomponent_classes=None,
        neo4j_session=None,
    )

    dispatcher.dispatch("draft_design", {"design": _minimal_design_dict()})

    commit_result = json.loads(dispatcher.dispatch(
        "commit_design_and_verifications",
        {
            "oo_design": _minimal_design_dict(),
            "verifications": {"1": [_minimal_verification_dict()]},
        },
    ))
    assert commit_result["committed"] is True
    assert "1" in commit_result["verifications"]


def test_design_verify_warns_about_unqualified_caller():
    """design_and_verify adds warnings for caller_qualified_name without :: separators."""
    from backend.ticketing_agent.design_verify.combined_loop import _collect_verification_warnings

    verifications = {
        1: [VerificationSchema(
            method="automated",
            test_name="test_call",
            description="Test",
            preconditions=[],
            actions=[VerificationActionSchema(
                description="Call method",
                callee_qualified_name="calculation_engine::Calculator::add",
                caller_qualified_name="TestSuite",
            )],
            postconditions=[],
        )]
    }
    warnings = _collect_verification_warnings(verifications)
    assert any("TestSuite" in w and "not a valid qualified name" in w for w in warnings)


def test_draft_verifications_then_commit_workflow():
    """Full workflow: draft design -> draft_verifications -> commit."""
    dispatcher = CombinedDispatcher(
        prior_class_lookup={},
        dependency_lookup=None,
        intercomponent_classes=None,
        neo4j_session=None,
    )

    # Step 1: Draft the design
    draft_result = json.loads(dispatcher.dispatch("draft_design", {"design": _minimal_design_dict()}))
    assert draft_result["valid"] is True

    # Step 2: Draft verifications with unresolved references
    bad_verifs = {
        "1": [{
            "method": "automated",
            "test_name": "test_add_bad_ref",
            "description": "Test with placeholder reference",
            "preconditions": [],
            "actions": [{
                "description": "Call add",
                "callee_qualified_name": "Calculator.add",
            }],
            "postconditions": [{
                "subject_qualified_name": "Calculator.add.output",
                "operator": "==",
                "expected_value": "5.0",
            }],
        }]
    }
    draft_verif_result = json.loads(dispatcher.dispatch("draft_verifications", {"verifications": bad_verifs}))
    assert draft_verif_result["valid"] is False
    assert len(draft_verif_result["unresolved_details"]) >= 2  # callee + subject
    # Should have suggestions
    suggestions = [d for d in draft_verif_result["unresolved_details"] if "suggestion" in d]
    assert len(suggestions) >= 1

    # Step 3: Re-draft with resolved references
    good_verifs = {
        "1": [{
            "method": "automated",
            "test_name": "test_add",
            "description": "Test addition",
            "preconditions": [],
            "actions": [{
                "description": "Call add",
                "callee_qualified_name": "calculation_engine::Calculator::add",
            }],
            "postconditions": [{
                "subject_qualified_name": "calculation_engine::Calculator",
                "operator": "not_null",
                "expected_value": "exists",
            }],
        }]
    }
    draft_verif_result2 = json.loads(dispatcher.dispatch("draft_verifications", {"verifications": good_verifs}))
    assert draft_verif_result2["valid"] is True
    assert draft_verif_result2["errors"] == []

    # Step 4: Commit with the resolved verifications
    commit_result = json.loads(dispatcher.dispatch(
        "commit_design_and_verifications",
        {
            "oo_design": _minimal_design_dict(),
            "verifications": good_verifs,
        },
    ))
    assert commit_result["committed"] is True