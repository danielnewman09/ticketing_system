"""Sync project environment from filesystem to Neo4j.

Reads the conanfile.py (and other project files) on disk and ensures
that the corresponding Language, Component, and Dependency nodes exist
in Neo4j with the correct relationships.

This module is the migrated equivalent of the SQLAlchemy event listeners
and UI-driven CRUD that populated the ``languages``, ``components``,
``dependency_managers``, and ``dependencies`` tables.  Instead of
writing to SQLite, we write to Neo4j via neomodel.

The sync is **idempotent** — running it multiple times produces the same
result without creating duplicate nodes or relationships.

**Tag policy**: this module does NOT set workflow tags on nodes.  Tag
computation is the sole responsibility of
:mod:`frontend_migrated.data.tags`, which runs after this module in the
page-load sequence.  Nodes created here start with an empty ``tags``
list; ``sync_all_tags()`` fills in the correct tags based on
deterministic state checks.

Usage::

    from frontend_migrated.data.environment import sync_project_environment
    from frontend_migrated.data.tags import sync_all_tags

    # After scaffolding or on page load — sync nodes, then tags:
    sync_project_environment(project_dir)
    sync_all_tags(project_dir)
"""

from __future__ import annotations

import ast
import logging
import os
import re

from codegraph.persistence.config import config as _neo4j_config  # noqa: F401

from backend_migrated.models import Component, Dependency, Language, ProjectMeta

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Conanfile parsing (pure functions — no I/O side effects)
# ---------------------------------------------------------------------------


def parse_conan_requires(conanfile_path: str) -> list[dict]:
    """Parse a conanfile.py and extract ``self.requires()`` calls.

    Returns a list of dicts with keys:
        - name: package name (e.g. 'spdlog')
        - version: version string (e.g. '1.14.1')
        - is_dev: True if inside ``build_requirements()`` or
          ``tool_requires()``, False otherwise.

    Handles both ``self.requires("pkg/version")`` and
    ``self.requires("pkg/version")`` inside ``requirements()`` or
    ``build_requirements()``.
    """
    if not os.path.isfile(conanfile_path):
        return []

    try:
        with open(conanfile_path, "r") as f:
            source = f.read()
    except OSError:
        log.warning("Could not read conanfile: %s", conanfile_path)
        return []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        log.warning("Could not parse conanfile: %s", conanfile_path)
        return []

    deps: list[dict] = []

    # Regex to extract "package/version" from self.requires("...") calls
    _requires_re = re.compile(r'([\w\-]+)/([\w\.\-]+)')

    def _extract_requires(call: ast.Call, is_dev: bool = False) -> None:
        """Extract package/version from a self.requires() or self.tool_requires() call."""
        for arg in call.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                m = _requires_re.match(arg.value.strip())
                if m:
                    deps.append({
                        "name": m.group(1),
                        "version": m.group(2),
                        "is_dev": is_dev,
                    })

    class RequiresVisitor(ast.NodeVisitor):
        """AST visitor that finds self.requires() and self.tool_requires() calls."""

        def __init__(self):
            self._in_build_requires = False

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            was_build = self._in_build_requires
            if node.name == "build_requirements":
                self._in_build_requires = True
            self.generic_visit(node)
            self._in_build_requires = was_build

        def visit_Call(self, node: ast.Call) -> None:
            # self.requires("pkg/version") or self.tool_requires("pkg/version")
            if isinstance(node.func, ast.Attribute):
                method = node.func.attr
                if method in ("requires", "tool_requires"):
                    is_dev = self._in_build_requires or method == "tool_requires"
                    _extract_requires(node, is_dev=is_dev)
            self.generic_visit(node)

    visitor = RequiresVisitor()
    visitor.visit(tree)
    return deps


def detect_language_from_cmake(project_dir: str) -> dict | None:
    """Detect the C++ standard from CMakeLists.txt.

    Returns a dict with keys ``name`` and ``version``, or None if
    the CMakeLists.txt cannot be found or parsed.
    """
    cmake_path = os.path.join(project_dir, "CMakeLists.txt")
    if not os.path.isfile(cmake_path):
        return None

    try:
        with open(cmake_path, "r") as f:
            content = f.read()
    except OSError:
        return None

    # Look for CMAKE_CXX_STANDARD or cxx_std_20 etc.
    m = re.search(r"CMAKE_CXX_STANDARD\s+(\d+)", content)
    if m:
        return {"name": "C++", "version": m.group(1)}

    m = re.search(r"cxx_std_(\d+)", content)
    if m:
        return {"name": "C++", "version": m.group(1)}

    # Default to C++ 20 if a CMakeLists.txt exists but no standard found
    return {"name": "C++", "version": "20"}


