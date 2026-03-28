"""SQLAlchemy event listeners (replaces Django signals)."""

from sqlalchemy import event

from backend.db.models.components import Component, Language
from backend.db.models.tickets import Ticket


@event.listens_for(Language, "after_insert")
def create_environment_component(mapper, connection, target):
    """Create Environment component when a Language is created.

    Uses raw connection.execute to avoid flush-inside-flush errors.
    """
    from sqlalchemy import text

    # Ensure root Environment component exists
    row = connection.execute(
        text("SELECT id FROM components WHERE name = :n AND parent_id IS NULL"),
        {"n": "Environment"},
    ).first()
    if row:
        root_id = row[0]
    else:
        connection.execute(
            text("INSERT INTO components (name, description, namespace) VALUES (:n, '', '')"),
            {"n": "Environment"},
        )
        root_id = connection.execute(
            text("SELECT id FROM components WHERE name = :n AND parent_id IS NULL"),
            {"n": "Environment"},
        ).first()[0]

    # Create child component for this language
    child_name = f"Environment: {target.name}"
    exists = connection.execute(
        text("SELECT id FROM components WHERE name = :n AND parent_id = :pid"),
        {"n": child_name, "pid": root_id},
    ).first()
    if not exists:
        connection.execute(
            text(
                "INSERT INTO components (name, description, namespace, parent_id, language_id) "
                "VALUES (:n, '', '', :pid, :lid)"
            ),
            {"n": child_name, "pid": root_id, "lid": target.id},
        )


@event.listens_for(Ticket, "after_insert")
@event.listens_for(Ticket, "after_update")
def update_ticket_embedding(mapper, connection, target):
    """Update ticket embedding on insert/update."""
    try:
        from backend.search.embeddings import upsert_ticket_embedding
        upsert_ticket_embedding(target.id, target.title, target.summary)
    except Exception:
        # Don't fail the transaction if embedding update fails
        pass
