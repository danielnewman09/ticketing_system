"""
Ticket Content Indexer

Parses ticket markdown files and stores their content, metadata,
acceptance criteria, file declarations, and cross-references
into the database.
"""

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .markdown_parser import parse_metadata


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_title(content: str) -> str:
    """Extract ticket title from the first heading."""
    for line in content.splitlines():
        stripped = line.strip()
        # "# Feature Ticket: <title>" or "# Ticket NNNN: <title>" or just "# <title>"
        m = re.match(r"^#\s+(?:Feature\s+)?(?:Ticket:?\s*(?:\d+:?\s*)?)?(.+)", stripped, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return "Untitled"


def _extract_section(content: str, heading: str) -> str | None:
    """Extract text under a ## heading, stopping at the next ## heading."""
    pattern = rf"^## {re.escape(heading)}\s*$"
    lines = content.splitlines()
    collecting = False
    section_lines: list[str] = []

    for line in lines:
        if re.match(pattern, line.strip()):
            collecting = True
            continue
        if collecting and line.strip().startswith("## "):
            break
        if collecting:
            section_lines.append(line)

    if not section_lines:
        return None

    text = "\n".join(section_lines).strip()
    return text if text else None


def _parse_summary(content: str) -> str | None:
    """Extract ## Summary section text."""
    return _extract_section(content, "Summary")


def _parse_requirements(content: str) -> list[dict[str, Any]]:
    """Extract requirements from a ## Requirements table or list.

    Supports two formats:

    1. **Table format** (preferred):
       | Description | Verification |
       |-------------|--------------|
       | Description | Automated    |

    2. **List format** (legacy, treated as verification=review):
       ### R1: Title
       - Description text

    Returns dicts with 'description' and 'verification' keys.
    """
    section = _extract_section(content, "Requirements")
    if not section:
        return []

    requirements: list[dict[str, Any]] = []

    # Try table format first: look for a header row with "Requirement" or "Description"
    lines = section.splitlines()
    table_header_idx = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("|") and ("Requirement" in stripped or "Description" in stripped):
            table_header_idx = i
            break

    if table_header_idx is not None:
        # Determine column positions from header
        header_cells = [c.strip() for c in lines[table_header_idx].strip().split("|")]
        if header_cells and header_cells[0] == "":
            header_cells = header_cells[1:]
        if header_cells and header_cells[-1] == "":
            header_cells = header_cells[:-1]

        # Find description and verification column indexes
        desc_col = None
        verif_col = None
        for idx, h in enumerate(header_cells):
            h_lower = h.strip().lower()
            if h_lower in ("requirement", "description"):
                desc_col = idx
            elif h_lower == "verification":
                verif_col = idx

        if desc_col is None:
            desc_col = 1 if len(header_cells) > 1 else 0

        for line in lines[table_header_idx + 2:]:
            stripped = line.strip()
            if not stripped.startswith("|"):
                continue
            cells = [c.strip() for c in stripped.split("|")]
            if cells and cells[0] == "":
                cells = cells[1:]
            if cells and cells[-1] == "":
                cells = cells[:-1]
            if len(cells) < 1:
                continue
            if all(set(c) <= {"-", " ", ""} for c in cells):
                continue

            description = cells[desc_col].strip() if desc_col < len(cells) else ""
            verification = "review"
            if verif_col is not None and verif_col < len(cells):
                verification = cells[verif_col].strip().lower()

            if not description:
                continue

            if verification not in ("automated", "review", "inspection"):
                verification = "review"

            requirements.append({
                "description": description,
                "verification": verification,
            })

        return requirements

    # Fallback: parse ### R1: heading format
    current_id: str | None = None
    current_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        heading_match = re.match(r"^###\s+(?:R\d+:?\s*)?(.+)", stripped)
        if heading_match:
            if current_id and current_lines:
                requirements.append({
                    "description": "\n".join(current_lines).strip(),
                    "verification": "review",
                })
            current_id = heading_match.group(1)
            current_lines = [current_id.strip()]
            continue
        if current_id is not None:
            current_lines.append(line)

    if current_id and current_lines:
        requirements.append({
            "description": "\n".join(current_lines).strip(),
            "verification": "review",
        })

    return requirements


def _parse_acceptance_criteria(content: str) -> list[dict[str, Any]]:
    """Extract acceptance criteria checkboxes with optional IDs and categories."""
    section = _extract_section(content, "Acceptance Criteria")
    if not section:
        return []

    criteria: list[dict[str, Any]] = []

    for line in section.splitlines():
        stripped = line.strip()

        # "- [x] AC1: Description" or "- [x] Description" or "- [ ] Description"
        m = re.match(r"-\s+\[[xX ]\]\s+(?:[A-Z]+\d+:\s+)?(.+)", stripped)
        if m:
            description = m.group(1).strip()
            criteria.append({
                "description": description,
            })

    return criteria


def _parse_files(content: str) -> list[dict[str, Any]]:
    """Extract file declarations from ## Files section and sub-sections."""
    files: list[dict[str, Any]] = []

    # Map of subsection heading patterns to change types
    heading_to_type = {
        "new files": "new",
        "new": "new",
        "modified files": "modified",
        "modified": "modified",
        "removed files": "removed",
        "removed": "removed",
        "deleted files": "removed",
    }

    # Extract the ## Files section first
    files_section = _extract_section(content, "Files")
    if files_section is None:
        # Try ## New Files, ## Modified Files as top-level sections
        for change_type, headings in [
            ("new", ["New Files"]),
            ("modified", ["Modified Files"]),
            ("removed", ["Removed Files"]),
        ]:
            section = _extract_section(content, headings[0])
            if section:
                files.extend(_parse_file_lines(section, change_type))
        return files

    # Parse ### sub-headings within the Files section
    current_type = "new"  # default if no sub-heading
    section_lines: list[str] = []

    for line in files_section.splitlines():
        stripped = line.strip()
        heading_match = re.match(r"^###\s+(.+)", stripped)
        if heading_match:
            # Process accumulated lines
            if section_lines:
                files.extend(_parse_file_lines("\n".join(section_lines), current_type))
                section_lines = []
            heading_text = heading_match.group(1).strip().lower()
            current_type = heading_to_type.get(heading_text, "new")
            continue
        section_lines.append(line)

    # Process remaining lines
    if section_lines:
        files.extend(_parse_file_lines("\n".join(section_lines), current_type))

    return files


def _parse_file_lines(section: str, change_type: str) -> list[dict[str, Any]]:
    """Parse file entries from a section of text."""
    files: list[dict[str, Any]] = []

    for line in section.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        # Table row: "| path | description |"
        table_match = re.match(r"\|\s*`?(.+?)`?\s*\|(?:\s*(.+?)\s*\|)?", stripped)
        if table_match and not stripped.startswith("|---") and not stripped.startswith("| File"):
            path = table_match.group(1).strip().strip("`")
            desc = (table_match.group(2) or "").strip() if table_match.group(2) else None
            if path and not path.startswith("-"):
                files.append({
                    "file_path": path,
                    "change_type": change_type,
                    "description": desc,
                })
                continue

        # List item: "- `path` — description" or "- path"
        list_match = re.match(r"-\s+`(.+?)`(?:\s*[—–-]\s*(.+))?$", stripped)
        if list_match:
            path = list_match.group(1).strip()
            desc = list_match.group(2).strip() if list_match.group(2) else None
            files.append({
                "file_path": path,
                "change_type": change_type,
                "description": desc,
            })

    return files


def _parse_references(content: str) -> list[dict[str, Any]]:
    """Extract cross-references from ## References, ## Dependencies, ## Related Code."""
    refs: list[dict[str, Any]] = []

    for section_name in ["References", "Dependencies", "Related Code", "Related Tickets"]:
        section = _extract_section(content, section_name)
        if not section:
            continue

        for line in section.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            # Ticket reference: "85", "ticket 85", "#85"
            ticket_match = re.findall(r"\b(\d+)\b", stripped)
            for t in ticket_match:
                ref_type = "ticket"
                # Determine more specific ref_type from context
                lower = stripped.lower()
                if "parent" in lower:
                    ref_type = "parent"
                elif "subtask" in lower or "sub-ticket" in lower:
                    ref_type = "subtask"
                elif "block" in lower:
                    ref_type = "blocks"
                elif "supersede" in lower:
                    ref_type = "supersedes"
                refs.append({"ref_type": ref_type, "ref_target": t})

            # Code/doc references: backtick paths
            code_refs = re.findall(r"`([^`]+\.\w+)`", stripped)
            for c in code_refs:
                refs.append({"ref_type": "code", "ref_target": c})

    return refs


def _detect_ticket_type(content: str) -> str:
    """Detect whether this is a feature ticket or debug ticket."""
    first_line = content.splitlines()[0] if content.splitlines() else ""
    if "debug" in first_line.lower():
        return "debug"
    return "feature"


# ---------------------------------------------------------------------------
# Main indexer
# ---------------------------------------------------------------------------


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

    Does NOT commit or rebuild FTS — callers are responsible for that.

    Args:
        conn: Open SQLite connection to the database.
        content: The full markdown content of the ticket.
        ticket_id: Optional explicit ticket ID.

    Returns:
        Dict with parsed ticket metadata: id, title.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Parse all fields
    title = _parse_title(content)
    metadata = parse_metadata(content)
    summary = _parse_summary(content)
    requirements = _parse_requirements(content)
    criteria = _parse_acceptance_criteria(content)
    files = _parse_files(content)
    references = _parse_references(content)
    ticket_type = _detect_ticket_type(content)

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

    # Delete existing rows for this ticket (full replace)
    if ticket_id is not None:
        _delete_ticket(conn, ticket_id)

    # Insert core ticket
    if ticket_id is not None:
        cursor = conn.execute(
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

    # Insert low-level requirements parsed from markdown
    for req in requirements:
        conn.execute(
            "INSERT INTO low_level_requirements (description, verification) VALUES (?, ?)",
            (req["description"], req["verification"]),
        )

    # Insert acceptance criteria
    for ac in criteria:
        conn.execute(
            """INSERT INTO ticket_acceptance_criteria
               (ticket_id, description)
               VALUES (?, ?)""",
            (ticket_id, ac["description"]),
        )

    # Insert file declarations
    for f in files:
        conn.execute(
            """INSERT INTO ticket_files
               (ticket_id, file_path, change_type, description)
               VALUES (?, ?, ?, ?)""",
            (ticket_id, f["file_path"], f["change_type"], f["description"]),
        )

    # Insert references
    for ref in references:
        conn.execute(
            """INSERT INTO ticket_references
               (ticket_id, ref_type, ref_target)
               VALUES (?, ?, ?)""",
            (ticket_id, ref["ref_type"], ref["ref_target"]),
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
    (e.g. 0050_collision.md → id 50).

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

    # Get existing indexed timestamps
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
        # Extract ticket ID from filename
        match = re.match(id_regex, md_file.name)
        if not match:
            continue
        ticket_id = int(match.group(1))

        # Check if file is newer than indexed version
        file_mtime = datetime.fromtimestamp(md_file.stat().st_mtime, tz=timezone.utc).isoformat()
        if ticket_id in existing:
            if file_mtime <= existing[ticket_id]:
                continue

        content = md_file.read_text(encoding="utf-8")

        is_update = ticket_id in existing
        index_single_ticket(conn, content, ticket_id=ticket_id)

        if is_update:
            updated_count += 1
        else:
            new_count += 1

    # Rebuild FTS
    try:
        conn.execute("INSERT INTO tickets_fts(tickets_fts) VALUES('rebuild')")
    except sqlite3.OperationalError:
        pass

    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]

    return {"new_count": new_count, "updated_count": updated_count, "total": total}


def _delete_ticket(conn: sqlite3.Connection, ticket_id: int) -> None:
    """Delete all rows for a ticket (for re-indexing)."""
    conn.execute("DELETE FROM ticket_requirements WHERE ticket_id = ?", (ticket_id,))
    conn.execute("DELETE FROM ticket_acceptance_criteria WHERE ticket_id = ?", (ticket_id,))
    conn.execute("DELETE FROM ticket_files WHERE ticket_id = ?", (ticket_id,))
    conn.execute("DELETE FROM ticket_references WHERE ticket_id = ?", (ticket_id,))
    conn.execute("DELETE FROM tickets WHERE id = ?", (ticket_id,))


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

        # Delete existing rows for this ticket (full replace)
        _delete_ticket(conn, tid)

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

    conn.commit()
    return {"total": len(tickets)}
