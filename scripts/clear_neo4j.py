#!/usr/bin/env python
"""Clear all nodes and relationships from the Neo4j database."""

from services.dependencies import get_neo4j

from backend.db import init_db

def main():
    init_db()

    with get_neo4j().session() as session:
        result = session.run("MATCH (n) DETACH DELETE n")
        summary = result.consume()
        print(f"Deleted {summary.counters.nodes_deleted} nodes, "
              f"{summary.counters.relationships_deleted} relationships")


if __name__ == "__main__":
    main()
