"""Markdown parsing helpers for ticket files.

Extracts structured data (metadata, title, summary, requirements,
acceptance criteria, files, references) from ticket markdown content.
"""

import re
from typing import Any


def parse_metadata(content: str) -> dict[str, Any]:
    """Parse the ## Metadata section of a ticket markdown file.

    Returns a dict of key -> value for all "- **Key**: Value" lines.
    """
    metadata: dict[str, Any] = {}
    in_metadata = False

    for line in content.splitlines():
        stripped = line.strip()
        if stripped == "## Metadata":
            in_metadata = True
            continue
        if in_metadata and stripped.startswith("## "):
            break
        if in_metadata:
            match = re.match(r"-\s+\*\*(.+?)\*\*:\s*(.*)", stripped)
            if match:
                key = match.group(1).strip()
                value = match.group(2).strip()
                metadata[key] = value if value else None

    return metadata


def parse_title(content: str) -> str:
    """Extract ticket title from the first heading."""
    for line in content.splitlines():
        stripped = line.strip()
        m = re.match(r"^#\s+(?:Feature\s+)?(?:Ticket:?\s*(?:\d+:?\s*)?)?(.+)", stripped, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return "Untitled"


def extract_section(content: str, heading: str) -> str | None:
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


def parse_summary(content: str) -> str | None:
    """Extract ## Summary section text."""
    return extract_section(content, "Summary")


def parse_requirements(content: str) -> list[dict[str, Any]]:
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
    section = extract_section(content, "Requirements")
    if not section:
        return []

    requirements: list[dict[str, Any]] = []

    lines = section.splitlines()
    table_header_idx = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("|") and ("Requirement" in stripped or "Description" in stripped):
            table_header_idx = i
            break

    if table_header_idx is not None:
        header_cells = [c.strip() for c in lines[table_header_idx].strip().split("|")]
        if header_cells and header_cells[0] == "":
            header_cells = header_cells[1:]
        if header_cells and header_cells[-1] == "":
            header_cells = header_cells[:-1]

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


def parse_acceptance_criteria(content: str) -> list[dict[str, Any]]:
    """Extract acceptance criteria checkboxes with optional IDs and categories."""
    section = extract_section(content, "Acceptance Criteria")
    if not section:
        return []

    criteria: list[dict[str, Any]] = []

    for line in section.splitlines():
        stripped = line.strip()
        m = re.match(r"-\s+\[[xX ]\]\s+(?:[A-Z]+\d+:\s+)?(.+)", stripped)
        if m:
            description = m.group(1).strip()
            criteria.append({
                "description": description,
            })

    return criteria


def parse_files(content: str) -> list[dict[str, Any]]:
    """Extract file declarations from ## Files section and sub-sections."""
    files: list[dict[str, Any]] = []

    heading_to_type = {
        "new files": "new",
        "new": "new",
        "modified files": "modified",
        "modified": "modified",
        "removed files": "removed",
        "removed": "removed",
        "deleted files": "removed",
    }

    files_section = extract_section(content, "Files")
    if files_section is None:
        for change_type, headings in [
            ("new", ["New Files"]),
            ("modified", ["Modified Files"]),
            ("removed", ["Removed Files"]),
        ]:
            section = extract_section(content, headings[0])
            if section:
                files.extend(_parse_file_lines(section, change_type))
        return files

    current_type = "new"
    section_lines: list[str] = []

    for line in files_section.splitlines():
        stripped = line.strip()
        heading_match = re.match(r"^###\s+(.+)", stripped)
        if heading_match:
            if section_lines:
                files.extend(_parse_file_lines("\n".join(section_lines), current_type))
                section_lines = []
            heading_text = heading_match.group(1).strip().lower()
            current_type = heading_to_type.get(heading_text, "new")
            continue
        section_lines.append(line)

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


def parse_references(content: str) -> list[dict[str, Any]]:
    """Extract cross-references from ## References, ## Dependencies, ## Related Code."""
    refs: list[dict[str, Any]] = []

    for section_name in ["References", "Dependencies", "Related Code", "Related Tickets"]:
        section = extract_section(content, section_name)
        if not section:
            continue

        for line in section.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            ticket_match = re.findall(r"\b(\d+)\b", stripped)
            for t in ticket_match:
                ref_type = "ticket"
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

            code_refs = re.findall(r"`([^`]+\.\w+)`", stripped)
            for c in code_refs:
                refs.append({"ref_type": "code", "ref_target": c})

    return refs


def detect_ticket_type(content: str) -> str:
    """Detect whether this is a feature ticket or debug ticket."""
    first_line = content.splitlines()[0] if content.splitlines() else ""
    if "debug" in first_line.lower():
        return "debug"
    return "feature"
