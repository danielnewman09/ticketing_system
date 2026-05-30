"""Neo4j driver management — NiceGUI-bound singleton and standalone connection."""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager

from neo4j import GraphDatabase

log = logging.getLogger(__name__)

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD")


class Neo4jConnection:
    """Manages a Neo4j driver singleton (NiceGUI app-bound) with session helpers."""

    def __init__(self) -> None:
        self._uri = NEO4J_URI
        self._user = NEO4J_USER
        self._password = NEO4J_PASSWORD
        self._driver = None
        log.info("Neo4jConnection created (uri=%s, user=%s)", self._uri, self._user)

    def get_driver(self):
        if self._driver is None:
            self._driver = GraphDatabase.driver(self._uri, auth=(self._user, self._password))
            log.info("Neo4j driver created (uri=%s)", self._uri)
        return self._driver

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None
            log.info("Neo4j driver closed")

    @contextmanager
    def session(self, database: str = "neo4j"):
        driver = self.get_driver()
        neo4j_session = driver.session(database=database)
        try:
            yield neo4j_session
        finally:
            neo4j_session.close()

    def verify_connectivity(self) -> bool:
        try:
            self.get_driver().verify_connectivity()
            log.debug("Neo4j connectivity verified")
            return True
        except Exception as e:
            log.warning("Neo4j connection failed: %s", e)
            return False

    def ensure_constraints(self):
        if not self.verify_connectivity():
            log.warning("Neo4j not reachable — skipping constraint setup")
            return False
        statements = [
            # Use INDEX instead of CONSTRAINT — :Compound/:Member/:Namespace may
            # already have data (e.g. cppreference) with existing indexes.
            "CREATE INDEX compound_qualified_name IF NOT EXISTS FOR (n:Compound) ON (n.qualified_name)",
            "CREATE INDEX member_qualified_name IF NOT EXISTS FOR (n:Member) ON (n.qualified_name)",
            "CREATE INDEX namespace_qualified_name IF NOT EXISTS FOR (n:Namespace) ON (n.qualified_name)",
            # Legacy Design constraint (kept for migration period)
            "CREATE CONSTRAINT hlr_id IF NOT EXISTS FOR (n:HLR) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT llr_id IF NOT EXISTS FOR (n:LLR) REQUIRE n.id IS UNIQUE",
            # New indexes
            "CREATE INDEX compound_layer IF NOT EXISTS FOR (n:Compound) ON (n.layer)",
            "CREATE INDEX compound_kind IF NOT EXISTS FOR (n:Compound) ON (n.kind)",
            "CREATE INDEX compound_component_id IF NOT EXISTS FOR (n:Compound) ON (n.component_id)",
            "CREATE INDEX member_layer IF NOT EXISTS FOR (n:Member) ON (n.layer)",
            "CREATE INDEX member_kind IF NOT EXISTS FOR (n:Member) ON (n.kind)",
            "CREATE INDEX namespace_layer IF NOT EXISTS FOR (n:Namespace) ON (n.layer)",
            # Legacy indexes (kept during migration)
            "CREATE CONSTRAINT verification_method_id IF NOT EXISTS FOR (n:VerificationMethod) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT condition_id IF NOT EXISTS FOR (n:Condition) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT action_id IF NOT EXISTS FOR (n:Action) REQUIRE n.id IS UNIQUE",
        ]
        with self.session() as session:
            for stmt in statements:
                try:
                    session.run(stmt)
                except Exception as e:
                    log.debug("Index/constraint may already exist: %s", e)
        log.info("Neo4j constraints and indexes ensured")
        return True

    def ensure_design_constraints(self):
        """Create additional constraints and indexes for the design layer.

        Includes both new Compound/Member/Namespace indexes and legacy Design
        indexes for migration compatibility.
        """
        if not self.verify_connectivity():
            log.warning("Neo4j not reachable — skipping design constraint setup")
            return False
        statements = [
            # New layer-based indexes
            "CREATE INDEX compound_layer IF NOT EXISTS FOR (n:Compound) ON (n.layer)",
            "CREATE INDEX compound_implementation_status IF NOT EXISTS FOR (n:Compound) ON (n.implementation_status)",
            "CREATE INDEX compound_component_id IF NOT EXISTS FOR (n:Compound) ON (n.component_id)",
            "CREATE INDEX member_layer IF NOT EXISTS FOR (n:Member) ON (n.layer)",
            "CREATE INDEX namespace_layer IF NOT EXISTS FOR (n:Namespace) ON (n.layer)",
        ]
        with self.session() as session:
            for stmt in statements:
                try:
                    session.run(stmt)
                except Exception as e:
                    log.debug("Index/constraint may already exist: %s", e)
        log.info("Neo4j design constraints and indexes ensured")
        return True

    def ensure_requirement_constraints(self):
        """Drop old sqlite_id constraints and create new id constraints for HLR/LLR.

        Call this during Phase 2 migration to transition from sqlite_id to native id.
        Also removes the sqlite_id property from all HLR/LLR nodes.
        """
        if not self.verify_connectivity():
            log.warning("Neo4j not reachable — skipping requirement constraint setup")
            return False
        with self.session() as session:
            # Drop old constraints (they may not exist if Phase 1 was skipped)
            for old_constraint in ["hlr_sqlite_id", "llr_sqlite_id"]:
                try:
                    session.run(f"DROP CONSTRAINT {old_constraint} IF EXISTS")
                except Exception:
                    log.debug("Constraint %s did not exist, skipping drop", old_constraint)
            # Remove sqlite_id property from all HLR/LLR nodes
            try:
                session.run("MATCH (h:HLR) REMOVE h.sqlite_id")
            except Exception:
                log.debug("No HLR nodes with sqlite_id to remove")
            try:
                session.run("MATCH (l:LLR) REMOVE l.sqlite_id")
            except Exception:
                log.debug("No LLR nodes with sqlite_id to remove")
        log.info("Neo4j requirement constraints ensured (sqlite_id dropped, id unique)")
        return True


# Standalone driver (not bound to NiceGUI app state)
_standalone_driver = None


def get_standalone_driver():
    """Get or create the standalone Neo4j driver singleton."""
    global _standalone_driver
    if _standalone_driver is None:
        _standalone_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        log.info("Standalone Neo4j driver created")
    return _standalone_driver


def close_standalone_driver():
    global _standalone_driver
    if _standalone_driver is not None:
        _standalone_driver.close()
        _standalone_driver = None
        log.info("Standalone Neo4j driver closed")


@contextmanager
def get_standalone_session(database: str = "neo4j"):
    driver = get_standalone_driver()
    session = driver.session(database=database)
    try:
        yield session
    finally:
        session.close()
