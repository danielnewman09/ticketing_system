"""SQLAlchemy event listeners (replaces Django signals)."""

from sqlalchemy import event

from db.models.components import Component, Language
from db.models.tickets import Ticket


@event.listens_for(Language, "after_insert")
def create_environment_component(mapper, connection, target):
    """Create Environment component when a Language is created."""
    from sqlalchemy.orm import Session
    from db import get_or_create

    session = Session.object_session(target)
    if session is None:
        return
    root, _ = get_or_create(session, Component, name="Environment", parent_id=None)
    get_or_create(
        session, Component,
        defaults={"language_id": target.id},
        name=f"Environment: {target.name}",
        parent_id=root.id,
    )


@event.listens_for(Ticket, "after_insert")
@event.listens_for(Ticket, "after_update")
def update_ticket_embedding(mapper, connection, target):
    """Update ticket embedding on insert/update."""
    try:
        from search.embeddings import upsert_ticket_embedding
        upsert_ticket_embedding(target.id, target.title, target.summary)
    except Exception:
        # Don't fail the transaction if embedding update fails
        pass
