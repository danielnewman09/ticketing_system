"""Smoke tests — prove conftest fixtures work end-to-end."""

from backend.db.models.requirements import HighLevelRequirement
from backend.db.models.components import Component, Language
from backend.db.models.ontology import Predicate


def test_session_can_create_hlr(session):
    """The bare session fixture lets us create and query an HLR."""
    hlr = HighLevelRequirement(description="Test HLR")
    session.add(hlr)
    session.flush()
    assert hlr.id is not None
    found = session.query(HighLevelRequirement).filter_by(id=hlr.id).first()
    assert found is not None
    assert found.description == "Test HLR"


def test_seeded_session_has_defaults(seeded_session):
    """The seeded_session fixture populates language, component, HLR, predicates."""
    assert seeded_session.query(Language).count() == 1
    assert seeded_session.query(Component).count() == 1
    assert seeded_session.query(HighLevelRequirement).count() == 1
    # Ensure_defaults creates at least 7 predicates
    assert seeded_session.query(Predicate).count() >= 7


def test_session_rolls_back_between_tests(session):
    """Each test starts with a clean DB — no data leaks."""
    assert session.query(HighLevelRequirement).count() == 0


def test_seeded_session_rolls_back(seeded_session):
    """Seeded session also rolls back — modifications don't leak."""
    # This test relies on the previous test_not_leaked having run.
    # If data leaked, we'd see >1 HLR.
    assert seeded_session.query(HighLevelRequirement).count() == 1