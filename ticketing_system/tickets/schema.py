"""Schema: tickets, acceptance criteria, files, references, and vector embeddings."""

import sqlite3
import sqlite_vec

from ticketing_system.requirements import create_requirements_tables


def create_tickets_table(conn: sqlite3.Connection, prefix: str = "") -> None:
    """Core ticket content parsed from markdown ticket files.

    Each row represents a single ticket with its metadata and
    categorization fields.

    Columns:
        id:                Integer primary key (the ticket ID).
        title:             Ticket title.
        priority:          Priority level.
        complexity:        Estimated complexity.
        created_date:      When the ticket was created.
        author:            Ticket author.
        summary:           Brief description of the ticket.
        ticket_type:       Type classification (default "feature").
        parent_id:         Parent ticket ID for sub-tickets.
        target_components: Components affected by the ticket.
        languages:         Implementation languages (default "C++").
        requires_math:     Whether mathematical implementation is needed.
        generate_tutorial: Whether a tutorial should be generated.
        last_modified:     ISO-8601 timestamp of last modification.

    Indexes:
        idx_tickets_parent:   Lookup sub-tickets by parent.
        idx_tickets_priority: Filter by priority.
    """
    conn.executescript(f"""
        CREATE TABLE IF NOT EXISTS {prefix}tickets (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            title           TEXT NOT NULL,
            priority        TEXT,
            complexity      TEXT,
            created_date    TEXT,
            author          TEXT,
            summary         TEXT,
            ticket_type     TEXT DEFAULT 'feature',
            parent_id       INTEGER,
            target_components TEXT,
            languages       TEXT DEFAULT 'C++',
            requires_math   INTEGER DEFAULT 0,
            generate_tutorial INTEGER DEFAULT 0,
            last_modified   TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS {prefix}idx_tickets_parent ON {prefix}tickets(parent_id);
        CREATE INDEX IF NOT EXISTS {prefix}idx_tickets_priority ON {prefix}tickets(priority);
    """)


def create_ticket_acceptance_criteria_table(conn: sqlite3.Connection, prefix: str = "") -> None:
    """Acceptance criteria extracted from ticket files.

    Each criterion describes a testable condition that must be met
    for the ticket to be considered complete.

    Columns:
        ticket_id:     FK to tickets.id.
        description:   Full text of the criterion.

    Indexes:
        idx_tac_ticket: Lookup by ticket.
    """
    conn.executescript(f"""
        CREATE TABLE IF NOT EXISTS {prefix}ticket_acceptance_criteria (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id       INTEGER NOT NULL REFERENCES {prefix}tickets(id),
            description     TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS {prefix}idx_tac_ticket ON {prefix}ticket_acceptance_criteria(ticket_id);
    """)

def create_ticket_files_table(conn: sqlite3.Connection, prefix: str = "") -> None:
    """Files declared in ticket New/Modified/Removed sections.

    Records the expected file changes described in the ticket, used
    to verify that implementation matches the plan.

    Columns:
        ticket_id:   FK to tickets.id.
        file_path:   Path of the declared file.
        change_type: One of "new", "modified", "removed".
        description: What the change entails.

    Indexes:
        idx_tf_ticket: Lookup by ticket.
        idx_tf_path:   Lookup by file path.
    """
    conn.executescript(f"""
        CREATE TABLE IF NOT EXISTS {prefix}ticket_files (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id       INTEGER NOT NULL REFERENCES {prefix}tickets(id),
            file_path       TEXT NOT NULL,
            change_type     TEXT NOT NULL,
            description     TEXT
        );
        CREATE INDEX IF NOT EXISTS {prefix}idx_tf_ticket ON {prefix}ticket_files(ticket_id);
        CREATE INDEX IF NOT EXISTS {prefix}idx_tf_path ON {prefix}ticket_files(file_path);
    """)

def create_ticket_references_table(conn: sqlite3.Connection, prefix: str = "") -> None:
    """Cross-references between tickets, code, and documentation.

    Captures relationships like "depends on ticket X", "references
    file Y", or "see design doc Z".

    Columns:
        ticket_id: FK to tickets.id.
        ref_type:  Reference type (e.g. "depends_on", "references").
        ref_target: Target of the reference (ticket ID, file path, URL).

    Indexes:
        idx_tr_ticket: Lookup by ticket.
    """
    conn.executescript(f"""
        CREATE TABLE IF NOT EXISTS {prefix}ticket_references (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id       INTEGER NOT NULL REFERENCES {prefix}tickets(id),
            ref_type        TEXT NOT NULL,
            ref_target      TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS {prefix}idx_tr_ticket ON {prefix}ticket_references(ticket_id);
    """)

def create_ticket_embeddings_table(conn: sqlite3.Connection) -> None:
    """Virtual table for vector similarity search over tickets.

    Uses sqlite-vec's vec0 module with 384-dimensional float embeddings
    (matching the all-MiniLM-L6-v2 sentence-transformers model).

    Each row's rowid corresponds to a ticket id.
    """
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS ticket_embeddings USING vec0(
            embedding float[384]
        )
    """)


def create_ticket_tables(conn: sqlite3.Connection, prefix: str = "") -> None:
    """Create all tables: requirements, tickets, and child tables."""
    create_requirements_tables(conn, prefix)
    create_tickets_table(conn, prefix)
    create_ticket_acceptance_criteria_table(conn, prefix)
    create_ticket_files_table(conn, prefix)
    create_ticket_references_table(conn, prefix)
