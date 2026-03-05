"""Schema: high-level requirements, low-level requirements, and ticket-requirement linkage."""

import sqlite3


def create_high_level_requirements_table(conn: sqlite3.Connection, prefix: str = "") -> None:
    """High-level requirements that capture broad project goals.

    These are decomposed into low-level requirements (in the
    ``low_level_requirements`` table) that are concrete and verifiable.

    Columns:
        id:          Integer primary key.
        description: Full text of the high-level requirement.
    """
    conn.executescript(f"""
        CREATE TABLE IF NOT EXISTS {prefix}high_level_requirements (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            description     TEXT NOT NULL
        );
    """)


def create_low_level_requirements_table(conn: sqlite3.Connection, prefix: str = "") -> None:
    """Low-level requirements — concrete, verifiable decompositions
    of high-level requirements.

    Each low-level requirement optionally references a high-level
    requirement it helps fulfill.

    Columns:
        id:                         Auto-incrementing integer primary key.
        high_level_requirement_id:  FK to high_level_requirements.id (optional).
        description:                Full text of the requirement.
        verification:               How the requirement is verified
                                    ("automated", "review", "inspection").

    Indexes:
        idx_llr_hlr: Lookup by high-level requirement.
    """
    conn.executescript(f"""
        CREATE TABLE IF NOT EXISTS {prefix}low_level_requirements (
            id                          INTEGER PRIMARY KEY AUTOINCREMENT,
            high_level_requirement_id   INTEGER REFERENCES {prefix}high_level_requirements(id),
            description                 TEXT NOT NULL,
            verification                TEXT NOT NULL DEFAULT 'review'
        );
        CREATE INDEX IF NOT EXISTS {prefix}idx_llr_hlr ON {prefix}low_level_requirements(high_level_requirement_id);
    """)


def create_ticket_requirements_table(conn: sqlite3.Connection, prefix: str = "") -> None:
    """Join table linking tickets to the high-level requirements they fulfill.

    Columns:
        ticket_id:                  FK to tickets.id.
        high_level_requirement_id:  FK to high_level_requirements.id.

    Indexes:
        idx_treq_ticket: Lookup requirements by ticket.
        idx_treq_hlr:    Lookup tickets by requirement.
    """
    conn.executescript(f"""
        CREATE TABLE IF NOT EXISTS {prefix}ticket_requirements (
            id                          INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id                   INTEGER NOT NULL REFERENCES {prefix}tickets(id),
            high_level_requirement_id   INTEGER NOT NULL REFERENCES {prefix}high_level_requirements(id),
            UNIQUE(ticket_id, high_level_requirement_id)
        );
        CREATE INDEX IF NOT EXISTS {prefix}idx_treq_ticket ON {prefix}ticket_requirements(ticket_id);
        CREATE INDEX IF NOT EXISTS {prefix}idx_treq_hlr ON {prefix}ticket_requirements(high_level_requirement_id);
    """)

def create_requirements_tables(conn: sqlite3.Connection, prefix: str = "") -> None:
    """Create all requirements tables: high-level, low-level, and ticket linkage."""
    create_high_level_requirements_table(conn, prefix)
    create_low_level_requirements_table(conn, prefix)
    create_ticket_requirements_table(conn, prefix)
