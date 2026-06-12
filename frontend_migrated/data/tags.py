"""Workflow tag computation and application for Neo4j nodes.

Deterministic state checks compute tags from the current state of
the system (filesystem + Neo4j) and apply them to nodes.  Tags are
mutually exclusive within each phase — applying a new phase tag
removes any prior tag in the same phase.

Tag phases
~~~~~~~~~~
Dependency:
  - Presence: registered | missing | integrated | indexed
  - Health:   passing | failing  (or empty if not yet checked)

Component:
  - Presence: declared | scaffolded
  - Health:   passing | failing  (or empty if not yet checked)

Language:
  - Detection: detected | configured

ProjectMeta:
  - Presence: scaffolded  (or empty if not yet scaffolded)
  - Health:   passing | failing  (or empty if not yet checked)

Usage
~~~~~
::

    from frontend_migrated.data.tags import sync_dependency_tags

    # After sync_project_environment or on page load:
    sync_dependency_tags(project_dir)

    # Or sync all node types at once:
    from frontend_migrated.data.tags import sync_all_tags
    sync_all_tags(project_dir)
"""

from __future__ import annotations

import logging
import os

from backend_migrated.models import Component, Dependency, Language, ProjectMeta

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tag phase definitions — mutually exclusive within each phase
# ---------------------------------------------------------------------------

# Dependency presence tags (exactly one should be active)
_DEPENDENCY_PRESENCE_TAGS = frozenset({"registered", "missing", "integrated", "indexed"})
# Dependency health tags (at most one should be active)
_DEPENDENCY_HEALTH_TAGS = frozenset({"passing", "failing"})

# Component presence tags (exactly one should be active)
_COMPONENT_PRESENCE_TAGS = frozenset({"declared", "scaffolded"})
# Component health tags (at most one should be active)
_COMPONENT_HEALTH_TAGS = frozenset({"passing", "failing"})

# Language detection tags (at most one should be active)
_LANGUAGE_TAGS = frozenset({"detected", "configured"})

# Project presence tags
_PROJECT_PRESENCE_TAGS = frozenset({"scaffolded"})
# Project health tags (at most one should be active)
_PROJECT_HEALTH_TAGS = frozenset({"passing", "failing"})


# ---------------------------------------------------------------------------
# Tag mutation helpers
# ---------------------------------------------------------------------------


def _apply_tag(node, tag: str, phase_tags: frozenset) -> None:
    """Apply *tag* to *node*, removing any other tags in the same phase.

    Mutually exclusive: applying 'integrated' removes 'registered',
    'missing', and 'indexed' if present.  Tags from other phases are
    left untouched.

    Args:
        node: A neomodel node instance with a ``tags`` ArrayProperty.
        tag: The tag to apply (e.g. 'integrated', 'passing').
        phase_tags: The set of tags that are mutually exclusive with *tag*.
    """
    current = list(node.tags) if node.tags else []
    # Remove any existing tag from the same phase (except the one we're adding)
    new_tags = [t for t in current if t not in phase_tags or t == tag]
    if tag not in new_tags:
        new_tags.append(tag)
    if new_tags != current:
        node.tags = new_tags
        node.save()


def _remove_phase_tags(node, phase_tags: frozenset) -> None:
    """Remove all tags from *node* that belong to *phase_tags*.

    Args:
        node: A neomodel node instance with a ``tags`` ArrayProperty.
        phase_tags: The set of tags to remove.
    """
    current = list(node.tags) if node.tags else []
    new_tags = [t for t in current if t not in phase_tags]
    if new_tags != current:
        node.tags = new_tags
        node.save()


def _set_tags(node, tags: list[str]) -> None:
    """Set the tags list on *node* to exactly *tags*.

    This replaces the entire tags array. Use _apply_tag for phase-aware
    mutations that preserve tags from other phases.

    Args:
        node: A neomodel node instance with a ``tags`` ArrayProperty.
        tags: The new tags list.
    """
    current = list(node.tags) if node.tags else []
    if current != tags:
        node.tags = tags
        node.save()


