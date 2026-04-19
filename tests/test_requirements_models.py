"""Tests for HighLevelRequirement, LowLevelRequirement, TicketRequirement models
and their dict-formatting helper functions.
"""

import pytest
from sqlalchemy.exc import IntegrityError

from backend.db.models.requirements import (
    HighLevelRequirement,
    LowLevelRequirement,
    TicketRequirement,
    format_hlr_dict,
    format_hlrs_for_prompt,
    format_llr_dict,
)
from backend.db.models.components import Component, Language
from backend.db.models.tickets import Ticket


# ---------------------------------------------------------------------------
# HighLevelRequirement
# ---------------------------------------------------------------------------


class TestHighLevelRequirement:
    """ORM and business logic for HighLevelRequirement."""

    def test_create_hlr_minimal(self, session):
        hlr = HighLevelRequirement(description="The system shall be fast")
        session.add(hlr)
        session.flush()
        assert hlr.id is not None
        assert hlr.description == "The system shall be fast"
        assert hlr.component_id is None
        assert hlr.dependency_context is None

    def test_create_hlr_with_component(self, seeded_session):
        comp = seeded_session.query(Component).first()
        hlr = HighLevelRequirement(
            description="The system shall perform arithmetic operations",
            component=comp,
        )
        seeded_session.add(hlr)
        seeded_session.flush()
        assert hlr.component_id == comp.id
        assert hlr.component.name == "Calculator"

    def test_create_hlr_with_dependency_context(self, session):
        ctx = {"depends_on": ["mod_a", "mod_b"], "priority": 1}
        hlr = HighLevelRequirement(
            description="The system shall handle dependencies",
            dependency_context=ctx,
        )
        session.add(hlr)
        session.flush()
        assert hlr.dependency_context == ctx

    def test_repr_with_description(self, session):
        hlr = HighLevelRequirement(description="Short desc")
        session.add(hlr)
        session.flush()
        assert repr(hlr) == "Short desc"

    def test_repr_with_long_description(self, session):
        long_desc = "A" * 120
        hlr = HighLevelRequirement(description=long_desc)
        session.add(hlr)
        session.flush()
        assert repr(hlr) == long_desc[:80]

    def test_repr_without_description(self, session):
        # Flush to get auto-increment id; description is NOT NULL at DB level,
        # but we can test __repr__ logic by constructing in-memory.
        hlr = HighLevelRequirement(description="placeholder")
        session.add(hlr)
        session.flush()
        # Override description to empty string to test the else-branch
        # (can't set to None due to NOT NULL constraint)
        hlr.description = ""
        assert repr(hlr) == f"HLR {hlr.id}"

    def test_to_prompt_text_basic(self, seeded_session):
        comp = seeded_session.query(Component).first()
        hlr = HighLevelRequirement(description="Perform arithmetic", component=comp)
        seeded_session.add(hlr)
        seeded_session.flush()
        text = hlr.to_prompt_text()
        assert text == f"HLR {hlr.id}: Perform arithmetic"

    def test_to_prompt_text_with_component(self, seeded_session):
        comp = seeded_session.query(Component).first()
        hlr = HighLevelRequirement(description="Perform arithmetic", component=comp)
        seeded_session.add(hlr)
        seeded_session.flush()
        text = hlr.to_prompt_text(include_component=True)
        assert text == f"HLR {hlr.id} [Component: Calculator]: Perform arithmetic"

    def test_to_prompt_text_component_without_component_id(self, seeded_session):
        hlr = HighLevelRequirement(description="No component needed")
        seeded_session.add(hlr)
        seeded_session.flush()
        text = hlr.to_prompt_text(include_component=True)
        # component_id is None, so no component annotation
        assert text == f"HLR {hlr.id}: No component needed"

    def test_to_prompt_text_with_llrs(self, seeded_session):
        hlr = HighLevelRequirement(description="Top-level requirement")
        seeded_session.add(hlr)
        seeded_session.flush()

        llr1 = LowLevelRequirement(
            description="Sub-requirement A",
            high_level_requirement=hlr,
        )
        llr2 = LowLevelRequirement(
            description="Sub-requirement B",
            high_level_requirement=hlr,
        )
        seeded_session.add_all([llr1, llr2])
        seeded_session.flush()

        text = hlr.to_prompt_text(include_llrs=True)
        assert f"HLR {hlr.id}: Top-level requirement" in text
        assert f"  LLR {llr1.id}: Sub-requirement A" in text
        assert f"  LLR {llr2.id}: Sub-requirement B" in text

    def test_hlr_low_level_requirements_relationship(self, seeded_session):
        hlr = HighLevelRequirement(description="Parent HLR")
        seeded_session.add(hlr)
        seeded_session.flush()

        llr = LowLevelRequirement(
            description="Child LLR", high_level_requirement=hlr
        )
        seeded_session.add(llr)
        seeded_session.flush()

        assert len(hlr.low_level_requirements) == 1
        assert hlr.low_level_requirements[0].description == "Child LLR"

    def test_hlr_component_set_null_on_delete(self, seeded_session):
        """When component is deleted, component_id should be SET NULL."""
        comp = seeded_session.query(Component).first()
        hlr = HighLevelRequirement(description="HLR with comp", component=comp)
        seeded_session.add(hlr)
        seeded_session.flush()
        hlr_id = hlr.id

        seeded_session.delete(comp)
        seeded_session.flush()

        refreshed = seeded_session.get(HighLevelRequirement, hlr_id)
        assert refreshed.component_id is None


