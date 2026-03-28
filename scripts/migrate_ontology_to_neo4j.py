"""One-time migration: sync all ontology data from SQLite to Neo4j.

Usage:
    python -m scripts.migrate_ontology_to_neo4j
"""

from __future__ import annotations

import sys

from backend.db import init_db, get_session
from backend.db.neo4j import verify_connection, get_neo4j_session
from backend.db.neo4j_constraints import ensure_neo4j_constraints
from backend.db.neo4j_sync import sync_full_design


def main():
    print("Initializing database...")
    init_db()

    print("Checking Neo4j connectivity...")
    if not verify_connection():
        print("ERROR: Cannot connect to Neo4j. Is it running?")
        print("  docker compose up -d")
        sys.exit(1)

    print("Ensuring constraints and indexes...")
    ensure_neo4j_constraints()

    print("Syncing ontology data to Neo4j...")
    with get_session() as sql_session, get_neo4j_session() as neo4j_session:
        stats = sync_full_design(neo4j_session, sql_session)

    print()
    print("=== Migration Summary ===")
    print(f"  Design nodes synced:      {stats['nodes']}")
    print(f"  Design triples synced:    {stats['triples']}")
    print(f"  HLR references synced:    {stats['hlrs']}")
    print(f"  LLR references synced:    {stats['llrs']}")
    print(f"  IMPLEMENTED_BY links:     {stats['implemented_by']}")
    print()
    print("Done. Verify with:")
    print("  MATCH (n:Design) RETURN n LIMIT 10")
    print("  MATCH (r:HLR)-[:TRACES_TO]->(d:Design) RETURN r, d LIMIT 5")


if __name__ == "__main__":
    main()