# ---------------------------------------------------------------------------
# Deterministic state checks
# ---------------------------------------------------------------------------


def _conan_package_names(project_dir: str) -> set[str]:
    """Return the set of lowercased package names from conanfile.py.

    Returns an empty set if the conanfile cannot be read.
    """
    from frontend_migrated.data.environment import parse_conan_requires

    conanfile = os.path.join(project_dir, "conanfile.py")
    if not os.path.isfile(conanfile):
        return set()

    deps = parse_conan_requires(conanfile)
    return {d["name"].lower() for d in deps}


def _project_is_scaffolded(project_dir: str) -> bool:
    """Return True if CMakeLists.txt exists in the project directory."""
    if not project_dir:
        return False
    return os.path.isfile(os.path.join(project_dir, "CMakeLists.txt"))


# ---------------------------------------------------------------------------
# Tag sync functions (idempotent — safe to call multiple times)
# ---------------------------------------------------------------------------


def sync_dependency_tags(project_dir: str = "") -> int:
    """Compute and apply presence tags to all Dependency nodes.

    For each Dependency node in Neo4j, determines its lifecycle state
    based on whether the project is scaffolded and whether the
    dependency appears in conanfile.py:

    - ``registered`` — declared in Neo4j, project not yet scaffolded
    - ``missing`` — declared in Neo4j, project scaffolded, but NOT in
      conanfile.py (expected but absent from build)
    - ``integrated`` — found in conanfile.py (Conan knows about it)
    - ``indexed`` — already indexed into the documentation graph

    The ``indexed`` tag is preserved if already present on the node,
    since indexing status is determined by a separate process (not
    this function).

    Health tags (``passing``, ``failing``) are left untouched — they
    are set by build/integration verification, not by this function.

    Args:
        project_dir: Absolute path to the project directory.

    Returns:
        Number of Dependency nodes whose tags were updated.
    """
    updated = 0
    conan_names: set[str] | None = None  # lazy-loaded

    scaffolded = _project_is_scaffolded(project_dir)

    for dep in Dependency.nodes.all():
        current = list(dep.tags) if dep.tags else []
        # Preserve health tags (passing/failing) and indexed tag
        health_tags = [t for t in current if t in _DEPENDENCY_HEALTH_TAGS]
        is_indexed = "indexed" in current

        # Determine presence tag
        if is_indexed:
            # Indexed deps keep their tag regardless of conanfile state
            presence_tag = "indexed"
        elif not scaffolded:
            # Project not yet scaffolded — dependency is registered but
            # not yet integrated into a build system
            presence_tag = "registered"
        else:
            # Project is scaffolded — check if the dep is in conanfile
            if conan_names is None:
                conan_names = _conan_package_names(project_dir)
            if dep.name.lower() in conan_names:
                presence_tag = "integrated"
            else:
                presence_tag = "missing"

        # Build the new tags list: presence + health + indexed
        new_tags = [presence_tag] + health_tags
        if is_indexed and presence_tag != "indexed":
            new_tags.append("indexed")

        # Deduplicate while preserving order
        seen = set()
        deduped = []
        for t in new_tags:
            if t not in seen:
                seen.add(t)
                deduped.append(t)

        if deduped != current:
            dep.tags = deduped
            dep.save()
            updated += 1

    return updated


def sync_component_tags(project_dir: str = "") -> int:
    """Compute and apply presence tags to all Component nodes.

    For each Component node in Neo4j, determines its state:

    - ``declared`` — exists in Neo4j but no matching directory on disk
    - ``scaffolded`` — directory exists on disk (CMakeLists.txt present)

    Health tags (``passing``, ``failing``) are left untouched.

    Args:
        project_dir: Absolute path to the project directory.

    Returns:
        Number of Component nodes whose tags were updated.
    """
    updated = 0
    scaffolded = _project_is_scaffolded(project_dir)

    for comp in Component.nodes.all():
        current = list(comp.tags) if comp.tags else []
        # Preserve health tags (passing/failing)
        health_tags = [t for t in current if t in _COMPONENT_HEALTH_TAGS]

        # Determine presence tag
        if scaffolded:
            # Check if this component has a directory under the project
            comp_dir = os.path.join(project_dir, comp.name) if project_dir else ""
            if comp_dir and os.path.isdir(comp_dir):
                presence_tag = "scaffolded"
            else:
                presence_tag = "declared"
        else:
            presence_tag = "declared"

        new_tags = [presence_tag] + health_tags
        if new_tags != current:
            comp.tags = new_tags
            comp.save()
            updated += 1

    return updated


