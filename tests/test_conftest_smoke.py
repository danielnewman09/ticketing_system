"""Smoke tests — prove conftest fixtures work end-to-end."""

from backend.db.models.components import Component, Language
from backend.db.models.verification import VerificationMethod


def test_seeded_session_has_defaults(seeded_session):
    """The seeded_session fixture populates language and component."""
    assert seeded_session.query(Language).count() == 1
    assert seeded_session.query(Component).count() == 1


def test_session_rolls_back_between_tests(session):
    """Each test starts with a clean DB — no data leaks."""
    assert session.query(VerificationMethod).count() == 0


def test_seeded_session_rolls_back(seeded_session):
    """Seeded session also rolls back — modifications don't leak."""
    assert seeded_session.query(Language).count() == 1