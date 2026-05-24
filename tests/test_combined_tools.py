"""Tests for combined design+verify tool dispatcher."""

import json
import pytest

from backend.codebase.schemas import OODesignSchema
from backend.requirements.schemas import (
    VerificationSchema,
    VerificationConditionSchema,
    VerificationActionSchema,
)
from backend.ticketing_agent.design_verify.combined_tools import (
    ALL_TOOLS,
    make_combined_dispatcher,
)


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
                "attributes": [
                    {
                        "name": "lastResult",
                        "type_name": "CalculationResult",
                        "visibility": "private",
                        "description": "Last result",
                    }
                ],
                "methods": [
                    {
                        "name": "add",
                        "description": "Add two numbers",
                        "visibility": "public",
                        "parameters": ["double a", "double b"],
                        "return_type": "CalculationResult",
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


def _minimal_design():
    return OODesignSchema.model_validate(_minimal_design_dict())


def _sample_verification():
    return VerificationSchema(
        method="automated",
        test_name="test_calc_add",
        description="Test addition",
        preconditions=[
            VerificationConditionSchema(
                subject_qualified_name="calculation_engine::Calculator",
                operator="not_null",
                expected_value="exists",
            )
        ],
        actions=[
            VerificationActionSchema(
                description="Call add method",
                callee_qualified_name="calculation_engine::Calculator::add",
            )
        ],
        postconditions=[],
    )


class TestDraftDesign:
    def test_draft_design_stores_and_validates(self):
        """draft_design stores a design and returns validation results."""
        dispatcher = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            neo4j_session=None,
        )
        result = json.loads(dispatcher("draft_design", {"design": _minimal_design_dict()}))
        assert result["valid"] is True
        assert result["errors"] == []
        assert result["draft_summary"]["classes"] == 1

    def test_draft_design_validates_associations(self):
        """draft_design catches unknown association targets."""
        design = _minimal_design_dict()
        design["associations"] = [
            {
                "from_class": "Calculator",
                "to_class": "NonExistentClass",
                "kind": "depends_on",
                "description": "Missing dependency",
            }
        ]
        dispatcher = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            neo4j_session=None,
        )
        result = json.loads(dispatcher("draft_design", {"design": design}))
        assert result["valid"] is False
        assert any("NonExistentClass" in e for e in result["errors"])

    def test_draft_design_returns_member_count(self):
        """draft_design summary includes attribute and method counts."""
        dispatcher = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            neo4j_session=None,
        )
        result = json.loads(dispatcher("draft_design", {"design": _minimal_design_dict()}))
        summary = result["draft_summary"]
        assert summary["attributes"] == 1
        assert summary["methods"] == 1


class TestLookupDesignElement:
    def test_lookup_finds_draft_class(self):
        """lookup_design_element finds classes in the draft."""
        dispatcher = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            neo4j_session=None,
        )
        # Store a draft first
        dispatcher("draft_design", {"design": _minimal_design_dict()})
        result = json.loads(dispatcher("lookup_design_element", {"name": "Calculator"}))
        assert len(result["elements"]) >= 1
        matches = [e for e in result["elements"] if e["source"] == "draft"]
        assert len(matches) >= 1
        assert matches[0]["qualified_name"] == "calculation_engine::Calculator"

    def test_lookup_finds_draft_method(self):
        """lookup_design_element finds methods in the draft."""
        dispatcher = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            neo4j_session=None,
        )
        dispatcher("draft_design", {"design": _minimal_design_dict()})
        result = json.loads(dispatcher("lookup_design_element", {"name": "add"}))
        methods = [e for e in result["elements"] if e["kind"] == "method" and e["source"] == "draft"]
        assert len(methods) >= 1
        assert methods[0]["qualified_name"] == "calculation_engine::Calculator::add"

    def test_lookup_finds_draft_attribute(self):
        """lookup_design_element finds attributes in the draft."""
        dispatcher = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            neo4j_session=None,
        )
        dispatcher("draft_design", {"design": _minimal_design_dict()})
        result = json.loads(dispatcher("lookup_design_element", {"name": "lastResult"}))
        attrs = [e for e in result["elements"] if e["kind"] == "attribute" and e["source"] == "draft"]
        assert len(attrs) >= 1
        assert attrs[0]["qualified_name"] == "calculation_engine::Calculator::lastResult"


class TestValidateQualifiedNames:
    def test_validate_draft_qnames_exist(self):
        """validate_qualified_names finds draft references as existing."""
        dispatcher = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            neo4j_session=None,
        )
        dispatcher("draft_design", {"design": _minimal_design_dict()})
        result = json.loads(dispatcher(
            "validate_qualified_names",
            {"qualified_names": ["calculation_engine::Calculator", "calculation_engine::Calculator::add"]},
        ))
        assert result["results"][0]["valid"] is True
        assert result["results"][0]["exists"] is True
        assert result["results"][0]["source"] == "draft"
        assert result["results"][1]["valid"] is True
        assert result["results"][1]["exists"] is True

    def test_validate_nonexistent_qname(self):
        """validate_qualified_names reports non-existent references."""
        dispatcher = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            neo4j_session=None,
        )
        dispatcher("draft_design", {"design": _minimal_design_dict()})
        result = json.loads(dispatcher(
            "validate_qualified_names",
            {"qualified_names": ["calculation_engine::NonExistent"]},
        ))
        assert result["results"][0]["valid"] is True  # format is valid
        assert result["results"][0]["exists"] is False  # but doesn't exist

    def test_validate_rejects_non_qname_object(self):
        """validate_qualified_names rejects symbols in object_qualified_name."""
        dispatcher = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            neo4j_session=None,
        )
        result = json.loads(dispatcher(
            "validate_qualified_names",
            {"qualified_names": ["×"]},
        ))
        assert result["results"][0]["valid"] is False


class TestCommitDesignAndVerifications:
    def test_commit_rejects_invalid_qname(self):
        """commit_design_and_verifications rejects with invalid qnames."""
        dispatcher = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            neo4j_session=None,
        )
        # Draft a design
        dispatcher("draft_design", {"design": _minimal_design_dict()})

        bad_verification = VerificationSchema(
            method="automated",
            test_name="test_bad",
            description="Bad qname test",
            preconditions=[
                VerificationConditionSchema(
                    subject_qualified_name="nonexistent::Class",
                    operator="not_null",
                    expected_value="exists",
                )
            ],
            actions=[],
            postconditions=[],
        )
        result = json.loads(dispatcher(
            "commit_design_and_verifications",
            {
                "oo_design": _minimal_design_dict(),
                "verifications": {"1": [bad_verification.model_dump()]},
            },
        ))
        assert result["committed"] is False
        assert len(result["errors"]) > 0

    def test_commit_accepts_valid(self):
        """commit_design_and_verifications accepts valid input."""
        dispatcher = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            neo4j_session=None,
        )
        # Draft a design first
        dispatcher("draft_design", {"design": _minimal_design_dict()})

        good_verification = VerificationSchema(
            method="automated",
            test_name="test_add",
            description="Test addition",
            preconditions=[
                VerificationConditionSchema(
                    subject_qualified_name="calculation_engine::Calculator",
                    operator="not_null",
                    expected_value="exists",
                )
            ],
            actions=[
                VerificationActionSchema(
                    description="Call add",
                    callee_qualified_name="calculation_engine::Calculator::add",
                )
            ],
            postconditions=[],
        )
        result = json.loads(dispatcher(
            "commit_design_and_verifications",
            {
                "oo_design": _minimal_design_dict(),
                "verifications": {"1": [good_verification.model_dump()]},
            },
        ))
        assert result["committed"] is True