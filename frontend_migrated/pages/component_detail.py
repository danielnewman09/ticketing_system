"""Component detail page — showing environment, dependencies, and ontology nodes."""

import asyncio

from nicegui import ui

from frontend_migrated.theme import BACKGROUNDS, add_cytoscape_cdn, apply_theme
from frontend_migrated.widgets import (
    section_header,
    breadcrumb,
    GraphConfig,
    render_cytoscape_graph,
)
from frontend_migrated.layout import page_layout
from frontend_migrated.data.components import get_component, add_dependency, delete_dependency
from frontend_migrated.data.ontology import (
    fetch_ontology_graph_data,
    resolve_node_id_by_qualified_name,
)


# ---------------------------------------------------------------------------
# Stateful UI sections
# ---------------------------------------------------------------------------


class DependencyPanel:
    """Refreshable panel that lists, adds, and deletes component dependencies.

    Encapsulates its own data fetch cycle: :meth:`refresh` re-loads the
    component from the data layer and re-renders the whole panel.
    """

    def __init__(self, component_id: str):
        self.component_id = component_id
        self.comp = None  # set by _load
        self._refreshable = None

    # -- public API ----------------------------------------------------------

    async def render(self):
        """Initial data fetch + mount the panel into the current context."""
        await self._load()
        self._refreshable = ui.refreshable(self._render)
        self._refreshable()

    async def refresh(self):
        """Re-fetch component and re-render."""
        await self._load()
        self._refreshable.refresh()

    # -- internals -----------------------------------------------------------

    async def _load(self):
        self.comp = await asyncio.to_thread(get_component, self.component_id)

    def _render(self):
        deps = self.comp.dependencies.all()
        with ui.card().classes("w-full"):
            section_header("Dependencies")

            if not deps:
                ui.label("No dependencies configured.").classes("text-sm text-gray-500")
            else:
                for dep in deps:
                    self._dep_row(dep)

            ui.separator().classes("my-2")
            self._add_form()

    # -- sub-renderers -------------------------------------------------------

    def _dep_row(self, dep):
        with ui.row().classes("items-center gap-2 py-1 w-full"):
            ui.label(dep.name).classes("text-sm font-mono flex-1")
            ui.label(dep.version or "-").classes("text-xs text-gray-400 font-mono")
            if dep.is_dev:
                ui.badge("dev", color="warning").classes("text-xs")
            ui.button(
                icon="close",
                on_click=lambda _, d=dep: self._on_delete(d.refid),
            ).props("flat round size=xs color=negative")

    def _add_form(self):
        self._name_input = ui.input("Package").classes("flex-1").props("dense")
        self._ver_input = ui.input("Version").classes("w-24").props("dense")
        self._dev_checkbox = ui.checkbox("Dev").classes("text-xs")
        ui.button("Add", on_click=self._on_add).props("flat size=xs color=positive")

    # -- event handlers -----------------------------------------------------

    async def _on_add(self):
        name = self._name_input.value.strip()
        if not name:
            ui.notify("Package name is required", type="warning")
            return
        try:
            await asyncio.to_thread(
                add_dependency,
                0,  # manager_id — stub placeholder
                name,
                self._ver_input.value.strip(),
                self._dev_checkbox.value,
                component_id=None,
            )
        except NotImplementedError:
            ui.notify("Add dependency not yet available in migrated backend", type="warning")
            return
        ui.notify(f"Added {name}", type="positive")
        self._name_input.value = ""
        self._ver_input.value = ""
        self._dev_checkbox.value = False
        await self.refresh()

    async def _on_delete(self, dep_refid: str):
        try:
            await asyncio.to_thread(delete_dependency, dep_refid)
        except NotImplementedError:
            ui.notify("Delete dependency not yet available in migrated backend", type="warning")
            return
        ui.notify("Dependency removed", type="info")
        await self.refresh()


# ---------------------------------------------------------------------------
# Static section renderers (stateless — data in, UI out)
# ---------------------------------------------------------------------------


def render_subcomponents(children):
    """Render the sub-components card (read-only)."""
    if not children:
        return
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
                        ui.label(child.namespace).classes("text-xs font-mono text-gray-500")
                    with ui.row().classes("gap-2 mt-1"):
                        ui.label(f"{len(child_hlrs)} HLRs").classes("text-xs text-gray-400")
                        ui.label(f"{len(child_nodes)} nodes").classes("text-xs text-gray-400")


def render_requirements(hlrs):
    """Render the requirements (HLRs) card (read-only)."""
    if not hlrs:
        return
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
                ui.badge(f"{llr_count} LLRs", color="grey").classes("text-xs")
            ui.separator()


# ---------------------------------------------------------------------------
# Page entry point
# ---------------------------------------------------------------------------


@ui.page("/component/{component_id}")
async def component_detail_page(component_id: str):
    """Component detail page — uses neomodel Component nodes directly."""
    apply_theme()
    page_layout("Component Detail")
    add_cytoscape_cdn()

    comp = await asyncio.to_thread(get_component, component_id)
    if not comp:
        ui.label("Component not found").classes("text-xl text-red-400 mt-4 px-2")
        return

    # -- Breadcrumb ----------------------------------------------------------
    crumbs = [("Components", "/components")]
    parents = comp.parent.all()
    if parents:
        crumbs.append((parents[0].name, f"/component/{parents[0].refid}"))
    crumbs.append((comp.name, None))
    breadcrumb(*crumbs)

    # -- Header --------------------------------------------------------------
    with ui.row().classes("w-full items-center justify-between px-2 mt-2 mb-4"):
        with ui.column().classes("gap-0"):
            ui.label(comp.name).classes("text-2xl font-bold")
            if comp.namespace:
                ui.label(comp.namespace).classes("text-sm font-mono text-gray-400")
        with ui.row().classes("gap-2"):
            ui.button(
                "Research Dependencies",
                icon="science",
                on_click=lambda: ui.navigate.to(
                    f"/component/{component_id}/dependencies/review"
                ),
            ).props("outline size=sm color=primary")
            ui.button(
                "All Components",
                icon="arrow_back",
                on_click=lambda: ui.navigate.to("/components"),
            ).props("flat size=sm")

    # -- Description ---------------------------------------------------------
    if comp.description:
        with ui.card().classes("w-full mx-2 mb-4"):
            ui.markdown(comp.description)

    # -- Two-column layout ---------------------------------------------------
    with ui.row().classes("w-full gap-4 px-2 items-start"):
        # Left column
        with ui.column().classes("flex-1 gap-4"):
            render_subcomponents(comp.children.all())
            render_requirements(comp.requirements.all())

            dep_panel = DependencyPanel(component_id)
            await dep_panel.render()

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

    # -- Graph wiring --------------------------------------------------------
    comp_config = GraphConfig(
        container_id="comp-cy-container",
        cy_var="_compCy",
        size="small",
        animate=False,
    )

    async def handle_node_dblclick(e):
        qn = e.args.get("qualified_name", "")
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
        pass  # graph data layer not yet implemented — container stays empty