"""Component CRUD, detail, and environment CRUD — migrated.

Component nodes live in Neo4j and are managed via neomodel.
``fetch_components`` returns node objects for UI dropdowns and pages.
``get_component`` looks up a single component by refid.
``create_component`` creates a new Component node with optional
parent and language relationships.

Other functions remain stubs until their pages are migrated.

Neomodel auto-initialises its database driver on first query, so no
explicit ``_ensure_driver()`` call is needed.

No imports from backend/ anywhere in this module.
"""

from __future__ import annotations

import logging

from codegraph_project.models import Component, Language


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
# Create
# ---------------------------------------------------------------------------


def create_component(
    name: str,
    description: str = "",
    namespace: str = "",
    parent_refid: str | None = None,
    language_name: str | None = None,
) -> Component:
    """Create a new Component node in Neo4j.

    Args:
        name: Component name (e.g. "calculation_engine").
        description: Human-readable description.
        namespace: Code-level namespace (e.g. "calculation_engine::").
        parent_refid: Optional refid of the parent Component.
        language_name: Optional language name to link via WRITTEN_IN
            (e.g. "C++").  If the Language node doesn't exist it is created.

    Returns:
        The newly created Component node.
    """
    # Generate a stable refid from the name.  This is required for
    # lookups — without it, the refid defaults to "" which breaks
    # name→refid resolution and causes duplicate creation.
    refid = name.lower().replace(" ", "-")
    if parent_refid:
        refid = f"{parent_refid}::{refid}"

    comp = Component(
        name=name,
        description=description,
        namespace=namespace,
        refid=refid,
    )
    comp.save()

    if parent_refid:
        parent = Component.nodes.get_or_none(refid=parent_refid)
        if parent:
            parent.children.connect(comp)

    if language_name:
        lang = Language.nodes.get_or_none(name=language_name)
        if lang is None:
            lang = Language(name=language_name)
            lang.save()
        comp.language.connect(lang)

    # Connect the component to the ProjectMeta singleton so that
    # ProjectMeta -[:COMPOSES]-> Component is always present.
    try:
        from codegraph_project.models import ProjectMeta
        meta = ProjectMeta.get_singleton()
        meta.components.connect(comp)
    except Exception as exc:
        # ProjectMeta may not be reachable — non-fatal but worth knowing
        log.warning("Could not connect component '%s' to ProjectMeta: %s", name, exc)

    log.info("Created component %s (refid=%s)", name, comp.refid)
    return comp

def fetch_languages() -> list[Language]:
    """Return all Language nodes, sorted by name."""
    return sorted(Language.nodes.all(), key=lambda l: l.name)


# ---------------------------------------------------------------------------
# Stubs — not yet reimplemented against neomodel
# ---------------------------------------------------------------------------


def fetch_component_detail(refid: str) -> dict | None:
    """Fetch full component detail including children, environment, requirements, and nodes.

    Returns a dict with component properties and environment data, or None
    if the component is not found.
    """
    comp = Component.nodes.get_or_none(refid=refid)
    if comp is None:
        return None

    # Language
    langs = comp.language.all()
    lang_info = None
    if langs:
        lang = langs[0]
        lang_info = {
            "language_id": lang.refid,
            "language": repr(lang),
            "build_systems": [],
            "test_frameworks": [],
            "dependency_managers": [],
        }

    # Dependencies
    comp_deps = [
        {"name": d.name, "version": d.version or "", "is_dev": d.is_dev}
        for d in comp.dependencies.all()
    ]

    # Children
    children = [
        {"name": c.name, "refid": c.refid}
        for c in comp.children.all()
    ]

    # Requirements (HLRs)
    hlrs = [
        {"refid": h.refid, "description": h.description}
        for h in comp.requirements.all()
    ]

    comp_data = comp.serialize()
    comp_data.update({
        "children": children,
        "environment": lang_info,
        "dependencies": comp_deps,
        "hlrs": hlrs,
    })
    return comp_data


def ensure_component_language(refid: str, language_name: str, version: str = "") -> str:
    """Ensure a component has a language set, creating it if needed.

    Args:
        refid: Component refid to update.
        language_name: Language name (e.g. "C++").
        version: Language version (e.g. "20").

    Returns:
        The language refid.
    """
    comp = Component.nodes.get_or_none(refid=refid)
    if comp is None:
        raise ValueError(f"Component not found: {refid}")

    lang = Language.nodes.get_or_none(name=language_name)
    if lang is None:
        refid_str = language_name.lower().replace(" ", "-")
        if version:
            refid_str = f"{refid_str}-{version}"
        lang = Language(name=language_name, version=version, refid=refid_str)
        lang.save()
        log.info("Created Language node: %s %s", language_name, version)
    elif version and lang.version != version:
        lang.version = version
        lang.save()

    comp.language.connect(lang)
    return lang.refid


