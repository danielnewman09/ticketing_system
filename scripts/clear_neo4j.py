#!/usr/bin/env python
"""Clear all nodes and relationships from the Neo4j database."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv

load_dotenv()

from services.dependencies import get_neo4j, init_neo4j, close_neo4j
from backend.db import init_db


def main():
    init_neo4j()
    try:
        init_db()

        with get_neo4j().session() as session:
            result = session.run("MATCH (n) DETACH DELETE n")
            summary = result.consume()
            print(
                f"Deleted {summary.counters.nodes_deleted} nodes, "
                f"{summary.counters.relationships_deleted} relationships"
            )
    finally:
        close_neo4j()


if __name__ == "__main__":
    main()