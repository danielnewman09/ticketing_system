"""Neo4j connection management for codebase graph data."""

import logging
log = logging.getLogger(__name__)

import os
from contextlib import contextmanager

from neo4j import GraphDatabase

class Neo4jConnection:
    """Manages a Neo4j driver singleton and provides session/utility helpers."""

    def __init__(self) -> None:
        self._uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        self._user = os.environ.get("NEO4J_USER", "neo4j")
        self._password = os.environ.get("NEO4J_PASSWORD")
        self._driver = None

    def get_driver(self):
        """Get or create the underlying Neo4j driver."""
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                self._uri, auth=(self._user, self._password)
            )
        return self._driver

    def close(self) -> None:
        """Close the driver and release resources."""
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    @contextmanager
    def session(self, database: str = "neo4j"):
        """Context manager that yields an open Neo4j session."""
        driver = self.get_driver()
        neo4j_session = driver.session(database=database)
        try:
            yield neo4j_session
        finally:
            neo4j_session.close()

    def verify_connectivity(self) -> bool:
        """Return True if Neo4j is reachable, False otherwise."""
        try:
            self.get_driver().verify_connectivity()
            return True
        except Exception as e:
            print(f"Neo4j connection failed: {e}")
            return False
            
    def ensure_constraints(self):
        """Create uniqueness constraints and indexes if they don't already exist.

        Safe to call repeatedly — each statement uses IF NOT EXISTS.
        """
        if not self.verify_connection():
            log.warning("Neo4j not reachable — skipping constraint setup")
            return False

        statements = [
            # Unique constraints
            "CREATE CONSTRAINT design_qualified_name IF NOT EXISTS FOR (n:Design) REQUIRE n.qualified_name IS UNIQUE",
            "CREATE CONSTRAINT hlr_sqlite_id IF NOT EXISTS FOR (n:HLR) REQUIRE n.sqlite_id IS UNIQUE",
            "CREATE CONSTRAINT llr_sqlite_id IF NOT EXISTS FOR (n:LLR) REQUIRE n.sqlite_id IS UNIQUE",
            # Indexes
            "CREATE INDEX design_kind IF NOT EXISTS FOR (n:Design) ON (n.kind)",
            "CREATE INDEX design_component_id IF NOT EXISTS FOR (n:Design) ON (n.component_id)",
        ]

        with self.session() as session:
            for stmt in statements:
                session.run(stmt)

        log.info("Neo4j constraints and indexes ensured")
        return True