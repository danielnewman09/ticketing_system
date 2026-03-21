"""LLR detail page."""

import asyncio

from nicegui import ui

from frontend.theme import apply_theme
from frontend.layout import page_layout
from frontend.widgets import render_verification_card, render_triples_card
from frontend.data import fetch_llr_detail, update_llr


@ui.page("/llr/{llr_id}")
async def llr_detail_page(llr_id: int):
    apply_theme()
    page_layout(f"LLR {llr_id}")

    # ---------------------------------------------------------------
    # Refreshable content
    # ---------------------------------------------------------------

    @ui.refreshable
    async def content():
        data = await asyncio.to_thread(fetch_llr_detail, llr_id)
        if not data:
            ui.label("LLR not found").classes("text-xl text-red-400")
            return

        hlr = data["hlr"]

        # Breadcrumb
        with ui.row().classes("items-center gap-1 px-2 mt-4"):
            ui.link("Requirements", "/").classes("text-blue-400 text-sm no-underline")
            ui.label("/").classes("text-gray-500 text-sm")
            if hlr:
                ui.link(f"HLR {hlr['id']}", f"/hlr/{hlr['id']}").classes("text-blue-400 text-sm no-underline")
                ui.label("/").classes("text-gray-500 text-sm")
            ui.label(f"LLR {data['id']}").classes("text-sm text-gray-300")

        # Header
        with ui.row().classes("w-full items-center justify-between px-2 mt-2 mb-4"):
            ui.label(f"LLR {data['id']}").classes("text-2xl font-bold")
            ui.button("Back", icon="arrow_back", on_click=lambda: ui.navigate.to(
                f"/hlr/{hlr['id']}" if hlr else "/"
            )).props("flat size=sm")

        with ui.row().classes("w-full gap-4 px-2 items-start"):
            # Left column
            with ui.column().classes("flex-1 gap-4"):
                with ui.card().classes("w-full"):
                    with ui.row().classes("w-full items-center justify-between mb-2"):
                        ui.label("Description").classes(
                            "text-xs uppercase tracking-wider text-gray-400"
                        )
                        ui.button(
                            icon="edit",
                            on_click=lambda d=data["description"]: show_edit_dialog(d),
                        ).props("flat round size=xs color=primary")
                    ui.label(data["description"]).classes("text-sm")

                if hlr:
                    with ui.card().classes("w-full"):
                        ui.label("Parent HLR").classes("text-xs uppercase tracking-wider text-gray-400 mb-2")
                        with ui.row().classes("items-center gap-2"):
                            ui.badge(f"HLR {hlr['id']}", color="blue").props("outline")
                            if hlr["component"]:
                                ui.badge(hlr["component"], color="grey")
                        desc = hlr["description"]
                        ui.link(
                            desc[:100] + ("..." if len(desc) > 100 else ""),
                            f"/hlr/{hlr['id']}",
                        ).classes("text-sm no-underline mt-1")

                if data["verifications"]:
                    for v in data["verifications"]:
                        render_verification_card(v)
                else:
                    with ui.card().classes("w-full"):
                        ui.label("Verifications").classes("text-xs uppercase tracking-wider text-gray-400 mb-2")
                        ui.label("No verifications defined.").classes("text-sm text-gray-500")

                if data["components"]:
                    with ui.card().classes("w-full"):
                        ui.label("Components").classes("text-xs uppercase tracking-wider text-gray-400 mb-2")
                        with ui.row().classes("gap-2"):
                            for name in data["components"]:
                                ui.badge(name, color="grey")

            # Right column
            with ui.column().classes("flex-1 gap-4"):
                render_triples_card(data["triples"])

    # ---------------------------------------------------------------
    # Edit LLR description
    # ---------------------------------------------------------------

    async def show_edit_dialog(current_description: str):
        with ui.dialog() as dialog, ui.card().classes("w-96"):
            ui.label(f"Edit LLR {llr_id}").classes("text-lg font-bold mb-2")
            desc_input = ui.textarea("Description", value=current_description).classes("w-full")

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
    # Initial render
    # ---------------------------------------------------------------

    await content()
