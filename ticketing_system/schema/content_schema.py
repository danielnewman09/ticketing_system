"""Schema: requirements, tickets, acceptance criteria, files, references, and FTS."""

import sqlite3


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


def create_ticket_fts(conn: sqlite3.Connection) -> None:
    """FTS5 virtual table for full-text search over tickets.

    Content-synced with tickets via content= directive.
    Uses Porter stemming and Unicode tokenization.

    Does not support schema prefixes — only for standalone databases.
    """
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS tickets_fts USING fts5(
            title,
            summary,
            content=tickets,
            content_rowid=id,
            tokenize='porter unicode61'
        )
    """)


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


def create_ticket_tables(conn: sqlite3.Connection, prefix: str = "") -> None:
    """Create all tables: requirements, tickets, and child tables."""
    create_high_level_requirements_table(conn, prefix)
    create_low_level_requirements_table(conn, prefix)
    create_tickets_table(conn, prefix)
    create_ticket_requirements_table(conn, prefix)
    create_ticket_acceptance_criteria_table(conn, prefix)
    create_ticket_files_table(conn, prefix)
    create_ticket_references_table(conn, prefix)
