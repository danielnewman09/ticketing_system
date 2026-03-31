"""Dependency review page route."""

import asyncio

from nicegui import ui

from frontend.theme import CLS_DIALOG_MD, CLS_DIALOG_TITLE, apply_theme
from frontend.widgets import section_header, breadcrumb
from frontend.layout import page_layout
from frontend.data.components import fetch_component_detail
from frontend.data.dependencies import (
    fetch_recommendations,
    save_recommendations,
    update_recommendation_status,
    accept_recommendation,
    add_manual_recommendation,
    reject_use_stdlib,
)
from frontend.pages.dependency_review.cards import render_recs_by_status
from frontend.pages.dependency_review.research import run_research


@ui.page("/component/{component_id}/dependencies/review")
async def dependency_review_page(component_id: int):
    apply_theme()
    page_layout("Dependency Review")

    comp = await asyncio.to_thread(fetch_component_detail, component_id)
    if not comp:
        ui.label("Component not found").classes("text-xl text-red-400 mt-4 px-2")
        return

    breadcrumb(
        ("Components", "/components"),
        (comp["name"], f"/component/{component_id}"),
        ("Dependency Review", None),
    )

    # Header
    with ui.row().classes("w-full items-center justify-between px-2 mt-2 mb-4"):
        ui.label(f"Dependency Research: {comp['name']}").classes("text-2xl font-bold")
        with ui.row().classes("gap-2"):
            ui.button(
                "Back", icon="arrow_back",
                on_click=lambda: ui.navigate.to(f"/component/{component_id}"),
            ).props("flat size=sm")
            ui.button(
                "Run Research", icon="science",
                on_click=lambda: do_run_research(),
            ).props("color=primary size=sm")
            ui.button(
                "Add Manually", icon="add",
                on_click=lambda: add_dialog.open(),
            ).props("size=sm outline").classes("text-white border-white")

    # Add-manually dialog
    with ui.dialog() as add_dialog, ui.card().classes(CLS_DIALOG_MD):
        ui.label("Add Dependency").classes(CLS_DIALOG_TITLE)
        name_input = ui.input("Package name").classes("w-full")
        version_input = ui.input("Version").classes("w-full")
        url_input = ui.input("GitHub URL").classes("w-full")
        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button("Cancel", on_click=add_dialog.close).props("flat size=sm")
            ui.button(
                "Add", icon="check",
                on_click=lambda: submit_manual(),
            ).props("color=primary size=sm")

    # --- Handlers ---

    async def submit_manual():
        name = name_input.value.strip()
        if not name:
            ui.notify("Package name is required", type="warning")
            return
        await asyncio.to_thread(add_manual_recommendation, component_id, {
            "name": name,
            "version": version_input.value.strip(),
            "github_url": url_input.value.strip(),
        })
        add_dialog.close()
        name_input.value = ""
        version_input.value = ""
        url_input.value = ""
        ui.notify(f"Added {name}", type="positive")
        await recs_section.refresh()

    async def do_run_research():
        ui.notify("Researching dependencies... this may take a moment", type="info")
        try:
            result = await asyncio.to_thread(run_research, component_id)
            await asyncio.to_thread(
                save_recommendations, component_id,
                result["summary"], result["recommendations"],
            )
            ui.notify(
                f"Found {len(result['recommendations'])} recommendations",
                type="positive",
            )
            await recs_section.refresh()
        except Exception as e:
            ui.notify(f"Research failed: {e}", type="negative")

    async def do_accept(rec_id: int, name: str, pending_recs: list[dict]):
        await asyncio.to_thread(accept_recommendation, rec_id)
        for rec in pending_recs:
            if rec["id"] != rec_id:
                await asyncio.to_thread(update_recommendation_status, rec["id"], "rejected")
        ui.notify(f"Accepted {name} — rejected others", type="positive")
        await recs_section.refresh()

    async def do_reject(rec_id: int, name: str):
        await asyncio.to_thread(update_recommendation_status, rec_id, "rejected")
        ui.notify(f"Rejected {name}", type="info")
        await recs_section.refresh()

    async def do_use_stdlib_all(pending_recs: list[dict]):
        for rec in pending_recs:
            await asyncio.to_thread(reject_use_stdlib, rec["id"])
        ui.notify("Rejected all — will use standard library", type="info")
        await recs_section.refresh()

    # --- Recommendations list ---

    @ui.refreshable
    async def recs_section():
        recs = await asyncio.to_thread(fetch_recommendations, component_id)
        if not recs:
            with ui.card().classes("w-full mx-2"):
                ui.label(
                    "No recommendations yet. Click 'Run Research' to search for dependencies."
                ).classes("text-gray-500")
            return

        summary = recs[0].get("summary", "")
        if summary:
            with ui.card().classes("w-full mx-2 mb-4"):
                section_header("Research Summary")
                ui.markdown(summary)

        render_recs_by_status(
            recs,
            on_accept=do_accept,
            on_reject=do_reject,
            on_use_stdlib=do_use_stdlib_all,
        )

    await recs_section()
