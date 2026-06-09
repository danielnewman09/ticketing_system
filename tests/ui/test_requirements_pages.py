"""NiceGUI User-simulation tests for the migrated requirements page.

Uses ``nicegui.testing.User`` (httpx + websocket simulation) to render
the /requirements page in-process with mocked Neo4j data — no running
server or browser needed.

Patches are applied **at the import site** (the page module) rather than
the definition site (the data module) so that ``asyncio.to_thread`` calls
see the mock.

Run with::

    pytest tests/ui/test_requirements_pages.py -v
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tests.ui.mocks import make_llr_dict
from tests.ui.conftest import PATCH_TARGETS as P

# ---------------------------------------------------------------------------
# Mock data helpers
# ---------------------------------------------------------------------------


def make_requirements_data(
    *,
    total_hlrs: int = 0,
    total_llrs: int = 0,
    total_verifications: int = 0,
    total_nodes: int = 0,
    total_triples: int = 0,
    hlrs: list[dict] | None = None,
    unlinked_llrs: list[dict] | None = None,
) -> dict:
    """Build a mock return value for ``fetch_requirements_data()``."""
    return {
        "hlrs": hlrs or [],
        "unlinked_llrs": unlinked_llrs or [],
        "total_hlrs": total_hlrs,
        "total_llrs": total_llrs,
        "total_verifications": total_verifications,
        "total_nodes": total_nodes,
        "total_triples": total_triples,
    }


def make_hlr_dict(
    *,
    refid: str = "test::HLR-1",
    description: str = "A test requirement",
    component: str | None = None,
    llrs: list[dict] | None = None,
) -> dict:
    """Build a serialized HLR dict for the requirements dashboard.

    Matches the structure returned by ``fetch_requirements_data()["hlrs"]``.
    """
    return {
        "refid": refid,
        "id": refid,
        "description": description,
        "component": component,
        "llrs": llrs if llrs is not None else [],
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def typical_data():
    """Return a requirements dashboard payload with 2 HLRs and 1 unlinked LLR."""
    return make_requirements_data(
        total_hlrs=2,
        total_llrs=3,
        total_verifications=5,
        total_nodes=8,
        total_triples=12,
        hlrs=[
            make_hlr_dict(
                refid="test::HLR-1",
                description="The system shall calculate accurately.",
                component="Calculator",
                llrs=[
                    make_llr_dict(refid="test::LLR-1-1", description="Verify addition"),
                    make_llr_dict(refid="test::LLR-1-2", description="Verify subtraction"),
                ],
            ),
            make_hlr_dict(
                refid="test::HLR-2",
                description="The system shall display results.",
                component=None,
                llrs=[],
            ),
        ],
        unlinked_llrs=[
            make_llr_dict(refid="test::LLR-ORPHAN", description="Orphaned LLR"),
        ],
    )


# ---------------------------------------------------------------------------
# Tests: Stat cards
# ---------------------------------------------------------------------------


async def test_requirements_page_shows_stat_cards(user, typical_data):
    """The dashboard displays all five stat cards with their values."""
    with patch(P["fetch_requirements_data"], return_value=typical_data):
        await user.open("/requirements")
        await user.should_see("HLRs")
        await user.should_see("LLRs")
        await user.should_see("Verifications")
        await user.should_see("Ontology Nodes")
        await user.should_see("Triples")


async def test_requirements_page_shows_counts(user, typical_data):
    """Stat card values match the mock data."""
    with patch(P["fetch_requirements_data"], return_value=typical_data):
        await user.open("/requirements")
        # NiceGUI stat_card renders the value as a separate element
        await user.should_see("2")   # total_hlrs
        await user.should_see("3")   # total_llrs
        await user.should_see("5")   # total_verifications
        await user.should_see("8")   # total_nodes
        await user.should_see("12")  # total_triples


async def test_requirements_page_zero_counts(user):
    """Zero counts are displayed when there are no requirements."""
    data = make_requirements_data(
        total_hlrs=0,
        total_llrs=0,
        total_verifications=0,
        total_nodes=0,
        total_triples=0,
    )
    with patch(P["fetch_requirements_data"], return_value=data):
        await user.open("/requirements")
        await user.should_see("0")


# ---------------------------------------------------------------------------
# Tests: HLR cards
# ---------------------------------------------------------------------------


async def test_requirements_page_lists_hlrs(user, typical_data):
    """HLR cards are rendered for each HLR in the data."""
    with patch(P["fetch_requirements_data"], return_value=typical_data):
        await user.open("/requirements")
        await user.should_see("The system shall calculate accurately.")
        await user.should_see("The system shall display results.")


async def test_requirements_page_shows_hlr_refid_badge(user, typical_data):
    """Each HLR card shows a badge with the HLR refid."""
    with patch(P["fetch_requirements_data"], return_value=typical_data):
        await user.open("/requirements")
        await user.should_see("HLR test::HLR-1")
        await user.should_see("HLR test::HLR-2")


async def test_requirements_page_shows_component_badge(user, typical_data):
    """HLRs with a component show a component badge."""
    with patch(P["fetch_requirements_data"], return_value=typical_data):
        await user.open("/requirements")
        await user.should_see("Calculator")


async def test_requirements_page_hlr_without_component_no_badge(user):
    """HLRs without a component do not show a component badge."""
    data = make_requirements_data(
        total_hlrs=1,
        hlrs=[
            make_hlr_dict(refid="test::HLR-X", description="Unassigned requirement", component=None),
        ],
    )
    with patch(P["fetch_requirements_data"], return_value=data):
        await user.open("/requirements")
        await user.should_see("HLR test::HLR-X")
        # "Calculator" is a component name — should not appear
        await user.should_not_see("Calculator")


async def test_requirements_page_shows_llr_count_badge(user, typical_data):
    """HLR cards display the LLR count badge."""
    with patch(P["fetch_requirements_data"], return_value=typical_data):
        await user.open("/requirements")
        await user.should_see("2 LLRs")
        await user.should_see("0 LLRs")


async def test_requirements_page_singular_llr(user):
    """An HLR with exactly one LLR shows '1 LLR' (singular)."""
    data = make_requirements_data(
        total_hlrs=1,
        total_llrs=1,
        hlrs=[
            make_hlr_dict(
                refid="test::HLR-S",
                description="Single LLR requirement",
                llrs=[make_llr_dict(refid="test::LLR-S1", description="Solo")],
            ),
        ],
    )
    with patch(P["fetch_requirements_data"], return_value=data):
        await user.open("/requirements")
        await user.should_see("1 LLR")


async def test_requirements_page_empty(user):
    """When there are no HLRs, the HLR list section still renders."""
    data = make_requirements_data()
    with patch(P["fetch_requirements_data"], return_value=data):
        await user.open("/requirements")
        await user.should_see("High-Level Requirements")


# ---------------------------------------------------------------------------
# Tests: LLR expansion panel
# ---------------------------------------------------------------------------


async def test_requirements_page_hlr_with_llrs_shows_expansion(user, typical_data):
    """An HLR that has LLRs renders a 'Low-Level Requirements' expansion."""
    with patch(P["fetch_requirements_data"], return_value=typical_data):
        await user.open("/requirements")
        await user.should_see("Low-Level Requirements")


async def test_requirements_page_hlr_without_llrs_no_expansion(user):
    """An HLR with no LLRs does not render the expansion panel."""
    data = make_requirements_data(
        total_hlrs=1,
        hlrs=[
            make_hlr_dict(refid="test::HLR-EMPTY", description="No LLRs here", llrs=[]),
        ],
    )
    with patch(P["fetch_requirements_data"], return_value=data):
        await user.open("/requirements")
        await user.should_not_see("Low-Level Requirements")


# ---------------------------------------------------------------------------
# Tests: Unlinked LLRs
# ---------------------------------------------------------------------------


async def test_requirements_page_shows_unlinked_llrs(user, typical_data):
    """Unlinked LLRs section appears at the bottom when there are orphans."""
    with patch(P["fetch_requirements_data"], return_value=typical_data):
        await user.open("/requirements")
        # The LLR text is inside a QTable (not inspectable by User.should_see),
        # but the section heading "Unlinked LLRs" is a visible Label.
        await user.should_see("Unlinked LLRs")


async def test_requirements_page_no_unlinked_llrs_section(user):
    """When there are no unlinked LLRs, that section is not shown."""
    data = make_requirements_data(
        total_hlrs=1,
        hlrs=[
            make_hlr_dict(refid="test::HLR-1", description="A requirement"),
        ],
    )
    with patch(P["fetch_requirements_data"], return_value=data):
        await user.open("/requirements")
        await user.should_not_see("Unlinked LLRs")


# ---------------------------------------------------------------------------
# Tests: Create HLR button
# ---------------------------------------------------------------------------


async def test_requirements_page_has_create_button(user, typical_data):
    """The '+ HLR' action button is shown on the dashboard."""
    with patch(P["fetch_requirements_data"], return_value=typical_data):
        await user.open("/requirements")
        await user.should_see("HLR")


# ---------------------------------------------------------------------------
# Tests: Menu actions
# ---------------------------------------------------------------------------


async def test_requirements_page_hlr_menu_has_actions(user, typical_data):
    """HLR card menu includes View Details, Add LLR, Decompose, Design, Delete."""
    with patch(P["fetch_requirements_data"], return_value=typical_data):
        await user.open("/requirements")
        # Menu items are in the DOM even when the menu is closed
        await user.should_see("View Details")
        await user.should_see("Add LLR")
        await user.should_see("Decompose")
        await user.should_see("Design")
        await user.should_see("Delete")