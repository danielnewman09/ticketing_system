"""Schema creation for the ticketing system.

Creates content indexing tables and vector embeddings for similarity search.
"""

import sqlite3
from pathlib import Path

from ticketing_system.tickets import create_ticket_tables, create_ticket_embeddings_table


def create_content_db(db_path: str | Path) -> sqlite3.Connection:
    """Create or open a content database.

    Sets WAL mode, busy_timeout, and foreign_keys.
    Creates all content tables and the vector embeddings table.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    create_ticket_tables(conn)
    create_ticket_embeddings_table(conn)
    conn.commit()
    return conn