# ---------------------------------------------------------------------------
# LowLevelRequirement
# ---------------------------------------------------------------------------


class TestLowLevelRequirement:
    """ORM and business logic for LowLevelRequirement."""

    def test_create_llr_minimal(self, session):
        llr = LowLevelRequirement(description="The module shall validate input")
        session.add(llr)
        session.flush()
        assert llr.id is not None
        assert llr.description == "The module shall validate input"
        assert llr.high_level_requirement_id is None

    def test_create_llr_with_hlr(self, seeded_session):
        hlr = seeded_session.query(HighLevelRequirement).first()
        llr = LowLevelRequirement(
            description="Validate numeric input",
            high_level_requirement=hlr,
        )
        seeded_session.add(llr)
        seeded_session.flush()
        assert llr.high_level_requirement_id == hlr.id

    def test_llr_repr_with_description(self, session):
        llr = LowLevelRequirement(description="Short LLR desc")
        session.add(llr)
        session.flush()
        assert repr(llr) == "Short LLR desc"

    def test_llr_repr_long_description(self, session):
        long_desc = "B" * 120
        llr = LowLevelRequirement(description=long_desc)
        session.add(llr)
        session.flush()
        assert repr(llr) == long_desc[:80]

    def test_llr_repr_empty_description(self, session):
        llr = LowLevelRequirement(description="temp")
        session.add(llr)
        session.flush()
        llr.description = ""
        assert repr(llr) == f"LLR {llr.id}"

    def test_llr_to_prompt_text_basic(self, session):
        llr = LowLevelRequirement(description="Validate input")
        session.add(llr)
        session.flush()
        text = llr.to_prompt_text()
        assert text == f"LLR {llr.id}: Validate input"

    def test_llr_to_prompt_text_with_verifications(self, seeded_session):
        from backend.db.models.verification import VerificationMethod

        hlr = seeded_session.query(HighLevelRequirement).first()
        llr = LowLevelRequirement(
            description="Validate numeric input",
            high_level_requirement=hlr,
        )
        seeded_session.add(llr)
        seeded_session.flush()

        vm = VerificationMethod(
            low_level_requirement_id=llr.id,
            method="automated",
            test_name="test_validate_input",
            description="Check that input is numeric",
        )
        seeded_session.add(vm)
        seeded_session.flush()

        text = llr.to_prompt_text(include_verifications=True)
        assert f"LLR {llr.id}: Validate numeric input" in text
        assert "automated" in text
        assert "test_validate_input" in text

    def test_llr_high_level_requirement_set_null_on_delete(self, seeded_session):
        """When HLR is deleted, LLR's high_level_requirement_id should be SET NULL."""
        hlr = HighLevelRequirement(description="To be deleted")
        seeded_session.add(hlr)
        seeded_session.flush()
        hlr_id = hlr.id

        llr = LowLevelRequirement(
            description="Orphaned LLR", high_level_requirement=hlr
        )
        seeded_session.add(llr)
        seeded_session.flush()
        llr_id = llr.id

        seeded_session.delete(hlr)
        seeded_session.flush()

        refreshed = seeded_session.get(LowLevelRequirement, llr_id)
        assert refreshed.high_level_requirement_id is None

    def test_llr_components_m2m(self, seeded_session):
        comp = seeded_session.query(Component).first()
        llr = LowLevelRequirement(description="LLR with component")
        llr.components.append(comp)
        seeded_session.add(llr)
        seeded_session.flush()

        assert comp in llr.components


