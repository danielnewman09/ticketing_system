"""
Tests for Pydantic schemas in the review prompt modules.

Covers: DesignChallenge, DesignChallengeResult (challenge_design_prompt),
NodeResolution, ConflictReviewResult (review_node_conflict_prompt),
ProposedHLR, HLRReviewResult (review_hlrs_prompt).
"""

import pytest
from pydantic import ValidationError

from backend.ticketing_agent.review.challenge_design_prompt import (
    DesignChallenge,
    DesignChallengeResult,
)
from backend.ticketing_agent.review.review_hlrs_prompt import (
    HLRReviewResult,
    ProposedHLR,
)
from backend.ticketing_agent.review.review_node_conflict_prompt import (
    ConflictReviewResult,
    NodeResolution,
)


# ---------------------------------------------------------------------------
# DesignChallenge
# ---------------------------------------------------------------------------

class TestDesignChallenge:
    def test_minimal(self):
        dc = DesignChallenge(
            category="cohesion",
            severity="major",
            description="Module has too many responsibilities",
            remedy_type="split_hlr",
            suggested_remedy="Split into separate modules",
        )
        assert dc.category == "cohesion"
        assert dc.severity == "major"
        assert dc.affected_hlr_ids == []
        assert dc.affected_llr_ids == []
        assert dc.affected_node_qualified_names == []

    def test_all_fields(self):
        dc = DesignChallenge(
            category="coupling",
            severity="critical",
            description="Tight coupling between modules",
            affected_hlr_ids=[1, 3],
            affected_llr_ids=[5, 7],
            affected_node_qualified_names=["A::B", "A::C"],
            remedy_type="restructure_ontology",
            suggested_remedy="Introduce an abstraction layer",
        )
        assert dc.affected_hlr_ids == [1, 3]
        assert dc.affected_node_qualified_names == ["A::B", "A::C"]

    def test_all_categories(self):
        for cat in ("cohesion", "coupling", "orphan", "testability", "granularity", "class_design"):
            dc = DesignChallenge(
                category=cat, severity="minor", description="x",
                remedy_type="no_action", suggested_remedy="none",
            )
            assert dc.category == cat

    def test_invalid_category(self):
        with pytest.raises(ValidationError):
            DesignChallenge(
                category="performance", severity="minor", description="x",
                remedy_type="no_action", suggested_remedy="none",
            )

    def test_all_severities(self):
        for sev in ("critical", "major", "minor"):
            dc = DesignChallenge(
                category="cohesion", severity=sev, description="x",
                remedy_type="no_action", suggested_remedy="none",
            )
            assert dc.severity == sev

    def test_invalid_severity(self):
        with pytest.raises(ValidationError):
            DesignChallenge(
                category="cohesion", severity="low", description="x",
                remedy_type="no_action", suggested_remedy="none",
            )

    def test_all_remedy_types(self):
        for rt in ("split_hlr", "merge_llrs", "add_llr", "remove_llr", "restructure_ontology", "no_action"):
            dc = DesignChallenge(
                category="orphan", severity="minor", description="x",
                remedy_type=rt, suggested_remedy="none",
            )
            assert dc.remedy_type == rt

    def test_invalid_remedy_type(self):
        with pytest.raises(ValidationError):
            DesignChallenge(
                category="orphan", severity="minor", description="x",
                remedy_type="refactor_code", suggested_remedy="none",
            )


# ---------------------------------------------------------------------------
# DesignChallengeResult
# ---------------------------------------------------------------------------

class TestDesignChallengeResult:
    def test_empty_challenges(self):
        result = DesignChallengeResult(challenges=[])
        assert result.challenges == []

    def test_with_challenges(self):
        result = DesignChallengeResult(
            challenges=[
                DesignChallenge(
                    category="testability", severity="minor", description="Hard to test",
                    remedy_type="add_llr", suggested_remedy="Add testable LLR",
                ),
                DesignChallenge(
                    category="coupling", severity="major", description="Tightly coupled",
                    remedy_type="restructure_ontology", suggested_remedy="Decouple A from B",
                ),
            ]
        )
        assert len(result.challenges) == 2
        assert result.challenges[0].category == "testability"

    def test_round_trip(self):
        result = DesignChallengeResult(
            challenges=[
                DesignChallenge(
                    category="orphan", severity="critical", description="Unused node",
                    affected_node_qualified_names=["ns::Ghost"],
                    remedy_type="remove_llr", suggested_remedy="Remove orphan",
                )
            ]
        )
        data = result.model_dump()
        restored = DesignChallengeResult.model_validate(data)
        assert len(restored.challenges) == 1
        assert restored.challenges[0].affected_node_qualified_names == ["ns::Ghost"]


# ---------------------------------------------------------------------------
# NodeResolution
# ---------------------------------------------------------------------------

