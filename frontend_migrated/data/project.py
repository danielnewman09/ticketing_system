"""Project metadata and environment data — migrated backend.

Uses neomodel-based ProjectMeta node (singleton pattern) and the
migrated Component/Language/Dependency nodes.  No imports from
backend/ (SQLAlchemy) anywhere in this module.

All node-to-dict conversions use ``CodeGraphNode.serialize()`` from
the shared codegraph layer — the canonical representation of a node
as a plain dict.  TypedDict wrappers are unnecessary because
``serialize()`` already defines the shape.
"""

from __future__ import annotations

import logging

# Importing codegraph.config at module level ensures the neomodel
# database URL is configured from environment variables before any
# neomodel model is touched.
from codegraph.config import config as _neo4j_config  # noqa: F401

from backend_migrated.models import Dependency, Language, ProjectMeta, Component


def _ensure_driver() -> None:
    """Ensure neomodel's database driver is initialised.

    Importing :mod:`codegraph.config` (done at module level) already
    sets the database URL.  This call ensures the driver object exists
    so that neomodel queries can proceed.  Safe to call multiple times.
    """
    from codegraph.connection import _ensure_driver as _cg_ensure
    _cg_ensure()


# ---------------------------------------------------------------------------
# Project metadata
# ---------------------------------------------------------------------------


def fetch_project_meta() -> dict:
    """Fetch project metadata (singleton), creating defaults if missing.

    Returns the ``serialize()`` dict from the ProjectMeta node.
    The dict contains ``type``, ``name``, ``description``,
    ``working_directory``, and ``edges`` keys.
    """
    _ensure_driver()
    node = ProjectMeta.get_singleton()
    return node.serialize()


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


# ---------------------------------------------------------------------------
# Environment data
# ---------------------------------------------------------------------------


def fetch_environment_data() -> list[dict]:
    """Fetch languages with their dependencies.

    Language nodes are returned via ``Language.serialize()`` (LLM fields:
    ``name``, ``version``).  Dependency nodes use
    ``Dependency.serialize(fields="all")`` so that indexing config
    (``index_file_patterns``, etc.) is included even though it falls
    outside ``_llm_fields``).

    Each language dict has the serialized node properties plus:
    ``build_systems``, ``test_frameworks``, ``dependency_managers``
    (empty lists — not yet migrated), and ``dependencies``
    (assembled from relationships).

    Each dependency dict has the serialized node properties plus:
    ``components`` (assembled from relationships).

    In addition to language-keyed entries, this function also returns
    a synthetic "(unaffiliated)" entry for dependencies that belong to
    components attached directly to ProjectMeta via COMPOSES but not
    reachable through any Language→Component traversal.  This ensures
    that dependencies registered before scaffolding (when no Language
    node exists yet) still appear in the dependency table.

    NOTE: BuildSystem, TestFramework, and DependencyManager have not
    been migrated yet. The returned dicts include empty lists for those
    fields.
    """
    _ensure_driver()
    result: list[dict] = []

    # --- Collect all components attached to the project via COMPOSES ---
    # ProjectMeta.components gives us the authoritative list of top-level
    # components regardless of whether they have a WRITTEN_IN language edge.
    project_components: list[Component] = []
    try:
        meta = ProjectMeta.get_singleton()
        project_components = list(meta.components.all())
    except Exception as exc:
        log.warning("Could not fetch ProjectMeta components: %s", exc)

    # --- Build a set of component names already visited via Language ---
    # so we don't double-count components that appear both under a
    # language and under ProjectMeta.
    visited_component_names: set[str] = set()

    for lang in Language.nodes.all():
        lang_data = lang.serialize()

        # Collect dependencies across all components for this language.
        # A dependency may be shared by multiple components — aggregate
        # their component names rather than duplicating the dependency.
        seen_deps: dict[str, dict] = {}  # refid -> dep_data

        for component in lang.components.all():
            comp_name = component.name or ""
            visited_component_names.add(comp_name)
            for dep in component.dependencies.all():
                dep_data = dep.serialize(fields="all")
                dep_refid = dep.refid or dep.name

                if dep_refid in seen_deps:
                    # Merge component name into existing entry
                    existing_comps = seen_deps[dep_refid].get("components", [])
                    if not any(c["name"] == comp_name for c in existing_comps):
                        existing_comps.append({"name": comp_name})
                else:
                    dep_data["components"] = [{"name": comp_name}]
                    seen_deps[dep_refid] = dep_data

        # Merge language serialization with the relationship-assembled deps.
        result.append(lang_data | {
            "build_systems": [],
            "test_frameworks": [],
            "dependency_managers": [],
            "dependencies": list(seen_deps.values()),
        })

    # --- Collect deps from components attached to ProjectMeta ---
    # but not reachable via any Language (orphaned components).
    # This ensures that dependencies registered before scaffolding
    # (when no Language node exists yet) still appear in the table.
    orphan_deps: dict[str, dict] = {}  # refid -> dep_data
    orphan_lang = "(unaffiliated)"

    for comp in project_components:
        comp_name = comp.name or ""
        if comp_name in visited_component_names:
            continue  # Already counted under a language
        for dep in comp.dependencies.all():
            dep_data = dep.serialize(fields="all")
            dep_refid = dep.refid or dep.name

            if dep_refid in orphan_deps:
                existing_comps = orphan_deps[dep_refid].get("components", [])
                if not any(c["name"] == comp_name for c in existing_comps):
                    existing_comps.append({"name": comp_name})
            else:
                dep_data["components"] = [{"name": comp_name}]
                orphan_deps[dep_refid] = dep_data

    if orphan_deps:
        result.append({
            "name": orphan_lang,
            "version": "",
            "build_systems": [],
            "test_frameworks": [],
            "dependency_managers": [],
            "dependencies": list(orphan_deps.values()),
        })

    return result