#!/usr/bin/env python
"""Clear all nodes and relationships from the Neo4j database."""

from backend.db import init_db
from backend.db.neo4j import verify_connection, get_neo4j_session


def main():
    init_db()

    if not verify_connection():
        print("Neo4j unavailable")
        return

    with get_neo4j_session() as session:
        result = session.run("MATCH (n) DETACH DELETE n")
        summary = result.consume()
        print(f"Deleted {summary.counters.nodes_deleted} nodes, "
              f"{summary.counters.relationships_deleted} relationships")


if __name__ == "__main__":
    main()