def add_dependency(
    dep_name: str,
    version: str = "",
    github_url: str = "",
    is_dev: bool = False,
    manager_name: str = "conan",
    component_refid: str | None = None,
) -> str:
    """Add a dependency, optionally linking it to a component.

    Creates the Dependency node if it doesn't exist. If ``component_refid``
    is provided, creates a DEPENDS_ON relationship from that component to
    the dependency.

    Args:
        dep_name: Dependency name (e.g. "spdlog").
        version: Pinned version string (e.g. "1.14.1").
        github_url: Repository URL for the dependency.
        is_dev: True if this is a dev-only dependency.
        manager_name: Package manager name (e.g. "conan").
        component_refid: Optional refid of the Component that depends on this.

    Returns:
        The refid of the Dependency node.
    """
    from codegraph_project.models import Dependency

    refid = f"{manager_name}::{dep_name}" if manager_name else dep_name.lower()

    dep = Dependency.nodes.get_or_none(refid=refid)
    if dep is None:
        dep = Dependency(
            name=dep_name,
            version=version,
            github_url=github_url,
            is_dev=is_dev,
            manager_name=manager_name,
            refid=refid,
        )
        dep.save()
        log.info("Created Dependency node: %s/%s (refid=%s)", dep_name, version, refid)
    else:
        # Update version/github if provided and different
        changed = False
        if version and dep.version != version:
            dep.version = version
            changed = True
        if github_url and dep.github_url != github_url:
            dep.github_url = github_url
            changed = True
        if changed:
            dep.save()

    # Connect to component if provided
    if component_refid:
        comp = Component.nodes.get_or_none(refid=component_refid)
        # Fallback: try name-based lookup for components created before
        # the refid-autogeneration fix (their refid is empty string).
        if comp is None and component_refid:
            comp = Component.nodes.get_or_none(name=component_refid)
        if comp:
            comp.dependencies.connect(dep)

    return dep.refid


def update_dependency_index_config(
    dep_refid: str,
    file_patterns: str,
    subdir: str,
    exclude_patterns: str,
    recursive: bool,
) -> bool:
    """Update the Doxygen indexing config for a dependency.

    Args:
        dep_refid: The Dependency node refid.
        file_patterns: Space-separated glob patterns (e.g. '*.h *.hpp').
        subdir: Subdirectory under include/ to index.
        exclude_patterns: Doxygen EXCLUDE_PATTERNS.
        recursive: Whether to index recursively.

    Returns:
        True if the update succeeded.
    """
    from codegraph_project.models import Dependency

    dep = Dependency.nodes.get_or_none(refid=dep_refid)
    if dep is None:
        log.warning("update_dependency_index_config: Dependency not found: %s", dep_refid)
        return False

    dep.index_file_patterns = file_patterns
    dep.index_subdir = subdir
    dep.index_exclude_patterns = exclude_patterns
    dep.index_recursive = recursive
    dep.save()
    log.info("Updated index config for dependency %s", dep_refid)
    return True


def delete_dependency(dep_refid: str) -> bool:
    """Delete a dependency by refid. Returns True on success.

    Also disconnects the dependency from all components that reference it.
    """
    from codegraph_project.models import Dependency

    dep = Dependency.nodes.get_or_none(refid=dep_refid)
    if dep is None:
        log.warning("delete_dependency: Dependency not found: %s", dep_refid)
        return False

    dep.delete()
    log.info("Deleted dependency %s", dep_refid)
    return True


def create_dependency_manager(
    language_refid: str,
    name: str,
    manifest_file: str,
    lock_file: str = "",
) -> str:
    """Create a dependency manager placeholder.

    DependencyManager has not been migrated to neomodel yet — its
    role is carried by the ``manager_name`` property on Dependency
    nodes. This function is a no-op placeholder that returns a
    refid derived from the language and manager name.

    Args:
        language_refid: Not used (reserved for future migration).
        name: Manager name (e.g. "conan").
        manifest_file: Not used (reserved for future migration).
        lock_file: Not used (reserved for future migration).

    Returns:
        A synthetic refid string for the manager.
    """
    log.warning(
        "create_dependency_manager: DependencyManager not yet migrated; "
        "using manager_name='%s' on Dependency nodes instead",
        name,
    )
    return f"{name}"


def delete_dependency_manager(manager_name: str) -> bool:
    """Delete all dependencies for a given package manager.

    DependencyManager has not been migrated to neomodel yet. This
    function deletes all Dependency nodes whose ``manager_name``
    matches the given name.

    Args:
        manager_name: The package manager name to clean up (e.g. "conan").

    Returns:
        True if any dependencies were deleted, False otherwise.
    """
    from codegraph_project.models import Dependency

    deleted = 0
    for dep in Dependency.nodes.filter(manager_name=manager_name):
        dep.delete()
        deleted += 1

    log.info("Deleted %d dependencies for manager '%s'", deleted, manager_name)
    return deleted > 0