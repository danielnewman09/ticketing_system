"""Ontology graph page — interactive Cytoscape.js visualization with a
collapsible detail panel.

Architecture
------------
- ``state`` — a ``GraphState`` dataclass holding all mutable page state;
  mutations are visible to ``@ui.refreshable`` widgets passed the same object.
- Handlers — async callbacks that mutate ``state`` and trigger data loads
  or detail-panel refreshes.
- Widget calls — delegate all rendering to ``frontend.widgets`` helpers
  (controls, legend, detail panel).
- ``load_graph()`` — fetches graph data from Neo4j via the data layer and
  renders it into the Cytoscape container. Called on initial load and on
  filter/search changes.

Inter-page events (``node_selected``, ``node_dblclick``) are emitted by
Cytoscape via JavaScript and received through ``ui.on()`` listeners.
"""

import asyncio

from nicegui import ui

from frontend.theme import (
    BACKGROUNDS,
    add_cytoscape_cdn,
    cytoscape_base_styles,
    apply_theme,
)
from frontend.layout import page_layout
from frontend.widgets import (
    GraphState,
    render_cytoscape_graph,
    render_graph_detail_panel,
    render_ontology_graph_controls,
    render_ontology_graph_legend,
)
from frontend.data.ontology import (
    fetch_ontology_graph_data,
    fetch_graph_node_detail,
    resolve_node_id_by_qualified_name,
)
from frontend.data.dependencies import (
    fetch_design_dependency_links_data,
)


@ui.page("/ontology/graph")
async def ontology_graph_page():
    """Render the ontology-graph page: graph canvas, filter controls,
    legend, and a detail sidebar for the selected node."""
    apply_theme()
    page_layout("Ontology Graph")

    # -- Mutable state (passed by reference to @ui.refreshable widgets) --
    state = GraphState()

    # -- Cytoscape setup --
    add_cytoscape_cdn()
    base_styles = cytoscape_base_styles(size="large")

    # -- Data-loading and event-handling closures --

    async def load_graph():
        """Fetch graph data for the current layer/filters and render it."""
        layer = state.graph_layer
        search = state.search_text or ""

        if layer == "dependency" and not search.strip():
            # Dependency layer requires a search term — show placeholder
            await ui.run_javascript("""
                if (window._cy) window._cy.destroy();
                const container = document.getElementById('cy-container');
                if (container) {
                    container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#888;font-size:1.1rem;">Search for a class or namespace to explore dependencies</div>';
                }
            """)
            return

        requirement_tags = "hlr" if state.show_requirement_tags else "none"
        data = await asyncio.to_thread(
            fetch_ontology_graph_data,
            layer=layer,
            kind_filter=state.kind_filter,
            search=search or None,
            source_filter=state.source_filter,
            requirement_tags=requirement_tags,
        )
        await render_cytoscape_graph(
            data["nodes"] + data["edges"],
            base_styles,
            container_id="cy-container",
            cy_var="_cy",
        )
        # Render HLR badges on design nodes
        if layer == "design" and state.show_requirement_tags:
            await ui.run_javascript('''
                if (window._cy) {
                    window._cy.nodes().forEach(function(node) {
                        const reqs = node.data('requirements');
                        if (reqs && reqs.length > 0) {
                            const badges = reqs.map(r => '[' + r.type + ' ' + r.id + ']').join(' ');
                            node.data('label', node.data('name') + '\n' + badges);
                            node.addClass('has-requirements');
                        }
                    });
                }
            ''')

    async def on_layer_change(e):
        state.graph_layer = e.value
        await load_graph()

    async def on_kind_change(e):
        state.kind_filter = e.value if e.value != "all" else None
        await load_graph()

    async def on_search(e):
        state.search_text = e.value
        await load_graph()

    async def on_layout_change(e):
        await ui.run_javascript(f"""
            window._cyLayout = '{e.value}';
            if (window._cy) window._cy.layout({{ name: '{e.value}', animate: true, animationDuration: 500 }}).run();
        """)

    async def on_toggle_req_tags(e):
        state.show_requirement_tags = e.value
        await load_graph()

    async def handle_node_selected(e):
        """On node click/tap: fetch detail and refresh the side panel."""
        qn = e.args.get("qualified_name", "")
        if not qn:
            return
        layer = e.args.get("layer", "")
        detail = await asyncio.to_thread(fetch_graph_node_detail, qn)
        # Design-layer nodes also carry dependency cross-links
        if detail and layer == "design":
            dep_links = await asyncio.to_thread(fetch_design_dependency_links_data, [qn])
            detail["dependency_links"] = dep_links.get("nodes", [])
        if detail:
            state.selected_node_data = detail
            render_graph_detail_panel.refresh()

    async def handle_node_dblclick(e):
        """On node double-click: navigate to the full node detail page."""
        qn = e.args.get("qualified_name", "")
        if not qn:
            return
        node_id = await asyncio.to_thread(resolve_node_id_by_qualified_name, qn)
        if node_id:
            ui.navigate.to(f"/node/{node_id}")

    # ------------------------------------------------------------------
    # Layout: header, controls, legend, then graph + detail panel
    # ------------------------------------------------------------------

    # Header row
    with ui.row().classes("w-full items-center justify-between px-2 mt-4 mb-2"):
        ui.label("Ontology Graph").classes("text-xl font-semibold")
        ui.link("← Table View", "/ontology").classes("text-sm")

    # Filter / layout controls (callbacks close over ``state``)
    render_ontology_graph_controls(
        on_layer_change=on_layer_change,
        on_kind_change=on_kind_change,
        on_search=on_search,
        on_layout_change=on_layout_change,
        on_fit=lambda: ui.run_javascript("if(window._cy) window._cy.fit()"),
        on_toggle_req_tags=on_toggle_req_tags,
    )

    # Legend
    render_ontology_graph_legend()

    # Main content: graph canvas + detail sidebar
    with (
        ui.row()
        .classes("w-full gap-0 px-2")
        .style("height: calc(100vh - 240px); min-height: 400px")
    ):
        # Graph container — single div with id for Cytoscape to mount into
        cy = (
            ui.element("div")
            .classes("flex-grow")
            .style(f"height: 100%; background: {BACKGROUNDS['base']}; border-radius: 8px;")
        )
        cy._props["id"] = "cy-container"

        # Detail sidebar (refreshable — updates on node selection)
        render_graph_detail_panel(state)

    # -- Cytoscape event listeners --
    ui.on("node_selected", handle_node_selected)
    ui.on("node_dblclick", handle_node_dblclick)

    # -- Initial data load --
    await load_graph()
