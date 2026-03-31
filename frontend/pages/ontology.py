"""Ontology overview page."""

import asyncio

from nicegui import ui

from frontend.theme import KIND_COLORS, apply_theme
from frontend.layout import page_layout, stat_card
from frontend.data.ontology import fetch_ontology_data


@ui.page("/ontology")
async def ontology_page():
    apply_theme()
    page_layout("Ontology")

    data = await asyncio.to_thread(fetch_ontology_data)

    with ui.row().classes("w-full items-center justify-between px-2 mt-4 mb-4"):
        ui.label("Ontology").classes("text-xl font-semibold")
        ui.link("View Graph →", "/ontology/graph").classes("text-sm")

    with ui.row().classes("w-full gap-4 flex-wrap px-2 mb-4"):
        stat_card("Nodes", data["total_nodes"], "purple-5")
        stat_card("Triples", data["total_triples"], "cyan-5")
        stat_card("Predicates", data["total_predicates"], "amber-5")

    with ui.card().classes("w-full mx-2 mb-4"):
        ui.label("Nodes by Kind").classes("text-xs uppercase tracking-wider text-gray-400 mb-3")
        with ui.row().classes("gap-3 flex-wrap"):
            for kind, count in sorted(data["kind_counts"].items(), key=lambda x: -x[1]):
                color = KIND_COLORS.get(kind, "#666")
                with ui.row().classes("items-center gap-1"):
                    ui.html(f'<div style="width:12px;height:12px;border-radius:50%;background:{color}"></div>')
                    ui.label(f"{kind}: {count}").classes("text-sm")

    with ui.card().classes("w-full mx-2"):
        ui.label("All Nodes").classes("text-xs uppercase tracking-wider text-gray-400 mb-2")
        columns = [
            {"name": "name", "label": "Name", "field": "name", "align": "left", "sortable": True},
            {"name": "kind", "label": "Kind", "field": "kind", "align": "left", "sortable": True},
            {"name": "qualified_name", "label": "Qualified Name", "field": "qualified_name", "align": "left"},
            {"name": "component", "label": "Component", "field": "component", "align": "left"},
        ]
        t = ui.table(columns=columns, rows=data["nodes"]).classes("w-full")
        t.props("dense flat")
        t.add_slot(
            "body-cell-kind",
            """
            <q-td :props="props">
                <q-badge :label="props.value" color="grey" class="text-xs" />
            </q-td>
            """,
        )
