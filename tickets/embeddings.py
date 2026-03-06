"""Embedding generation and vector search for tickets.

Uses sentence-transformers for 384-dimensional embeddings and
sqlite-vec for KNN similarity search.
"""

from sentence_transformers import SentenceTransformer
from sqlite_vec import serialize_float32
from django.db import connection

_MODEL_NAME = "all-MiniLM-L6-v2"
_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(_MODEL_NAME)
    return _model


def embed_text(text: str) -> list[float]:
    """Generate a 384-dimensional embedding for a single text string."""
    model = get_model()
    return model.encode(text, normalize_embeddings=True).tolist()


def _raw_conn():
    """Get the underlying sqlite3 connection, ensuring it's open."""
    connection.ensure_connection()
    return connection.connection


def upsert_ticket_embedding(ticket_id: int, title: str, summary: str | None = None) -> None:
    """Generate and store an embedding for a ticket."""
    text = f"{title} {summary or ''}"
    embedding = embed_text(text)
    blob = serialize_float32(embedding)
    conn = _raw_conn()
    conn.execute("DELETE FROM ticket_embeddings WHERE rowid = ?", (ticket_id,))
    conn.execute(
        "INSERT INTO ticket_embeddings (rowid, embedding) VALUES (?, ?)",
        (ticket_id, blob),
    )


def search_tickets(query: str, limit: int = 20) -> list[dict]:
    """Search tickets by semantic similarity.

    Returns a list of dicts with ticket id, title, priority, summary,
    target_components, and distance (lower = more similar).
    """
    query_embedding = embed_text(query)
    blob = serialize_float32(query_embedding)
    conn = _raw_conn()
    cursor = conn.execute(
        """
        SELECT t.id, t.title, t.priority,
               t.summary, t.target_components,
               e.distance
        FROM ticket_embeddings e
        JOIN tickets t ON t.id = e.rowid
        WHERE e.embedding MATCH ?
          AND e.k = ?
        ORDER BY e.distance
        LIMIT ?
        """,
        (blob, limit, limit),
    )
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]
