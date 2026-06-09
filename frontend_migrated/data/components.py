"""Component CRUD, detail, and environment CRUD — migrated.

Component nodes live in Neo4j and are managed via neomodel.
``fetch_components`` returns node objects for UI dropdowns and pages.
``get_component`` looks up a single component by refid.

Other functions remain stubs until their pages are migrated.

Neomodel auto-initialises its database driver on first query, so no
explicit ``_ensure_driver()`` call is needed.

No imports from backend/ anywhere in this module.
"""

from __future__ import annotations

import logging

from backend_migrated.models import Component

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Read queries — implemented against neomodel
# ---------------------------------------------------------------------------


def get_component(refid: str) -> Component | None:
    """Look up a Component node by refid.

    Returns the node object (with all relationship managers available)
    or None if not found.
    """
    return Component.nodes.get_or_none(refid=refid)


def fetch_components() -> list[Component]:
    """Return all Component nodes for UI dropdowns and pages.

    Components are read from Neo4j via neomodel.  The caller can
    access ``.name``, ``.refid``, and any other property directly
    on the node object.
    """
    return sorted(Component.nodes.all(), key=lambda c: c.name)


# ---------------------------------------------------------------------------
# Stubs — not yet reimplemented against neomodel
# ---------------------------------------------------------------------------


def fetch_component_detail(component_id: int) -> dict | None:
    """Fetch full component detail including children, environment, requirements, and nodes."""
    raise NotImplementedError("fetch_component_detail — requires backend_migrated data layer")


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