# ---------------------------------------------------------------------------
# TicketRequirement
# ---------------------------------------------------------------------------


class TestTicketRequirement:
    """ORM and constraint tests for TicketRequirement."""

    def test_create_ticket_requirement(self, seeded_session):
        from backend.db.models.verification import VerificationMethod

        hlr = seeded_session.query(HighLevelRequirement).first()
        llr = LowLevelRequirement(
            description="LLR for ticket",
            high_level_requirement=hlr,
        )
        seeded_session.add(llr)
        seeded_session.flush()

        ticket = Ticket(title="Test ticket")
        seeded_session.add(ticket)
        seeded_session.flush()

        tr = TicketRequirement(
            ticket_id=ticket.id,
            low_level_requirement_id=llr.id,
        )
        seeded_session.add(tr)
        seeded_session.flush()
        assert tr.id is not None

    def test_ticket_requirement_repr(self, seeded_session):
        from backend.db.models.verification import VerificationMethod

        hlr = seeded_session.query(HighLevelRequirement).first()
        llr = LowLevelRequirement(
            description="LLR repr test",
            high_level_requirement=hlr,
        )
        seeded_session.add(llr)
        seeded_session.flush()

        ticket = Ticket(title="Repr ticket")
        seeded_session.add(ticket)
        seeded_session.flush()

        tr = TicketRequirement(
            ticket_id=ticket.id,
            low_level_requirement_id=llr.id,
        )
        seeded_session.add(tr)
        seeded_session.flush()

        assert repr(tr) == f"Ticket {ticket.id} -> LLR {llr.id}"

    def test_ticket_requirement_unique_constraint(self, seeded_session):
        """Duplicate ticket_id + low_level_requirement_id must raise IntegrityError."""
        hlr = seeded_session.query(HighLevelRequirement).first()
        llr = LowLevelRequirement(
            description="Unique LLR", high_level_requirement=hlr
        )
        seeded_session.add(llr)
        seeded_session.flush()

        ticket = Ticket(title="Unique constraint ticket")
        seeded_session.add(ticket)
        seeded_session.flush()

        tr1 = TicketRequirement(
            ticket_id=ticket.id, low_level_requirement_id=llr.id
        )
        seeded_session.add(tr1)
        seeded_session.flush()

        tr2 = TicketRequirement(
            ticket_id=ticket.id, low_level_requirement_id=llr.id
        )
        seeded_session.add(tr2)
        with pytest.raises(IntegrityError):
            seeded_session.flush()
        seeded_session.rollback()


# ---------------------------------------------------------------------------
# format_hlr_dict
# ---------------------------------------------------------------------------


