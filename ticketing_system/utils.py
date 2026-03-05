"""Shared utilities: SQLite helpers and string manipulation."""

import re
import sqlite3
import unicodedata
from typing import Any


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    """Convert a list of sqlite3.Row objects to plain dicts."""
    return [dict(row) for row in rows]


def slugify(text: str) -> str:
    """Convert text to a filename-safe slug."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[-\s]+", "_", text).strip("_")


def split_pascal_case(text: str) -> list[str]:
    """Split PascalCase (and camelCase) tokens into individual words."""
    tokens = text.split()
    words = []
    for token in tokens:
        parts = re.sub(r'([a-z])([A-Z])', r'\1 \2', token)
        parts = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', parts)
        words.extend(parts.split())
    return words
