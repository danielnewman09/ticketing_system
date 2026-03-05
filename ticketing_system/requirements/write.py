"""Requirements write operations: loading from JSON."""

import json
import sqlite3


def load_high_level_requirements(conn: sqlite3.Connection, json_path: str) -> dict:
    """Load high-level requirements from a JSON file into the database.

    Each entry must have: description.
    Optional: id (explicit integer ID).

    Returns a dict with total count.
    """
    with open(json_path) as f:
        hlrs = json.load(f)

    for hlr in hlrs:
        hlr_id = hlr.get("id")
        if hlr_id is not None:
            conn.execute(
                "INSERT INTO high_level_requirements (id, description) VALUES (?, ?)",
                (hlr_id, hlr["description"]),
            )
        else:
            conn.execute(
                "INSERT INTO high_level_requirements (description) VALUES (?)",
                (hlr["description"],),
            )

    conn.commit()
    return {"total": len(hlrs)}


def load_low_level_requirements(conn: sqlite3.Connection, json_path: str) -> dict:
    """Load low-level requirements from a JSON file into the database.

    Each entry must have: description, verification.
    Optional: id (explicit integer ID),
              high_level_requirement_id (FK to high_level_requirements).

    Returns a dict with total count.
    """
    with open(json_path) as f:
        requirements = json.load(f)

    for req in requirements:
        req_id = req.get("id")
        hlr_id = req.get("high_level_requirement_id")
        if req_id is not None:
            conn.execute(
                """INSERT INTO low_level_requirements
                   (id, high_level_requirement_id, description, verification)
                   VALUES (?, ?, ?, ?)""",
                (req_id, hlr_id, req["description"], req["verification"]),
            )
        else:
            conn.execute(
                """INSERT INTO low_level_requirements
                   (high_level_requirement_id, description, verification)
                   VALUES (?, ?, ?)""",
                (hlr_id, req["description"], req["verification"]),
            )

    conn.commit()
    return {"total": len(requirements)}
