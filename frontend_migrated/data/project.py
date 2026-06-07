"""Project metadata and environment data — migrated backend.

Uses neomodel-based ProjectMeta node (singleton pattern) and the
migrated Component/Language/Dependency nodes. No imports from
backend/ (SQLAlchemy) anywhere in this module.
"""

from __future__ import annotations

from typing import TypedDict

# Importing codegraph.config at module level ensures the neomodel
# database URL is configured from environment variables before any
# neomodel model is touched.
from codegraph.config import config as _neo4j_config  # noqa: F401

from backend_migrated.models import Dependency, Language, ProjectMeta


class BuildSystemRow(TypedDict):
    name: str
    config_file: str | None
    version: str | None


class TestFrameworkRow(TypedDict):
    name: str
    config_file: str | None
    discovery_path: str | None


class ProjectMeta(TypedDict):
    name: str
    description: str
    working_directory: str


class EnvironmentDependency(TypedDict):
    id: int
    name: str
    version: str
    github_url: str
    manager: str
    is_dev: bool
    index_file_patterns: str
    index_subdir: str
    index_exclude_patterns: str
    index_recursive: bool
    components: list[dict]  # {id: int, name: str}


class LanguageEnvironment(TypedDict):
    id: int
    name: str
    version: str
    build_systems: list[BuildSystemRow]
    test_frameworks: list[TestFrameworkRow]
    dependency_managers: list[str]
    dependencies: list[EnvironmentDependency]


def _ensure_driver() -> None:
    """Ensure neomodel's database driver is initialised.

    Importing :mod:`codegraph.config` (done at module level) already
    sets the database URL.  This call ensures the driver object exists
    so that neomodel queries can proceed.  Safe to call multiple times.
    """
    from codegraph.connection import _ensure_driver as _cg_ensure
    _cg_ensure()


def fetch_project_meta() -> ProjectMeta:
    """Fetch project metadata (singleton), creating defaults if missing.

    Returns:
        A dict with keys ``name``, ``description``, ``working_directory``.
    """
    _ensure_driver()
    node = ProjectMeta.get_singleton()
    return {
        "name": node.name or "",
        "description": node.description or "",
        "working_directory": node.working_directory or "",
    }


def update_project_meta(name: str, description: str, working_directory: str) -> bool:
    """Update project metadata. Returns True on success.

    Args:
        name: Project name.
        description: Project description.
        working_directory: Filesystem path for the project.

    Returns:
        True if the update succeeded.
    """
    _ensure_driver()
    ProjectMeta.update_singleton(
        name=name,
        description=description,
        working_directory=working_directory,
    )
    return True


def fetch_environment_data() -> list[LanguageEnvironment]:
    """Fetch languages with their dependencies.

    NOTE: BuildSystem, TestFramework, and DependencyManager have not
    been migrated yet. The returned dicts include empty lists for those
    fields. Dependencies are populated via the migrated Dependency
    neomodel node.
    """
    _ensure_driver()
    result: list[LanguageEnvironment] = []

    for lang in Language.nodes.all():
        # Dependencies linked to this language via components
        # Since Dependency has a manager_name string property (until
        # DependencyManager is migrated), we group by language.
        deps: list[EnvironmentDependency] = []
        for component in lang.components.all():
            for dep in component.dependencies.all():
                deps.append({
                    "id": id(dep),
                    "name": dep.name or "",
                    "version": dep.version or "",
                    "github_url": dep.github_url or "",
                    "manager": dep.manager_name or "",
                    "is_dev": bool(dep.is_dev),
                    "index_file_patterns": dep.index_file_patterns or "*.h *.hpp",
                    "index_subdir": dep.index_subdir or "",
                    "index_exclude_patterns": dep.index_exclude_patterns or "",
                    "index_recursive": bool(dep.index_recursive),
                    "components": [{"id": id(component), "name": component.name or ""}],
                })

        result.append({
            "id": id(lang),
            "name": lang.name or "",
            "version": lang.version or "",
            "build_systems": [],
            "test_frameworks": [],
            "dependency_managers": [],
            "dependencies": deps,
        })

    return result