class TestNodeResolution:
    def test_minimal(self):
        nr = NodeResolution(
            proposed_qualified_name="gui::Button",
            existing_qualified_name="ui::Button",
            action="keep_proposed",
            winning_qualified_name="gui::Button",
            rationale="Better namespace scope",
        )
        assert nr.proposed_qualified_name == "gui::Button"
        assert nr.action == "keep_proposed"

    def test_all_actions(self):
        for action in ("keep_proposed", "keep_existing", "keep_both"):
            nr = NodeResolution(
                proposed_qualified_name="A",
                existing_qualified_name="B",
                action=action,
                winning_qualified_name="A",
                rationale="reason",
            )
            assert nr.action == action

    def test_invalid_action(self):
        with pytest.raises(ValidationError):
            NodeResolution(
                proposed_qualified_name="A",
                existing_qualified_name="B",
                action="merge",
                winning_qualified_name="A",
                rationale="reason",
            )

    def test_missing_fields(self):
        with pytest.raises(ValidationError):
            NodeResolution(proposed_qualified_name="A")  # missing required fields


# ---------------------------------------------------------------------------
# ConflictReviewResult
# ---------------------------------------------------------------------------

class TestConflictReviewResult:
    def test_empty(self):
        result = ConflictReviewResult(resolutions=[])
        assert result.resolutions == []

    def test_with_resolutions(self):
        result = ConflictReviewResult(
            resolutions=[
                NodeResolution(
                    proposed_qualified_name="ns::Widget",
                    existing_qualified_name="ns::OldWidget",
                    action="keep_proposed",
                    winning_qualified_name="ns::Widget",
                    rationale="More descriptive name",
                ),
                NodeResolution(
                    proposed_qualified_name="ns::Helper",
                    existing_qualified_name="ns::Helper",
                    action="keep_existing",
                    winning_qualified_name="ns::Helper",
                    rationale="No change needed",
                ),
            ]
        )
        assert len(result.resolutions) == 2
        assert result.resolutions[1].action == "keep_existing"

    def test_round_trip(self):
        result = ConflictReviewResult(
            resolutions=[
                NodeResolution(
                    proposed_qualified_name="A::B",
                    existing_qualified_name="A::C",
                    action="keep_both",
                    winning_qualified_name="A::B",
                    rationale="different abstractions",
                )
            ]
        )
        data = result.model_dump()
        restored = ConflictReviewResult.model_validate(data)
        assert restored.resolutions[0].action == "keep_both"


# ---------------------------------------------------------------------------
# ProposedHLR
# ---------------------------------------------------------------------------

class TestProposedHLR:
    def test_keep_action(self):
        ph = ProposedHLR(
            action="keep", original_id=1, description="System shall be fast", rationale="Looks good"
        )
        assert ph.action == "keep"
        assert ph.original_id == 1

    def test_add_action_no_original_id(self):
        ph = ProposedHLR(
            action="add", description="New requirement", rationale="Coverage gap"
        )
        assert ph.original_id is None  # default for new additions

    def test_all_actions(self):
        for action in ("keep", "modify", "add", "delete"):
            ph = ProposedHLR(
                action=action, description="test", rationale="reason"
            )
            assert ph.action == action

    def test_invalid_action(self):
        with pytest.raises(ValidationError):
            ProposedHLR(action="replace", description="test", rationale="reason")

    def test_missing_description(self):
        with pytest.raises(ValidationError):
            ProposedHLR(action="keep", rationale="reason")


# ---------------------------------------------------------------------------
# HLRReviewResult
# ---------------------------------------------------------------------------

class TestHLRReviewResult:
    def test_empty(self):
        result = HLRReviewResult(proposals=[])
        assert result.proposals == []

    def test_with_proposals(self):
        result = HLRReviewResult(
            proposals=[
                ProposedHLR(action="keep", original_id=1, description="Fast response", rationale="Well-scoped"),
                ProposedHLR(action="add", description="New requirement", rationale="Gap in coverage"),
                ProposedHLR(action="delete", original_id=3, description="Obsolete", rationale="No longer needed"),
            ]
        )
        assert len(result.proposals) == 3
        assert result.proposals[0].action == "keep"
        assert result.proposals[1].original_id is None

    def test_round_trip(self):
        result = HLRReviewResult(
            proposals=[
                ProposedHLR(
                    action="modify", original_id=2,
                    description="Updated text", rationale="Clarify scope"
                )
            ]
        )
        data = result.model_dump()
        restored = HLRReviewResult.model_validate(data)
        assert restored.proposals[0].action == "modify"
        assert restored.proposals[0].original_id == 2

    def test_json_round_trip(self):
        result = HLRReviewResult(
            proposals=[
                ProposedHLR(action="add", description="Backup", rationale="Disaster recovery")
            ]
        )
        json_str = result.model_dump_json()
        restored = HLRReviewResult.model_validate_json(json_str)
        assert restored.proposals[0].description == "Backup"