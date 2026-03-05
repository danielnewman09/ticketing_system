"""Ticket write operations: indexing from markdown and loading from JSON."""

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from sqlite_vec import serialize_float32

from ticketing_system.embeddings import embed_text
from ticketing_system.tickets.delete import delete_ticket
from ticketing_system.tickets.parsing import (
    detect_ticket_type,
    parse_acceptance_criteria,
    parse_files,
    parse_metadata,
    parse_references,
    parse_requirements,
    parse_summary,
    parse_title,
)


def index_single_ticket(
    conn: sqlite3.Connection,
    content: str,
    *,
    ticket_id: int | None = None,
) -> dict:
    """Parse and index a single ticket from its markdown content.

    If ticket_id is provided and a ticket with that ID exists, it is
    replaced. If ticket_id is provided and no ticket exists, the ticket
    is inserted with that explicit ID. If ticket_id is None, the DB
    auto-assigns an ID.

    Does NOT commit — callers are responsible for that.

    Args:
        conn: Open SQLite connection to the database.
        content: The full markdown content of the ticket.
        ticket_id: Optional explicit ticket ID.

    Returns:
        Dict with parsed ticket metadata: id, title.
    """
    now = datetime.now(timezone.utc).isoformat()

    title = parse_title(content)
    metadata = parse_metadata(content)
    summary = parse_summary(content)
    requirements = parse_requirements(content)
    criteria = parse_acceptance_criteria(content)
    files = parse_files(content)
    references = parse_references(content)
    ticket_type = detect_ticket_type(content)

    priority = metadata.get("Priority")
    complexity = metadata.get("Estimated Complexity")
    created_date = metadata.get("Created")
    author = metadata.get("Author")
    target_components = metadata.get("Target Component(s)") or metadata.get("Target Components")
    languages = metadata.get("Languages", "C++")
    requires_math = 1 if (metadata.get("Requires Math Design") or "").lower() in ("yes", "true") else 0
    generate_tutorial = 1 if (metadata.get("Generate Tutorial") or "").lower() in ("yes", "true") else 0
    parent_id_str = metadata.get("Parent Ticket")
    parent_id = int(parent_id_str) if parent_id_str and parent_id_str.strip().isdigit() else None

    if ticket_id is not None:
        delete_ticket(conn, ticket_id)

    if ticket_id is not None:
        conn.execute(
            """INSERT INTO tickets (
                id, title,
                priority, complexity, created_date, author, summary,
                ticket_type, parent_id, target_components, languages,
                requires_math, generate_tutorial, last_modified
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ticket_id, title,
                priority, complexity, created_date, author, summary,
                ticket_type, parent_id, target_components, languages,
                requires_math, generate_tutorial, now,
            ),
        )
    else:
        cursor = conn.execute(
            """INSERT INTO tickets (
                title,
                priority, complexity, created_date, author, summary,
                ticket_type, parent_id, target_components, languages,
                requires_math, generate_tutorial, last_modified
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                title,
                priority, complexity, created_date, author, summary,
                ticket_type, parent_id, target_components, languages,
                requires_math, generate_tutorial, now,
            ),
        )
        ticket_id = cursor.lastrowid

    for req in requirements:
        conn.execute(
            "INSERT INTO low_level_requirements (description, verification) VALUES (?, ?)",
            (req["description"], req["verification"]),
        )

    for ac in criteria:
        conn.execute(
            """INSERT INTO ticket_acceptance_criteria
               (ticket_id, description)
               VALUES (?, ?)""",
            (ticket_id, ac["description"]),
        )

    for f in files:
        conn.execute(
            """INSERT INTO ticket_files
               (ticket_id, file_path, change_type, description)
               VALUES (?, ?, ?, ?)""",
            (ticket_id, f["file_path"], f["change_type"], f["description"]),
        )

    for ref in references:
        conn.execute(
            """INSERT INTO ticket_references
               (ticket_id, ref_type, ref_target)
               VALUES (?, ?, ?)""",
            (ticket_id, ref["ref_type"], ref["ref_target"]),
        )

    embed_source = f"{title} {summary or ''}"
    embedding = embed_text(embed_source)
    conn.execute(
        "INSERT INTO ticket_embeddings (rowid, embedding) VALUES (?, ?)",
        (ticket_id, serialize_float32(embedding)),
    )

    return {
        "id": ticket_id,
        "title": title,
    }


