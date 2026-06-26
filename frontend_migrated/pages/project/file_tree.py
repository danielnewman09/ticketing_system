"""File tree for a project directory — class-based, neomodel-native.

Combines filesystem scanning (what's on disk) with Neo4j metadata
(what's indexed in the graph) via the ProjectMeta singleton and
CodeGraphNode's node-type registry.  No raw Cypher is used — all
graph queries go through neomodel ORM operations.

Usage::

    tree = ProjectFileTree()
    if tree.project_exists:
        cmake = tree.cmake_tree()
        conan = tree.conan_tree()
        deps = tree.conan_dependency_status()
        tree.render(cmake)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from codegraph_project.models import ProjectMeta
from codegraph.models.tags import CodeGraphNode

from nicegui import ui

from frontend_migrated.pages.project.vscode import open_file


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_IGNORED_DIRS = frozenset(
    {"build", ".git", "__pycache__", ".venv", "installs", ".vscode", "node_modules"}
)
_CMAKE_FILES = frozenset({"CMakeLists.txt", "CMakeUserPresets.json"})
_CONAN_ROOT_FILES = frozenset({"conanfile.py", "conanfile.txt"})


# ---------------------------------------------------------------------------
# Data classes for tree nodes
# ---------------------------------------------------------------------------


@dataclass
class TreeNode:
    """A single entry (file or directory) in the project file tree.

    Replaces the ad-hoc ``dict`` schema (``{"name": ..., "path": ...,
    "is_dir": ..., "children": ...}``) with a typed structure.
    """

    name: str
    path: str
    is_dir: bool
    children: list["TreeNode"] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to a plain dict (for serialization or API responses)."""
        if self.is_dir:
            return {
                "name": self.name,
                "path": self.path,
                "is_dir": True,
                "children": [c.to_dict() for c in self.children],
            }
        return {"name": self.name, "path": self.path, "is_dir": False}


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def sources_indexed(sources: set[str]) -> set[str]:
    """Return the subset of *sources* that exist as ``source`` on any Neo4j node.

    Uses :class:`CodeGraphNode`'s registry to query each registered node
    type for a matching ``source`` property.  Pure neomodel — no raw Cypher.

    Short-circuits once all sources have been found.
    """
    found: set[str] = set()
    for node_cls in CodeGraphNode._registry.values():
        if "source" not in node_cls.defined_properties():
            continue
        for src in sources - found:
            if node_cls.nodes.filter(source=src).first():
                found.add(src)
        if found >= sources:
            break
    return found


# ---------------------------------------------------------------------------
# ProjectFileTree
# ---------------------------------------------------------------------------


