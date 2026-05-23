#!/usr/bin/env python
"""Migrate Phase 2 requirement data from SQLite to Neo4j.

Reads HLR and LLR rows from SQLite and creates full :HLR/:LLR nodes
in Neo4j with native id properties (replacing sqlite_id). Also
migrates AFFECTS_COMPONENT relationships and drops sqlite_id properties
from existing stub nodes.

NOTE: This script should be run AFTER the Alembic migration that drops
the HLR/LLR tables. If you need to migrate before dropping the tables,
use --skip-table-drop flag.

Usage:
    python scripts/migrate_phase2_requirements_to_neo4j.py [--clear-stubs]
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from backend.db.neo4j.connection import Neo4jConnection, get_standalone_driver
from backend.db.neo4j.repositories.requirement import RequirementRepository


def migrate_hlrs(session, neo4j_session, repo):
    """Migrate all HLR rows from SQLite to Neo4j :HLR nodes.

    This function is only useful if run BEFORE the Alembic migration
    drops the high_level_requirements table. If the table is already
    dropped, HLR data should be created directly in Neo4j.
    """
    try:
        from backend.db.models import HighLevelRequirement
    except ImportError:
        print("  HighLevelRequirement model not available (table already dropped).")
        print("  Skipping HLR migration — data must already be in Neo4j.")
        return 0

    hlrs = session.query(HighLevelRequirement).all()
    print(f"Migrating {len(hlrs)} HLRs...")

    # Clear existing HLR nodes (they may have sqlite_id from Phase 1)
    neo4j_session.run("MATCH (h:HLR) DETACH DELETE h")

    count = 0
    for hlr in hlrs:
        # Preserve the SQLite ID as the Neo4j node id
        neo4j_session.run(
            """
            CREATE (h:HLR {
                id: $id,
                description: $desc,
                component_id: $cid,
                dependency_context: $dep_ctx
            })
            """,
            {
                "id": hlr.id,
                "desc": hlr.description,
                "cid": hlr.component_id,
                "dep_ctx": hlr.dependency_context,
            },
        )
        count += 1

    print(f"  Migrated {count} HLRs")
    return count


def migrate_llrs(session, neo4j_session, repo):
    """Migrate all LLR rows from SQLite to Neo4j :LLR nodes with DECOMPOSES_INTO edges."""
    try:
        from backend.db.models import LowLevelRequirement
    except ImportError:
        print("  LowLevelRequirement model not available (table already dropped).")
        print("  Skipping LLR migration — data must already be in Neo4j.")
        return 0

    llrs = session.query(LowLevelRequirement).all()
    print(f"Migrating {len(llrs)} LLRs...")

    # Clear existing LLR nodes
    neo4j_session.run("MATCH (l:LLR) DETACH DELETE l")

    count = 0
    for llr in llrs:
        neo4j_session.run(
            """
            MATCH (h:HLR {id: $hid})
            CREATE (l:LLR {
                id: $id,
                description: $desc,
                high_level_requirement_id: $hid
            })
            CREATE (h)-[:DECOMPOSES_INTO]->(l)
            """,
            {
                "hid": llr.high_level_requirement_id,
                "id": llr.id,
                "desc": llr.description,
            },
        )
        count += 1

    print(f"  Migrated {count} LLRs")
    return count


def migrate_llr_components(session, neo4j_session):
    """Migrate low_level_requirements_components M2M to component_ids property on :LLR.

    Since Component nodes aren't in Neo4j yet, we store component_ids as a
    list property on the LLR node.
    """
    try:
        from sqlalchemy import text
    except ImportError:
        print("  SQLAlchemy not available, skipping component migration.")
        return 0

    try:
        result = session.execute(
            text("SELECT lowlevelrequirement_id, component_id FROM low_level_requirements_components")
        ).fetchall()
    except Exception:
        print("  low_level_requirements_components table not found (already dropped).")
        print("  Skipping component links migration.")
        return 0

    print(f"Migrating {len(result)} LLR↔Component links...")

    # Group by LLR id
    llr_components: dict[int, list[int]] = {}
    for llr_id, comp_id in result:
        llr_components.setdefault(llr_id, []).append(comp_id)

    for llr_id, comp_ids in llr_components.items():
        neo4j_session.run(
            "MATCH (l:LLR {id: $lid}) SET l.component_ids = $cids",
            {"lid": llr_id, "cids": comp_ids},
        )

    print(f"  Migrated {len(llr_components)} LLR component links")
    return len(llr_components)


def verify_counts(session, neo4j_session):
    """Verify that Neo4j counts look reasonable."""
    neo4j_hlrs = neo4j_session.run("MATCH (h:HLR) RETURN count(h) AS cnt").single()["cnt"]
    neo4j_llrs = neo4j_session.run("MATCH (l:LLR) RETURN count(l) AS cnt").single()["cnt"]

    # SQLite counts may be 0 if tables already dropped
    try:
        from backend.db.models import HighLevelRequirement, LowLevelRequirement
        sqlite_hlrs = session.query(HighLevelRequirement).count()
        sqlite_llrs = session.query(LowLevelRequirement).count()
    except ImportError:
        sqlite_hlrs = 0
        sqlite_llrs = 0
        print("  (SQLite models not available — skipping count comparison)")

    print(f"\nCount verification:")
    if sqlite_hlrs > 0 or sqlite_llrs > 0:
        print(f"  HLRs: SQLite={sqlite_hlrs}, Neo4j={neo4j_hlrs} {'✓' if sqlite_hlrs == neo4j_hlrs else '✗ MISMATCH'}")
        print(f"  LLRs: SQLite={sqlite_llrs}, Neo4j={neo4j_llrs} {'✓' if sqlite_llrs == neo4j_llrs else '✗ MISMATCH'}")
        return sqlite_hlrs == neo4j_hlrs and sqlite_llrs == neo4j_llrs
    else:
        print(f"  HLRs in Neo4j: {neo4j_hlrs}")
        print(f"  LLRs in Neo4j: {neo4j_llrs}")
        return True


def remove_sqlite_id_properties(neo4j_session):
    """Remove sqlite_id properties from any existing HLR/LLR nodes (Phase 1 cleanup)."""
    try:
        neo4j_session.run("MATCH (h:HLR) REMOVE h.sqlite_id")
        neo4j_session.run = neo4j_session.run  # noqa: keep reference
    except Exception:
        pass  # May not exist

    try:
        neo4j_session.run("MATCH (l:LLR) REMOVE l.sqlite_id")
    except Exception:
        pass  # May not exist

    print("  Removed sqlite_id properties from HLR/LLR nodes (if any)")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Migrate Phase 2 requirement data to Neo4j")
    parser.add_argument("--clear-stubs", action="store_true", help="Clear existing HLR/LLR stubs before migrating")
    args = parser.parse_args()

    from backend.db import init_db, get_session

    init_db()
    driver = get_standalone_driver()

    # Ensure constraints
    neo4j_conn = Neo4jConnection()
    neo4j_conn.ensure_constraints()
    neo4j_conn.ensure_requirement_constraints()

    with driver.session(database="neo4j") as neo4j_session:
        repo = RequirementRepository(neo4j_session)

        if args.clear_stubs:
            print("Clearing existing HLR/LLR stubs...")
            neo4j_session.run("MATCH (h:HLR) DETACH DELETE h")
            neo4j_session.run("MATCH (l:LLR) DETACH DELETE l")

        # Clean up Phase 1 sqlite_id properties
        remove_sqlite_id_properties(neo4j_session)

        with get_session() as session:
            print("=" * 60)
            print("Phase 2 Data Migration: SQLite HLR/LLR → Neo4j")
            print("=" * 60)

            hlr_count = migrate_hlrs(session, neo4j_session, repo)
            llr_count = migrate_llrs(session, neo4j_session, repo)
            comp_count = migrate_llr_components(session, neo4j_session)

            ok = verify_counts(session, neo4j_session)

            print("=" * 60)
            if ok:
                print("Migration complete!")
            else:
                print("Migration COMPLETE WITH WARNINGS!")
            print(f"  HLRs migrated: {hlr_count}")
            print(f"  LLRs migrated: {llr_count}")
            print(f"  Component links: {comp_count}")
            print("=" * 60)

            if not ok:
                sys.exit(1)

    driver.close()


if __name__ == "__main__":
    main()