"""SQL query builders for requirements queries.

Each function returns a (sql, params) tuple, keeping query construction
separate from execution.
"""


def get_ticket_requirements(ticket_id: int) -> tuple[str, list]:
    """High-level requirements linked to a ticket."""
    sql = """SELECT hlr.id, hlr.description
             FROM high_level_requirements hlr
             JOIN ticket_requirements tr ON tr.high_level_requirement_id = hlr.id
             WHERE tr.ticket_id = ?"""
    return sql, [ticket_id]
