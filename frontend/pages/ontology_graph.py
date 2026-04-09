"""Ontology graph visualization page using Cytoscape.js."""

import asyncio

import logging

from nicegui import ui

from frontend.theme import (
    KIND_COLORS,
    BACKGROUNDS,
    CLS_SECTION_HEADER,
    add_cytoscape_cdn,
    cytoscape_base_styles,
    apply_theme,
)
from frontend.layout import page_layout
from frontend.widgets import render_cytoscape_graph
from frontend.data.ontology import (
    fetch_ontology_graph_data,
    fetch_graph_node_detail,
    resolve_node_id_by_qualified_name,
)
from frontend.data.dependencies import (
    fetch_design_dependency_links_data,
)

log = logging.getLogger(__name__)

@ui.page("/ontology/graph")
async def ontology_graph_page():
    apply_theme()
    page_layout("Ontology Graph")

    # -- State --
    kind_filter = {"value": None}
    search_text = {"value": ""}
    selected_node = {"data": None}
    graph_layer = {"value": "design"}  # "design", "codebase", or "dependency"
    source_filter = {"value": None}  # dependency source filter (e.g. "eigen")

    add_cytoscape_cdn()
    base_styles = cytoscape_base_styles(size="large")

    async def load_graph():
        layer = graph_layer["value"]
        search = search_text["value"] or ""

        if layer == "dependency" and not search.strip():
            # Show placeholder — don't load the entire dependency graph
            await ui.run_javascript("""
                if (window._cy) window._cy.destroy();
                const container = document.getElementById('cy-container');
                if (container) {
                    container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#888;font-size:1.1rem;">Search for a class or namespace to explore dependencies</div>';
                }
            """)
            return

        data = await asyncio.to_thread(
            fetch_ontology_graph_data,
            layer=layer,
            kind_filter=kind_filter["value"],
            search=search or None,
            source_filter=source_filter["value"],
        )

        log.debug(data)

        await render_cytoscape_graph(
            data["nodes"] + data["edges"],
            base_styles,
            container_id="cy-container",
            cy_var="_cy",
        )

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
        layer = e.args.get("layer", "")
        detail = await asyncio.to_thread(fetch_graph_node_detail, qn)
        # Fetch dependency links for design nodes
        if detail and layer == "design":
            dep_links = await asyncio.to_thread(fetch_design_dependency_links_data, [qn])
            detail["dependency_links"] = dep_links.get("nodes", [])
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
            {"design": "Design Intent", "codebase": "As-Built Codebase", "dependency": "Dependencies"},
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
        with ui.row().classes("items-center gap-1"):
            ui.html('<div style="width:10px;height:10px;border-radius:50%;background:#009688;border:2px dashed #4db6ac"></div>')
            ui.label("Dependency").classes("text-xs")

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
                if d.get("outgoing"):
                    ui.separator().classes("my-2")
                    ui.label("Outgoing").classes(CLS_SECTION_HEADER)
                    for r in d["outgoing"]:
                        with ui.row().classes("items-center gap-1"):
                            ui.badge(r["rel"], color="grey").classes("text-xs")
                            ui.label(r.get("target_name") or r.get("target_qn", "")).classes("text-xs")

                # Incoming relationships
                if d.get("incoming"):
                    ui.separator().classes("my-2")
                    ui.label("Incoming").classes(CLS_SECTION_HEADER)
                    for r in d["incoming"]:
                        with ui.row().classes("items-center gap-1"):
                            ui.label(r.get("source_name") or r.get("source_qn", "")).classes("text-xs")
                            ui.badge(r["rel"], color="grey").classes("text-xs")

                # Implemented by
                if d.get("implemented_by"):
                    ui.separator().classes("my-2")
                    ui.label("Implemented By").classes(CLS_SECTION_HEADER)
                    for impl in d["implemented_by"]:
                        ui.label(impl.get("qualified_name", impl.get("name", ""))).classes("text-xs text-blue-300")

                # Requirements
                if d.get("requirements"):
                    ui.separator().classes("my-2")
                    ui.label("Traced Requirements").classes(CLS_SECTION_HEADER)
                    for req in d["requirements"]:
                        with ui.row().classes("items-center gap-1"):
                            ui.badge(req["type"], color="orange" if req["type"] == "HLR" else "amber").classes("text-xs")
                            ui.label(req.get("name", "")).classes("text-xs")

                # Dependency links (shown for design nodes)
                if d.get("dependency_links"):
                    ui.separator().classes("my-2")
                    ui.label("Dependencies").classes(CLS_SECTION_HEADER)
                    for dep in d["dependency_links"]:
                        dep_data = dep.get("data", dep)
                        with ui.row().classes("items-center gap-1"):
                            ui.badge(dep_data.get("source", ""), color="teal").classes("text-xs")
                            ui.label(dep_data.get("qualified_name", dep_data.get("label", ""))).classes("text-xs text-teal-300")

                # Design links (shown for dependency nodes)
                if d.get("design_links"):
                    ui.separator().classes("my-2")
                    ui.label("Referenced by Design").classes(CLS_SECTION_HEADER)
                    for link in d["design_links"]:
                        with ui.row().classes("items-center gap-1"):
                            ui.badge(link.get("rel", ""), color="grey").classes("text-xs")
                            ui.label(link.get("design_name", link.get("design_qn", ""))).classes("text-xs text-blue-300")

                # Members (shown for dependency compound nodes)
                if d.get("members") and props.get("layer") == "dependency":
                    ui.separator().classes("my-2")
                    ui.label("Members").classes(CLS_SECTION_HEADER)
                    for m in d["members"][:20]:
                        with ui.row().classes("items-center gap-1"):
                            ui.badge(m.get("kind", ""), color="grey").classes("text-xs")
                            ui.label(m.get("name", "")).classes("text-xs")

                # Source library (shown for dependency nodes)
                if props.get("source"):
                    ui.separator().classes("my-2")
                    with ui.row().classes("items-center gap-1"):
                        ui.label("Source:").classes("text-xs text-gray-400")
                        ui.badge(props["source"], color="teal").classes("text-xs")

        detail_panel()

    # Listen for node selection events from Cytoscape
    ui.on("node_selected", handle_node_selected)
    ui.on("node_dblclick", handle_node_dblclick)

    # Initial load
    await load_graph()
