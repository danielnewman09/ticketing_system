"""Neomodel connection configuration for the ticketing system.

Replaces the old codegraph.neo4j re-export shim.
Import this module before any neomodel model class is imported.
"""

from __future__ import annotations

import logging
import os
from neomodel import config, db as neomodel_db

log = logging.getLogger(__name__)

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "")

_bolt_host = NEO4J_URI.replace("bolt://", "")
config.DATABASE_URL = f"bolt://{NEO4J_USER}:{NEO4J_PASSWORD}@{_bolt_host}"
config.ALLOW_RELOAD = True


class Neo4jSessionManager:
    """Lightweight wrapper that provides .session() for getting Neo4j driver sessions.

    Uses neomodel's configured driver under the hood. Replaces the old
    codegraph.neo4j.Neo4jConnection pattern.
    """

    def session(self):
        """Return a Neo4j driver session as a context manager."""
        return neomodel_db.driver.session()

    def verify_connectivity(self) -> bool:
        """Check that Neo4j is reachable."""
        try:
            neomodel_db.cypher_query("RETURN 1")
            return True
        except Exception:
            log.warning("Neo4j connectivity check failed", exc_info=True)
            return False

    def get_driver(self):
        """Return the underlying neomodel driver (for callers that need it)."""
        return neomodel_db.driver

    def ensure_constraints(self) -> None:
        """Ensure ticketing-specific constraints exist (backward compat)."""
        from backend.db.neo4j.constraints import ensure_ticketing_constraints
        ensure_ticketing_constraints()

    def close(self) -> None:
        """No-op — neomodel manages the driver lifecycle."""
        pass
