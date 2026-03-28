"""Dependency research review page."""

import asyncio

from nicegui import ui

from frontend.theme import apply_theme
from frontend.layout import page_layout
from frontend.data import (
    fetch_component_detail,
    fetch_recommendations,
    save_recommendations,
    update_recommendation_status,
    accept_recommendation,
)


@ui.page("/component/{component_id}/dependencies/review")
async def dependency_review_page(component_id: int):
    apply_theme()
    page_layout("Dependency Review")

    comp = await asyncio.to_thread(fetch_component_detail, component_id)
    if not comp:
        ui.label("Component not found").classes("text-xl text-red-400 mt-4 px-2")
        return

    # Breadcrumb
    with ui.row().classes("items-center gap-1 px-2 mt-4"):
        ui.link("Components", "/components").classes("text-blue-400 text-sm no-underline")
        ui.label("/").classes("text-gray-500 text-sm")
        ui.link(comp["name"], f"/component/{component_id}").classes(
            "text-blue-400 text-sm no-underline"
        )
        ui.label("/").classes("text-gray-500 text-sm")
        ui.label("Dependency Review").classes("text-sm text-gray-300")

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
                on_click=lambda: run_research(),
            ).props("color=primary size=sm")

    # --- Handlers ---

    async def run_research():
        ui.notify("Researching dependencies... this may take a moment", type="info")
        try:
            result = await asyncio.to_thread(_do_research, component_id)
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

    async def do_accept(rec_id: int, name: str):
        await asyncio.to_thread(accept_recommendation, rec_id)
        ui.notify(f"Accepted {name} — added to dependencies", type="positive")
        await recs_section.refresh()

    async def do_reject(rec_id: int, name: str):
        await asyncio.to_thread(update_recommendation_status, rec_id, "rejected")
        ui.notify(f"Rejected {name}", type="info")
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

        # Show summary from first recommendation
        summary = recs[0].get("summary", "")
        if summary:
            with ui.card().classes("w-full mx-2 mb-4"):
                ui.label("Research Summary").classes(
                    "text-xs uppercase tracking-wider text-gray-400 mb-2"
                )
                ui.markdown(summary)

        # Group by status
        pending = [r for r in recs if r["status"] == "pending"]
        accepted = [r for r in recs if r["status"] == "accepted"]
        rejected = [r for r in recs if r["status"] == "rejected"]

        if pending:
            ui.label("Pending Review").classes(
                "text-sm font-semibold text-gray-300 px-2 mt-2 mb-2"
            )
            for rec in pending:
                _render_recommendation_card(rec, show_actions=True)

        if accepted:
            ui.label("Accepted").classes(
                "text-sm font-semibold text-green-400 px-2 mt-4 mb-2"
            )
            for rec in accepted:
                _render_recommendation_card(rec, show_actions=False)

        if rejected:
            ui.label("Rejected").classes(
                "text-sm font-semibold text-gray-500 px-2 mt-4 mb-2"
            )
            for rec in rejected:
                _render_recommendation_card(rec, show_actions=False)

    def _render_recommendation_card(rec: dict, show_actions: bool):
        status_style = ""
        if rec["status"] == "accepted":
            status_style = "border-left: 3px solid #10b981;"
        elif rec["status"] == "rejected":
            status_style = "border-left: 3px solid #6b7280; opacity: 0.6;"

        with ui.card().classes("w-full mx-2 mb-3").style(status_style):
            # Header row
            with ui.row().classes("w-full items-center justify-between"):
                with ui.row().classes("items-center gap-3"):
                    ui.label(rec["name"]).classes("text-lg font-bold")
                    if rec["stars"]:
                        ui.badge(f"{rec['stars']} stars", color="grey").classes("text-xs")
                    if rec["license"]:
                        ui.badge(rec["license"], color="grey").classes("text-xs")
                    if rec["last_updated"]:
                        date = rec["last_updated"][:10]
                        ui.label(f"Updated {date}").classes("text-xs text-gray-500")

                if show_actions:
                    with ui.row().classes("gap-1"):
                        ui.button(
                            "Accept", icon="check",
                            on_click=lambda _, r=rec: do_accept(r["id"], r["name"]),
                        ).props("color=positive size=sm")
                        ui.button(
                            "Reject", icon="close",
                            on_click=lambda _, r=rec: do_reject(r["id"], r["name"]),
                        ).props("color=negative size=sm outline")
                else:
                    ui.badge(rec["status"], color="positive" if rec["status"] == "accepted" else "grey")

            # GitHub link
            if rec["github_url"]:
                ui.link(
                    rec["github_url"], rec["github_url"],
                ).classes("text-xs text-blue-400 no-underline")

            # Description
            if rec["description"]:
                ui.label(rec["description"]).classes("text-sm mt-2")

            # Pros / Cons
            with ui.row().classes("w-full gap-4 mt-3"):
                if rec["pros"]:
                    with ui.column().classes("flex-1"):
                        ui.label("Pros").classes("text-xs text-green-400 uppercase tracking-wider mb-1")
                        for pro in rec["pros"]:
                            ui.label(f"+ {pro}").classes("text-xs text-green-300")
                if rec["cons"]:
                    with ui.column().classes("flex-1"):
                        ui.label("Cons").classes("text-xs text-red-400 uppercase tracking-wider mb-1")
                        for con in rec["cons"]:
                            ui.label(f"- {con}").classes("text-xs text-red-300")

            # Relevant HLRs and structures
            with ui.row().classes("gap-2 mt-2 flex-wrap"):
                for hlr_id in rec.get("relevant_hlrs", []):
                    ui.link(
                        f"HLR {hlr_id}", f"/hlr/{hlr_id}",
                    ).classes("text-xs text-blue-400 no-underline").props("outline")
                for struct in rec.get("relevant_structures", []):
                    ui.badge(struct, color="grey").classes("text-xs font-mono")

    await recs_section()


def _do_research(component_id: int) -> dict:
    """Run the research agent (called in a thread)."""
    from db import get_session
    from db.models import Component, HighLevelRequirement

    with get_session() as session:
        comp = session.query(Component).filter_by(id=component_id).first()
        if not comp:
            raise ValueError(f"Component {component_id} not found")

        hlrs = [
            {"id": h.id, "description": h.description}
            for h in comp.high_level_requirements
        ]

        language = repr(comp.language) if comp.language else "C++"

        existing_deps = []
        if comp.language:
            for dm in comp.language.dependency_managers:
                for d in dm.dependencies:
                    existing_deps.append(d.name)

    from ticketing_agent.design.research_dependencies import research_dependencies
    return research_dependencies(
        component_name=comp.name,
        component_description=comp.description or "",
        hlrs=hlrs,
        language=language,
        existing_deps=existing_deps,
    )
