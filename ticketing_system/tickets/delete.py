"""Ticket delete operations."""

import sqlite3


def delete_ticket(conn: sqlite3.Connection, ticket_id: int) -> None:
    """Delete all rows for a ticket (for re-indexing)."""
    conn.execute("DELETE FROM ticket_requirements WHERE ticket_id = ?", (ticket_id,))
    conn.execute("DELETE FROM ticket_acceptance_criteria WHERE ticket_id = ?", (ticket_id,))
    conn.execute("DELETE FROM ticket_files WHERE ticket_id = ?", (ticket_id,))
    conn.execute("DELETE FROM ticket_references WHERE ticket_id = ?", (ticket_id,))
    conn.execute("DELETE FROM ticket_embeddings WHERE rowid = ?", (ticket_id,))
    conn.execute("DELETE FROM tickets WHERE id = ?", (ticket_id,))
