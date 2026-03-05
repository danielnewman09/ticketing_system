"""Shared fixtures for ticketing_system tests."""

import sqlite3

import pytest

from ticketing_system.content_schema import create_ticket_tables, create_ticket_fts


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def conn(db_path):
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    create_ticket_tables(c)
    try:
        create_ticket_fts(c)
    except sqlite3.OperationalError:
        pass
    c.commit()
    yield c
    c.close()
