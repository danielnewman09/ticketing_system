"""Neo4j constraints and indexes for migrated ticketing node types.

Creates uniqueness constraints on refid and lookup indexes for
ProjectMeta, Component, Language, Dependency, HLR, and LLR nodes.
"""

from __future__ import annotations

import logging

from neomodel import db

log = logging.getLogger(__name__)


def ensure_migrated_constraints() -> bool:
    """Create constraints and indexes for all migrated node types.

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
            "CREATE CONSTRAINT projectmeta_refid IF NOT EXISTS "
            "FOR (p:ProjectMeta) REQUIRE p.refid IS UNIQUE",
            "CREATE CONSTRAINT component_refid IF NOT EXISTS "
            "FOR (c:Component) REQUIRE c.refid IS UNIQUE",
            "CREATE CONSTRAINT language_refid IF NOT EXISTS "
            "FOR (l:Language) REQUIRE l.refid IS UNIQUE",
            "CREATE CONSTRAINT dependency_refid IF NOT EXISTS "
            "FOR (d:Dependency) REQUIRE d.refid IS UNIQUE",
            "CREATE CONSTRAINT hlr_refid IF NOT EXISTS "
            "FOR (h:HLR) REQUIRE h.refid IS UNIQUE",
            "CREATE CONSTRAINT llr_refid IF NOT EXISTS "
            "FOR (l:LLR) REQUIRE l.refid IS UNIQUE",
            "CREATE CONSTRAINT testnode_uid IF NOT EXISTS "
            "FOR (v:Test) REQUIRE v.uid IS UNIQUE",
            "CREATE CONSTRAINT assertion_uid IF NOT EXISTS "
            "FOR (c:Assertion) REQUIRE c.uid IS UNIQUE",
            "CREATE CONSTRAINT teststep_uid IF NOT EXISTS "
            "FOR (s:TestStep) REQUIRE s.uid IS UNIQUE",
            "CREATE CONSTRAINT testfixture_uid IF NOT EXISTS "
            "FOR (f:TestFixture) REQUIRE f.uid IS UNIQUE",
        ]:
            try:
                session.run(stmt)
            except Exception as e:
                log.debug("Constraint may already exist: %s", e)

        # Lookup indexes
        for stmt in [
            "CREATE INDEX projectmeta_name IF NOT EXISTS "
            "FOR (p:ProjectMeta) ON (p.name)",
            "CREATE INDEX projectmeta_working_directory IF NOT EXISTS "
            "FOR (p:ProjectMeta) ON (p.working_directory)",
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
            "CREATE INDEX hlr_description IF NOT EXISTS "
            "FOR (h:HLR) ON (h.description)",
            "CREATE INDEX hlr_layer IF NOT EXISTS "
            "FOR (h:HLR) ON (h.layer)",
            "CREATE INDEX llr_description IF NOT EXISTS "
            "FOR (l:LLR) ON (l.description)",
            "CREATE INDEX llr_layer IF NOT EXISTS "
            "FOR (l:LLR) ON (l.layer)",
            "CREATE INDEX hlr_tags IF NOT EXISTS "
            "FOR (h:HLR) ON (h.tags)",
            "CREATE INDEX llr_tags IF NOT EXISTS "
            "FOR (l:LLR) ON (l.tags)",
            "CREATE INDEX testnode_test_name IF NOT EXISTS "
            "FOR (v:Test) ON (v.test_name)",
            "CREATE INDEX testnode_method IF NOT EXISTS "
            "FOR (v:Test) ON (v.method)",
            "CREATE INDEX testnode_tags IF NOT EXISTS "
            "FOR (v:Test) ON (v.tags)",
            "CREATE INDEX assertion_phase IF NOT EXISTS "
            "FOR (a:Assertion) ON (a.phase)",
            "CREATE INDEX assertion_tags IF NOT EXISTS "
            "FOR (a:Assertion) ON (a.tags)",
            "CREATE INDEX teststep_tags IF NOT EXISTS "
            "FOR (s:TestStep) ON (s.tags)",
            "CREATE INDEX testfixture_tags IF NOT EXISTS "
            "FOR (f:TestFixture) ON (f.tags)",
        ]:
            try:
                session.run(stmt)
            except Exception as e:
                log.debug("Index may already exist: %s", e)

    log.info("Migrated node type constraints and indexes ensured")
    return True