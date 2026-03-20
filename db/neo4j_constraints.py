"""Neo4j schema constraints and indexes for the design-intent layer."""

import logging

from db.neo4j import get_neo4j_session, verify_connection

log = logging.getLogger(__name__)


def ensure_neo4j_constraints():
    """Create uniqueness constraints and indexes if they don't already exist.

    Safe to call repeatedly — each statement uses IF NOT EXISTS.
    """
    if not verify_connection():
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

    with get_neo4j_session() as session:
        for stmt in statements:
            session.run(stmt)

    log.info("Neo4j constraints and indexes ensured")
    return True
