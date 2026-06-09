"""Component detail page — showing environment, dependencies, and ontology nodes."""

import asyncio

from nicegui import ui

from frontend_migrated.theme import BACKGROUNDS, add_cytoscape_cdn, apply_theme
from frontend_migrated.widgets import section_header, breadcrumb, GraphConfig, render_cytoscape_graph
from frontend_migrated.layout import page_layout
from frontend_migrated.data.components import get_component, add_dependency, delete_dependency
from frontend_migrated.data.ontology import fetch_ontology_graph_data, resolve_node_id_by_qualified_name


@ui.page("/component/{component_id}")
async def component_detail_page(component_id: str):
    """Component detail page — uses neomodel Component nodes directly."""
    apply_theme()
    page_layout("Component Detail")

    # -- CDN scripts must load before any Cytoscape rendering --
    add_cytoscape_cdn()

    comp = await asyncio.to_thread(get_component, component_id)

    if not comp:
        ui.label("Component not found").classes("text-xl text-red-400 mt-4 px-2")
        return

    # Mutable ref for refreshable sections
    comp_ref = {"comp": comp}

    async def refresh_comp():
        comp_ref["comp"] = await asyncio.to_thread(get_component, component_id)

    c = comp_ref["comp"]

    # Breadcrumb
    crumbs = [("Components", "/components")]
    parents = c.parent.all()
    if parents:
        crumbs.append((parents[0].name, f"/component/{parents[0].refid}"))
    crumbs.append((c.name, None))
    breadcrumb(*crumbs)

    # Header
    with ui.row().classes("w-full items-center justify-between px-2 mt-2 mb-4"):
        with ui.column().classes("gap-0"):
            ui.label(c.name).classes("text-2xl font-bold")
            if c.namespace:
                ui.label(c.namespace).classes("text-sm font-mono text-gray-400")
        with ui.row().classes("gap-2"):
            ui.button(
                "Research Dependencies",
                icon="science",
                on_click=lambda: ui.navigate.to(f"/component/{component_id}/dependencies/review"),
            ).props("outline size=sm color=primary")
            ui.button(
                "All Components",
                icon="arrow_back",
                on_click=lambda: ui.navigate.to("/components"),
            ).props("flat size=sm")

    # Description
    if c.description:
        with ui.card().classes("w-full mx-2 mb-4"):
            ui.markdown(c.description)

    # Two-column layout
    with ui.row().classes("w-full gap-4 px-2 items-start"):
        # Left column
        with ui.column().classes("flex-1 gap-4"):
            # Sub-components
            children = c.children.all()
            if children:
                with ui.card().classes("w-full"):
                    section_header("Sub-Components")
                    with ui.row().classes("gap-3 flex-wrap"):
                        for child in children:
                            child_hlrs = child.requirements.all()
                            child_nodes = child.namespaces.all() + child.classes.all()
                            with (
                                ui.card()
                                .classes("w-56 cursor-pointer")
                                .on(
                                    "click",
                                    lambda _, ch=child: ui.navigate.to(f"/component/{ch.refid}"),
                                )
                            ):
                                ui.label(child.name).classes("font-semibold")
                                if child.namespace:
                                    ui.label(child.namespace).classes(
                                        "text-xs font-mono text-gray-500"
                                    )
                                with ui.row().classes("gap-2 mt-1"):
                                    ui.label(f"{len(child_hlrs)} HLRs").classes("text-xs text-gray-400")
                                    ui.label(f"{len(child_nodes)} nodes").classes("text-xs text-gray-400")

            # Requirements (HLRs)
            hlrs = c.requirements.all()
            if hlrs:
                with ui.card().classes("w-full"):
                    section_header("Requirements")
                    for hlr in hlrs:
                        llr_count = len(hlr.llrs.all())
                        with ui.row().classes("items-start gap-2 py-2 w-full"):
                            ui.link(
                                f"HLR {hlr.refid}",
                                f"/hlr/{hlr.refid}",
                            ).classes("text-blue-400 text-sm no-underline min-w-[60px]")
                            ui.label(hlr.description).classes("text-sm flex-1")
                            ui.badge(
                                f"{llr_count} LLRs",
                                color="grey",
                            ).classes("text-xs")
                        ui.separator()

            # --- Dependencies ---
            async def do_add_dep(name_input, ver_input, dev_checkbox):
                dep_name = name_input.value.strip()
                if not dep_name:
                    ui.notify("Package name is required", type="warning")
                    return
                try:
                    await asyncio.to_thread(
                        add_dependency,
                        0,  # manager_id — stub placeholder
                        dep_name,
                        ver_input.value.strip(),
                        dev_checkbox.value,
                        component_id=None,
                    )
                except NotImplementedError:
                    ui.notify("Add dependency not yet available in migrated backend", type="warning")
                    return
                ui.notify(f"Added {dep_name}", type="positive")
                name_input.value = ""
                ver_input.value = ""
                dev_checkbox.value = False
                await refresh_comp()
                await dep_section.refresh()

            async def do_delete_dep(dep_refid: str):
                try:
                    await asyncio.to_thread(delete_dependency, dep_refid)
                except NotImplementedError:
                    ui.notify("Delete dependency not yet available in migrated backend", type="warning")
                    return
                ui.notify("Dependency removed", type="info")
                await refresh_comp()
                await dep_section.refresh()

            @ui.refreshable
            async def dep_section():
                current = comp_ref["comp"]
                deps = current.dependencies.all()

                with ui.card().classes("w-full"):
                    section_header("Dependencies")

                    if not deps:
                        ui.label("No dependencies configured.").classes("text-sm text-gray-500")
                    else:
                        for dep in deps:
                            with ui.row().classes("items-center gap-2 py-1 w-full"):
                                ui.label(dep.name).classes("text-sm font-mono flex-1")
                                ui.label(dep.version or "-").classes(
                                    "text-xs text-gray-400 font-mono"
                                )
                                if dep.is_dev:
                                    ui.badge("dev", color="warning").classes("text-xs")
                                ui.button(
                                    icon="close",
                                    on_click=lambda _, d=dep: do_delete_dep(d.refid),
                                ).props("flat round size=xs color=negative")

                    # Add-dependency form — only shown once the data layer
                    # implements add_dependency with a real manager_id.
                    # Kept as a placeholder; the form will be enabled when
                    # dependency manager integration is complete.
                    ui.separator().classes("my-2")
                    with ui.row().classes("items-end gap-2 w-full"):
                        dep_name = ui.input("Package").classes("flex-1").props("dense")
                        dep_ver = ui.input("Version").classes("w-24").props("dense")
                        dep_dev = ui.checkbox("Dev").classes("text-xs")
                        ui.button(
                            "Add",
                            on_click=lambda _, n=dep_name, v=dep_ver, dv=dep_dev: do_add_dep(
                                n, v, dv
                            ),
                        ).props("flat size=xs color=positive")

            await dep_section()

        # Right column — ontology graph
        with ui.column().classes("flex-1 gap-4"):
            with ui.card().classes("w-full"):
                section_header("Design Graph")
                cy = (
                    ui.element("div")
                    .style(
                        f"height: calc(100vh - 280px); min-height: 400px; "
                        f"background: {BACKGROUNDS['base']}; border-radius: 8px;"
                    )
                    .classes("w-full")
                )
                cy._props["id"] = "comp-cy-container"

    # Cytoscape graph config (page-level for event name access)
    comp_config = GraphConfig(
        container_id="comp-cy-container",
        cy_var="_compCy",
        size="small",
        animate=False,
    )

    async def handle_node_dblclick(e):
        args = e.args
        qn = args.get("qualified_name", "")
        if not qn:
            return
        try:
            node_id = await asyncio.to_thread(resolve_node_id_by_qualified_name, qn)
        except NotImplementedError:
            ui.notify("Node detail lookup not yet available", type="warning")
            return
        if node_id:
            ui.navigate.to(f"/node/{node_id}")

    ui.on(comp_config.dbltap_event, handle_node_dblclick)

    # Load graph filtered to this component
    try:
        graph = await asyncio.to_thread(
            fetch_ontology_graph_data,
            component_id=component_id,
        )
        if graph["nodes"]:
            await render_cytoscape_graph(
                graph["nodes"] + graph["edges"],
                comp_config,
            )
    except NotImplementedError:
        # Graph data layer not yet implemented — the container stays empty
        pass