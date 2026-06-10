"""Project dependency management — panel, dialogs, and data transforms.

Contains the refreshable dependency table (:class:`DependencyPanel`),
two form dialogs (:class:`IntegrateDialog`, :class:`IndexConfigDialog`),
pure data transforms for flattening and formatting dependency data,
and the Vue slot templates used by the table.

Layout pattern
~~~~~~~~~~~~~~
- **Classes** for stateful sections that own refreshable UI or mutable
  dialog state (``DependencyPanel``, ``IntegrateDialog``,
  ``IndexConfigDialog``).
- **Free functions** for stateless data transforms (``_flatten_deps``,
  ``_build_dep_columns``, ``_build_dep_rows``).
- **Module constants** for static Vue templates (``_SLOT_STATUS``, etc.).
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable

from nicegui import ui

from frontend_migrated.theme import CLS_DIALOG_MD, CLS_DIALOG_TITLE, CLS_DIALOG_ACTIONS
from frontend_migrated.data.project import fetch_environment_data
from frontend_migrated.data.components import (
    delete_dependency,
    update_dependency_index_config,
)
from frontend_migrated.pages.project.file_tree import ProjectFileTree

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
)
# NOTE: The original code had these skill paths swapped — the integrate
# function used the scaffold skill dir and vice versa.  Fixed here.
_SKILL_INTEGRATE = os.path.join(_REPO_ROOT, "skills", "add-conan-dependency")


# ---------------------------------------------------------------------------
# Pure data transforms (stateless: data in → data out)
# ---------------------------------------------------------------------------


def _flatten_deps(
    env_data: list[dict],
    conan_deps: dict[str, str],
    has_project_dir: bool,
) -> list[dict]:
    """Flatten language→dependency nesting into a single list with status.

    Each dependency dict gains ``language`` (e.g. ``"C++ 20"``) and
    ``integration_status`` (``"indexed"``, ``"integrated"``,
    ``"not in build"``, or ``"unknown"``) keys.
    """
    all_deps: list[dict] = []
    for lang in env_data:
        lang_label = lang["name"]
        if lang.get("version"):
            lang_label += f" {lang['version']}"
        for dep in lang.get("dependencies", []):
            dep_lower = dep["name"].lower()
            status = conan_deps.get(
                dep_lower,
                "not in build" if has_project_dir else "unknown",
            )
            all_deps.append({**dep, "language": lang_label, "integration_status": status})
    return all_deps


def _build_dep_columns() -> list[dict]:
    """Return the column definitions for the dependency table.

    Static — the schema never changes at runtime.
    """
    return [
        {"name": "name", "label": "Name", "field": "name", "align": "left", "sortable": True},
        {"name": "source_url", "label": "Source URL", "field": "source_url", "align": "left"},
        {"name": "version", "label": "Version", "field": "version", "align": "left"},
        {"name": "components", "label": "Used in Components", "field": "components", "align": "left"},
        {"name": "status", "label": "Integration Status", "field": "status", "align": "left"},
        {"name": "language", "label": "Language", "field": "language", "align": "left"},
        {"name": "actions", "label": "", "field": "actions", "align": "right"},
    ]


def _build_dep_rows(all_deps: list[dict]) -> list[dict]:
    """Convert flattened dependency dicts into table row dicts.

    Adds convenience keys for the Vue action-slot templates:
    ``unused`` (bool) and index-config fields with defaults.
    """
    rows: list[dict] = []
    for dep in all_deps:
        comps = dep.get("components", [])
        comp_names = ", ".join(c["name"] for c in comps) or "—"
        rows.append(
            {
                "refid": dep.get("refid", dep.get("id", "")),
                "name": dep["name"],
                "source_url": dep.get("github_url") or "—",
                "version": dep.get("version") or "—",
                "components": comp_names,
                "unused": len(comps) == 0,
                "status": dep["integration_status"],
                "language": dep["language"],
                "index_file_patterns": dep.get("index_file_patterns", "*.h *.hpp"),
                "index_subdir": dep.get("index_subdir", ""),
                "index_exclude_patterns": dep.get("index_exclude_patterns", ""),
                "index_recursive": dep.get("index_recursive", True),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Vue slot templates (static strings — not inline for readability)
# ---------------------------------------------------------------------------

_SLOT_STATUS = r"""
    <q-td :props="props">
        <q-badge
            :color="props.value === 'indexed' ? 'positive' : props.value === 'integrated' ? 'info' : props.value === 'not in build' ? 'negative' : 'grey'"
            class="text-xs"
        >{{ props.value }}</q-badge>
    </q-td>
