"""Tests for combined design+verify tool dispatcher."""

import json
import pytest
from unittest.mock import MagicMock

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

class TestQnameResolves:
    def test_resolves_in_draft_lookup(self):
        """_qname_resolves finds qname in draft lookup."""
        from backend.ticketing_agent.design_verify.combined_tools import _qname_resolves
        draft_lookup = {"ns::Calculator": {"kind": "class"}}
        assert _qname_resolves("ns::Calculator", draft_lookup=draft_lookup) is True

    def test_resolves_in_prior_lookup_values(self):
        """_qname_resolves finds qname as a value in prior_class_lookup."""
        from backend.ticketing_agent.design_verify.combined_tools import _qname_resolves
        prior_lookup = {"Calculator": "ns::Calculator"}
        assert _qname_resolves("ns::Calculator", prior_class_lookup=prior_lookup) is True

    def test_resolves_in_prior_lookup_keys(self):
        """_qname_resolves finds qname as a key in prior_class_lookup."""
        from backend.ticketing_agent.design_verify.combined_tools import _qname_resolves
        prior_lookup = {"Calculator": "ns::Calculator"}
        assert _qname_resolves("Calculator", prior_class_lookup=prior_lookup) is True

    def test_resolves_in_dep_lookup(self):
        """_qname_resolves finds qname in dependency lookup."""
        from backend.ticketing_agent.design_verify.combined_tools import _qname_resolves
        dep_lookup = {"std::vector": "std::vector"}
        assert _qname_resolves("std::vector", dep_lookup=dep_lookup) is True

    def test_resolves_in_intercomponent(self):
        """_qname_resolves finds qname in intercomponent classes."""
        from backend.ticketing_agent.design_verify.combined_tools import _qname_resolves
        ic = [{"qualified_name": "user_interface::Display"}]
        assert _qname_resolves("user_interface::Display", intercomponent_classes=ic) is True

    def test_returns_false_for_unknown(self):
        """_qname_resolves returns False for unknown qnames."""
        from backend.ticketing_agent.design_verify.combined_tools import _qname_resolves
        assert _qname_resolves("ns::NonExistent") is False


class TestSuggestQname:
    def test_suggests_bare_name_match(self):
        """_suggest_qname finds match by bare name in prior/dep lookup."""
        from backend.ticketing_agent.design_verify.combined_tools import _suggest_qname
        result = _suggest_qname(
            "Calculator",
            draft_lookup={},
            prior_class_lookup={"Calculator": "calculation_engine::Calculator"},
            dep_lookup={},
            intercomponent_classes=[],
        )
        assert result == "calculation_engine::Calculator"

    def test_suggests_member_name_match(self):
        """_suggest_qname finds match by member name in draft lookup."""
        from backend.ticketing_agent.design_verify.combined_tools import _suggest_qname
        draft_lookup = {
            "calculation_engine::Calculator": {"kind": "class"},
            "calculation_engine::Calculator::add": {"kind": "method"},
        }
        result = _suggest_qname(
            "add",
            draft_lookup=draft_lookup,
            prior_class_lookup={},
            dep_lookup={},
            intercomponent_classes=[],
        )
        assert result == "calculation_engine::Calculator::add"

    def test_strips_stub_suffixes(self):
        """_suggest_qname strips .output/.result/.return_value before matching."""
        from backend.ticketing_agent.design_verify.combined_tools import _suggest_qname
        result = _suggest_qname(
            "Calculator.add.output",
            draft_lookup={
                "calculation_engine::Calculator::add": {"kind": "method"},
            },
            prior_class_lookup={},
            dep_lookup={},
            intercomponent_classes=[],
        )
        assert result == "calculation_engine::Calculator::add"

    def test_returns_none_for_no_match(self):
        """_suggest_qname returns None when no match found."""
        from backend.ticketing_agent.design_verify.combined_tools import _suggest_qname
        result = _suggest_qname(
            "CompletelyUnknown",
            draft_lookup={},
            prior_class_lookup={},
            dep_lookup={},
            intercomponent_classes=[],
        )
        assert result is None

    def test_substring_match(self):
        """_suggest_qname finds partial matches via substring."""
        from backend.ticketing_agent.design_verify.combined_tools import _suggest_qname
        draft_lookup = {"calculation_engine::CalculationResult": {"kind": "class"}}
        result = _suggest_qname(
            "CalculationResult",
            draft_lookup=draft_lookup,
            prior_class_lookup={},
            dep_lookup={},
            intercomponent_classes=[],
        )
        assert result == "calculation_engine::CalculationResult"