def detect_components_from_cmake(project_dir: str, project_name: str) -> list[str]:
    """Detect library components from the project directory structure.

    Looks for subdirectories under ``{project_dir}/{project_name}/``
    that contain a ``CMakeLists.txt`` — these are the project's libraries.
    """
    lib_dir = os.path.join(project_dir, project_name)
    if not os.path.isdir(lib_dir):
        return []

    components: list[str] = []
    for entry in sorted(os.listdir(lib_dir)):
        entry_path = os.path.join(lib_dir, entry)
        if os.path.isdir(entry_path) and os.path.isfile(
            os.path.join(entry_path, "CMakeLists.txt")
        ):
            components.append(entry)

    return components


# ---------------------------------------------------------------------------
# Neo4j sync (idempotent — safe to call multiple times)
# ---------------------------------------------------------------------------


def _ensure_driver() -> None:
    """Ensure neomodel's database driver is initialised."""
    from codegraph.persistence.connection import _ensure_driver as _cg_ensure
    _cg_ensure()


def _get_or_create_language(name: str, version: str = "") -> Language:
    """Get or create a Language node.

    Looks up by name first. If found, updates version if provided.
    If not found, creates a new Language node.

    Tags are NOT set here — :func:`sync_language_tags` is the sole
    authority for tag computation.
    """
    existing = Language.nodes.get_or_none(name=name)
    if existing is not None:
        if version and existing.version != version:
            existing.version = version
            existing.save()
        return existing

    refid = name.lower().replace(" ", "-")
    if version:
        refid = f"{refid}-{version}"

    lang = Language(name=name, version=version, refid=refid)
    lang.save()
    log.info("Created Language node: %s %s (refid=%s)", name, version, refid)
    return lang


def _get_or_create_component(name: str, description: str = "",
                              namespace: str = "",
                              parent_refid: str | None = None,
                              language_name: str | None = None,
                              language_version: str = "") -> Component:
    """Get or create a Component node with optional language connection.

    Tags are NOT set here — :func:`sync_component_tags` is the sole
    authority for tag computation.
    """
    # Look up by name (components should have unique names within a project)
    existing = Component.nodes.get_or_none(name=name)
    if existing is not None:
        # Ensure language connection exists
        if language_name:
            lang = _get_or_create_language(language_name, language_version)
            existing.language.connect(lang)
        return existing

    refid = name.lower().replace(" ", "-")
    if parent_refid:
        refid = f"{parent_refid}::{refid}"

    comp = Component(name=name, description=description, namespace=namespace, refid=refid)
    comp.save()

    if parent_refid:
        parent = Component.nodes.get_or_none(refid=parent_refid)
        if parent:
            parent.children.connect(comp)

    if language_name:
        lang = _get_or_create_language(language_name, language_version)
        comp.language.connect(lang)

    log.info("Created Component node: %s (refid=%s)", name, refid)
    return comp