class TestFormatHlrDict:
    """Unit tests for the format_hlr_dict helper."""

    def test_basic_format(self):
        hlr = {"id": 1, "description": "The system shall be fast"}
        result = format_hlr_dict(hlr)
        assert result == "HLR 1: The system shall be fast"

    def test_with_component_name(self):
        hlr = {
            "id": 5,
            "description": "Perform arithmetic",
            "component_name": "Calculator",
        }
        result = format_hlr_dict(hlr, include_component=True)
        assert result == "HLR 5 [Component: Calculator]: Perform arithmetic"

    def test_with_component__name_dunder(self):
        """Some query results use component__name (Django-style join)."""
        hlr = {
            "id": 5,
            "description": "Perform arithmetic",
            "component__name": "Calculator",
        }
        result = format_hlr_dict(hlr, include_component=True)
        assert result == "HLR 5 [Component: Calculator]: Perform arithmetic"

    def test_component_name_takes_precedence_over_dunder(self):
        hlr = {
            "id": 5,
            "description": "Test",
            "component_name": "Primary",
            "component__name": "Secondary",
        }
        result = format_hlr_dict(hlr, include_component=True)
        assert result == "HLR 5 [Component: Primary]: Test"

    def test_no_component_name_when_include_component_false(self):
        hlr = {
            "id": 1,
            "description": "Test",
            "component_name": "Calculator",
        }
        result = format_hlr_dict(hlr, include_component=False)
        assert result == "HLR 1: Test"

    def test_missing_component_name_shows_no_component(self):
        hlr = {"id": 1, "description": "No comp"}
        result = format_hlr_dict(hlr, include_component=True)
        assert result == "HLR 1: No comp"


# ---------------------------------------------------------------------------
# format_llr_dict
# ---------------------------------------------------------------------------


class TestFormatLlrDict:
    """Unit tests for the format_llr_dict helper."""

    def test_basic_format(self):
        llr = {"id": 10, "description": "Validate numeric input"}
        result = format_llr_dict(llr)
        assert result == "LLR 10: Validate numeric input"


# ---------------------------------------------------------------------------
# format_hlrs_for_prompt
# ---------------------------------------------------------------------------


class TestFormatHlrsForPrompt:
    """Unit tests for the format_hlrs_for_prompt helper."""

    def test_hlrs_only(self):
        hlrs = [
            {"id": 1, "description": "HLR one"},
            {"id": 2, "description": "HLR two"},
        ]
        result = format_hlrs_for_prompt(hlrs)
        assert "HLR 1: HLR one" in result
        assert "HLR 2: HLR two" in result

    def test_hlrs_with_linked_llrs(self):
        hlrs = [{"id": 1, "description": "HLR one"}]
        llrs = [
            {"id": 10, "description": "LLR for one", "hlr_id": 1},
        ]
        result = format_hlrs_for_prompt(hlrs, llrs=llrs)
        assert "HLR 1: HLR one" in result
        assert "  LLR 10: LLR for one" in result

    def test_hlrs_with_unlinked_llrs(self):
        hlrs = [{"id": 1, "description": "HLR one"}]
        llrs = [
            {"id": 10, "description": "Linked", "hlr_id": 1},
            {"id": 11, "description": "Unlinked", "hlr_id": None},
        ]
        result = format_hlrs_for_prompt(hlrs, llrs=llrs)
        assert "HLR 1: HLR one" in result
        assert "  LLR 10: Linked" in result
        assert "\nUnlinked LLRs:" in result
        assert "  LLR 11: Unlinked" in result

    def test_no_unlinked_llrs_no_separator(self):
        hlrs = [{"id": 1, "description": "HLR one"}]
        llrs = [{"id": 10, "description": "Linked", "hlr_id": 1}]
        result = format_hlrs_for_prompt(hlrs, llrs=llrs)
        assert "Unlinked LLRs" not in result

    def test_with_include_component(self):
        hlrs = [
            {"id": 1, "description": "HLR one", "component_name": "Calc"},
        ]
        result = format_hlrs_for_prompt(hlrs, include_component=True)
        assert "HLR 1 [Component: Calc]: HLR one" in result

    def test_llrs_only_no_hlrs(self):
        result = format_hlrs_for_prompt([], llrs=[{"id": 5, "description": "Orphan", "hlr_id": None}])
        assert "Unlinked LLRs:" in result
        assert "  LLR 5: Orphan" in result

    def test_empty_inputs(self):
        result = format_hlrs_for_prompt([])
        assert result == ""

    def test_hlrs_only_no_llrs(self):
        hlrs = [{"id": 1, "description": "HLR one"}]
        result = format_hlrs_for_prompt(hlrs)
        assert result == "HLR 1: HLR one"