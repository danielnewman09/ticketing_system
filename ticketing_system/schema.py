"""Unified schema creation for the ticketing system.

Combines both the workflow orchestration tables (tickets, phases, gates, agents,
audit_log) and the content indexing tables (ticket_requirements, acceptance_criteria,
workflow_log, artifacts, files, references).

When both systems share a database, the content tables use a "content_" prefix
to avoid collision with the workflow "tickets" table.
"""

import sqlite3
from pathlib import Path

from .workflow_schema import open_db, migrate as migrate_workflow
from .content_schema import create_ticket_tables, create_ticket_fts


# Prefix for content tables when coexisting with workflow tables
CONTENT_PREFIX = "content_"


def create_db(db_path: str | Path) -> sqlite3.Connection:
    """Create or open the ticketing database with all tables.

    Applies workflow schema migrations, then creates content tables with
    a "content_" prefix to avoid collisions with the workflow tickets table.
    Returns an open connection with WAL mode, busy_timeout, and foreign_keys.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = open_db(path)
    migrate_workflow(conn)
    create_ticket_tables(conn, prefix=CONTENT_PREFIX)
    conn.commit()
    return conn


def create_content_db(db_path: str | Path) -> sqlite3.Connection:
    """Create or open a content-only database (no workflow tables).

    Content tables use no prefix since there's no collision risk.
    Useful for standalone ticket content indexing without the workflow
    orchestration layer.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = open_db(path)
    create_ticket_tables(conn)
    try:
        create_ticket_fts(conn)
    except sqlite3.OperationalError:
        pass
    conn.commit()
    return conn
