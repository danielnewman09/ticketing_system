"""Project metadata and environment data — stubs.

Return types are documented via TypedDicts. All functions raise
NotImplementedError until reimplemented against the migrated backend.
No imports from backend/ anywhere in this module.
"""

from __future__ import annotations

from typing import TypedDict


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


def fetch_project_meta() -> ProjectMeta:
    """Fetch project metadata (single row), creating defaults if missing."""
    raise NotImplementedError("fetch_project_meta — requires backend_migrated data layer")


def update_project_meta(name: str, description: str, working_directory: str) -> bool:
    """Update project metadata. Returns True on success."""
    raise NotImplementedError("update_project_meta — requires backend_migrated data layer")


def fetch_environment_data() -> list[LanguageEnvironment]:
    """Fetch languages with their build systems, test frameworks, and dependencies."""
    raise NotImplementedError("fetch_environment_data — requires backend_migrated data layer")