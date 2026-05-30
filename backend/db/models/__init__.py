"""Re-export all models for convenient imports.

Phase 4: OntologyNode, OntologyTriple, Predicate ORM models deleted.
Design data lives in Neo4j via DesignRepository using typed graph
primitives (CompoundNode, MemberNode, NamespaceNode, CodebaseEdge)
from backend.db.neo4j.models.
Constants moved to backend.db.neo4j.models.constants.
"""

from backend.db.models.associations import (
    tickets_components,
    tickets_languages,
)
from backend.db.models.components import (
    BuildSystem,
    Component,
    Dependency,
    DependencyManager,
    DependencyRecommendation,
    Language,
    TestFramework,
)
from backend.requirements.formatting import format_hlr_dict, format_hlrs_for_prompt, format_llr_dict
from backend.requirements.verification_formatting import CONDITION_OPERATORS, VERIFICATION_METHODS

from backend.db.models.tickets import (
    Ticket,
    TicketAcceptanceCriteria,
    TicketFile,
    TicketReference,
)
from backend.db.models.project import ProjectMeta
from backend.db.models.tasks import (
    Task,
    TaskDesignNode,
    TaskVerification,
)

__all__ = [
    # Associations
    "tickets_components",
    "tickets_languages",
    # Components
    "BuildSystem",
    "Component",
    "Dependency",
    "DependencyManager",
    "DependencyRecommendation",
    "Language",
    "TestFramework",
    # Requirements
    "format_hlr_dict",
    "format_hlrs_for_prompt",
    "format_llr_dict",
    # Verification constants
    "CONDITION_OPERATORS",
    "VERIFICATION_METHODS",
    # Tickets
    "Ticket",
    "TicketAcceptanceCriteria",
    "TicketFile",
    "TicketReference",
    # Project
    "ProjectMeta",
    # Tasks
    "Task",
    "TaskDesignNode",
    "TaskVerification",
]