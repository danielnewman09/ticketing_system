"""SQL query builders for reading tickets.

Each function returns a (sql, params) tuple, keeping query construction
separate from execution.
"""

from sqlite_vec import serialize_float32


def search_tickets_vec(
    query_embedding: list[float],
    *,
    priority: str | None = None,
    component: str | None = None,
    limit: int = 20,
) -> tuple[str, list]:
    """Vector similarity search over ticket embeddings.

    Uses sqlite-vec KNN matching against pre-computed embeddings
    of ticket titles and summaries.

    Optional filters narrow results to a specific priority or component.
    """
    embedding_blob = serialize_float32(query_embedding)

    if priority or component:
        # Filter via subquery on tickets, then KNN on matching rowids
        where_parts = []
        params: list = []
        if priority:
            where_parts.append("t.priority = ?")
            params.append(priority)
        if component:
            where_parts.append("t.target_components LIKE ?")
            params.append(f"%{component}%")

        sql = f"""
            SELECT t.id, t.title, t.priority,
                   t.summary, t.target_components,
                   e.distance
            FROM ticket_embeddings e
            JOIN tickets t ON t.id = e.rowid
            WHERE e.embedding MATCH ?
              AND e.k = ?
              AND {' AND '.join(where_parts)}
            ORDER BY e.distance
            LIMIT ?
        """
        params = [embedding_blob, limit * 5] + params + [limit]
    else:
        sql = """
            SELECT t.id, t.title, t.priority,
                   t.summary, t.target_components,
                   e.distance
            FROM ticket_embeddings e
            JOIN tickets t ON t.id = e.rowid
            WHERE e.embedding MATCH ?
              AND e.k = ?
            ORDER BY e.distance
            LIMIT ?
        """
        params = [embedding_blob, limit, limit]

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
