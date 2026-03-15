"""HLR detail page."""

import asyncio

from nicegui import ui

from frontend.theme import apply_theme
from frontend.layout import page_layout
from frontend.widgets import render_llr_table, render_triples_card
from frontend.data import fetch_hlr_detail


@ui.page("/hlr/{hlr_id}")
async def hlr_detail_page(hlr_id: int):
    apply_theme()
    page_layout(f"HLR {hlr_id}")

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
            ui.button("Decompose", icon="account_tree", on_click=lambda: ui.notify("Would decompose")).props(
                "color=warning size=sm"
            )

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
                    ui.button(icon="add", on_click=lambda: ui.notify("Would create LLR")).props(
                        "flat round size=xs color=positive"
                    )
                if hlr["llrs"]:
                    render_llr_table(hlr["llrs"])
                else:
                    ui.label("No low-level requirements yet.").classes("text-sm text-gray-500")

        with ui.column().classes("flex-1 gap-4"):
            render_triples_card(hlr["triples"])
