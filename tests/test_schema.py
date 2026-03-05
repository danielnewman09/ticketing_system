"""Tests for the unified schema creation."""

import sqlite3

import pytest

from ticketing_system.schema import create_db, create_content_db


def test_create_db_has_workflow_tables(tmp_path):
    """create_db() creates both workflow and content tables."""
    conn = create_db(tmp_path / "test.db")
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    # Workflow tables
    assert "tickets" in tables
    assert "phases" in tables
    assert "human_gates" in tables
    assert "audit_log" in tables
    # Content tables (prefixed with "content_" to avoid collision)
    assert "content_tickets" in tables
    assert "content_ticket_requirements" in tables
    assert "content_ticket_acceptance_criteria" in tables
    assert "content_ticket_workflow_log" in tables
    assert "content_ticket_files" in tables
    assert "content_ticket_references" in tables
    conn.close()


def test_create_content_db_no_workflow_tables(tmp_path):
    """create_content_db() creates content tables without workflow tables."""
    conn = create_content_db(tmp_path / "content.db")
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "ticket_requirements" in tables
    assert "ticket_acceptance_criteria" in tables
    # Should NOT have workflow-specific tables
    assert "phases" not in tables
    assert "human_gates" not in tables
    conn.close()


def test_create_db_idempotent(tmp_path):
    """create_db() can be called multiple times safely."""
    db_path = tmp_path / "test.db"
    conn1 = create_db(db_path)
    conn1.close()
    conn2 = create_db(db_path)
    tables = {
        row[0]
        for row in conn2.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "tickets" in tables
    assert "content_ticket_requirements" in tables
    conn2.close()
