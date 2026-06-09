"""Component CRUD, detail, options, and environment CRUD — migrated.

Component nodes live in Neo4j and are managed via neomodel.
``fetch_components`` returns node objects for UI dropdowns.
Other functions remain stubs until their pages are migrated.

Neomodel auto-initialises its database driver on first query, so no
explicit ``_ensure_driver()`` call is needed.

No imports from backend/ anywhere in this module.
"""

from __future__ import annotations

import logging

from typing import TypedDict

from backend_migrated.models import Component

log = logging.getLogger(__name__)


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
    name: str


def fetch_component_detail(component_id: int) -> ComponentDetail | None:
    """Fetch full component detail including children, environment, requirements, and nodes."""
    raise NotImplementedError("fetch_component_detail — requires backend_migrated data layer")


def fetch_components() -> list[Component]:
    """Return all Component nodes for UI dropdowns.

    Components are read from Neo4j via neomodel.  The caller can
    access ``.name``, ``.refid``, and any other property directly
    on the node object.
    """
    return sorted(Component.nodes.all(), key=lambda c: c.name)


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