"""

_SLOT_SOURCE_URL = r"""
    <q-td :props="props">
        <a v-if="props.value !== '—'"
           :href="props.value" target="_blank"
           class="text-blue-400 text-xs font-mono no-underline hover:underline">
            {{ props.value }}
        </a>
        <span v-else class="text-gray-500">—</span>
    </q-td>
"""

_SLOT_ACTIONS = r"""
    <q-td :props="props">
        <q-btn v-if="props.row.status === 'not in build'"
            flat round dense size="xs" icon="add_circle"
            class="text-blue-400"
            @click="$parent.$emit('integrate', props.row)">
            <q-tooltip>Integrate dependency</q-tooltip>
        </q-btn>
        <q-btn v-if="props.row.status === 'integrated'"
            flat round dense size="xs" icon="menu_book"
            class="text-amber-400"
            @click="$parent.$emit('reindex', props.row)">
            <q-tooltip>Index into documentation graph</q-tooltip>
        </q-btn>
        <q-btn v-if="props.row.status !== 'not in build'"
            flat round dense size="xs" icon="settings"
            class="text-gray-400"
            @click="$parent.$emit('configure', props.row)">
            <q-tooltip>Configure indexing</q-tooltip>
        </q-btn>
        <q-btn v-if="props.row.unused"
            flat round dense size="xs" icon="delete"
            class="text-red-400"
            @click="$parent.$emit('remove', props.row)">
            <q-tooltip>Remove unused dependency</q-tooltip>
        </q-btn>
    </q-td>
