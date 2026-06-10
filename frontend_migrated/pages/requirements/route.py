"""Requirements dashboard — page entry point.

Orchestrates the HLR dashboard: fetches requirements data, renders
stat cards and the HLR list, and wires up dialog actions.

All dialog ``show()`` methods are async — they must be called from
async event handlers so NiceGUI's slot context is preserved.
"""

from __future__ import annotations

import asyncio

from nicegui import ui

from frontend_migrated.theme import apply_theme
from frontend_migrated.layout import page_layout, stat_card
from frontend_migrated.widgets import render_llr_table
from frontend_migrated.data.hlr import fetch_requirements_data
from frontend_migrated.pages.requirements.cards import render_hlr_card
from frontend_migrated.pages.requirements.dialogs import (
    CreateHLRDialog,
    DeleteHLRDialog,
    DecomposeHLRDialog,
    DesignHLRDialog,
    AddLLRDialog,
)


@ui.page("/requirements")
async def requirements_page():
    """Requirements dashboard — HLR listing with create/decompose/design actions."""
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

            async def _create_hlr():
                await CreateHLRDialog(on_done=content.refresh).show()

            ui.button(
                "+ HLR",
                icon="add",
                on_click=_create_hlr,
            ).props("color=positive size=sm")

        for hlr in data["hlrs"]:
            render_hlr_card(
                hlr,
                on_add_llr=lambda h: AddLLRDialog(h, on_done=content.refresh).show(),
                on_decompose=lambda h: DecomposeHLRDialog(h, on_done=content.refresh).show(),
                on_design=lambda h: DesignHLRDialog(h, on_done=content.refresh).show(),
                on_delete=lambda h: DeleteHLRDialog(h, on_done=content.refresh).show(),
            )

        if data["unlinked_llrs"]:
            ui.separator().classes("my-4")
            ui.label("Unlinked LLRs").classes(
                "text-lg font-semibold text-amber-400 px-2 mb-2"
            )
            render_llr_table(data["unlinked_llrs"])

    await content()