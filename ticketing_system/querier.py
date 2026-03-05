"""Ticket query logic.

Encapsulates all ticket-related queries: search, detail retrieval,
listing, and creation.  Delegates SQL construction to queries.py.
"""

import sqlite3
from pathlib import Path

from .queries import (
    get_ticket_acceptance_criteria,
    get_ticket_detail,
    get_ticket_files,
    get_ticket_references,
    get_ticket_requirements,
    list_tickets_filtered,
    search_tickets_fts,
    search_tickets_like,
)
from .utils import rows_to_dicts, slugify, split_pascal_case


class TicketQuerier:
    """Queries over the tickets family of tables."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def search(
        self,
        query: str,
        priority: str | None = None,
        component: str | None = None,
    ) -> list[dict]:
        """Search tickets by keyword, with FTS5 ranked search
        and automatic LIKE fallback.

        If query is empty, delegates to list() for filter-based listing.

        Args:
            query: Free-text search string (supports PascalCase splitting).
            priority: Optional priority filter.
            component: Optional component substring filter.

        Returns:
            List of matching ticket dicts, ordered by relevance (max 20).
        """
        if not query.strip():
            return self.list(priority=priority, component=component)

        results = []

        try:
            sql, params = search_tickets_fts(
                query, priority=priority, component=component
            )
            cursor = self.conn.execute(sql, params)
            results = rows_to_dicts(cursor.fetchall())
        except sqlite3.OperationalError:
            pass

        if results:
            return results

        words = split_pascal_case(query)
        if not words:
            return []

        sql, params = search_tickets_like(
            words, priority=priority, component=component
        )
        cursor = self.conn.execute(sql, params)
        return rows_to_dicts(cursor.fetchall())

    def get(self, ticket_id: int) -> dict:
        """Get full ticket detail by ID.

        Returns a dict with the ticket fields plus:
            requirements: list of requirement dicts.
            acceptance_criteria: list of criterion dicts.
            files: list of file declaration dicts.
            references: list of reference dicts.

        Returns an ``{"error": ...}`` dict if the ticket is not found.
        """
        sql, params = get_ticket_detail(ticket_id)
        row = self.conn.execute(sql, params).fetchone()
        if not row:
            return {"error": f"Ticket {ticket_id} not found"}

        result = dict(row)

        # Requirements
        sql, params = get_ticket_requirements(ticket_id)
        result["requirements"] = rows_to_dicts(
            self.conn.execute(sql, params).fetchall()
        )

        # Acceptance criteria
        sql, params = get_ticket_acceptance_criteria(ticket_id)
        result["acceptance_criteria"] = rows_to_dicts(
            self.conn.execute(sql, params).fetchall()
        )

        # File declarations
        sql, params = get_ticket_files(ticket_id)
        result["files"] = rows_to_dicts(self.conn.execute(sql, params).fetchall())

        # References
        sql, params = get_ticket_references(ticket_id)
        result["references"] = rows_to_dicts(self.conn.execute(sql, params).fetchall())

        return result

    def list(
        self,
        priority: str | None = None,
        component: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """List tickets filtered by priority and/or component.

        Returns:
            List of ticket summary dicts, ordered by id (max ``limit``).
        """
        sql, params = list_tickets_filtered(
            priority=priority, component=component, limit=limit
        )
        cursor = self.conn.execute(sql, params)
        return rows_to_dicts(cursor.fetchall())

    def create(
        self,
        content: str,
        repo_root: str,
        tickets_dir: str = "tickets",
    ) -> dict:
        """Write a new ticket file to disk and index it into the database.

        Args:
            content: Full markdown content for the ticket.
            repo_root: Absolute path to the repository root.
            tickets_dir: Relative path to the tickets directory.

        Returns:
            Dict with id, file_path, and title on success,
            or a dict with an "error" key on failure.
        """
        from .indexer import (
            _parse_title,
            index_single_ticket,
        )

        result = index_single_ticket(self.conn, content)
        ticket_id = result["id"]

        tickets_path = Path(repo_root) / tickets_dir
        tickets_path.mkdir(parents=True, exist_ok=True)

        title = result["title"]
        slug = slugify(title) if title != "Untitled" else "untitled"
        filename = f"{ticket_id}_{slug}.md"
        file_path = tickets_path / filename

        file_path.write_text(content, encoding="utf-8")

        try:
            self.conn.execute("INSERT INTO tickets_fts(tickets_fts) VALUES('rebuild')")
        except sqlite3.OperationalError:
            pass
        self.conn.commit()

        return {
            "id": ticket_id,
            "file_path": str(file_path),
            "title": title,
        }
