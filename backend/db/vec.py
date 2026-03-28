"""sqlite-vec virtual table setup for ticket embeddings."""

from backend.db import get_main_engine


def ensure_vec_table():
    """Create the ticket_embeddings virtual table if it doesn't exist."""
    engine = get_main_engine()
    with engine.raw_connection() as conn:
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS ticket_embeddings "
            "USING vec0(embedding float[384])"
        )
        conn.commit()
