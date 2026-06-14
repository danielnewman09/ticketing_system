"""Migrated design agents — LLM tool-loop orchestration.

Agents in this package orchestrate multi-phase LLM tool loops for
project scaffolding, requirement decomposition, dependency integration,
and other design tasks.

Unlike the ``backend.ticketing_agent.design`` originals, these modules
import from ``backend_migrated`` for data access and schemas — no imports
from ``backend/``.
"""

from backend_migrated.agents.decompose_hlr import decompose
from backend_migrated.agents.scaffold_project import scaffold_project

__all__ = ["decompose", "scaffold_project"]