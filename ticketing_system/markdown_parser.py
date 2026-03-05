"""
Markdown parsing for ticket files.

Provides metadata extraction from ## Metadata sections.
"""

import re
from typing import Any


def parse_metadata(content: str) -> dict[str, Any]:
    """
    Parse the ## Metadata section of a ticket markdown file.

    Returns a dict of key → value for all "- **Key**: Value" lines.
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
