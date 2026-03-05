"""Embedding generation using sentence-transformers.

Provides a lazily-loaded singleton model for generating 384-dimensional
embeddings from text, suitable for sqlite-vec similarity search.
"""

from sentence_transformers import SentenceTransformer

_MODEL_NAME = "all-MiniLM-L6-v2"
_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    """Return the shared SentenceTransformer instance, loading on first call."""
    global _model
    if _model is None:
        _model = SentenceTransformer(_MODEL_NAME)
    return _model


def embed_text(text: str) -> list[float]:
    """Generate a 384-dimensional embedding for a single text string."""
    model = get_model()
    return model.encode(text, normalize_embeddings=True).tolist()
