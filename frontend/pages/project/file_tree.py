"""File tree scanning and rendering for project directories."""

import os
import re

from services.dependencies import get_neo4j

from nicegui import ui

from frontend.pages.project.vscode import open_file

_IGNORED_DIRS = {"build", ".git", "__pycache__", ".venv", "installs", ".vscode", "node_modules"}
_CMAKE_FILES = {"CMakeLists.txt", "CMakeUserPresets.json"}
_CONAN_ROOT_FILES = {"conanfile.py", "conanfile.txt"}


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------


def scan_filtered_tree(root: str, allowed_files: set[str], rel: str = "") -> list[dict]:
    """Scan directory tree, returning only files in allowed_files."""
    full = os.path.join(root, rel) if rel else root
    try:
        items = sorted(os.listdir(full))
    except OSError:
        return []

    dirs, files = [], []
    for name in items:
        path = os.path.join(full, name)
        rel_path = os.path.join(rel, name) if rel else name
        if os.path.isdir(path) and name not in _IGNORED_DIRS and not name.startswith("."):
            children = scan_filtered_tree(root, allowed_files, rel_path)
            if children:
                dirs.append({"name": name, "path": rel_path, "is_dir": True, "children": children})
        elif name in allowed_files:
            files.append({"name": name, "path": rel_path, "is_dir": False})
    return dirs + files


def scan_all_files(root: str, rel: str) -> list[dict]:
    """Scan a directory recursively, returning all non-hidden files."""
    full = os.path.join(root, rel)
    try:
        items = sorted(os.listdir(full))
    except OSError:
        return []

    dirs, files = [], []
    for name in items:
        path = os.path.join(full, name)
        rel_path = os.path.join(rel, name)
        if name.startswith("."):
            continue
        if os.path.isdir(path):
            children = scan_all_files(root, rel_path)
            if children:
                dirs.append({"name": name, "path": rel_path, "is_dir": True, "children": children})
        else:
            files.append({"name": name, "path": rel_path, "is_dir": False})
    return dirs + files


def scan_cmake_tree(root: str) -> list[dict]:
    """Scan for CMakeLists.txt and CMakeUserPresets.json files."""
    return scan_filtered_tree(root, _CMAKE_FILES)


def scan_conan_files(root: str) -> list[dict]:
    """Scan for conanfile at root + full conan/ directory."""
    entries = []
    for name in _CONAN_ROOT_FILES:
        if os.path.isfile(os.path.join(root, name)):
            entries.append({"name": name, "path": name, "is_dir": False})
    conan_dir = os.path.join(root, "conan")
    if os.path.isdir(conan_dir):
        children = scan_all_files(root, "conan")
        if children:
            entries.append({"name": "conan", "path": "conan", "is_dir": True, "children": children})
    return entries


def get_conan_deps(project_dir: str) -> dict[str, str]:
    """Check integration status of dependencies.

    Returns a dict mapping lowercase dep names to their status:
      - "indexed"    — conanfile exists AND dependency is indexed in Neo4j
      - "integrated" — conanfile exists but not yet indexed
    """
    conan_dir = os.path.join(project_dir, "conan")
    if not os.path.isdir(conan_dir):
        return {}

    # Find deps with a conanfile
    deps_with_recipe: set[str] = set()
    try:
        for name in os.listdir(conan_dir):
            if os.path.isfile(os.path.join(conan_dir, name, "conanfile.py")):
                deps_with_recipe.add(name.lower())
    except Exception:
        pass

    if not deps_with_recipe:
        return {}

    # Check which deps have been indexed into Neo4j
    indexed: set[str] = set()
    try:
        with get_neo4j().session() as session:
            result = session.run(
                "MATCH (n) WHERE n.source IS NOT NULL "
                "RETURN DISTINCT n.source AS source"
            )
            indexed = {r["source"].lower() for r in result if r["source"]}
    except Exception:
        pass

    return {
        name: "indexed" if name in indexed else "integrated"
        for name in deps_with_recipe
    }


def project_exists(working_directory: str, project_name: str) -> bool:
    """Check if the scaffold has already been created."""
    if not working_directory or not project_name:
        return False
    return os.path.isfile(os.path.join(working_directory, project_name, "CMakeLists.txt"))


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_file_tree(tree: list[dict], project_dir: str, depth: int = 0):
    """Render a file tree with clickable files and expandable directories."""
    for entry in tree:
        indent = f"padding-left: {depth * 16 + 4}px;"
        if entry["is_dir"]:
            with ui.expansion(
                entry["name"], icon="folder",
            ).classes("w-full").props("dense").style(indent):
                render_file_tree(entry["children"], project_dir, depth + 1)
        else:
            ui.label(entry["name"]).classes(
                "text-xs font-mono text-blue-400 cursor-pointer py-0.5"
            ).style(indent).on(
                "click",
                lambda _, p=entry["path"]: open_file(project_dir, p),
            ).tooltip(entry["path"])
