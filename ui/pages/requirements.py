"""Requirements dashboard — main page."""

import asyncio

from nicegui import ui

from ui.theme import apply_theme
from ui.layout import page_layout, stat_card
from ui.widgets import render_hlr_card, render_llr_table
from ui.data import fetch_requirements_data


@ui.page("/")
async def requirements_page():
    apply_theme()
    page_layout("Requirements")

    data = await asyncio.to_thread(fetch_requirements_data)

    with ui.row().classes("w-full gap-4 flex-wrap px-2 mt-4"):
        stat_card("HLRs", data["total_hlrs"], "blue-5")
        stat_card("LLRs", data["total_llrs"], "green-5")
        stat_card("Verifications", data["total_verifications"], "amber-5")
        stat_card("Ontology Nodes", data["total_nodes"], "purple-5")
        stat_card("Triples", data["total_triples"], "cyan-5")

    with ui.row().classes("w-full items-center justify-between px-2 mt-6 mb-2"):
        ui.label("High-Level Requirements").classes("text-xl font-semibold")
        with ui.row().classes("gap-2"):
            ui.button("+ HLR", icon="add", on_click=lambda: ui.navigate.to("/hlr/new")).props(
                "color=positive size=sm"
            )

    for hlr in data["hlrs"]:
        render_hlr_card(hlr)

    if data["unlinked_llrs"]:
        ui.separator().classes("my-4")
        ui.label("Unlinked LLRs").classes("text-lg font-semibold text-amber-400 px-2 mb-2")
        render_llr_table(data["unlinked_llrs"])
