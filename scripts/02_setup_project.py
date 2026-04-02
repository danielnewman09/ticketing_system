#!/usr/bin/env python
"""
Setup project: create HLRs, assign to components, load stdlib docs.

Steps:
  1. Load C++ standard library docs into Neo4j (idempotent)
  2. Create HLRs from descriptions
  3. Assign HLRs to architectural components via AI agent

Usage:
    source .venv/bin/activate
    python scripts/setup_project.py

Requires ANTHROPIC_API_KEY in the environment.
"""

import os
import sys

from services.dependencies import get_neo4j

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from backend.db import init_db, get_session, get_or_create
from backend.db.models import Component, HighLevelRequirement

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
LOGS_DIR = os.path.join(REPO_ROOT, "logs")

HLR_DESCRIPTIONS = [
    "The application displays a GUI window with a numeric display area and buttons for digits 0-9, basic arithmetic operators (+, -, ×, ÷), a clear button, and an equals button",
    "The calculator performs addition, subtraction, multiplication, and division operations with proper input validation, returns results immediately, and recovers from errors such as division by zero or invalid syntax",
]


def load_stdlib():
    """Load C++ standard library docs into Neo4j via doxygen-index cppreference."""
    print("=" * 60)
    print("STEP 1: Load C++ standard library documentation")
    print("=" * 60)

    from pathlib import Path

    try:
        from doxygen_index.cppreference import download, parse
        from doxygen_index.neo4j_backend import (
            _get_driver,
            ensure_schema,
            write_result,
        )
    except ImportError:
        print("  doxygen-index[cppreference] not installed — skipping stdlib load")
        print("  Install with: pip install doxygen-index[cppreference]\n")
        return

    with get_neo4j().session() as session:
        result = session.run(
            "MATCH (n) WHERE n.source = 'cppreference' RETURN count(n) AS cnt"
        )
        count = result.single()["cnt"]

    if count > 0:
        print(f"  cppreference already loaded ({count} nodes) — skipping\n")
        return

    cache_dir = Path("~/.cache/doxygen-index/cppreference").expanduser()
    print("  Downloading cppreference archive (cached)...")
    archive_root = download(cache_dir)

    print("  Parsing cppreference HTML...")
    parsed = parse(archive_root)

    print("  Ingesting into Neo4j...")
    write_result(get_neo4j().get_driver(), parsed)

    print(f"  Loaded {len(parsed.compounds)} classes, {len(parsed.members)} members\n")


def assign_components():
    print("=" * 60)
    print("STEP 2: Create HLRs and assign components")
    print("=" * 60)

    from backend.ticketing_agent.design.assign_components import assign_components as _assign

    os.makedirs(LOGS_DIR, exist_ok=True)

    with get_session() as session:
        for desc in HLR_DESCRIPTIONS:
            hlr = HighLevelRequirement(description=desc)
            session.add(hlr)
        session.flush()

        hlr_count = session.query(HighLevelRequirement).count()
        print(f"\n  Assigning {hlr_count} HLRs to components via AI agent...")

        hlr_dicts = [
            {"id": h.id, "description": h.description}
            for h in session.query(HighLevelRequirement).all()
        ]
        existing = [name for (name,) in session.query(Component.name).all()]

        assignments = _assign(
            hlr_dicts,
            existing_components=existing or None,
            prompt_log_file=os.path.join(LOGS_DIR, "assign_components.md"),
        )

        # First pass: create/update components with namespaces and parents
        component_cache: dict[str, Component] = {}
        for a in assignments:
            comp_name = a["component_name"]
            if comp_name in component_cache:
                continue
            namespace = a.get("namespace", "")
            desc = a.get("description", "")
            component, _ = get_or_create(
                session, Component,
                defaults={"namespace": namespace, "description": desc},
                name=comp_name,
            )
            if not component.namespace and namespace:
                component.namespace = namespace
            if not component.description and desc:
                component.description = desc
            component_cache[comp_name] = component

        # Set parent relationships
        session.flush()
        for a in assignments:
            parent_name = a.get("parent_component_name", "")
            if parent_name and parent_name in component_cache:
                child = component_cache[a["component_name"]]
                parent = component_cache[parent_name]
                if child.id != parent.id:
                    child.parent_id = parent.id

        session.flush()

        # Second pass: assign HLRs
        for a in assignments:
            component = component_cache[a["component_name"]]
            session.query(HighLevelRequirement).filter_by(id=a["hlr_id"]).update(
                {"component_id": component.id}
            )
            ns_info = f" ns={component.namespace}" if component.namespace else ""
            print(f"  HLR {a['hlr_id']} -> {a['component_name']}{ns_info} ({a['rationale'][:50]})")

    print()


if __name__ == "__main__":
    init_db()
    load_stdlib()
    assign_components()
    print("Setup complete. Review components in the dashboard:")
    print("  http://127.0.0.1:8081/components")