"""


# ---------------------------------------------------------------------------
# Dialog classes
# ---------------------------------------------------------------------------


class IntegrateDialog:
    """Dialog for running the add-conan-dependency skill.

    Pre-fills source URL, version, and consuming library from the
    table row.  On success, navigates to the project root (full
    page refresh).  On failure, shows an error notification.
    """

    def __init__(self, project_dir: str, on_done: Callable | None = None):
        self._project_dir = project_dir
        self._on_done = on_done
        self._dialog = None
        self._dep_name = ""
        self._source_url = None
        self._version = None
        self._consuming_lib = None

    def show(self, row: dict):
        """Open the dialog pre-filled from *row*."""
        asyncio.create_task(self._build_and_open(row))

    async def _build_and_open(self, row: dict):
        self._dep_name = row["name"]
        self._dialog = ui.dialog()
        with self._dialog, ui.card().classes("w-[480px]"):
            ui.label("Integrate Dependency").classes("text-lg font-bold mb-2")
            ui.label(
                "Run the add-conan-dependency skill to create a Conan recipe "
                "and wire the dependency into the build."
            ).classes("text-sm text-gray-400 mb-3")

            ui.label(f"Dependency: {self._dep_name}").classes("text-sm font-semibold")
            self._source_url = ui.input(
                "Source URL (git repo or download)",
                value="" if row.get("source_url") == "—" else row.get("source_url", ""),
            ).classes("w-full")
            self._version = ui.input(
                "Version / git tag",
                value="" if row.get("version") == "—" else row.get("version", ""),
            ).classes("w-full")
            self._consuming_lib = ui.input(
                "Consuming library",
                value=row.get("components", "") if row.get("components") != "—" else "",
            ).classes("w-full")

            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                ui.button("Cancel", on_click=self._dialog.close).props("flat size=sm")
                ui.button(
                    "Integrate", icon="build", on_click=self._run
                ).props("color=primary size=sm")

        self._dialog.open()

    async def _run(self):
        source_url = self._source_url.value.strip()
        version = self._version.value.strip()
        consuming_lib = self._consuming_lib.value.strip()

        if not source_url or not version or not consuming_lib:
            ui.notify("All fields are required", type="warning")
            return

        self._dialog.close()
        ui.notify(
            f"Integrating {self._dep_name} — this may take a few minutes…",
            type="info",
        )

        try:
            from backend.ticketing_agent.design.integrate_dependency import (
                integrate_dependency,
            )

            result = await asyncio.to_thread(
                integrate_dependency,
                skill_dir=_SKILL_INTEGRATE,
                dep_name=self._dep_name,
                source_url=source_url,
                version=version,
                consuming_lib=consuming_lib,
                working_directory=self._project_dir,
            )
            if result.get("build_success"):
                ui.notify(
                    f"{self._dep_name} integrated and build verified!",
                    type="positive",
                )
            else:
                ui.notify(
                    f"{self._dep_name} integrated (build not verified)",
                    type="warning",
                )
            ui.navigate.to("/")
        except Exception as e:
            ui.notify(f"Integration failed: {e}", type="negative")


class IndexConfigDialog:
    """Dialog for editing a dependency's Doxygen indexing configuration.

    Saves config via ``update_dependency_index_config`` and calls
    ``on_done`` (table refresh) on success.
    """

    def __init__(self, on_done: Callable | None = None):
        self._on_done = on_done
        self._dialog = None
        self._dep_refid = ""
        self._dep_name = ""
        self._file_patterns = None
        self._subdir = None
        self._exclude = None
        self._recursive = None

    def show(self, row: dict):
        """Open the dialog pre-filled from *row*."""
        asyncio.create_task(self._build_and_open(row))

    async def _build_and_open(self, row: dict):
        self._dep_refid = row.get("refid", "")
        self._dep_name = row["name"]
        self._dialog = ui.dialog()
        with self._dialog, ui.card().classes(CLS_DIALOG_MD):
            ui.label("Indexing Configuration").classes(CLS_DIALOG_TITLE)
            ui.label(f"Dependency: {self._dep_name}").classes(
                "text-sm font-semibold mb-2"
            )

            self._file_patterns = ui.input(
                "File patterns",
                value=row.get("index_file_patterns", "*.h *.hpp"),
            ).classes("w-full")
            self._file_patterns.tooltip(
                "Space-separated glob patterns for header files"
            )

            self._subdir = ui.input(
                "Include subdirectory (optional)",
                value=row.get("index_subdir", ""),
            ).classes("w-full")
            self._subdir.tooltip(
                "Subdirectory under include/ to index, e.g. 'eigen3/Eigen'"
            )

            self._exclude = ui.input(
                "Exclude patterns (optional)",
                value=row.get("index_exclude_patterns", ""),
            ).classes("w-full")
            self._exclude.tooltip(
                "Doxygen EXCLUDE_PATTERNS, e.g. '*/detail/* */impl/*'"
            )

            self._recursive = ui.checkbox(
                "Recursive",
                value=row.get("index_recursive", True),
            )

            with ui.row().classes(CLS_DIALOG_ACTIONS):
                ui.button("Cancel", on_click=self._dialog.close).props("flat")
                ui.button("Save", on_click=self._save).props("color=primary")

        self._dialog.open()

    async def _save(self):
        try:
            await asyncio.to_thread(
                update_dependency_index_config,
                self._dep_refid,
                self._file_patterns.value.strip(),
                self._subdir.value.strip(),
                self._exclude.value.strip(),
                self._recursive.value,
            )
        except NotImplementedError:
            ui.notify(
                "Index config not yet available in migrated backend",
                type="warning",
            )
            self._dialog.close()
            return

        self._dialog.close()
        ui.notify(
            f"Indexing config saved for {self._dep_name}", type="positive"
        )
        if self._on_done:
            self._on_done()


# ---------------------------------------------------------------------------
# Dependency panel (refreshable section)
# ---------------------------------------------------------------------------


class DependencyPanel:
    """Refreshable panel that lists and manages project dependencies.

    Encapsulates its own data fetch cycle — :meth:`refresh` re-loads
    environment data and Conan status, then re-renders the table.
    Dialog instances are persistent (created once in :meth:`render`)
    and pre-filled from the table row on each open.

    ``ProjectFileTree`` is created lazily on first use so the panel
    itself can always be instantiated — even when Neo4j is unreachable.
    """

    def __init__(self, project_dir: str):
        self._project_dir = project_dir
        self._tree: ProjectFileTree | None = None
        self._integrate = None
        self._config = None
        self._refreshable = None

    # -- Lazy Neo4j access ---------------------------------------------------

    def _get_tree(self) -> ProjectFileTree:
        """Lazy-init the ProjectFileTree (hits Neo4j on first call)."""
        if self._tree is None:
            self._tree = ProjectFileTree()
        return self._tree

    def _conan_status(self) -> dict[str, str]:
        """Conan integration status — returns {} on any failure."""
        try:
            return self._get_tree().conan_dependency_status()
        except Exception:
            return {}

    def _conan_tree(self) -> list:
        """Conan file tree — returns [] on any failure."""
        try:
            return self._get_tree().conan_tree()
        except Exception:
            return []

    # -- public API ----------------------------------------------------------

    async def render(self):
        """Initial render — create persistent dialogs, then mount table."""
        self._integrate = IntegrateDialog(self._project_dir, on_done=self.refresh)
        self._config = IndexConfigDialog(on_done=self.refresh)

        @ui.refreshable
        async def table():
            await self._render_table()

        self._refreshable = table
        await table()

    def refresh(self):
        """Re-render the table (called by dialog ``on_done`` callbacks)."""
        if self._refreshable:
            self._refreshable.refresh()

    # -- internals -----------------------------------------------------------

    async def _render_table(self):
        conan_deps = self._conan_status()
        try:
            env_data = await asyncio.to_thread(fetch_environment_data)
        except Exception:
            env_data = []

        all_deps = _flatten_deps(env_data, conan_deps, bool(self._project_dir))

        with ui.card().classes("w-full mx-2 mt-4"):
            ui.label("Dependency Management").classes("text-sm font-semibold mb-2")

            if not env_data:
                ui.label("No language environment data available.").classes(
                    "text-sm text-gray-500"
                )
            elif not all_deps:
                ui.label("No dependencies configured.").classes(
                    "text-sm text-gray-500"
                )
            else:
                columns = _build_dep_columns()
                rows = _build_dep_rows(all_deps)
                tbl = (
                    ui.table(columns=columns, rows=rows, row_key="refid")
                    .classes("w-full")
                    .props("dense flat")
                )
                tbl.add_slot("body-cell-status", _SLOT_STATUS)
                tbl.add_slot("body-cell-source_url", _SLOT_SOURCE_URL)
                tbl.add_slot("body-cell-actions", _SLOT_ACTIONS)
                tbl.on("integrate", lambda e: self._integrate.show(e.args))
                tbl.on("reindex", lambda e: self._on_index(e.args["name"]))
                tbl.on("configure", lambda e: self._config.show(e.args))
                tbl.on("remove", lambda e: self._on_delete(e.args))

        if self._project_dir:
            conan_files = self._conan_tree()
            if conan_files:
                ui.separator().classes("my-2")
                self._get_tree().render(conan_files)

    async def _on_delete(self, row: dict):
        dep_refid = row.get("refid", "")
        dep_name = row.get("name", "")
        try:
            await asyncio.to_thread(delete_dependency, dep_refid)
        except NotImplementedError:
            ui.notify(
                "Delete not yet available in migrated backend",
                type="warning",
            )
            return
        ui.notify(f"Removed {dep_name}", type="info")
        self.refresh()

    async def _on_index(self, dep_name: str):
        ui.notify(f"Indexing {dep_name}…", type="info")
        try:
            from backend.codebase.indexing import index_dependency

            result = await asyncio.to_thread(
                index_dependency, self._project_dir, dep_name
            )
            ui.notify(result.get("message", f"Indexed {dep_name}"),
                       type="positive" if result.get("success") else "negative")
        except Exception as e:
            ui.notify(f"Indexing failed: {e}", type="negative")
        self.refresh()


# ---------------------------------------------------------------------------
# Page section entry point
# ---------------------------------------------------------------------------


async def section_dependencies(project_dir: str = ""):
    """Render the dependency management section.

    Delegates to :class:`DependencyPanel` which owns the refreshable
    table and wires up the integrate / configure / delete handlers.
    """
    panel = DependencyPanel(project_dir)
    await panel.render()