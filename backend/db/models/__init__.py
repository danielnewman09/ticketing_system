"""Re-export all models for convenient imports.

Phase 3: VerificationMethod, VerificationCondition, VerificationAction
SQLAlchemy models deleted. Constants moved to verification_formatting.py.
Verification data lives in Neo4j via VerificationRepository.
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
from backend.db.models.ontology import (
    LANGUAGE_SPECIALIZATIONS,
    NODE_KIND_VALUES,
    NODE_KINDS,
    SOURCE_TYPE_VALUES,
    SOURCE_TYPES,
    SUPPORTED_LANGUAGES,
    TYPE_KINDS,
    VALUE_KINDS,
    VISIBILITY_CHOICES,
    OntologyNode,
    OntologyTriple,
    Predicate,
    valid_specializations,
)
from backend.requirements.formatting import format_hlr_dict, format_hlrs_for_prompt, format_llr_dict
from backend.requirements.verification_formatting import CONDITION_OPERATORS, VERIFICATION_METHODS

# TicketRequirement removed in Phase 2 — requirements are now in Neo4j
# VerificationMethod/VerificationCondition/VerificationAction removed in Phase 3
# — verification data lives in Neo4j via VerificationRepository

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
    # Ontology
    "LANGUAGE_SPECIALIZATIONS",
    "NODE_KIND_VALUES",
    "NODE_KINDS",
    "SOURCE_TYPE_VALUES",
    "SOURCE_TYPES",
    "SUPPORTED_LANGUAGES",
    "TYPE_KINDS",
    "VALUE_KINDS",
    "VISIBILITY_CHOICES",
    "OntologyNode",
    "OntologyTriple",
    "Predicate",
    "valid_specializations",
    # Requirements
    "format_hlr_dict",
    "format_hlrs_for_prompt",
    "format_llr_dict",
    # Verification constants (models removed in Phase 3)
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
