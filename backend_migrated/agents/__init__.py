"""Migrated design agents — LLM tool-loop orchestration.

Agents in this package orchestrate multi-phase LLM tool loops for
project scaffolding, dependency integration, and other design tasks.

Unlike the ``backend.ticketing_agent.design`` originals, these modules
import from ``backend_migrated`` for Neo4j data access.
"""

from backend_migrated.agents.scaffold_project import scaffold_project

__all__ = ["scaffold_project"]