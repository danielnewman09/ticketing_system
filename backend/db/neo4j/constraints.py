"""Ticketing-system-specific Neo4j constraint and index DDL."""

from __future__ import annotations

import logging
from neomodel import db

log = logging.getLogger(__name__)


def ensure_ticketing_constraints(conn=None) -> bool:
    """Create ticketing-specific constraints and indexes.

    Covers HLR, LLR, VerificationMethod, Condition, Action labels plus
    ticketing-only Compound indexes (component_id, implementation_status).
    Also handles Phase 2 migration cleanup (dropping sqlite_id constraints).

    Args:
        conn: Deprecated — kept for backward compatibility. Ignored.
    """
    try:
        db.cypher_query("RETURN 1")
    except Exception:
        log.warning("Neo4j not reachable — skipping ticketing constraint setup")
        return False

    with db.driver.session() as session:
        # Unique constraints
        for stmt in [
            "CREATE CONSTRAINT hlr_id IF NOT EXISTS FOR (n:HLR) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT llr_id IF NOT EXISTS FOR (n:LLR) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT verification_method_id IF NOT EXISTS FOR (n:VerificationMethod) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT condition_id IF NOT EXISTS FOR (n:Condition) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT action_id IF NOT EXISTS FOR (n:Action) REQUIRE n.id IS UNIQUE",
        ]:
            try:
                session.run(stmt)
            except Exception as e:
                log.debug("Constraint may already exist: %s", e)

        # Ticketing-specific indexes
        for stmt in [
            "CREATE INDEX compound_component_id IF NOT EXISTS FOR (n:Compound) ON (n.component_id)",
            "CREATE INDEX compound_implementation_status IF NOT EXISTS FOR (n:Compound) ON (n.implementation_status)",
        ]:
            try:
                session.run(stmt)
            except Exception as e:
                log.debug("Index may already exist: %s", e)

        # Phase 2 migration cleanup
        for old_constraint in ["hlr_sqlite_id", "llr_sqlite_id"]:
            try:
                session.run(f"DROP CONSTRAINT {old_constraint} IF EXISTS")
            except Exception:
                log.debug("Constraint %s did not exist, skipping drop", old_constraint)

        # Remove sqlite_id properties
        for label in ["HLR", "LLR"]:
            try:
                session.run(f"MATCH (n:{label}) REMOVE n.sqlite_id")
            except Exception:
                log.debug("No %s nodes with sqlite_id to remove", label)

    log.info("Ticketing-specific Neo4j constraints and indexes ensured")
    return True
