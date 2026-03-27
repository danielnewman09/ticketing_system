"""Requirements dashboard — main page."""

import asyncio

from nicegui import ui

from frontend.theme import apply_theme
from frontend.layout import page_layout, stat_card
from frontend.data import (
    fetch_requirements_data,
    fetch_project_meta,
    update_project_meta,
    fetch_components_options,
    fetch_pending_recommendations_summary,
    create_hlr,
    delete_hlr,
    create_llr,
    decompose_hlr,
)


@ui.page("/")
async def requirements_page():
    apply_theme()
    page_layout("Requirements")

    # ---------------------------------------------------------------
    # Refreshable content
    # ---------------------------------------------------------------

    # ---------------------------------------------------------------
    # Project metadata section
    # ---------------------------------------------------------------

    @ui.refreshable
    async def project_meta_section():
        meta = await asyncio.to_thread(fetch_project_meta)

        with ui.card().classes("w-full mx-2 mt-4").style(
            "background: #1e293b; border-left: 4px solid #5c7cfa;"
        ):
            with ui.row().classes("w-full items-start justify-between"):
                with ui.column().classes("flex-1 gap-1"):
                    ui.label(meta["name"] or "Untitled Project").classes(
                        "text-lg font-bold"
                    )
                    if meta["description"]:
                        ui.label(meta["description"]).classes(
                            "text-sm text-gray-400"
                        )
                    if meta["working_directory"]:
                        with ui.row().classes("items-center gap-1"):
                            ui.icon("folder", size="xs").classes("text-gray-500")
                            ui.label(meta["working_directory"]).classes(
                                "text-xs text-gray-500 font-mono"
                            )
                ui.button(icon="edit", on_click=lambda: show_edit_project_dialog(meta)).props(
                    "flat round size=sm"
                )

    async def show_edit_project_dialog(meta: dict):
        from frontend.widgets import directory_picker

        with ui.dialog() as dialog, ui.card().classes("w-96"):
            ui.label("Project Settings").classes("text-lg font-bold mb-2")
            name_input = ui.input("Name", value=meta["name"]).classes("w-full")
            desc_input = ui.textarea("Description", value=meta["description"]).classes("w-full")

            with ui.row().classes("w-full items-end gap-2"):
                dir_input = ui.input(
                    "Working Directory", value=meta["working_directory"],
                ).classes("flex-1 font-mono")
                dir_input.props("readonly")

                def open_picker():
                    def on_select(path: str):
                        dir_input.value = path

                    picker = directory_picker(
                        initial_path=dir_input.value,
                        on_select=on_select,
                    )
                    picker.open()

                ui.button(icon="folder_open", on_click=open_picker).props(
                    "flat round size=sm"
                ).tooltip("Browse…")

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
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
                    project_meta_section.refresh()

                ui.button("Save", on_click=do_save).props("color=primary")

        dialog.open()

    await project_meta_section()

    @ui.refreshable
    async def content():
        data = await asyncio.to_thread(fetch_requirements_data)

        with ui.row().classes("w-full gap-4 flex-wrap px-2 mt-4"):
            stat_card("HLRs", data["total_hlrs"], "blue-5")
            stat_card("LLRs", data["total_llrs"], "green-5")
            stat_card("Verifications", data["total_verifications"], "amber-5")
            stat_card("Ontology Nodes", data["total_nodes"], "purple-5")
            stat_card("Triples", data["total_triples"], "cyan-5")

        # Pending dependency recommendations notification
        pending = await asyncio.to_thread(fetch_pending_recommendations_summary)
        if pending:
            with ui.card().classes("w-full mx-2 mt-4").style(
                "background: #1e293b; border-left: 4px solid #f59e0b;"
            ):
                with ui.row().classes("items-center gap-3"):
                    ui.icon("science", color="warning", size="sm")
                    with ui.column().classes("gap-0 flex-1"):
                        ui.label("Dependency recommendations need review").classes(
                            "text-sm font-semibold text-amber-400"
                        )
                        for p in pending:
                            ui.label(
                                f"{p['component_name']}: {p['pending_count']} pending"
                            ).classes("text-xs text-gray-400")
                    for p in pending:
                        ui.button(
                            f"Review {p['component_name']}",
                            on_click=lambda _, c=p: ui.navigate.to(
                                f"/component/{c['component_id']}/dependencies/review"
                            ),
                        ).props("size=sm color=warning outline")

        with ui.row().classes("w-full items-center justify-between px-2 mt-6 mb-2"):
            ui.label("High-Level Requirements").classes("text-xl font-semibold")
            ui.button("+ HLR", icon="add", on_click=show_create_hlr_dialog).props(
                "color=positive size=sm"
            )

        for hlr in data["hlrs"]:
            _render_hlr_card(hlr)

        if data["unlinked_llrs"]:
            ui.separator().classes("my-4")
            ui.label("Unlinked LLRs").classes("text-lg font-semibold text-amber-400 px-2 mb-2")
            _render_llr_table(data["unlinked_llrs"])

    # ---------------------------------------------------------------
    # Create HLR dialog
    # ---------------------------------------------------------------

    async def show_create_hlr_dialog():
        components = await asyncio.to_thread(fetch_components_options)
        comp_map = {c["name"]: c["id"] for c in components}
        comp_names = ["(none)"] + [c["name"] for c in components]

        with ui.dialog() as dialog, ui.card().classes("w-96"):
            ui.label("Create HLR").classes("text-lg font-bold mb-2")
            desc_input = ui.textarea("Description").classes("w-full")
            comp_select = ui.select(comp_names, value="(none)", label="Component").classes("w-full")

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button("Cancel", on_click=dialog.close).props("flat")

                async def do_create():
                    desc = desc_input.value.strip()
                    if not desc:
                        ui.notify("Description is required", type="warning")
                        return
                    comp_id = comp_map.get(comp_select.value)
                    new_id = await asyncio.to_thread(create_hlr, desc, comp_id)
                    dialog.close()
                    ui.notify(f"Created HLR {new_id}", type="positive")
                    content.refresh()

                ui.button("Create", on_click=do_create).props("color=positive")

        dialog.open()

    # ---------------------------------------------------------------
    # Delete HLR
    # ---------------------------------------------------------------

    async def confirm_delete_hlr(hlr_id: int):
        with ui.dialog() as dialog, ui.card().classes("w-80"):
            ui.label(f"Delete HLR {hlr_id}?").classes("text-lg font-bold")
            ui.label("This will also delete all child LLRs and their verifications.").classes(
                "text-sm text-gray-400 mt-1"
            )
            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button("Cancel", on_click=dialog.close).props("flat")

                async def do_delete():
                    await asyncio.to_thread(delete_hlr, hlr_id)
                    dialog.close()
                    ui.notify(f"Deleted HLR {hlr_id}", type="negative")
                    content.refresh()

                ui.button("Delete", on_click=do_delete).props("color=negative")

        dialog.open()

    # ---------------------------------------------------------------
    # Decompose HLR
    # ---------------------------------------------------------------

    async def confirm_decompose_hlr(hlr_id: int):
        with ui.dialog() as dialog, ui.card().classes("w-96"):
            ui.label(f"Decompose HLR {hlr_id}?").classes("text-lg font-bold")
            ui.label(
                "This will run the decomposition agent to generate low-level "
                "requirements and verification methods."
            ).classes("text-sm text-gray-400 mt-1")

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button("Cancel", on_click=dialog.close).props("flat")

                async def do_decompose():
                    dialog.close()
                    ui.notify("Decomposing — this may take a moment…", type="info")
                    try:
                        result = await asyncio.to_thread(decompose_hlr, hlr_id)
                        ui.notify(
                            f"Created {result['llrs_created']} LLRs and "
                            f"{result['verifications_created']} verifications",
                            type="positive",
                        )
                        content.refresh()
                    except Exception as e:
                        ui.notify(f"Decomposition failed: {e}", type="negative")

                ui.button("Decompose", on_click=do_decompose).props("color=primary")

        dialog.open()

    # ---------------------------------------------------------------
    # Add LLR dialog
    # ---------------------------------------------------------------

    async def show_add_llr_dialog(hlr_id: int):
        with ui.dialog() as dialog, ui.card().classes("w-96"):
            ui.label(f"Add LLR to HLR {hlr_id}").classes("text-lg font-bold mb-2")
            desc_input = ui.textarea("Description").classes("w-full")

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button("Cancel", on_click=dialog.close).props("flat")

                async def do_create():
                    desc = desc_input.value.strip()
                    if not desc:
                        ui.notify("Description is required", type="warning")
                        return
                    new_id = await asyncio.to_thread(create_llr, hlr_id, desc)
                    dialog.close()
                    ui.notify(f"Created LLR {new_id}", type="positive")
                    content.refresh()

                ui.button("Create", on_click=do_create).props("color=positive")

        dialog.open()

    # ---------------------------------------------------------------
    # HLR card (inline)
    # ---------------------------------------------------------------

    def _render_hlr_card(hlr):
        llr_count = len(hlr["llrs"])
        hlr_id = hlr["id"]

        with ui.card().classes("w-full mb-2"):
            with ui.row().classes("w-full items-start justify-between"):
                with ui.column().classes("flex-1 gap-0"):
                    with ui.row().classes("items-center gap-2"):
                        ui.badge(f"HLR {hlr_id}", color="blue").props("outline")
                        if hlr["component"]:
                            ui.badge(hlr["component"], color="grey")
                        ui.badge(
                            f"{llr_count} LLR{'s' if llr_count != 1 else ''}",
                            color="green" if llr_count > 0 else "grey",
                        ).classes("text-xs")
                    ui.label(hlr["description"]).classes("text-sm mt-1")

                with ui.button(icon="more_vert").props("flat round size=sm"):
                    with ui.menu():
                        ui.menu_item(
                            "View Details",
                            on_click=lambda h=hlr_id: ui.navigate.to(f"/hlr/{h}"),
                        )
                        ui.menu_item(
                            "Add LLR",
                            on_click=lambda h=hlr_id: show_add_llr_dialog(h),
                        )
                        ui.menu_item(
                            "Decompose",
                            on_click=lambda h=hlr_id: confirm_decompose_hlr(h),
                        )
                        ui.separator()
                        ui.menu_item(
                            "Delete",
                            on_click=lambda h=hlr_id: confirm_delete_hlr(h),
                        )

            if hlr["llrs"]:
                with ui.expansion("Low-Level Requirements", icon="list").classes(
                    "w-full mt-2"
                ).props("dense"):
                    _render_llr_table(hlr["llrs"])

    # ---------------------------------------------------------------
    # LLR table (inline — kept here for access to content.refresh)
    # ---------------------------------------------------------------

    def _render_llr_table(llrs):
        from frontend.widgets import render_llr_table
        render_llr_table(llrs)

    # ---------------------------------------------------------------
    # Initial render
    # ---------------------------------------------------------------

    await content()