def index_tickets(
    conn: sqlite3.Connection,
    repo_root: str,
    *,
    tickets_dir: str = "tickets",
) -> dict:
    """Index ticket markdown files into the database.

    Ticket IDs are derived from the numeric prefix of the filename
    (e.g. 0050_collision.md -> id 50).

    Args:
        conn: Open SQLite connection to the database.
        repo_root: Path to the git repository root.
        tickets_dir: Relative path to tickets directory.

    Returns:
        Dict with indexing results: new_count, updated_count, total.
    """
    tickets_path = Path(repo_root) / tickets_dir
    if not tickets_path.is_dir():
        return {"new_count": 0, "updated_count": 0, "total": 0}

    existing: dict[int, str] = {}
    try:
        rows = conn.execute(
            "SELECT id, last_modified FROM tickets"
        ).fetchall()
        existing = {row["id"]: row["last_modified"] for row in rows}
    except sqlite3.OperationalError:
        pass

    id_regex = r"^(\d+)_"
    new_count = 0
    updated_count = 0

    for md_file in sorted(tickets_path.glob("*.md")):
        match = re.match(id_regex, md_file.name)
        if not match:
            continue
        ticket_id = int(match.group(1))

        file_mtime = datetime.fromtimestamp(md_file.stat().st_mtime, tz=timezone.utc).isoformat()
        if ticket_id in existing and file_mtime <= existing[ticket_id]:
            continue

        content = md_file.read_text(encoding="utf-8")

        is_update = ticket_id in existing
        index_single_ticket(conn, content, ticket_id=ticket_id)

        if is_update:
            updated_count += 1
        else:
            new_count += 1

    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]

    return {"new_count": new_count, "updated_count": updated_count, "total": total}


def load_tickets(conn: sqlite3.Connection, json_path: str) -> dict:
    """Load tickets from a JSON file into the database.

    Each entry must have at minimum: id, title, summary.
    Optional fields: priority, complexity, created_date, author, ticket_type,
    parent_id, target_components, languages, requires_math, generate_tutorial,
    acceptance_criteria, files, references, high_level_requirement_ids.

    Returns a dict with total count.
    """
    with open(json_path) as f:
        tickets = json.load(f)

    now = datetime.now(timezone.utc).isoformat()

    for ticket in tickets:
        tid = ticket["id"]

        delete_ticket(conn, tid)

        conn.execute(
            """INSERT INTO tickets (
                id, title,
                priority, complexity, created_date, author, summary,
                ticket_type, parent_id, target_components, languages,
                requires_math, generate_tutorial, last_modified
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                tid, ticket["title"],
                ticket.get("priority"), ticket.get("complexity"),
                ticket.get("created_date"), ticket.get("author"),
                ticket.get("summary"),
                ticket.get("ticket_type", "feature"),
                ticket.get("parent_id"),
                ticket.get("target_components"),
                ticket.get("languages", "C++"),
                1 if ticket.get("requires_math") else 0,
                1 if ticket.get("generate_tutorial") else 0,
                now,
            ),
        )

        for ac in ticket.get("acceptance_criteria", []):
            conn.execute(
                """INSERT INTO ticket_acceptance_criteria
                   (ticket_id, description)
                   VALUES (?, ?)""",
                (tid, ac["description"]),
            )

        for f in ticket.get("files", []):
            conn.execute(
                """INSERT INTO ticket_files
                   (ticket_id, file_path, change_type, description)
                   VALUES (?, ?, ?, ?)""",
                (tid, f["file_path"], f["change_type"], f.get("description")),
            )

        for ref in ticket.get("references", []):
            conn.execute(
                """INSERT INTO ticket_references
                   (ticket_id, ref_type, ref_target)
                   VALUES (?, ?, ?)""",
                (tid, ref["ref_type"], ref["ref_target"]),
            )

        for hlr_id in ticket.get("high_level_requirement_ids", []):
            conn.execute(
                "INSERT OR IGNORE INTO ticket_requirements (ticket_id, high_level_requirement_id) VALUES (?, ?)",
                (tid, hlr_id),
            )

        embed_source = f"{ticket['title']} {ticket.get('summary') or ''}"
        embedding = embed_text(embed_source)
        conn.execute(
            "INSERT INTO ticket_embeddings (rowid, embedding) VALUES (?, ?)",
            (tid, serialize_float32(embedding)),
        )

    conn.commit()
    return {"total": len(tickets)}
