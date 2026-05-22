"""Neo4j data access — connection, repositories, and raw queries."""

from backend.db.neo4j.connection import (
    NEO4J_PASSWORD,
    NEO4J_URI,
    NEO4J_USER,
    Neo4jConnection,
    close_standalone_driver,
    get_standalone_driver,
    get_standalone_session,
)
from backend.db.neo4j.queries import (
    fetch_codebase_compounds,
    fetch_dependency_compounds,
    fetch_design_dependency_links,
    fetch_design_graph,
    fetch_hlr_subgraph,
    fetch_neighbourhood_graph,
    fetch_node_detail,
)
from backend.db.neo4j.repositories import DesignRepository
from backend.db.neo4j.repositories.models import DesignNode, DesignTripleUpdate

__all__ = [
    "Neo4jConnection",
    "NEO4J_URI",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
    "get_standalone_driver",
    "get_standalone_session",
    "close_standalone_driver",
    # Repositories
    "DesignRepository",
    "DesignNode",
    "DesignTripleUpdate",
    # Queries
    "fetch_codebase_compounds",
    "fetch_dependency_compounds",
    "fetch_design_dependency_links",
    "fetch_design_graph",
    "fetch_hlr_subgraph",
    "fetch_neighbourhood_graph",
    "fetch_node_detail",
]