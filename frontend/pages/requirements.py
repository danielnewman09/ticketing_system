"""Requirements dashboard."""

import asyncio

from nicegui import ui

from frontend.theme import CLS_DIALOG_SM, CLS_DIALOG_MD, CLS_DIALOG_TITLE, CLS_DIALOG_ACTIONS, apply_theme
from frontend.layout import page_layout, stat_card
from frontend.data import (
    fetch_requirements_data,
    fetch_components_options,
    create_hlr,
    delete_hlr,
    create_llr,
    decompose_hlr,
)


@ui.page("/requirements")
async def requirements_page():
    apply_theme()
    page_layout("Requirements")

    @ui.refreshable
    async def content():
        data = await asyncio.to_thread(fetch_requirements_data)

        with ui.row().classes("w-full gap-4 flex-wrap px-2 mt-4"):
            stat_card("HLRs", data["total_hlrs"], "blue-5")
            stat_card("LLRs", data["total_llrs"], "green-5")
            stat_card("Verifications", data["total_verifications"], "amber-5")
            stat_card("Ontology Nodes", data["total_nodes"], "purple-5")
            stat_card("Triples", data["total_triples"], "cyan-5")

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

        with ui.dialog() as dialog, ui.card().classes(CLS_DIALOG_MD):
            ui.label("Create HLR").classes(CLS_DIALOG_TITLE)
            desc_input = ui.textarea("Description").classes("w-full")
            comp_select = ui.select(comp_names, value="(none)", label="Component").classes("w-full")

            with ui.row().classes(CLS_DIALOG_ACTIONS):
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
        with ui.dialog() as dialog, ui.card().classes(CLS_DIALOG_SM):
            ui.label(f"Delete HLR {hlr_id}?").classes("text-lg font-bold")
            ui.label("This will also delete all child LLRs and their verifications.").classes(
                "text-sm text-gray-400 mt-1"
            )
            with ui.row().classes(CLS_DIALOG_ACTIONS):
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
        with ui.dialog() as dialog, ui.card().classes(CLS_DIALOG_MD):
            ui.label(f"Decompose HLR {hlr_id}?").classes("text-lg font-bold")
            ui.label(
                "This will run the decomposition agent to generate low-level "
                "requirements and verification methods."
            ).classes("text-sm text-gray-400 mt-1")

            with ui.row().classes(CLS_DIALOG_ACTIONS):
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
        with ui.dialog() as dialog, ui.card().classes(CLS_DIALOG_MD):
            ui.label(f"Add LLR to HLR {hlr_id}").classes(CLS_DIALOG_TITLE)
            desc_input = ui.textarea("Description").classes("w-full")

            with ui.row().classes(CLS_DIALOG_ACTIONS):
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
