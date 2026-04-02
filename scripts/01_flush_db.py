#!/usr/bin/env python
"""
Flush all data: SQLite tables, Neo4j design graph, and logs.

Can be run standalone or imported as a library function.

Usage:
    python scripts/flush_db.py
"""

import os
import shutil
import sys

# Allow running directly from the scripts/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
LOGS_DIR = os.path.join(REPO_ROOT, "logs")


def flush_all(clear_logs: bool = True, clear_project_dir: str = ""):
    """Flush SQLite tables, Neo4j design graph, and optionally logs/project dir.

    Args:
        clear_logs: If True, clear and recreate the logs directory.
        clear_project_dir: If non-empty, remove this directory.
    """
    from backend.db import init_db, get_session, get_main_engine
    from backend.db.base import Base
    from backend.db.models import Predicate
    from backend.db.vec import ensure_vec_table
    from backend.db.neo4j_sync import clear_design_graph

    init_db()
    engine = get_main_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    ensure_vec_table()

    with get_session() as session:
        Predicate.ensure_defaults(session)

    # Clear Neo4j design graph (preserves cppreference data)
    clear_design_graph()

    if clear_logs:
        if os.path.exists(LOGS_DIR):
            shutil.rmtree(LOGS_DIR)
        os.makedirs(LOGS_DIR, exist_ok=True)

    if clear_project_dir and os.path.exists(clear_project_dir):
        shutil.rmtree(clear_project_dir)


if __name__ == "__main__":
    flush_all()
    print("Database flushed (SQLite + Neo4j design graph).")
    print(f"Logs cleared: {LOGS_DIR}")
