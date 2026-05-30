#!/usr/bin/env python
"""
Flush all data: SQLite tables, Neo4j design graph, logs, and project directory.

Can be run standalone or imported as a library function.

Usage:
    python scripts/flush_db.py
    python scripts/flush_db.py --keep-project  # keep the project directory on disk
"""

import os
import shutil
import sys

# Allow running directly from the scripts/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
LOGS_DIR = os.path.join(REPO_ROOT, "logs")


def flush_all(clear_logs: bool = True, clear_project_dir: bool = True):
    """Flush SQLite tables, Neo4j design graph, and optionally logs/project dir.

    Args:
        clear_logs: If True, clear and recreate the logs directory.
        clear_project_dir: If True, remove the project directory from disk
            using the name and working_directory stored in ProjectMeta.
    """
    from services.dependencies import init_neo4j, close_neo4j
    from backend.db import init_db, get_session, get_main_engine
    from backend.db.base import Base

    init_db()
    engine = get_main_engine()
    Base.metadata.create_all(engine)

    # Read project metadata before dropping tables so we know what to clean up
    project_dir = ""
    if clear_project_dir:
        from backend.db.models import ProjectMeta
        with get_session() as session:
            meta = session.query(ProjectMeta).filter_by(id=1).first()
            if meta and meta.name and meta.working_directory:
                project_dir = os.path.join(meta.working_directory, meta.name)

    init_neo4j()

    # Now drop everything for a clean slate
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    from backend.db.vec import ensure_vec_table
    ensure_vec_table()

    with get_session() as session:
        pass  # Predicate seeding removed — predicates live in Neo4j via DEFAULT_PREDICATES

    # Clear Neo4j design graph (preserves cppreference data)
    from backend.db.neo4j.sync import clear_design_graph
    clear_design_graph()

    # Clear HLR/LLR nodes too (Phase 2 primary store)
    from services.dependencies import get_neo4j
    with get_neo4j().session() as session:
        session.run("MATCH (n:HLR) DETACH DELETE n")
        session.run("MATCH (n:LLR) DETACH DELETE n")
        session.run("MATCH (n:VerificationMethod) DETACH DELETE n")
        session.run("MATCH (n:Condition) DETACH DELETE n")
        session.run("MATCH (n:Action) DETACH DELETE n")

        # Clean up verification stub nodes (source_type='verification')
        result = session.run(
            "MATCH (d:Design {source_type: 'verification'}) DETACH DELETE d "
            "RETURN count(d) AS deleted"
        )
        deleted = result.single()["deleted"]
        if deleted:
            print(f"  Deleted {deleted} verification stub design nodes")

    close_neo4j()

    if clear_logs:
        if os.path.exists(LOGS_DIR):
            shutil.rmtree(LOGS_DIR)
        os.makedirs(LOGS_DIR, exist_ok=True)

    if clear_project_dir and project_dir and os.path.exists(project_dir):
        shutil.rmtree(project_dir)
        print(f"  Removed project directory: {project_dir}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Flush all data: SQLite, Neo4j, logs, and project directory.")
    parser.add_argument(
        "--keep-project", action="store_true",
        help="Keep the project directory on disk (only flush DB and logs)",
    )
    parser.add_argument(
        "--nuke-neo4j", action="store_true",
        help="Delete ALL Neo4j nodes, relationships, constraints, and indexes. "
             "Use this when the schema changes (e.g. constraint -> index migration). "
             "WARNING: This requires re-importing cppreference.",
    )
    args = parser.parse_args()

    if args.nuke_neo4j:
        _nuke_neo4j()

    flush_all(clear_project_dir=not args.keep_project)
    print("Database flushed (SQLite + Neo4j design graph).")
    print(f"Logs cleared: {LOGS_DIR}")


def _nuke_neo4j():
    """Delete ALL nodes, relationships, constraints, and indexes from Neo4j."""
    from backend.db.neo4j.connection import Neo4jConnection

    print("Nuking Neo4j - this will delete EVERYTHING (nodes, constraints, indexes)...")
    conn = Neo4jConnection()
    if not conn.verify_connectivity():
        print("  Neo4j not reachable - skipping")
        return

    driver = conn.get_driver()
    with driver.session(database="neo4j") as session:
        # Drop all constraints
        result = session.run("SHOW CONSTRAINTS")
        constraints = [record["name"] for record in result]
        for name in constraints:
            try:
                session.run(f"DROP CONSTRAINT {name}")
                print(f"  Dropped constraint: {name}")
            except Exception as e:
                print(f"  Failed to drop constraint {name}: {e}")

        # Drop all indexes
        result = session.run("SHOW INDEXES")
        indexes = [record["name"] for record in result]
        for name in indexes:
            try:
                session.run(f"DROP INDEX {name}")
                print(f"  Dropped index: {name}")
            except Exception as e:
                print(f"  Failed to drop index {name}: {e}")

        # Delete all nodes and relationships
        session.run("MATCH (n) DETACH DELETE n")
        print(f"  Deleted all nodes and relationships")

    conn.close()
    print("Neo4j nuked.")