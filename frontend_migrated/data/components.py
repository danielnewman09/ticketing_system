"""Component CRUD, detail, options, and environment CRUD — stubs.

Return types are documented via TypedDicts. All functions raise
NotImplementedError until reimplemented against the migrated backend.
No imports from backend/ anywhere in this module.
"""

from __future__ import annotations

from typing import TypedDict


class ComponentRow(TypedDict):
    id: int
    name: str
    namespace: str
    language: str | None
    parent: str | None
    hlr_count: int
    node_count: int


class ComponentChild(TypedDict):
    id: int
    name: str
    namespace: str | None
    hlr_count: int
    node_count: int


class BuildSystemRow(TypedDict):
    name: str
    config_file: str | None
    version: str | None


class TestFrameworkRow(TypedDict):
    name: str
    config_file: str | None
    discovery_path: str | None


class DependencyInManager(TypedDict):
    id: int
    name: str
    version: str
    is_dev: bool


class DependencyManagerRow(TypedDict):
    id: int
    name: str
    manifest_file: str
    lock_file: str
    dependencies: list[DependencyInManager]


class ComponentEnvironment(TypedDict):
    language_id: int
    language: str
    build_systems: list[BuildSystemRow]
    test_frameworks: list[TestFrameworkRow]
    dependency_managers: list[DependencyManagerRow]


class ComponentDetail(TypedDict):
    id: int
    name: str
    description: str
    namespace: str
    parent: dict | None  # {id: int, name: str}
    children: list[ComponentChild]
    environment: ComponentEnvironment | None
    hlrs: list[dict]  # {id, description, llr_count}
    dependencies: list[dict]  # {id, name, version, is_dev}
    default_manager_id: int | None
    node_kinds: dict[str, int]
    nodes_sample: list[dict]
    node_count: int


class ComponentOption(TypedDict):
    id: int
    name: str


def fetch_components_data() -> list[ComponentRow]:
    """Fetch all data needed for the components page."""
    raise NotImplementedError("fetch_components_data — requires backend_migrated data layer")


def fetch_component_detail(component_id: int) -> ComponentDetail | None:
    """Fetch full component detail including children, environment, requirements, and nodes."""
    raise NotImplementedError("fetch_component_detail — requires backend_migrated data layer")


def fetch_components_options() -> list[ComponentOption]:
    """Return list of {id, name} for component dropdowns."""
    raise NotImplementedError("fetch_components_options — requires backend_migrated data layer")


def ensure_component_language(component_id: int, language_name: str, version: str = "") -> int:
    """Ensure a component has a language set, creating it if needed. Returns language id."""
    raise NotImplementedError("ensure_component_language — requires backend_migrated data layer")


def create_dependency_manager(
    language_id: int,
    name: str,
    manifest_file: str,
    lock_file: str = "",
) -> int:
    """Create a dependency manager. Returns the new id."""
    raise NotImplementedError("create_dependency_manager — requires backend_migrated data layer")


def add_dependency(
    manager_id: int,
    name: str,
    version: str = "",
    is_dev: bool = False,
    component_id: int | None = None,
) -> int:
    """Add a dependency to a manager. Returns the new id."""
    raise NotImplementedError("add_dependency — requires backend_migrated data layer")


def update_dependency_index_config(
    dep_id: int,
    file_patterns: str,
    subdir: str,
    exclude_patterns: str,
    recursive: bool,
) -> bool:
    """Update the Doxygen indexing config for a dependency."""
    raise NotImplementedError("update_dependency_index_config — requires backend_migrated data layer")


def delete_dependency(dep_id: int) -> bool:
    """Delete a dependency. Returns True on success."""
    raise NotImplementedError("delete_dependency — requires backend_migrated data layer")


def delete_dependency_manager(manager_id: int) -> bool:
    """Delete a dependency manager and its dependencies. Returns True on success."""
    raise NotImplementedError("delete_dependency_manager — requires backend_migrated data layer")