"""Tests for content database schema creation."""

import sqlite3
from pathlib import Path

import pytest

from ticketing_system.schema import create_content_db

TEST_DB_DIR = Path(__file__).parent / "test_dbs"
TEST_DB_DIR.mkdir(exist_ok=True)


def test_create_content_db_has_tables():
    """create_content_db() creates all content tables."""
    conn = create_content_db(TEST_DB_DIR / "content_tables.db")
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "high_level_requirements" in tables
    assert "low_level_requirements" in tables
    assert "tickets" in tables
    assert "ticket_requirements" in tables
    assert "ticket_acceptance_criteria" in tables
    assert "ticket_files" in tables
    assert "ticket_references" in tables
    conn.close()


def test_create_content_db_idempotent():
    """create_content_db() can be called multiple times safely."""
    db_path = TEST_DB_DIR / "idempotent.db"
    conn1 = create_content_db(db_path)
    conn1.close()
    conn2 = create_content_db(db_path)
    tables = {
        row[0]
        for row in conn2.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "high_level_requirements" in tables
    assert "low_level_requirements" in tables
    assert "tickets" in tables
    assert "ticket_requirements" in tables
    conn2.close()
