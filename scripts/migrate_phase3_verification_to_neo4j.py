#!/usr/bin/env python
"""Migrate Phase 3 verification data from SQLite to Neo4j.

Reads VerificationMethod, VerificationCondition, VerificationAction rows
from SQLite and creates :VerificationMethod/:Condition/:Action nodes in Neo4j
with proper edge types:
  (:LLR)-[:VERIFIES]->(:VerificationMethod)
  (:VerificationMethod)-[:HAS_CONDITION]->(:Condition)
  (:Condition)-[:LEFT_OPERAND]->(:Design)  (subject_qualified_name)
  (:Condition)-[:RIGHT_OPERAND]->(:Design) (object_qualified_name, from ontology_node)
  (:VerificationMethod)-[:HAS_ACTION]->(:Action)
  (:Action)-[:CALLEE]->(:Design)           (member_qualified_name → callee)
  (:Action)-[:CALLER]->(:Design)           (caller, inferred or empty)

Preserves SQLite ids as Neo4j node ids for consistency.

NOTE: Run this script BEFORE the Alembic migration that drops the
verification tables. If the tables are already dropped, this script
will exit gracefully.

Usage:
    python scripts/migrate_phase3_verification_to_neo4j.py [--clear]
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from backend.db.neo4j.connection import Neo4jConnection, get_standalone_driver
from backend.db.neo4j.repositories.verification import VerificationRepository


def check_sqlite_tables(session):
    """Check if verification tables still exist in SQLite. Returns (methods, conditions, actions) or None."""
    from sqlalchemy import text, inspect

    insp = inspect(session.bind)
    tables = insp.get_table_names()
    needed = {"verification_methods", "verification_conditions", "verification_actions"}
    if not needed.issubset(set(tables)):
        missing = needed - set(tables)
        print(f"  SQLite verification tables not found: {missing}")
        print("  If tables were already dropped by Alembic, verification data should be")
        print("  created by the design pipeline directly in Neo4j. Exiting.")
        return None

    # Read all rows using raw SQL (no ORM models available)
    methods = session.execute(text(
        "SELECT id, low_level_requirement_id, method, test_name, description "
        "FROM verification_methods ORDER BY id"
    )).fetchall()

    conditions = session.execute(text(
        "SELECT id, verification_id, phase, `order`, ontology_node_id, "
        "ontology_node_qualified_name, member_qualified_name, operator, expected_value "
        "FROM verification_conditions ORDER BY id"
    )).fetchall()

    actions = session.execute(text(
        "SELECT id, verification_id, `order`, description, "
        "ontology_node_id, ontology_node_qualified_name, member_qualified_name "
        "FROM verification_actions ORDER BY id"
    )).fetchall()

    return methods, conditions, actions


def migrate_verification_methods(neo4j_session, methods):
    """Create :VerificationMethod nodes with (:LLR)-[:VERIFIES]-> edges."""
    print(f"  Migrating {len(methods)} VerificationMethods...")

    # Clear existing :VerificationMethod nodes (and cascading :Condition/:Action)
    neo4j_session.run("MATCH (vm:VerificationMethod) DETACH DELETE vm")

    count = 0
    for row in methods:
        vm_id, llr_id, method, test_name, description = row
        neo4j_session.run(
            """
            MATCH (l:LLR {id: $llr_id})
            CREATE (vm:VerificationMethod {
                id: $id, method: $method,
                test_name: $test_name, description: $desc
            })
            CREATE (l)-[:VERIFIES]->(vm)
            """,
            {
                "llr_id": llr_id,
                "id": vm_id,
                "method": method,
                "test_name": test_name or "",
                "desc": description or "",
            },
        )
        count += 1

    # Also handle VerificationMethods whose LLR doesn't exist in Neo4j
    # (edge case: LLR may not have been migrated yet)
    orphans = neo4j_session.run(
        "MATCH (vm:VerificationMethod) WHERE NOT (:LLR)-[:VERIFIES]->(vm) RETURN count(vm) AS cnt"
    ).single()["cnt"]
    if orphans > 0:
        print(f"  WARNING: {orphans} VerificationMethods have no :LLR parent")

    print(f"  Migrated {count} VerificationMethods")
    return count


def migrate_conditions(neo4j_session, conditions):
    """Create :Condition nodes with :HAS_CONDITION and operand edges.

    Maps SQLite columns:
      - member_qualified_name → subject_qualified_name + :LEFT_OPERAND edge
      - ontology_node_qualified_name → object_qualified_name + :RIGHT_OPERAND edge
    """
    print(f"  Migrating {len(conditions)} Conditions...")

    # Clear existing :Condition nodes
    neo4j_session.run("MATCH (c:Condition) DETACH DELETE c")

    count = 0
    operand_edges = 0
    for row in conditions:
        cond_id, verification_id, phase, order, ontology_node_id, \
            ontology_node_qn, member_qn, operator, expected_value = row

        # member_qualified_name → subject_qualified_name
        subject_qn = member_qn or ""
        # ontology_node_qualified_name → object_qualified_name (if any)
        object_qn = ontology_node_qn or ""

        neo4j_session.run(
            """
            MATCH (vm:VerificationMethod {id: $vm_id})
            CREATE (c:Condition {
                id: $id, phase: $phase, `order`: $order,
                operator: $operator, expected_value: $expected_value,
                subject_qualified_name: $sqn, object_qualified_name: $oqn
            })
            CREATE (vm)-[:HAS_CONDITION]->(c)
            """,
            {
                "vm_id": verification_id,
                "id": cond_id,
                "phase": phase,
                "order": order or 0,
                "operator": operator or "==",
                "expected_value": expected_value or "",
                "sqn": subject_qn,
                "oqn": object_qn,
            },
        )

        # :LEFT_OPERAND edge from subject_qualified_name
        if subject_qn:
            result = neo4j_session.run(
                """
                MATCH (c:Condition {id: $cid})
                MATCH (d:Design {qualified_name: $qn})
                MERGE (c)-[:LEFT_OPERAND]->(d)
                RETURN count(*) AS cnt
                """,
                {"cid": cond_id, "qn": subject_qn},
            )
            if result.single()["cnt"] > 0:
                operand_edges += 1

        # :RIGHT_OPERAND edge from object_qualified_name
        if object_qn:
            result = neo4j_session.run(
                """
                MATCH (c:Condition {id: $cid})
                MATCH (d:Design {qualified_name: $qn})
                MERGE (c)-[:RIGHT_OPERAND]->(d)
                RETURN count(*) AS cnt
                """,
                {"cid": cond_id, "qn": object_qn},
            )
            if result.single()["cnt"] > 0:
                operand_edges += 1

        count += 1

    print(f"  Migrated {count} Conditions ({operand_edges} operand edges to :Design)")
    return count, operand_edges


def migrate_actions(neo4j_session, actions):
    """Create :Action nodes with :HAS_ACTION and callee/caller edges.

    Maps SQLite columns:
      - member_qualified_name → callee_qualified_name + :CALLEE edge
      - caller_qualified_name was not in SQLite, left empty
    """
    print(f"  Migrating {len(actions)} Actions...")

    # Clear existing :Action nodes
    neo4j_session.run("MATCH (a:Action) DETACH DELETE a")

    count = 0
    callee_edges = 0
    for row in actions:
        action_id, verification_id, order, description, \
            ontology_node_id, ontology_node_qn, member_qn = row

        # member_qualified_name → callee_qualified_name
        callee_qn = member_qn or ""
        # caller not tracked in SQLite schema
        caller_qn = ""

        neo4j_session.run(
            """
            MATCH (vm:VerificationMethod {id: $vm_id})
            CREATE (a:Action {
                id: $id, `order`: $order, description: $desc,
                caller_qualified_name: $caller_qn, callee_qualified_name: $callee_qn
            })
            CREATE (vm)-[:HAS_ACTION]->(a)
            """,
            {
                "vm_id": verification_id,
                "id": action_id,
                "order": order or 0,
                "desc": description or "",
                "caller_qn": caller_qn,
                "callee_qn": callee_qn,
            },
        )

        # :CALLEE edge from callee_qualified_name
        if callee_qn:
            result = neo4j_session.run(
                """
                MATCH (a:Action {id: $aid})
                MATCH (d:Design {qualified_name: $qn})
                MERGE (a)-[:CALLEE]->(d)
                RETURN count(*) AS cnt
                """,
                {"aid": action_id, "qn": callee_qn},
            )
            if result.single()["cnt"] > 0:
                callee_edges += 1

        count += 1

    print(f"  Migrated {count} Actions ({callee_edges} :CALLEE edges to :Design)")
    return count, callee_edges


def verify_counts(neo4j_session, methods, conditions, actions):
    """Verify Neo4j counts match SQLite counts."""
    neo4j_vms = neo4j_session.run(
        "MATCH (vm:VerificationMethod) RETURN count(vm) AS cnt"
    ).single()["cnt"]
    neo4j_conds = neo4j_session.run(
        "MATCH (c:Condition) RETURN count(c) AS cnt"
    ).single()["cnt"]
    neo4j_acts = neo4j_session.run(
        "MATCH (a:Action) RETURN count(a) AS cnt"
    ).single()["cnt"]

    sql_vms = len(methods) if methods else 0
    sql_conds = len(conditions) if conditions else 0
    sql_acts = len(actions) if actions else 0

    print(f"\n  Count verification:")
    ok = True
    for label, sql_c, neo_c in [
        ("VerificationMethod", sql_vms, neo4j_vms),
        ("Condition", sql_conds, neo4j_conds),
        ("Action", sql_acts, neo4j_acts),
    ]:
        match = "✓" if sql_c == neo_c else "✗ MISMATCH"
        print(f"    {label}: SQLite={sql_c}, Neo4j={neo_c} {match}")
        if sql_c != neo_c:
            ok = False

    return ok


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Migrate Phase 3 verification data from SQLite to Neo4j"
    )
    parser.add_argument(
        "--clear", action="store_true",
        help="Clear existing :VerificationMethod/:Condition/:Action nodes before migrating",
    )
    args = parser.parse_args()

    from backend.db import init_db, get_session

    init_db()

    print("=" * 60)
    print("Phase 3 Data Migration: SQLite Verification → Neo4j")
    print("=" * 60)

    # Step 1: Check if SQLite tables still exist
    with get_session() as session:
        data = check_sqlite_tables(session)

    if data is None:
        print("No SQLite verification data to migrate. Exiting.")
        print("=" * 60)
        return

    methods, conditions, actions = data
    print(f"\n  SQLite data found:")
    print(f"    VerificationMethods: {len(methods)}")
    print(f"    Conditions: {len(conditions)}")
    print(f"    Actions: {len(actions)}")

    # Step 2: Migrate to Neo4j
    driver = get_standalone_driver()
    neo4j_conn = Neo4jConnection()
    neo4j_conn.ensure_constraints()

    # Ensure verification constraints exist
    with driver.session(database="neo4j") as neo4j_session:
        # Create uniqueness constraints (idempotent)
        neo4j_session.run(
            "CREATE CONSTRAINT verification_method_id IF NOT EXISTS "
            "FOR (vm:VerificationMethod) REQUIRE vm.id IS UNIQUE"
        )
        neo4j_session.run(
            "CREATE CONSTRAINT condition_id IF NOT EXISTS "
            "FOR (c:Condition) REQUIRE c.id IS UNIQUE"
        )
        neo4j_session.run(
            "CREATE CONSTRAINT action_id IF NOT EXISTS "
            "FOR (a:Action) REQUIRE a.id IS UNIQUE"
        )

        if args.clear:
            print("\n  Clearing existing :VerificationMethod/:Condition/:Action nodes...")
            neo4j_session.run("MATCH (vm:VerificationMethod) DETACH DELETE vm")
            neo4j_session.run("MATCH (c:Condition) DETACH DELETE c")
            neo4j_session.run("MATCH (a:Action) DETACH DELETE a")

        print("\n  Migrating to Neo4j...")
        vm_count = migrate_verification_methods(neo4j_session, methods)
        cond_count, operand_edges = migrate_conditions(neo4j_session, conditions)
        act_count, callee_edges = migrate_actions(neo4j_session, actions)

        ok = verify_counts(neo4j_session, methods, conditions, actions)

        print("\n" + "=" * 60)
        if ok:
            print("Migration complete!")
        else:
            print("Migration COMPLETE WITH WARNINGS!")
        print(f"  VerificationMethods migrated: {vm_count}")
        print(f"  Conditions migrated: {cond_count} ({operand_edges} operand edges)")
        print(f"  Actions migrated: {act_count} ({callee_edges} callee edges)")
        print("=" * 60)

        if not ok:
            sys.exit(1)

    driver.close()


if __name__ == "__main__":
    main()
