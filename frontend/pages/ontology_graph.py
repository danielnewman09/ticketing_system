"""Ontology graph visualization page using Cytoscape.js."""

import asyncio
import json

from nicegui import ui

from frontend.theme import (
    KIND_COLORS,
    BACKGROUNDS,
    CLS_SECTION_HEADER,
    KIND_COLORS_JS,
    add_cytoscape_cdn,
    cytoscape_base_styles,
    apply_theme,
)
from frontend.layout import page_layout
from frontend.data import (
    fetch_ontology_graph_data,
    fetch_codebase_graph_data,
    fetch_graph_node_detail,
    resolve_node_id_by_qualified_name,
)


@ui.page("/ontology/graph")
async def ontology_graph_page():
    apply_theme()
    page_layout("Ontology Graph")

    # -- State --
    kind_filter = {"value": None}
    search_text = {"value": ""}
    selected_node = {"data": None}
    graph_layer = {"value": "design"}  # "design" or "codebase"

    add_cytoscape_cdn()
    base_styles = cytoscape_base_styles(size="large")

    async def load_graph():
        if graph_layer["value"] == "codebase":
            data = await asyncio.to_thread(
                fetch_codebase_graph_data,
                search=search_text["value"] or None,
            )
        else:
            data = await asyncio.to_thread(
                fetch_ontology_graph_data,
                kind_filter=kind_filter["value"],
                search=search_text["value"] or None,
            )
        elements_json = json.dumps(data["nodes"] + data["edges"])
        await ui.run_javascript(f"""
            if (window._cy) window._cy.destroy();
            const KIND_COLORS = {KIND_COLORS_JS};
            const container = document.getElementById('cy-container');
            if (!container) {{ console.error('cy-container not found'); return; }}
            window._cy = cytoscape({{
                container: container,
                elements: {elements_json},
                style: {base_styles},
                layout: {{ name: window._cyLayout || 'fcose', animate: true, animationDuration: 500 }},
            }});
            window._cy.on('tap', 'node', function(evt) {{
                const data = evt.target.data();
                if (data.qualified_name) {{
                    emitEvent('node_selected', data);
                }}
            }});
            window._cy.on('dbltap', 'node', function(evt) {{
                const data = evt.target.data();
                if (data.qualified_name) {{
                    emitEvent('node_dblclick', data);
                }}
            }});
        """)

    async def on_layer_change(e):
        graph_layer["value"] = e.value
        await load_graph()

    async def on_kind_change(e):
        kind_filter["value"] = e.value if e.value != "all" else None
        await load_graph()

    async def on_search(e):
        search_text["value"] = e.value
        await load_graph()

    async def on_layout_change(e):
        await ui.run_javascript(f"""
            window._cyLayout = '{e.value}';
            if (window._cy) window._cy.layout({{ name: '{e.value}', animate: true, animationDuration: 500 }}).run();
        """)

    async def handle_node_selected(e):
        qn = e.args.get("qualified_name", "")
        if not qn:
            return
        detail = await asyncio.to_thread(fetch_graph_node_detail, qn)
        if detail:
            selected_node["data"] = detail
            detail_panel.refresh()

    async def handle_node_dblclick(e):
        qn = e.args.get("qualified_name", "")
        if not qn:
            return
        node_id = await asyncio.to_thread(resolve_node_id_by_qualified_name, qn)
        if node_id:
            ui.navigate.to(f"/node/{node_id}")

    # -- Layout --
    with ui.row().classes("w-full items-center justify-between px-2 mt-4 mb-2"):
        ui.label("Ontology Graph").classes("text-xl font-semibold")
        ui.link("← Table View", "/ontology").classes("text-sm")

    # Controls
    with ui.row().classes("w-full gap-4 px-2 mb-2 items-end"):
        ui.select(
            {"design": "Design Intent", "codebase": "As-Built Codebase"},
            value="design",
            label="Layer",
            on_change=on_layer_change,
        ).classes("w-44")
        kind_options = ["all"] + sorted(KIND_COLORS.keys())
        ui.select(kind_options, value="all", label="Kind", on_change=on_kind_change).classes("w-36")
        ui.input("Search", on_change=on_search).classes("w-48")
        ui.select(
            ["fcose", "breadthfirst", "circle", "grid", "concentric"],
            value="fcose",
            label="Layout",
            on_change=on_layout_change,
        ).classes("w-36")
        ui.button("Fit", on_click=lambda: ui.run_javascript("if(window._cy) window._cy.fit()")).props("flat dense")

    # Legend
    with ui.row().classes("px-2 mb-2 gap-3 flex-wrap"):
        for kind, color in sorted(KIND_COLORS.items()):
            with ui.row().classes("items-center gap-1"):
                ui.html(f'<div style="width:10px;height:10px;border-radius:50%;background:{color}"></div>')
                ui.label(kind).classes("text-xs")
        with ui.row().classes("items-center gap-1"):
            ui.html('<div style="width:10px;height:10px;transform:rotate(45deg);background:#e67e22"></div>')
            ui.label("Requirement").classes("text-xs")

    # Main content: graph + detail panel
    with ui.row().classes("w-full gap-0 px-2").style("height: calc(100vh - 240px); min-height: 400px"):
        # Graph container — single div with id for Cytoscape to mount into
        cy = ui.element("div").classes("flex-grow").style(
            f"height: 100%; background: {BACKGROUNDS['base']}; border-radius: 8px;"
        )
        cy._props["id"] = "cy-container"

        # Detail panel
        @ui.refreshable
        def detail_panel():
            with ui.card().classes("w-80 ml-2 overflow-auto").style("max-height: 100%"):
                d = selected_node["data"]
                if not d:
                    ui.label("Click a node to see details").classes("text-gray-400 text-sm")
                    return

                props = d["properties"]
                kind = props.get("kind", "")
                color = KIND_COLORS.get(kind, "#666")

                ui.label(props.get("name", "")).classes("text-lg font-bold")
                ui.label(props.get("qualified_name", "")).classes("text-xs text-gray-400 break-all")
                with ui.row().classes("gap-2 mt-1"):
                    ui.badge(kind, color="grey").style(f"background:{color} !important")
                    if props.get("visibility"):
                        ui.badge(props["visibility"], color="grey")

                if props.get("description"):
                    ui.separator().classes("my-2")
                    ui.label(props["description"]).classes("text-sm")

                # Outgoing relationships
                if d["outgoing"]:
                    ui.separator().classes("my-2")
                    ui.label("Outgoing").classes(CLS_SECTION_HEADER)
                    for r in d["outgoing"]:
                        with ui.row().classes("items-center gap-1"):
                            ui.badge(r["rel"], color="grey").classes("text-xs")
                            ui.label(r.get("target_name") or r.get("target_qn", "")).classes("text-xs")

                # Incoming relationships
                if d["incoming"]:
                    ui.separator().classes("my-2")
                    ui.label("Incoming").classes(CLS_SECTION_HEADER)
                    for r in d["incoming"]:
                        with ui.row().classes("items-center gap-1"):
                            ui.label(r.get("source_name") or r.get("source_qn", "")).classes("text-xs")
                            ui.badge(r["rel"], color="grey").classes("text-xs")

                # Implemented by
                if d["implemented_by"]:
                    ui.separator().classes("my-2")
                    ui.label("Implemented By").classes(CLS_SECTION_HEADER)
                    for impl in d["implemented_by"]:
                        ui.label(impl.get("qualified_name", impl.get("name", ""))).classes("text-xs text-blue-300")

                # Requirements
                if d["requirements"]:
                    ui.separator().classes("my-2")
                    ui.label("Traced Requirements").classes(CLS_SECTION_HEADER)
                    for req in d["requirements"]:
                        with ui.row().classes("items-center gap-1"):
                            ui.badge(req["type"], color="orange" if req["type"] == "HLR" else "amber").classes("text-xs")
                            ui.label(req.get("name", "")).classes("text-xs")

        detail_panel()

    # Listen for node selection events from Cytoscape
    ui.on("node_selected", handle_node_selected)
    ui.on("node_dblclick", handle_node_dblclick)

    # Initial load
    await load_graph()
