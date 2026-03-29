"""Components page."""

import asyncio

from nicegui import ui

from frontend.theme import apply_theme
from frontend.layout import page_layout
from frontend.data import fetch_components_data


def _is_environment(comp: dict) -> bool:
    """Check if a component is an environment entry."""
    return comp["name"] == "Environment" or comp.get("parent") == "Environment"


def _render_component_card(comp: dict):
    """Render a single component card."""
    with ui.card().classes("w-72 cursor-pointer").on(
        "click", lambda _, c=comp: ui.navigate.to(f"/component/{c['id']}")
    ):
        with ui.row().classes("items-center justify-between w-full"):
            ui.label(comp["name"]).classes("text-lg font-semibold")
            if comp["language"]:
                ui.badge(comp["language"], color="grey").classes("text-xs")

        if comp.get("namespace"):
            ui.label(comp["namespace"]).classes("text-xs text-gray-500 font-mono")

        with ui.row().classes("gap-3 mt-2"):
            with ui.row().classes("items-center gap-1"):
                ui.icon("description", size="xs").classes("text-gray-500")
                ui.label(f"{comp['hlr_count']} HLRs").classes("text-xs text-gray-400")
            with ui.row().classes("items-center gap-1"):
                ui.icon("hub", size="xs").classes("text-gray-500")
                ui.label(f"{comp['node_count']} nodes").classes("text-xs text-gray-400")


@ui.page("/components")
async def components_page():
    apply_theme()
    page_layout("Components")

    all_components = await asyncio.to_thread(fetch_components_data)

    arch_components = [c for c in all_components if not _is_environment(c)]

    # --- Architectural Components ---
    with ui.row().classes("w-full items-center justify-between px-2 mt-4 mb-4"):
        ui.label("Components").classes("text-xl font-semibold")

    if not arch_components:
        ui.label("No components defined yet.").classes("text-gray-500 px-2")
    else:
        with ui.row().classes("w-full gap-4 flex-wrap px-2"):
            for comp in arch_components:
                _render_component_card(comp)