def _get_or_create_dependency(name: str, version: str = "",
                               manager_name: str = "",
                               github_url: str = "",
                               is_dev: bool = False) -> Dependency:
    """Get or create a Dependency node.

    Looks up by refid (constructed from manager_name and name).
    If found, updates properties. If not found, creates a new node.

    Tags are NOT set here — :func:`sync_dependency_tags` is the sole
    authority for tag computation.
    """
    refid = f"{manager_name}::{name}" if manager_name else name.lower()

    existing = Dependency.nodes.get_or_none(refid=refid)
    if existing is not None:
        # Update version if provided and different
        if version and existing.version != version:
            existing.version = version
            existing.save()
        return existing

    dep = Dependency(
        name=name,
        version=version,
        manager_name=manager_name,
        github_url=github_url,
        is_dev=is_dev,
        refid=refid,
    )
    dep.save()
    log.info("Created Dependency node: %s/%s (refid=%s)", name, version, refid)
    return dep


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def sync_project_environment(project_dir: str = "") -> list[dict]:
    """Sync project environment from filesystem to Neo4j.

    Reads the conanfile.py and CMakeLists.txt on disk, then ensures
    that corresponding Language, Component, and Dependency nodes exist
    in Neo4j with the correct relationships.

    This function is **idempotent** — calling it multiple times will not
    create duplicate nodes or relationships.

    **Important**: this function does NOT set workflow tags.  Call
    :func:`~frontend_migrated.data.tags.sync_all_tags` afterwards to
    compute the correct tags based on deterministic state checks.

    Args:
        project_dir: Absolute path to the project directory. If empty,
            reads from ProjectMeta.working_directory + ProjectMeta.name.

    Returns:
        The same structure as ``fetch_environment_data()`` — a list of
        language dicts with dependencies, suitable for passing directly
        to ``_flatten_deps()``.
    """
    _ensure_driver()

    # Resolve project directory from ProjectMeta if not provided
    if not project_dir:
        try:
            meta = ProjectMeta.get_singleton()
            wd = meta.working_directory or ""
            pname = meta.name or ""
            if wd and pname:
                project_dir = os.path.join(wd, pname)
        except Exception:
            log.warning("Could not read ProjectMeta for project directory")
            return []

    if not project_dir or not os.path.isdir(project_dir):
        log.debug("sync_project_environment: project_dir not found or empty: %s", project_dir)
        return _fetch_environment_data_from_neo4j()

    # --- Detect project info from filesystem ---
    project_name = os.path.basename(project_dir)
    language_info = detect_language_from_cmake(project_dir)
    conan_deps = parse_conan_requires(os.path.join(project_dir, "conanfile.py"))
    components = detect_components_from_cmake(project_dir, project_name)

    if not language_info and not conan_deps and not components:
        # No project files found — nothing to sync
        log.debug("sync_project_environment: no project files found in %s", project_dir)
        return _fetch_environment_data_from_neo4j()

    lang_name = language_info["name"] if language_info else "C++"
    lang_version = language_info["version"] if language_info else ""

    # --- Ensure Language node ---
    language = _get_or_create_language(lang_name, lang_version)

    # --- Ensure Component nodes ---
    # Each library detected from the CMake structure becomes a Component
    # connected to the Language via WRITTEN_IN.
    comp_nodes: list[Component] = []
    for comp_name in components:
        comp = _get_or_create_component(
            name=comp_name,
            namespace=f"{comp_name}::",
            language_name=lang_name,
            language_version=lang_version,
        )
        comp_nodes.append(comp)

    # If no components were detected from CMake, create a default one
    # based on the project name. This handles projects with a single
    # library or non-standard layouts.
    if not comp_nodes and project_name:
        comp = _get_or_create_component(
            name=project_name,
            namespace=f"{project_name}::",
            language_name=lang_name,
            language_version=lang_version,
        )
        comp_nodes.append(comp)

    # --- Ensure Dependency nodes ---
    # Each conan dependency becomes a Dependency node connected to ALL
    # components via DEPENDS_ON. This is a simplification — in the
    # original system, dependencies were linked to specific components
    # via the dependency_components M2M table. We link to all components
    # because the conanfile doesn't specify which library uses which dep.
    # The user can refine this later via the UI.
    #
    # Filter out gtest and benchmark — these are test/dev dependencies
    # that don't need to appear in the dependency management table.
    _TEST_DEPS = {"gtest", "benchmark", "cmake"}

    for dep_info in conan_deps:
        dep_name = dep_info["name"]
        if dep_name.lower() in _TEST_DEPS:
            continue

        dep = _get_or_create_dependency(
            name=dep_name,
            version=dep_info.get("version", ""),
            manager_name="conan",
            is_dev=dep_info.get("is_dev", False),
        )

        # Connect the dependency to all components (idempotent — neomodel
        # handles duplicate relationship creation)
        for comp in comp_nodes:
            comp.dependencies.connect(dep)

    # --- Ensure ProjectMeta → Component COMPOSES edges ---
    # Every component should be owned by the project.  This gives a
    # direct traversal from the singleton ProjectMeta node to all
    # top-level components, independent of the Language→Component path.
    try:
        meta = ProjectMeta.get_singleton()
        for comp in comp_nodes:
            meta.components.connect(comp)
    except Exception as exc:
        log.warning("Could not connect components to ProjectMeta: %s", exc)

    log.info(
        "sync_project_environment: synced %d components, %d deps from %s",
        len(comp_nodes),
        len([d for d in conan_deps if d["name"].lower() not in _TEST_DEPS]),
        project_dir,
    )

    # Return fresh data from Neo4j
    return _fetch_environment_data_from_neo4j()


def _fetch_environment_data_from_neo4j() -> list[dict]:
    """Fetch languages with their dependencies from Neo4j.

    Internal function — the public API is ``fetch_environment_data``
    in ``frontend_migrated.data.project``, which this module calls
    after syncing.
    """
    from frontend_migrated.data.project import fetch_environment_data
    return fetch_environment_data()