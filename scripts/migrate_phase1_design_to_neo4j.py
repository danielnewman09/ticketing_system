#!/usr/bin/env python
"""Migrate Phase 1 design data from SQLite to Neo4j.

Reads ontology_nodes, ontology_triples, and HLR/LLR association tables
from SQLite and MERGEs them into Neo4j as :Design nodes, typed
relationships, and :HLR/:LLR stub nodes with TRACES_TO edges.

Usage:
    python scripts/migrate_phase1_design_to_neo4j.py [--clear]
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.db import init_db, get_session
from backend.db.neo4j.connection import get_standalone_driver, Neo4jConnection
from backend.db.neo4j.repositories.design import DesignRepository
from backend.db.neo4j.repositories.models import DesignNode


def clear_neo4j_design_graph(neo4j_session):
    """Remove all Design nodes and HLR/LLR stubs from Neo4j."""
    neo4j_session.run("MATCH (d:Design) DETACH DELETE d")
    neo4j_session.run("MATCH (h:HLR) DETACH DELETE h")
    neo4j_session.run("MATCH (l:LLR) DETACH DELETE l")
    print("  Cleared Design, HLR, and LLR nodes from Neo4j")


def migrate_design_nodes(session, repo):
    """Migrate all ontology_nodes → :Design nodes in Neo4j."""
    from backend.db.models import OntologyNode

    nodes = session.query(OntologyNode).all()
    print(f"Migrating {len(nodes)} design nodes...")
    count = 0
    for node in nodes:
        dn = DesignNode(
            qualified_name=node.qualified_name or node.name,
            name=node.name,
            kind=node.kind,
            specialization=node.specialization or "",
            visibility=node.visibility or "",
            description=node.description or "",
            refid=node.refid or "",
            source_type=node.source_type or "",
            type_signature=node.type_signature or "",
            argsstring=node.argsstring or "",
            definition=node.definition or "",
            file_path=node.file_path or "",
            line_number=node.line_number,
            is_static=node.is_static or False,
            is_const=node.is_const or False,
            is_virtual=node.is_virtual or False,
            is_abstract=node.is_abstract or False,
            is_final=node.is_final or False,
            component_id=node.component_id,
            is_intercomponent=node.is_intercomponent or False,
            implementation_status=node.implementation_status or "designed",
            source_file=node.source_file or "",
            test_file=node.test_file or "",
        )
        repo.merge_node(dn)
        count += 1
    print(f"  Migrated {count} design nodes")
    return count


def migrate_triples(session, repo):
    """Migrate all ontology_triples → typed relationships in Neo4j."""
    from backend.db.models import OntologyTriple, Predicate

    # Build predicate cache
    predicate_cache = {}
    for pred in session.query(Predicate).all():
        predicate_cache[pred.id] = pred.name

    triples = session.query(OntologyTriple).all()
    print(f"Migrating {len(triples)} triples...")
    count = 0
    skipped = 0
    for triple in triples:
        pred_name = predicate_cache.get(triple.predicate_id)
        if not pred_name:
            skipped += 1
            continue
        subj = triple.subject
        obj = triple.object
        if not subj or not obj:
            skipped += 1
            continue
        subj_qn = subj.qualified_name
        obj_qn = obj.qualified_name
        if not subj_qn or not obj_qn:
            skipped += 1
            continue
        repo.merge_triple(subj_qn, pred_name, obj_qn)
        count += 1
    print(f"  Migrated {count} triples, skipped {skipped}")
    return count


def migrate_hlr_stubs(session, neo4j_session, repo):
    """Migrate HLR rows → :HLR stubs with TRACES_TO edges."""
    from backend.db.models import HighLevelRequirement

    hlrs = session.query(HighLevelRequirement).all()
    print(f"Migrating {len(hlrs)} HLR stubs...")
    count = 0
    for hlr in hlrs:
        # Create/update :HLR stub
        repo.merge_hlr_stub(
            sqlite_id=hlr.id,
            description=hlr.description,
        )
        # Also set component_id if present
        if hlr.component_id:
            neo4j_session.run(
                "MATCH (h:HLR {sqlite_id: $sid}) SET h.component_id = $cid",
                {"sid": hlr.id, "cid": hlr.component_id},
            )

        # Create DECOMPOSES_INTO edges to LLR stubs
        for llr in hlr.low_level_requirements:
            repo.merge_llr_stub(sqlite_id=llr.id, description=llr.description)
            neo4j_session.run(
                """
                MATCH (h:HLR {sqlite_id: $hid})
                MATCH (l:LLR {sqlite_id: $lid})
                MERGE (h)-[:DECOMPOSES_INTO]->(l)
                """,
                {"hid": hlr.id, "lid": llr.id},
            )

        count += 1
    print(f"  Migrated {count} HLR stubs")
    return count


def migrate_llr_stubs(session, repo):
    """Migrate LLR rows → :LLR stubs."""
    from backend.db.models import LowLevelRequirement

    llrs = session.query(LowLevelRequirement).all()
    print(f"Migrating {len(llrs)} LLR stubs...")
    count = 0
    for llr in llrs:
        repo.merge_llr_stub(sqlite_id=llr.id, description=llr.description)
        count += 1
    print(f"  Migrated {count} LLR stubs")
    return count


def migrate_hlr_traces(session, neo4j_session, repo):
    """Migrate HLR ↔ OntologyNode M2M → TRACES_TO edges.

    The M2M table may still exist in SQLite even though the ORM
    relationship was removed. Read directly via SQL.
    """
    result = session.execute(
        "SELECT highlevelrequirement_id, ontologynode_id "
        "FROM high_level_requirements_nodes"
    ).fetchall()
    print(f"Migrating {len(result)} HLR↔Node traces...")

    # Build a qname lookup for node IDs
    from backend.db.models import OntologyNode
    node_lookup = {}
    for node in session.query(OntologyNode).all():
        node_lookup[node.id] = node.qualified_name

    count = 0
    for hlr_id, node_id in result:
        qname = node_lookup.get(node_id)
        if qname:
            try:
                repo.trace_design_to_hlr(hlr_id, qname)
                count += 1
            except Exception as e:
                print(f"  Warning: Failed to trace HLR {hlr_id} → {qname}: {e}")
    print(f"  Migrated {count} HLR↔Node traces")
    return count


def migrate_llr_traces(session, neo4j_session, repo):
    """Migrate LLR ↔ OntologyNode M2M → TRACES_TO edges.

    The M2M table may still exist in SQLite even though the ORM
    relationship was removed. Read directly via SQL.
    """
    result = session.execute(
        "SELECT lowlevelrequirement_id, ontologynode_id "
        "FROM low_level_requirements_nodes"
    ).fetchall()
    print(f"Migrating {len(result)} LLR↔Node traces...")

    # Build a qname lookup for node IDs
    from backend.db.models import OntologyNode
    node_lookup = {}
    for node in session.query(OntologyNode).all():
        node_lookup[node.id] = node.qualified_name

    count = 0
    for llr_id, node_id in result:
        qname = node_lookup.get(node_id)
        if qname:
            try:
                repo.trace_design_to_llr(llr_id, qname)
                count += 1
            except Exception as e:
                print(f"  Warning: Failed to trace LLR {llr_id} → {qname}: {e}")
    print(f"  Migrated {count} LLR↔Node traces")
    return count


def migrate_task_links(session, neo4j_session):
    """Migrate TaskDesignNode links → IMPLEMENTING edges in Neo4j.

    Updates TaskDesignNode.ontology_node_qualified_name for each row.
    """
    from backend.db.models import OntologyNode, Task

    # Build qname lookup
    node_lookup = {}
    for node in session.query(OntologyNode).all():
        node_lookup[node.id] = node.qualified_name

    # Update ontology_node_qualified_name for existing TaskDesignNode rows
    from sqlalchemy import text
    result = session.execute(
        text("SELECT id, ontology_node_id FROM task_design_nodes "
            "WHERE ontology_node_qualified_name = '' OR ontology_node_qualified_name IS NULL")
    ).fetchall()
    updated = 0
    for td_id, node_id in result:
        qname = node_lookup.get(node_id)
        if qname:
            session.execute(
                text("UPDATE task_design_nodes SET ontology_node_qualified_name = :qn WHERE id = :tid"),
                {"qn": qname, "tid": td_id},
            )
            updated += 1
    session.flush()
    print(f"Updated {updated} TaskDesignNode rows with qualified_name")

    # Also sync Task nodes to Neo4j
    from backend.db.neo4j.sync import sync_task
    tasks = session.query(Task).all()
    print(f"Syncing {len(tasks)} Task nodes to Neo4j...")
    for task in tasks:
        try:
            sync_task(neo4j_session, task)
        except Exception as e:
            print(f"  Warning: Failed to sync Task {task.id}: {e}")
    print(f"  Synced {len(tasks)} Task nodes")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Migrate Phase 1 design data to Neo4j")
    parser.add_argument("--clear", action="store_true", help="Clear Neo4j Design/HLR/LLR nodes before migrating")
    args = parser.parse_args()

    init_db()
    driver = get_standalone_driver()

    # Ensure constraints
    neo4j_conn = Neo4jConnection()
    neo4j_conn.ensure_constraints()
    neo4j_conn.ensure_design_constraints()

    with driver.session(database="neo4j") as neo4j_session:
        repo = DesignRepository(neo4j_session)

        if args.clear:
            print("Clearing existing Neo4j design data...")
            clear_neo4j_design_graph(neo4j_session)

        with get_session() as session:
            print("=" * 60)
            print("Phase 1 Data Migration: SQLite → Neo4j")
            print("=" * 60)

            # Step 1: Design nodes
            node_count = migrate_design_nodes(session, repo)

            # Step 2: Triples
            triple_count = migrate_triples(session, repo)

            # Step 3: HLR stubs
            hlr_count = migrate_hlr_stubs(session, neo4j_session, repo)

            # Step 4: LLR stubs
            llr_count = migrate_llr_stubs(session, repo)

            # Step 5: HLR → Design traces (M2M)
            hlr_trace_count = migrate_hlr_traces(session, neo4j_session, repo)

            # Step 6: LLR → Design traces (M2M)
            llr_trace_count = migrate_llr_traces(session, neo4j_session, repo)

            # Step 7: Task links
            migrate_task_links(session, neo4j_session)

            print("=" * 60)
            print(f"Migration complete!")
            print(f"  Design nodes:  {node_count}")
            print(f"  Triples:       {triple_count}")
            print(f"  HLR stubs:    {hlr_count}")
            print(f"  LLR stubs:    {llr_count}")
            print(f"  HLR traces:   {hlr_trace_count}")
            print(f"  LLR traces:   {llr_trace_count}")
            print("=" * 60)

    driver.close()


if __name__ == "__main__":
    main()