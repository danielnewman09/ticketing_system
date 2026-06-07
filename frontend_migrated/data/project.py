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

# Importing codegraph.config at module level ensures the neomodel
# database URL is configured from environment variables before any
# neomodel model is touched.
from codegraph.config import config as _neo4j_config  # noqa: F401

from backend_migrated.models import Dependency, Language, ProjectMeta


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
    outside ``_llm_fields``.

    Each language dict has the serialized node properties plus:
    ``build_systems``, ``test_frameworks``, ``dependency_managers``
    (empty lists — not yet migrated), and ``dependencies``
    (assembled from relationships).

    Each dependency dict has the serialized node properties plus:
    ``components`` (assembled from relationships).

    NOTE: BuildSystem, TestFramework, and DependencyManager have not
    been migrated yet. The returned dicts include empty lists for those
    fields.
    """
    _ensure_driver()
    result: list[dict] = []

    for lang in Language.nodes.all():
        lang_data = lang.serialize()

        deps: list[dict] = []
        for component in lang.components.all():
            comp_name = component.name or ""
            for dep in component.dependencies.all():
                dep_data = dep.serialize(fields="all")

                # Attach the component(s) that use this dependency.
                dep_data["components"] = [{"name": comp_name}]

                deps.append(dep_data)

        # Merge language serialization with the relationship-assembled deps.
        result.append(lang_data | {
            "build_systems": [],
            "test_frameworks": [],
            "dependency_managers": [],
            "dependencies": deps,
        })

    return result