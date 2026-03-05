"""SQL query builders for ticket queries.

Each function returns a (sql, params) tuple, keeping query construction
separate from execution.  This makes queries independently testable and
self-documenting via their docstrings.
"""

from __future__ import annotations


def search_tickets_fts(
    query: str,
    *,
    priority: str | None = None,
    component: str | None = None,
) -> tuple[str, list]:
    """FTS5 ranked search across ticket titles and summaries.

    Uses bm25 ranking on the tickets_fts virtual table.
    Results are ordered by relevance and capped at 20.

    Optional filters narrow results to a specific priority or component.
    """
    sql = """
        SELECT t.id, t.title, t.priority,
               t.summary, t.target_components,
               bm25(tickets_fts) as rank
        FROM tickets_fts fts
        JOIN tickets t ON t.id = fts.rowid
        WHERE tickets_fts MATCH ?
    """
    params: list = [query]

    if priority:
        sql += " AND t.priority = ?"
        params.append(priority)
    if component:
        sql += " AND t.target_components LIKE ?"
        params.append(f"%{component}%")

    sql += " ORDER BY rank LIMIT 20"
    return sql, params


def search_tickets_like(
    words: list[str],
    *,
    priority: str | None = None,
    component: str | None = None,
) -> tuple[str, list]:
    """LIKE-based fallback search when FTS is unavailable.

    Builds a WHERE clause requiring every word to appear in at least one
    of: title or summary.  Results capped at 20.

    Optional filters narrow results to a specific priority or component.
    """
    word_clauses = []
    params: list = []
    for word in words:
        pattern = f"%{word}%"
        word_clauses.append("(title LIKE ? OR summary LIKE ?)")
        params.extend([pattern] * 2)

    sql = f"""
        SELECT id, title, priority,
               summary, target_components
        FROM tickets
        WHERE {' AND '.join(word_clauses)}
    """

    if priority:
        sql += " AND priority = ?"
        params.append(priority)
    if component:
        sql += " AND target_components LIKE ?"
        params.append(f"%{component}%")

    sql += " LIMIT 20"
    return sql, params


def list_tickets_filtered(
    *,
    priority: str | None = None,
    component: str | None = None,
    limit: int = 50,
) -> tuple[str, list]:
    """List tickets filtered by priority and/or component.

    Returns up to ``limit`` tickets ordered by id.
    """
    sql = """
        SELECT id, title, priority,
               complexity, target_components, ticket_type
        FROM tickets
        WHERE 1=1
    """
    params: list = []

    if priority:
        sql += " AND priority = ?"
        params.append(priority)
    if component:
        sql += " AND target_components LIKE ?"
        params.append(f"%{component}%")

    sql += " ORDER BY id LIMIT ?"
    params.append(limit)
    return sql, params


def get_ticket_detail(ticket_id: int) -> tuple[str, list]:
    """Fetch a single ticket row by id."""
    return "SELECT * FROM tickets WHERE id = ?", [ticket_id]


def get_ticket_requirements(ticket_id: int) -> tuple[str, list]:
    """High-level requirements linked to a ticket."""
    sql = """SELECT hlr.id, hlr.description
             FROM high_level_requirements hlr
             JOIN ticket_requirements tr ON tr.high_level_requirement_id = hlr.id
             WHERE tr.ticket_id = ?"""
    return sql, [ticket_id]


def get_ticket_acceptance_criteria(ticket_id: int) -> tuple[str, list]:
    """Acceptance criteria for a ticket."""
    sql = """SELECT id, description
             FROM ticket_acceptance_criteria
             WHERE ticket_id = ?"""
    return sql, [ticket_id]


def get_ticket_files(ticket_id: int) -> tuple[str, list]:
    """File declarations for a ticket."""
    sql = """SELECT file_path, change_type, description
             FROM ticket_files
             WHERE ticket_id = ?"""
    return sql, [ticket_id]


def get_ticket_references(ticket_id: int) -> tuple[str, list]:
    """References for a ticket."""
    sql = """SELECT ref_type, ref_target
             FROM ticket_references
             WHERE ticket_id = ?"""
    return sql, [ticket_id]
