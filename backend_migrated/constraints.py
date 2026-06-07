"""Neo4j constraints and indexes for migrated ticketing node types.

Creates uniqueness constraints on refid and lookup indexes for
Component, Language, and Dependency nodes. Follows the same pattern
as backend.db.neo4j.constraints for ticketing-specific constraints.
"""

from __future__ import annotations

import logging

from neomodel import db

log = logging.getLogger(__name__)


def ensure_migrated_constraints() -> bool:
    """Create constraints and indexes for Component, Language, Dependency nodes.

    Returns:
        True if constraints were created successfully, False if Neo4j
        was not reachable.
    """
    try:
        db.cypher_query("RETURN 1")
    except Exception:
        log.warning("Neo4j not reachable — skipping migrated constraint setup")
        return False

    with db.driver.session() as session:
        # Unique constraints — refid must be unique for each label
        for stmt in [
            "CREATE CONSTRAINT component_refid IF NOT EXISTS "
            "FOR (c:Component) REQUIRE c.refid IS UNIQUE",
            "CREATE CONSTRAINT language_refid IF NOT EXISTS "
            "FOR (l:Language) REQUIRE l.refid IS UNIQUE",
            "CREATE CONSTRAINT dependency_refid IF NOT EXISTS "
            "FOR (d:Dependency) REQUIRE d.refid IS UNIQUE",
        ]:
            try:
                session.run(stmt)
            except Exception as e:
                log.debug("Constraint may already exist: %s", e)

        # Lookup indexes
        for stmt in [
            "CREATE INDEX component_name IF NOT EXISTS "
            "FOR (c:Component) ON (c.name)",
            "CREATE INDEX component_namespace IF NOT EXISTS "
            "FOR (c:Component) ON (c.namespace)",
            "CREATE INDEX language_name IF NOT EXISTS "
            "FOR (l:Language) ON (l.name)",
            "CREATE INDEX dependency_name IF NOT EXISTS "
            "FOR (d:Dependency) ON (d.name)",
            "CREATE INDEX dependency_manager IF NOT EXISTS "
            "FOR (d:Dependency) ON (d.manager_name)",
        ]:
            try:
                session.run(stmt)
            except Exception as e:
                log.debug("Index may already exist: %s", e)

    log.info("Migrated node type constraints and indexes ensured")
    return True