class ProjectFileTree:
    """File tree for a project, combining filesystem scanning with Neo4j metadata.

    Owns a :class:`ProjectMeta` singleton instance so that the project name,
    working directory, and graph queries are all derived from one source of
    truth.  Replaces the raw-Cypher dependency check with neomodel ORM
    queries via :func:`sources_indexed`.

    All filesystem I/O is in the ``*_tree`` / ``_scan_*`` methods; all Neo4j
    queries go through :func:`sources_indexed`.  Rendering is in
    :meth:`render`.
    """

    def __init__(self):
        self._meta = ProjectMeta.get_singleton()

    # ------------------------------------------------------------------
    # Properties derived from ProjectMeta
    # ------------------------------------------------------------------

    @property
    def meta(self) -> ProjectMeta:
        """The backing ProjectMeta node (singleton)."""
        return self._meta

    @property
    def project_name(self) -> str:
        return self._meta.name or ""

    @property
    def working_directory(self) -> str:
        return self._meta.working_directory or ""

    @property
    def project_dir(self) -> str:
        if self.working_directory and self.project_name:
            return os.path.join(self.working_directory, self.project_name)
        return ""

    @property
    def project_exists(self) -> bool:
        """Whether the project scaffold (CMakeLists.txt) has been created."""
        if not self.project_dir:
            return False
        return os.path.isfile(os.path.join(self.project_dir, "CMakeLists.txt"))

    # ------------------------------------------------------------------
    # Filesystem scanning (returns TreeNode trees)
    # ------------------------------------------------------------------

    def cmake_tree(self) -> list[TreeNode]:
        """Scan for CMakeLists.txt and CMakeUserPresets.json."""
        return self._scan_filtered(self.project_dir, _CMAKE_FILES)

    def conan_tree(self) -> list[TreeNode]:
        """Scan for conanfile at root + full ``conan/`` directory."""
        if not self.project_dir:
            return []
        entries: list[TreeNode] = []
        for name in _CONAN_ROOT_FILES:
            if os.path.isfile(os.path.join(self.project_dir, name)):
                entries.append(TreeNode(name=name, path=name, is_dir=False))
        conan_dir = os.path.join(self.project_dir, "conan")
        if os.path.isdir(conan_dir):
            children = self._scan_all(self.project_dir, "conan")
            if children:
                entries.append(
                    TreeNode(name="conan", path="conan", is_dir=True, children=children)
                )
        return entries

    # ------------------------------------------------------------------
    # Neo4j metadata queries (neomodel, no raw Cypher)
    # ------------------------------------------------------------------

    def conan_dependency_status(self) -> dict[str, str]:
        """Check integration status of conan dependencies.

        Returns a dict mapping lowercase dep names to:

        - ``"indexed"``    — conanfile exists on disk AND dependency is
          indexed in Neo4j.
        - ``"integrated"`` — conanfile exists on disk but not yet indexed.
        """
        conan_dir = os.path.join(self.project_dir, "conan") if self.project_dir else ""
        if not conan_dir or not os.path.isdir(conan_dir):
            return {}

        # Find deps with a conanfile on disk
        deps_with_recipe: set[str] = set()
        try:
            for name in os.listdir(conan_dir):
                if os.path.isfile(os.path.join(conan_dir, name, "conanfile.py")):
                    deps_with_recipe.add(name.lower())
        except OSError:
            return {}

        if not deps_with_recipe:
            return {}

        # Check which deps are indexed in Neo4j via neomodel ORM
        indexed = sources_indexed(deps_with_recipe)

        return {
            name: "indexed" if name in indexed else "integrated"
            for name in deps_with_recipe
        }

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render(self, tree: list[TreeNode], depth: int = 0) -> None:
        """Render a file tree with clickable files and expandable directories."""
        for entry in tree:
            indent = f"padding-left: {depth * 16 + 4}px;"
            if entry.is_dir:
                with (
                    ui.expansion(entry.name, icon="folder")
                    .classes("w-full")
                    .props("dense")
                    .style(indent)
                ):
                    self.render(entry.children, depth + 1)
            else:
                ui.label(entry.name).classes(
                    "text-xs font-mono text-blue-400 cursor-pointer py-0.5"
                ).style(indent).on(
                    "click",
                    lambda _, p=entry.path: open_file(self.project_dir, p),
                ).tooltip(entry.path)

    # ------------------------------------------------------------------
    # Private scanning helpers
    # ------------------------------------------------------------------

    def _scan_filtered(
        self, root: str, allowed_files: set[str], rel: str = ""
    ) -> list[TreeNode]:
        """Scan directory tree, returning only files in *allowed_files*."""
        full = os.path.join(root, rel) if rel else root
        try:
            items = sorted(os.listdir(full))
        except OSError:
            return []

        dirs: list[TreeNode] = []
        files: list[TreeNode] = []
        for name in items:
            path = os.path.join(full, name)
            rel_path = os.path.join(rel, name) if rel else name
            if os.path.isdir(path) and name not in _IGNORED_DIRS and not name.startswith("."):
                children = self._scan_filtered(root, allowed_files, rel_path)
                if children:
                    dirs.append(
                        TreeNode(name=name, path=rel_path, is_dir=True, children=children)
                    )
            elif name in allowed_files:
                files.append(TreeNode(name=name, path=rel_path, is_dir=False))
        return dirs + files

    def _scan_all(self, root: str, rel: str) -> list[TreeNode]:
        """Scan a directory recursively, returning all non-hidden files."""
        full = os.path.join(root, rel)
        try:
            items = sorted(os.listdir(full))
        except OSError:
            return []

        dirs: list[TreeNode] = []
        files: list[TreeNode] = []
        for name in items:
            path = os.path.join(full, name)
            rel_path = os.path.join(rel, name)
            if name.startswith("."):
                continue
            if os.path.isdir(path):
                children = self._scan_all(root, rel_path)
                if children:
                    dirs.append(
                        TreeNode(name=name, path=rel_path, is_dir=True, children=children)
                    )
            else:
                files.append(TreeNode(name=name, path=rel_path, is_dir=False))
        return dirs + files