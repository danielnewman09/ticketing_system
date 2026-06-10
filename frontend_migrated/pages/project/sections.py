"""Page sections for the project homepage — migrated backend.

Project metadata, stats, and stubs.  Dependency management lives in
:mod:`frontend_migrated.pages.project.dependencies`.
"""

import asyncio

from nicegui import ui

from frontend_migrated.theme import (
    BACKGROUNDS,
    COLORS,
    CLS_DIALOG_MD,
    CLS_DIALOG_TITLE,
    CLS_DIALOG_ACTIONS,
)
from frontend_migrated.data.project import fetch_project_meta, update_project_meta
from frontend_migrated.layout import stat_card
from frontend_migrated.data.hlr import fetch_requirements_data


# ---------------------------------------------------------------------------
# Project metadata
# ---------------------------------------------------------------------------


async def section_project_meta():
    """Project name, description, working directory with edit dialog.

    Uses ``ProjectMeta.serialize()`` for the data dict — keys include
    ``type``, ``name``, ``description``, ``working_directory``, ``edges``,
    etc.  The UI reads only the content keys it needs.
    """

    @ui.refreshable
    async def card():
        # fetch_project_meta() returns ProjectMeta.serialize() — a dict
        # with {type, name, description, working_directory, edges, ...}.
        meta = await asyncio.to_thread(fetch_project_meta)
        with (
            ui.card()
            .classes("w-full mx-2 mt-4")
            .style(
                f"background: {BACKGROUNDS['surface']}; border-left: 4px solid {COLORS['primary']};"
            )
        ):
            with ui.row().classes("w-full items-start justify-between"):
                with ui.column().classes("flex-1 gap-1"):
                    ui.label(meta.get("name") or "Untitled Project").classes("text-lg font-bold")
                    if meta.get("description"):
                        ui.label(meta["description"]).classes("text-sm text-gray-400")
                    if meta.get("working_directory"):
                        with ui.row().classes("items-center gap-1"):
                            ui.icon("folder", size="xs").classes("text-gray-500")
                            ui.label(meta["working_directory"]).classes(
                                "text-xs text-blue-400 font-mono cursor-pointer"
                            ).tooltip("Open in VS Code").on(
                                "click",
                                lambda wd=meta["working_directory"]: _open_vscode(wd),
                            )
                ui.button(
                    icon="edit",
                    on_click=lambda: _show_edit_dialog(meta, card),
                ).props("flat round size=sm")

    await card()


def _show_edit_dialog(meta: dict, refreshable):
    from frontend_migrated.widgets import directory_picker

    with ui.dialog() as dialog, ui.card().classes(CLS_DIALOG_MD):
        ui.label("Project Settings").classes(CLS_DIALOG_TITLE)
        name_input = ui.input("Name", value=meta.get("name", "")).classes("w-full")
        desc_input = ui.textarea("Description", value=meta.get("description", "")).classes("w-full")

        with ui.row().classes("w-full items-end gap-2"):
            dir_input = ui.input(
                "Working Directory",
                value=meta.get("working_directory", ""),
            ).classes("flex-1 font-mono")
            dir_input.props("readonly")

            def open_picker():
                picker = directory_picker(
                    initial_path=dir_input.value,
                    on_select=lambda path: setattr(dir_input, "value", path),
                )
                picker.open()

            ui.button(icon="folder_open", on_click=open_picker).props("flat round size=sm").tooltip(
                "Browse…"
            )

        with ui.row().classes(CLS_DIALOG_ACTIONS):
            ui.button("Cancel", on_click=dialog.close).props("flat")

            async def do_save():
                await asyncio.to_thread(
                    update_project_meta,
                    name_input.value.strip(),
                    desc_input.value.strip(),
                    dir_input.value.strip(),
                )
                dialog.close()
                ui.notify("Project settings saved", type="positive")
                refreshable.refresh()

            ui.button("Save", on_click=do_save).props("color=primary")

    dialog.open()


def _open_vscode(path: str):
    """Open a directory in VS Code."""
    import subprocess

    try:
        subprocess.Popen(["code", path])
    except FileNotFoundError:
        # VS Code CLI not available — try generic opener
        import webbrowser

        webbrowser.open(f"file://{path}")


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


async def section_stats():
    """Stat cards row — HLRs, LLRs, Components, Ontology Nodes."""
    data = await asyncio.to_thread(fetch_requirements_data)
    with ui.row().classes("w-full gap-4 flex-wrap px-2 mt-4"):
        stat_card("HLRs", data["total_hlrs"], "blue-5")
        stat_card("LLRs", data["total_llrs"], "green-5")
        stat_card(
            "Components",
            len({h["component"] for h in data["hlrs"] if h["component"]}),
            "teal-5",
        )
        stat_card("Ontology Nodes", data["total_nodes"], "purple-5")


# ---------------------------------------------------------------------------
# Stubs — not yet migrated
# ---------------------------------------------------------------------------


def section_pending_recommendations():
    """STUB: Render pending dependency recommendations section."""
    pass


def section_scaffold(meta: dict, project_dir: str = ""):
    """STUB: Render project scaffolding section."""
    pass