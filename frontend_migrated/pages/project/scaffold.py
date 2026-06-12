"""Project scaffold — dialog and section for creating a C++ project skeleton.

Contains :class:`ScaffoldDialog` (pre-fill, validate, call the
``scaffold_project`` agent) and :func:`section_scaffold` (card with
status, file tree, and create/open actions).
"""

from __future__ import annotations

import asyncio
import logging
import os

log = logging.getLogger(__name__)

from nicegui import ui

from frontend_migrated.data.project import fetch_project_meta, fetch_environment_data
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

    Pre-fills the libraries field with non-Environment component names
    and the dependencies field with any Dependency nodes already in
    Neo4j.  On success, navigates to the project root (full page refresh).
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
        except Exception as exc:
            log.warning("Could not fetch components for scaffold dialog: %s", exc)
            lib_names = []

        # Pre-fill dependencies from Neo4j — any Dependency nodes that
        # the user has already registered (e.g. via the Add Dependency
        # dialog on the project page).
        dep_str = ""
        try:
            env_data = await asyncio.to_thread(fetch_environment_data)
            dep_tokens: list[str] = []
            for lang in env_data:
                for dep in lang.get("dependencies", []):
                    name = dep.get("name", "")
                    version = dep.get("version", "")
                    if name:
                        token = f"{name}/{version}" if version else name
                        dep_tokens.append(token)
            dep_str = ", ".join(dep_tokens)
        except Exception as exc:
            log.warning("Could not fetch environment data for scaffold dialog: %s", exc)

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
                "Conan dependencies",
                value=dep_str,
                placeholder="e.g. eigen/3.4.0, spdlog/1.14.1",
            ).classes("w-full")
            self._deps_input.props(
                'hint="Pre-filled from registered dependencies — edit as needed"'
            )
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
            from backend_migrated.agents.scaffold_project import scaffold_project

            # Ensure the lazy-imported module uses the patched call_tool_loop
            # (install_hooks patches already-imported modules, but this lazy
            # import happens at click time and may not have been caught)
            try:
                from frontend_migrated.agent_log import agent_log as _agent_log
                import backend_migrated.agents.scaffold_project as _sp
                import llm_caller.tool_loop as _tl
                if not _sp.call_tool_loop.__qualname__.startswith("install_hooks"):
                    _sp.call_tool_loop = _tl.call_tool_loop
                import llm_caller.skill_runner as _sr
                if not _sr.call_tool_loop.__qualname__.startswith("install_hooks"):
                    _sr.call_tool_loop = _tl.call_tool_loop
            except Exception as exc:
                log.debug("Could not patch call_tool_loop: %s", exc)

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

            # Sync the project environment to Neo4j so that
            # Language/Component/Dependency nodes exist for the
            # dependency table and project view.
            project_dir = os.path.join(
                meta.get("working_directory", ""),
                meta.get("name", ""),
            )
            if project_dir:
                try:
                    from frontend_migrated.data.environment import sync_project_environment
                    await asyncio.to_thread(sync_project_environment, project_dir)
                except Exception as exc:
                    log.warning("sync_project_environment after scaffold failed: %s", exc)

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
            except Exception as exc:
                # Neo4J unreachable — still show the card, just skip the tree
                log.debug("File tree render failed: %s", exc)
                ui.label("(File tree unavailable)").classes("text-xs text-gray-500")