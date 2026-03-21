"""HLR detail page."""

import asyncio

from nicegui import ui

from frontend.theme import apply_theme
from frontend.layout import page_layout
from frontend.widgets import render_llr_table, render_triples_card
from frontend.data import (
    fetch_hlr_detail,
    fetch_components_options,
    update_hlr,
    delete_hlr,
    create_llr,
    update_llr,
    delete_llr,
    decompose_hlr,
)


@ui.page("/hlr/{hlr_id}")
async def hlr_detail_page(hlr_id: int):
    apply_theme()
    page_layout(f"HLR {hlr_id}")

    # ---------------------------------------------------------------
    # Refreshable content
    # ---------------------------------------------------------------

    @ui.refreshable
    async def content():
        hlr = await asyncio.to_thread(fetch_hlr_detail, hlr_id)
        if not hlr:
            ui.label("HLR not found").classes("text-xl text-red-400")
            return

        # Breadcrumb
        with ui.row().classes("items-center gap-1 px-2 mt-4"):
            ui.link("Requirements", "/").classes("text-blue-400 text-sm no-underline")
            ui.label("/").classes("text-gray-500 text-sm")
            ui.label(f"HLR {hlr['id']}").classes("text-sm text-gray-300")

        # Header
        with ui.row().classes("w-full items-center justify-between px-2 mt-2 mb-4"):
            with ui.row().classes("items-center gap-3"):
                ui.label(f"HLR {hlr['id']}").classes("text-2xl font-bold")
                if hlr["component"]:
                    ui.badge(hlr["component"], color="grey")
            with ui.row().classes("gap-2"):
                ui.button("Back", icon="arrow_back", on_click=lambda: ui.navigate.to("/")).props(
                    "flat size=sm"
                )
                ui.button("Edit", icon="edit", on_click=lambda: show_edit_dialog(hlr)).props(
                    "color=primary size=sm"
                )
                ui.button(
                    "Delete",
                    icon="delete",
                    on_click=lambda: confirm_delete(hlr["id"]),
                ).props("color=negative size=sm")

        # Two-column layout
        with ui.row().classes("w-full gap-4 px-2 items-start"):
            with ui.column().classes("flex-1 gap-4"):
                with ui.card().classes("w-full"):
                    ui.label("Description").classes("text-xs uppercase tracking-wider text-gray-400 mb-2")
                    ui.label(hlr["description"]).classes("text-sm")

                with ui.card().classes("w-full"):
                    with ui.row().classes("w-full items-center justify-between mb-2"):
                        ui.label("Low-Level Requirements").classes(
                            "text-xs uppercase tracking-wider text-gray-400"
                        )
                        with ui.row().classes("gap-1"):
                            ui.button(
                                "Decompose",
                                icon="auto_awesome",
                                on_click=lambda: confirm_decompose(),
                            ).props("flat size=xs color=primary")
                            ui.button(
                                icon="add",
                                on_click=lambda: show_add_llr_dialog(),
                            ).props("flat round size=xs color=positive")
                    if hlr["llrs"]:
                        render_llr_table(hlr["llrs"], on_delete=confirm_delete_llr, on_edit=show_edit_llr_dialog)
                    else:
                        ui.label("No low-level requirements yet.").classes("text-sm text-gray-500")

            with ui.column().classes("flex-1 gap-4"):
                render_triples_card(hlr["triples"])

    # ---------------------------------------------------------------
    # Edit HLR dialog
    # ---------------------------------------------------------------

    async def show_edit_dialog(hlr):
        components = await asyncio.to_thread(fetch_components_options)
        comp_map = {c["name"]: c["id"] for c in components}
        comp_names = ["(none)"] + [c["name"] for c in components]
        current_comp = hlr["component"] if hlr["component"] else "(none)"

        with ui.dialog() as dialog, ui.card().classes("w-96"):
            ui.label(f"Edit HLR {hlr['id']}").classes("text-lg font-bold mb-2")
            desc_input = ui.textarea("Description", value=hlr["description"]).classes("w-full")
            comp_select = ui.select(comp_names, value=current_comp, label="Component").classes("w-full")

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button("Cancel", on_click=dialog.close).props("flat")

                async def do_update():
                    desc = desc_input.value.strip()
                    if not desc:
                        ui.notify("Description is required", type="warning")
                        return
                    comp_id = comp_map.get(comp_select.value)
                    await asyncio.to_thread(update_hlr, hlr["id"], desc, comp_id)
                    dialog.close()
                    ui.notify("HLR updated", type="positive")
                    content.refresh()

                ui.button("Save", on_click=do_update).props("color=positive")

        dialog.open()

    # ---------------------------------------------------------------
    # Delete HLR
    # ---------------------------------------------------------------

    async def confirm_delete(hid: int):
        with ui.dialog() as dialog, ui.card().classes("w-80"):
            ui.label(f"Delete HLR {hid}?").classes("text-lg font-bold")
            ui.label("This will also delete all child LLRs and their verifications.").classes(
                "text-sm text-gray-400 mt-1"
            )
            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button("Cancel", on_click=dialog.close).props("flat")

                async def do_delete():
                    await asyncio.to_thread(delete_hlr, hid)
                    dialog.close()
                    ui.notify(f"Deleted HLR {hid}", type="negative")
                    ui.navigate.to("/")

                ui.button("Delete", on_click=do_delete).props("color=negative")

        dialog.open()

    # ---------------------------------------------------------------
    # Decompose HLR
    # ---------------------------------------------------------------

    async def confirm_decompose():
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
    # Add LLR
    # ---------------------------------------------------------------

    async def show_add_llr_dialog():
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
    # Edit LLR description
    # ---------------------------------------------------------------

    async def show_edit_llr_dialog(llr_id: int, current_description: str):
        with ui.dialog() as dialog, ui.card().classes("w-96"):
            ui.label(f"Edit LLR {llr_id}").classes("text-lg font-bold mb-2")
            desc_input = ui.textarea("Description", value=current_description or "").classes("w-full")

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button("Cancel", on_click=dialog.close).props("flat")

                async def do_update():
                    desc = desc_input.value.strip()
                    if not desc:
                        ui.notify("Description is required", type="warning")
                        return
                    await asyncio.to_thread(update_llr, llr_id, desc)
                    dialog.close()
                    ui.notify("LLR updated", type="positive")
                    content.refresh()

                ui.button("Save", on_click=do_update).props("color=positive")

        dialog.open()

    # ---------------------------------------------------------------
    # Delete LLR
    # ---------------------------------------------------------------

    async def confirm_delete_llr(llr_id: int):
        with ui.dialog() as dialog, ui.card().classes("w-80"):
            ui.label(f"Delete LLR {llr_id}?").classes("text-lg font-bold")
            ui.label("This will also delete its verification methods.").classes(
                "text-sm text-gray-400 mt-1"
            )
            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button("Cancel", on_click=dialog.close).props("flat")

                async def do_delete():
                    await asyncio.to_thread(delete_llr, llr_id)
                    dialog.close()
                    ui.notify(f"Deleted LLR {llr_id}", type="negative")
                    content.refresh()

                ui.button("Delete", on_click=do_delete).props("color=negative")

        dialog.open()

    # ---------------------------------------------------------------
    # Initial render
    # ---------------------------------------------------------------

    await content()