class TestDiscoveryToolDispatch:
    """Test that discovery tool calls route through the toolset correctly."""

    def test_search_symbols_dispatches_to_toolset(self):
        """search_symbols should call toolset.search_symbols and return results."""
        mock_toolset = MagicMock()
        mock_toolset.search_symbols.return_value = [
            {"qualified_name": "Fl_Window", "kind": "class", "source": "fltk", "score": 10.0},
        ]

        dispatch = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            toolset=mock_toolset,
        )

        result = json.loads(dispatch("search_symbols", {"query": "window"}))
        mock_toolset.search_symbols.assert_called_once_with(query="window")

    def test_get_compound_dispatches_to_toolset(self):
        """get_compound should call toolset.get_compound with the name parameter."""
        mock_toolset = MagicMock()
        mock_toolset.get_compound.return_value = [
            {"qualified_name": "Fl_Window", "kind": "class"},
        ]

        dispatch = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            toolset=mock_toolset,
        )

        result = json.loads(dispatch("get_compound", {"name": "Fl_Window"}))
        mock_toolset.get_compound.assert_called_once_with(name="Fl_Window")

    def test_list_sources_dispatches_to_toolset(self):
        """list_sources should call toolset.list_sources."""
        mock_toolset = MagicMock()
        mock_toolset.list_sources.return_value = [
            {"source": "fltk", "node_type": "Compound", "count": 212},
        ]

        dispatch = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            toolset=mock_toolset,
        )

        result = json.loads(dispatch("list_sources", {}))
        mock_toolset.list_sources.assert_called_once_with()

    def test_browse_namespace_dispatches_to_toolset(self):
        """browse_namespace should call toolset.browse_namespace."""
        mock_toolset = MagicMock()
        mock_toolset.browse_namespace.return_value = [
            {"qualified_name": "Fl_Window", "kind": "class"},
        ]

        dispatch = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            toolset=mock_toolset,
        )

        result = json.loads(dispatch("browse_namespace", {"name": "Fl"}))
        mock_toolset.browse_namespace.assert_called_once_with(name="Fl")

    def test_find_inheritance_dispatches_to_toolset(self):
        """find_inheritance should call toolset.find_inheritance."""
        mock_toolset = MagicMock()
        mock_toolset.find_inheritance.return_value = [
            {"qualified_name": "Fl_Group", "kind": "class", "direction": "up"},
        ]

        dispatch = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            toolset=mock_toolset,
        )

        result = json.loads(dispatch("find_inheritance", {"name": "Fl_Window"}))
        mock_toolset.find_inheritance.assert_called_once_with(name="Fl_Window")

    def test_discovery_without_toolset_returns_error(self):
        """When toolset is None, discovery tools should return a helpful error."""
        dispatch = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            toolset=None,
        )

        result = json.loads(dispatch("search_symbols", {"query": "window"}))
        assert "error" in result
        assert "not available" in result["error"]

    def test_discovery_tool_failure_returns_error(self):
        """If the toolset method raises, the dispatcher should return error JSON."""
        mock_toolset = MagicMock()
        mock_toolset.search_symbols.side_effect = RuntimeError("Neo4j down")

        dispatch = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            toolset=mock_toolset,
        )

        result = json.loads(dispatch("search_symbols", {"query": "window"}))
        assert "error" in result

    def test_slim_compound_strips_fields(self):
        """get_compound results should have 'detailed' and 'member_refid' stripped."""
        from backend.ticketing_agent.design_verify.combined_tools import _slim_compound
        records = [
            {"qualified_name": "Fl_Window", "detailed": "long text", "member_refid": "ref123", "name": "Fl_Window"},
            {"qualified_name": "Fl_Button", "member_brief": "brief", "name": "Fl_Button"},
        ]
        slimmed = _slim_compound(records)
        assert all("detailed" not in r for r in slimmed)
        assert all("member_refid" not in r for r in slimmed)
        assert all("member_brief" not in r for r in slimmed)
        assert slimmed[0]["name"] == "Fl_Window"


