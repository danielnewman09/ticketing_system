"""Project scaffold — dialog and section for creating a C++ project skeleton.

Contains :class:`ScaffoldDialog` (pre-fill, validate, call the
``scaffold_project`` agent) and :func:`section_scaffold` (card with
status, file tree, and create/open actions).
"""

from __future__ import annotations

import asyncio
import os

from nicegui import ui

from frontend_migrated.data.project import fetch_project_meta
from frontend_migrated.data.components import fetch_components
from frontend_migrated.pages.project.file_tree import ProjectFileTree
from frontend_migrated.pages.project.vscode import open_directory

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
)
_SKILL_SCAFFOLD = os.path.join(_REPO_ROOT, "skills", "cpp-project-scaffold")


# ---------------------------------------------------------------------------
# Dialog class
# ---------------------------------------------------------------------------


class ScaffoldDialog:
    """Dialog for creating a project scaffold.

    Pre-fills the libraries field with non-Environment component names.
    On success, navigates to the project root (full page refresh).
    """

    def __init__(self, project_dir: str):
        self._project_dir = project_dir
        self._dialog = None
        self._libs_input = None
        self._deps_input = None
        self._cpp_select = None

    async def show(self):
        """Build and open the dialog, fetching component names for pre-fill.

        Must be called from an async NiceGUI event handler so the
        slot context is preserved for UI element creation.
        """
        try:
            components = await asyncio.to_thread(fetch_components)
            lib_names = [
                c.name
                for c in components
                if c.name != "Environment" and not c.name.startswith("Environment:")
            ]
        except Exception:
            lib_names = []

        self._dialog = ui.dialog()
        with self._dialog, ui.card().classes("w-[480px]"):
            ui.label("Create Project Scaffold").classes("text-lg font-bold mb-2")
            ui.label(
                "Generate a complete C++ project skeleton in the working directory. "
                "The project name and directory come from project settings."
            ).classes("text-sm text-gray-400 mb-3")

            self._libs_input = ui.input(
                "Libraries (comma-separated)",
                value=", ".join(lib_names),
                placeholder="e.g. core, physics, rendering",
            ).classes("w-full")
            self._deps_input = ui.input(
                "Extra Conan dependencies (optional)",
                placeholder="e.g. eigen/3.4.0, spdlog/1.14.1",
            ).classes("w-full")
            self._cpp_select = ui.select(
                {20: "C++20", 23: "C++23", 26: "C++26"},
                value=20,
                label="C++ Standard",
            ).classes("w-full")

            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                ui.button("Cancel", on_click=self._dialog.close).props("flat size=sm")
                ui.button(
                    "Scaffold", icon="construction", on_click=self._run
                ).props("color=primary size=sm")

        self._dialog.open()

    async def _run(self):
        try:
            meta = await asyncio.to_thread(fetch_project_meta)
        except Exception:
            ui.notify("Could not read project settings", type="negative")
            return

        if not meta.get("name") or not meta.get("working_directory"):
            ui.notify("Set project name and working directory first", type="warning")
            return

        lib_names = [s.strip() for s in self._libs_input.value.split(",") if s.strip()]
        if not lib_names:
            ui.notify("Specify at least one library", type="warning")
            return

        libraries = [{"name": name} for name in lib_names]
        extra_deps = [s.strip() for s in self._deps_input.value.split(",") if s.strip()] or None

        self._dialog.close()
        ui.notify("Scaffolding project — this may take a few minutes…", type="info")

        try:
            from backend.ticketing_agent.design.scaffold_project import scaffold_project

            result = await asyncio.to_thread(
                scaffold_project,
                skill_dir=_SKILL_SCAFFOLD,
                project_name=meta["name"],
                libraries=libraries,
                working_directory=meta["working_directory"],
                extra_dependencies=extra_deps,
                cpp_standard=self._cpp_select.value,
            )
            if result.get("build_success"):
                ui.notify("Project scaffolded and build verified!", type="positive")
            else:
                ui.notify("Project scaffolded (build not verified)", type="warning")
            ui.navigate.to("/")
        except Exception as e:
            ui.notify(f"Scaffold failed: {e}", type="negative")


# ---------------------------------------------------------------------------
# Page section entry point
# ---------------------------------------------------------------------------


async def section_scaffold(meta: dict, project_dir: str = ""):
    """Scaffold card with file tree and create/open actions.

    Checks whether the project scaffold already exists on disk and
    renders the CMake file tree if so.  The ``Create Scaffold`` button
    opens :class:`ScaffoldDialog` which runs the scaffold_project agent.
    """
    # Filesystem check — no Neo4j needed for this.
    scaffolded = (
        bool(project_dir)
        and os.path.isfile(os.path.join(project_dir, "CMakeLists.txt"))
    )

    with ui.card().classes("w-full mx-2 mt-4"):
        with ui.row().classes("w-full items-center justify-between"):
            with ui.column().classes("gap-0"):
                ui.label("Project Scaffold").classes("text-sm font-semibold")
                if scaffolded:
                    ui.label("Project has been scaffolded").classes("text-xs text-green-400")
                else:
                    ui.label("Generate the C++ project skeleton").classes("text-xs text-gray-400")

            if scaffolded:
                with ui.row().classes("gap-2 items-center"):
                    ui.badge("Created", color="positive").classes("text-xs")
                    ui.button(
                        "Open in VS Code",
                        icon="open_in_new",
                        on_click=lambda: open_directory(project_dir),
                    ).props("flat size=sm").classes("text-blue-400")
            else:
                async def _open_scaffold():
                    await ScaffoldDialog(project_dir).show()

                ui.button(
                    "Create Scaffold",
                    icon="construction",
                    on_click=_open_scaffold,
                ).props("color=primary size=sm")

        if scaffolded and project_dir:
            ui.separator().classes("my-2")
            try:
                tree = ProjectFileTree()
                cmake_tree = tree.cmake_tree()
                if cmake_tree:
                    tree.render(cmake_tree)
            except Exception:
                # Neo4J unreachable — still show the card, just skip the tree
                ui.label("(File tree unavailable)").classes("text-xs text-gray-500")