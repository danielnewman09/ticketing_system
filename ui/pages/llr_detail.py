"""LLR detail page."""

import asyncio

from nicegui import ui

from ui.theme import apply_theme
from ui.layout import page_layout
from ui.widgets import render_verification_card, render_triples_card
from ui.data import fetch_llr_detail


@ui.page("/llr/{llr_id}")
async def llr_detail_page(llr_id: int):
    apply_theme()
    page_layout(f"LLR {llr_id}")

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
                ui.label("Description").classes("text-xs uppercase tracking-wider text-gray-400 mb-2")
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
