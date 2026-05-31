"""Neo4j data access — repositories and raw queries."""

from backend.db.neo4j.connection import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER
from backend.db.neo4j.queries import (
    fetch_codebase_compounds,
    fetch_dependency_compounds,
    fetch_design_dependency_links,
    fetch_design_graph,
    fetch_hlr_subgraph,
    fetch_neighbourhood_graph,
    fetch_node_detail,
)
from backend.db.neo4j.repositories import DesignRepository, RequirementRepository, VerificationRepository
from backend.db.neo4j.models.nodes import NamespaceNode
from backend.db.neo4j.repositories.models import HLRNode, LLRNode, VerificationMethodNode, ConditionNode, ActionNode
from backend.db.neo4j.constraints import ensure_ticketing_constraints

__all__ = [
    "NEO4J_URI",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
    "DesignRepository",
    "RequirementRepository",
    "VerificationRepository",
    "NamespaceNode",
    "HLRNode",
    "LLRNode",
    "VerificationMethodNode",
    "ConditionNode",
    "ActionNode",
    "fetch_codebase_compounds",
    "fetch_dependency_compounds",
    "fetch_design_dependency_links",
    "fetch_design_graph",
    "fetch_hlr_subgraph",
    "fetch_neighbourhood_graph",
    "fetch_node_detail",
    "ensure_ticketing_constraints",
]