def sync_language_tags(project_dir: str = "") -> int:
    """Compute and apply detection tags to all Language nodes.

    For each Language node in Neo4j, determines its state:

    - ``detected`` — language was detected from project files
    - ``configured`` — CMakeLists.txt has the right language settings

    All languages synced from the project get ``detected``.  If the
    project is scaffolded and CMakeLists.txt exists, they also get
    ``configured``.

    Args:
        project_dir: Absolute path to the project directory.

    Returns:
        Number of Language nodes whose tags were updated.
    """
    updated = 0

    # Detect which languages exist in the project files
    detected_languages: set[str] = set()
    if project_dir:
        cmake_path = os.path.join(project_dir, "CMakeLists.txt")
        if os.path.isfile(cmake_path):
            detected_languages.add("c++")  # CMake project → C++ detected
            # If CMakeLists.txt exists, it's configured
            from frontend_migrated.data.environment import detect_language_from_cmake
            lang_info = detect_language_from_cmake(project_dir)
            if lang_info:
                detected_languages.add(lang_info["name"].lower())

    for lang in Language.nodes.all():
        current = list(lang.tags) if lang.tags else []

        lang_lower = lang.name.lower()
        if lang_lower in detected_languages:
            # Language detected from project files — set detection tags
            new_tags = ["detected"]
            if _project_is_scaffolded(project_dir):
                new_tags.append("configured")
            # Preserve health tags if any (future-proofing)
            health_tags = [t for t in current if t in ("passing", "failing")]
            new_tags.extend(health_tags)
        else:
            # Language not in project files — remove detection tags
            # but preserve any health tags
            new_tags = [t for t in current if t not in _LANGUAGE_TAGS]

        if new_tags != current:
            lang.tags = new_tags
            lang.save()
            updated += 1

    return updated


def sync_project_tags(project_dir: str = "") -> int:
    """Compute and apply tags to the ProjectMeta singleton.

    - ``scaffolded`` — CMakeLists.txt exists on disk
    - Health tags (``passing``, ``failing``) are left untouched.

    Args:
        project_dir: Absolute path to the project directory.

    Returns:
        1 if tags were updated, 0 otherwise.
    """
    try:
        meta = ProjectMeta.get_singleton()
    except Exception as exc:
        log.warning("Could not fetch ProjectMeta for tag sync: %s", exc)
        return 0

    current = list(meta.tags) if meta.tags else []
    # Preserve health tags
    health_tags = [t for t in current if t in _PROJECT_HEALTH_TAGS]

    new_tags = list(health_tags)
    if _project_is_scaffolded(project_dir):
        new_tags.append("scaffolded")

    if new_tags != current:
        meta.tags = new_tags
        meta.save()
        return 1

    return 0


def sync_all_tags(project_dir: str = "") -> dict[str, int]:
    """Sync tags on all node types.

    Convenience function that calls all four sync functions and
    returns a summary dict of how many nodes were updated.

    Args:
        project_dir: Absolute path to the project directory.

    Returns:
        Dict with keys 'dependencies', 'components', 'languages',
        'project' and integer counts of updated nodes.
    """
    results = {
        "dependencies": sync_dependency_tags(project_dir),
        "components": sync_component_tags(project_dir),
        "languages": sync_language_tags(project_dir),
        "project": sync_project_tags(project_dir),
    }
    total = sum(results.values())
    if total:
        log.info("sync_all_tags: updated %d nodes: %s", total, results)
    return results