class TestDraftVerifications:
    def test_draft_verifications_accepts_valid_references(self):
        """draft_verifications accepts verifications with references that exist in the draft."""
        dispatcher = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            neo4j_session=None,
        )
        # First draft a design so references can resolve
        dispatcher("draft_design", {"design": _minimal_design_dict()})

        result = json.loads(dispatcher("draft_verifications", {
            "verifications": {
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
                        "subject_qualified_name": "calculation_engine::Calculator::lastResult",
                        "operator": "==",
                        "expected_value": "5.0",
                    }],
                }]
            }
        }))
        assert result["valid"] is True
        assert result["errors"] == []
        assert "1" in result["verification_summary"]

    def test_draft_verifications_rejects_bad_qnames(self):
        """draft_verifications reports unresolved qname references."""
        dispatcher = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            neo4j_session=None,
        )
        dispatcher("draft_design", {"design": _minimal_design_dict()})

        result = json.loads(dispatcher("draft_verifications", {
            "verifications": {
                "1": [{
                    "method": "automated",
                    "test_name": "test_bad_ref",
                    "description": "Test with bad reference",
                    "preconditions": [{
                        "subject_qualified_name": "nonexistent::GhostClass",
                        "operator": "not_null",
                        "expected_value": "exists",
                    }],
                    "actions": [],
                    "postconditions": [],
                }]
            }
        }))
        assert result["valid"] is False
        assert any("GhostClass" in e for e in result["errors"])
        assert len(result["unresolved_details"]) > 0

    def test_draft_verifications_suggests_correction(self):
        """draft_verifications suggests corrections for near-miss qnames."""
        dispatcher = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            neo4j_session=None,
        )
        dispatcher("draft_design", {"design": _minimal_design_dict()})

        result = json.loads(dispatcher("draft_verifications", {
            "verifications": {
                "1": [{
                    "method": "automated",
                    "test_name": "test_suggestion",
                    "description": "Test with near-miss reference",
                    "preconditions": [{
                        "subject_qualified_name": "Calculator",
                        "operator": "not_null",
                        "expected_value": "exists",
                    }],
                    "actions": [],
                    "postconditions": [],
                }]
            }
        }))
        assert len(result["unresolved_details"]) > 0
        detail = result["unresolved_details"][0]
        assert detail["value"] == "Calculator"
        assert "suggestion" in detail
        assert "calculation_engine::Calculator" in detail["suggestion"]

    def test_draft_verifications_warns_about_unqualified_caller(self):
        """draft_verifications warns when caller_qualified_name is not a qname."""
        dispatcher = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            neo4j_session=None,
        )
        dispatcher("draft_design", {"design": _minimal_design_dict()})

        result = json.loads(dispatcher("draft_verifications", {
            "verifications": {
                "1": [{
                    "method": "automated",
                    "test_name": "test_caller",
                    "description": "Test with unqualified caller",
                    "preconditions": [],
                    "actions": [{
                        "description": "Call add",
                        "callee_qualified_name": "calculation_engine::Calculator::add",
                        "caller_qualified_name": "TestSuite",
                    }],
                    "postconditions": [],
                }]
            }
        }))
        assert any("TestSuite" in w for w in result["warnings"])

    def test_draft_verifications_warns_about_enum_in_expected_value(self):
        """draft_verifications warns when expected_value contains :: (possible design reference)."""
        dispatcher = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            neo4j_session=None,
        )
        dispatcher("draft_design", {"design": _minimal_design_dict()})

        result = json.loads(dispatcher("draft_verifications", {
            "verifications": {
                "1": [{
                    "method": "automated",
                    "test_name": "test_enum_ref",
                    "description": "Test with enum in expected_value",
                    "preconditions": [],
                    "actions": [{
                        "description": "Call add",
                        "callee_qualified_name": "calculation_engine::Calculator::add",
                    }],
                    "postconditions": [{
                        "subject_qualified_name": "calculation_engine::Calculator::lastResult",
                        "operator": "==",
                        "expected_value": "calculation_engine::CalculationError::invalid_input",
                    }],
                }]
            }
        }))
        assert any("::" in w and "expected_value" in w for w in result["warnings"])

    def test_draft_verifications_with_no_design_draft_warns(self):
        """draft_verifications warns when no design draft exists."""
        dispatcher = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            neo4j_session=None,
        )
        # No draft_design call — so no design draft exists

        result = json.loads(dispatcher("draft_verifications", {
            "verifications": {
                "1": [{
                    "method": "automated",
                    "test_name": "test_no_draft",
                    "description": "Test without draft",
                    "preconditions": [],
                    "actions": [{
                        "description": "Call add",
                        "callee_qualified_name": "calculation_engine::Calculator::add",
                    }],
                    "postconditions": [],
                }]
            }
        }))
        assert any("no design draft" in w.lower() for w in result["warnings"])

    def test_draft_verifications_strips_stub_suffix(self):
        """draft_verifications suggests corrections for stub-style references like 'CalculationEngine.add.output'."""
        dispatcher = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            neo4j_session=None,
        )
        dispatcher("draft_design", {"design": _minimal_design_dict()})

        result = json.loads(dispatcher("draft_verifications", {
            "verifications": {
                "1": [{
                    "method": "automated",
                    "test_name": "test_stub_ref",
                    "description": "Test with stub-style reference",
                    "preconditions": [],
                    "actions": [],
                    "postconditions": [{
                        "subject_qualified_name": "Calculator.add.output",
                        "operator": "==",
                        "expected_value": "5.0",
                    }],
                }]
            }
        }))
        # Should report unresolved with a suggestion
        assert result["valid"] is False
        details = result["unresolved_details"]
        assert len(details) > 0
        assert any("suggestion" in d for d in details)
