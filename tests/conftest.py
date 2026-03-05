"""Shared fixtures for ticketing_system tests."""

import sqlite3
from pathlib import Path

import pytest

from ticketing_system.tickets import create_ticket_tables, create_ticket_embeddings_table

TEST_DB_DIR = Path(__file__).parent / "test_dbs"


@pytest.fixture
def db_path(request):
    TEST_DB_DIR.mkdir(exist_ok=True)
    name = request.node.name.replace("/", "_").replace("::", "_")
    path = TEST_DB_DIR / f"{name}.db"
    if path.exists():
        path.unlink()
    return str(path)


@pytest.fixture
def conn(db_path):
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    create_ticket_tables(c)
    create_ticket_embeddings_table(c)
    c.commit()
    yield c
    c.close()
