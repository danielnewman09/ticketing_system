"""Neomodel connection configuration for the ticketing system.

Replaces the old codegraph.neo4j re-export shim.
Import this module before any neomodel model class is imported.
"""

import os
from neomodel import config

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "")

_bolt_host = NEO4J_URI.replace("bolt://", "")
config.DATABASE_URL = f"bolt://{NEO4J_USER}:{NEO4J_PASSWORD}@{_bolt_host}"
config.ALLOW_RELOAD = True
