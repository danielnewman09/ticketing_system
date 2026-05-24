"""Integration test for the combined design+verify loop."""

import json
import pytest
from unittest.mock import patch, MagicMock

from backend.codebase.schemas import OODesignSchema
from backend.requirements.schemas import VerificationSchema, VerificationConditionSchema
from backend.ticketing_agent.design_verify.combined_loop import design_and_verify


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
    from backend.ticketing_agent.design_verify.combined_tools import make_combined_dispatcher

    hlr = {"id": 1, "description": "The calculator performs addition."}
    llrs = [{"id": 1, "description": "The engine shall add two numbers."}]

    # Simulate a tool loop where the agent first drafts a design, then commits
    dispatcher = make_combined_dispatcher(
        prior_class_lookup={},
        dependency_lookup=None,
        intercomponent_classes=None,
        neo4j_session=None,
    )

    # Step 1: Draft the design
    draft_result = json.loads(dispatcher("draft_design", {"design": _minimal_design_dict()}))
    assert draft_result["valid"] is True

    # Step 2: Commit with verification
    commit_result = json.loads(dispatcher(
        "commit_design_and_verifications",
        {
            "oo_design": _minimal_design_dict(),
            "verifications": {"1": [_minimal_verification_dict()]},
        },
    ))
    assert commit_result["committed"] is True


def test_combined_loop_rejects_unresolved_references():
    """Commit rejects when verifications reference non-existent design elements."""
    from backend.ticketing_agent.design_verify.combined_tools import make_combined_dispatcher

    dispatcher = make_combined_dispatcher(
        prior_class_lookup={},
        dependency_lookup=None,
        intercomponent_classes=None,
        neo4j_session=None,
    )

    # Draft a design without the referenced class
    dispatcher("draft_design", {"design": _minimal_design_dict()})

    # Try to commit with a verification referencing a non-existent class
    bad_verification = _minimal_verification_dict()
    bad_verification["preconditions"][0]["subject_qualified_name"] = "nonexistent::GhostClass"

    commit_result = json.loads(dispatcher(
        "commit_design_and_verifications",
        {
            "oo_design": _minimal_design_dict(),
            "verifications": {"1": [bad_verification]},
        },
    ))
    assert commit_result["committed"] is False
    assert any("GhostClass" in e for e in commit_result["errors"])