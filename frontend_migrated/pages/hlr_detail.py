"""HLR detail page — detail view for a single high-level requirement.

Uses the HLR's ``refid`` (auto-generated hex UUID) as the URL key.
The route parameter is a string because refids are not integers.
"""

import asyncio
import logging

from nicegui import ui

from frontend_migrated.theme import (
    BACKGROUNDS,
    CLS_DIALOG_SM,
    CLS_DIALOG_MD,
    CLS_DIALOG_TITLE,
    CLS_DIALOG_ACTIONS,
    add_cytoscape_cdn,
    apply_theme,
)
from frontend_migrated.layout import page_layout
from frontend_migrated.widgets import (
    render_llr_table,
    section_header,
    breadcrumb,
    GraphConfig,
    render_cytoscape_graph,
)
from frontend_migrated.data.hlr import (
    fetch_hlr_detail,
    update_hlr,
    delete_hlr,
    decompose_hlr,
)
from frontend_migrated.data.llr import create_llr, update_llr, delete_llr
from frontend_migrated.data.components import fetch_components
from frontend_migrated.data.ontology import fetch_hlr_graph_data, resolve_node_id_by_qualified_name


def _short_refid(refid: str) -> str:
    """Return a shortened display form of a hex refid.

    Shows the first 8 characters followed by an ellipsis, e.g.
    ``'2c3463b2…'``.
    """
    if refid and len(refid) > 8:
        return f"{refid[:8]}…"
    return refid


@ui.page("/hlr/{hlr_id}")
async def hlr_detail_page(hlr_id: str):
    """HLR detail page showing description, LLR table, and design graph.

    ``hlr_id`` is the HLR's ``refid`` — a hex UUID string.
    """
    apply_theme()
    page_layout(f"HLR {_short_refid(hlr_id)}")

    # -- CDN scripts must load before any Cytoscape rendering --
    add_cytoscape_cdn()

    # Cytoscape graph config
    hlr_config = GraphConfig(
        container_id="hlr-cy-container",
        cy_var="_hlrCy",
        size="small",
        animate=False,
    )

    # ---------------------------------------------------------------
    # Refreshable content
    # ---------------------------------------------------------------

    @ui.refreshable
    async def content():
        hlr = await asyncio.to_thread(fetch_hlr_detail, hlr_id)
        if not hlr:
            ui.label("HLR not found").classes("text-xl text-red-400")
            return

        breadcrumb(("Requirements", "/"), (f"HLR {_short_refid(hlr_id)}", None))

        # Header
        with ui.row().classes("w-full items-center justify-between px-2 mt-2 mb-4"):
            with ui.row().classes("items-center gap-3"):
                ui.label(f"HLR {_short_refid(hlr_id)}").classes("text-2xl font-bold")
                if hlr.get("component"):
                    ui.badge(hlr["component"], color="grey")
            with ui.row().classes("gap-2"):
                ui.button("Back", icon="arrow_back", on_click=lambda: ui.navigate.to("/")).props(
                    "flat size=sm"
                )
                ui.button("Edit", icon="edit", on_click=lambda: show_edit_dialog(hlr)).props(
                    "color=primary size=sm"
                )
                ui.button(
                    "Delete",
                    icon="delete",
                    on_click=lambda: confirm_delete(hlr_id),
                ).props("color=negative size=sm")

        # Two-column layout
        with ui.row().classes("w-full gap-4 px-2 items-start"):
            with ui.column().classes("flex-1 gap-4"):
                with ui.card().classes("w-full"):
                    section_header("Description")
                    ui.label(hlr.get("description", "")).classes("text-sm")

                with ui.card().classes("w-full"):
                    with ui.row().classes("w-full items-center justify-between mb-2"):
                        section_header("Low-Level Requirements")
                        with ui.row().classes("gap-1"):
                            ui.button(
                                "Decompose",
                                icon="auto_awesome",
                                on_click=lambda: confirm_decompose(),
                            ).props("flat size=xs color=primary")
                            ui.button(
                                icon="add",
                                on_click=lambda: show_add_llr_dialog(),
                            ).props("flat round size=xs color=positive")
                    if hlr.get("llrs"):
                        render_llr_table(
                            hlr["llrs"], on_delete=confirm_delete_llr, on_edit=show_edit_llr_dialog
                        )
                    else:
                        ui.label("No low-level requirements yet.").classes("text-sm text-gray-500")

            with ui.column().classes("flex-1 gap-4"):
                with ui.card().classes("w-full"):
                    section_header("Design Graph")
                    cy = (
                        ui.element("div")
                        .style(
                            f"height: 400px; background: {BACKGROUNDS['base']}; border-radius: 8px;"
                        )
                        .classes("w-full")
                    )
                    cy._props["id"] = "hlr-cy-container"

                # Load graph data and render
                graph = await asyncio.to_thread(
                    fetch_hlr_graph_data, hlr_id, hlr.get("component_id"), requirement_tags="hlr"
                )
                if graph["nodes"]:
                    await render_cytoscape_graph(graph["nodes"] + graph["edges"], hlr_config)

    # ---------------------------------------------------------------
    # Edit HLR dialog
    # ---------------------------------------------------------------

    async def show_edit_dialog(hlr):
        components = await asyncio.to_thread(fetch_components)
        comp_map = {c.name: c for c in components}
        comp_names = ["(none)"] + [c.name for c in components]
        current_comp = hlr.get("component") or "(none)"

        with ui.dialog() as dialog, ui.card().classes(CLS_DIALOG_MD):
            ui.label(f"Edit HLR {_short_refid(hlr_id)}").classes(CLS_DIALOG_TITLE)
            desc_input = ui.textarea("Description", value=hlr.get("description", "")).classes("w-full")
            comp_select = ui.select(comp_names, value=current_comp, label="Component").classes(
                "w-full"
            )

            with ui.row().classes(CLS_DIALOG_ACTIONS):
                ui.button("Cancel", on_click=dialog.close).props("flat")

                async def do_update():
                    desc = desc_input.value.strip()
                    if not desc:
                        ui.notify("Description is required", type="warning")
                        return
                    comp_name = comp_select.value if comp_select.value != "(none)" else None
                    await asyncio.to_thread(update_hlr, hlr_id, desc, comp_name)
                    dialog.close()
                    ui.notify("HLR updated", type="positive")
                    content.refresh()

                ui.button("Save", on_click=do_update).props("color=positive")

        dialog.open()

    # ---------------------------------------------------------------
    # Delete HLR
    # ---------------------------------------------------------------

    async def confirm_delete(refid: str):
        with ui.dialog() as dialog, ui.card().classes(CLS_DIALOG_SM):
            ui.label(f"Delete HLR {_short_refid(refid)}?").classes("text-lg font-bold")
            ui.label("This will also delete all child LLRs and their verifications.").classes(
                "text-sm text-gray-400 mt-1"
            )
            with ui.row().classes(CLS_DIALOG_ACTIONS):
                ui.button("Cancel", on_click=dialog.close).props("flat")

                async def do_delete():
                    await asyncio.to_thread(delete_hlr, refid)
                    dialog.close()
                    ui.notify(f"Deleted HLR {_short_refid(refid)}", type="negative")
                    ui.navigate.to("/")

                ui.button("Delete", on_click=do_delete).props("color=negative")

        dialog.open()

    # ---------------------------------------------------------------
    # Decompose HLR
    # ---------------------------------------------------------------

    async def confirm_decompose():
        with ui.dialog() as dialog, ui.card().classes(CLS_DIALOG_MD):
            ui.label(f"Decompose HLR {_short_refid(hlr_id)}?").classes("text-lg font-bold")
            ui.label(
                "This will run the decomposition agent to generate low-level "
                "requirements and verification methods."
            ).classes("text-sm text-gray-400 mt-1")

            with ui.row().classes(CLS_DIALOG_ACTIONS):
                ui.button("Cancel", on_click=dialog.close).props("flat")

                async def do_decompose():
                    dialog.close()
                    ui.notify("Decomposing — this may take a moment…", type="info")
                    try:
                        result = await asyncio.to_thread(decompose_hlr, hlr_id)
                        llrs = result.get("llrs_created", 0)
                        vms = result.get("verifications_created", 0)
                        ui.notify(
                            f"Created {llrs} LLRs and {vms} verifications",
                            type="positive",
                        )
                        content.refresh()
                    except Exception as e:
                        import traceback
                        tb = traceback.format_exc()
                        log.error("Decomposition failed for HLR %s:\n%s", hlr_id, tb)
                        ui.notify(f"Decomposition failed: {e}", type="negative")

                ui.button("Decompose", on_click=do_decompose).props("color=primary")

        dialog.open()

    # ---------------------------------------------------------------
    # Add LLR
    # ---------------------------------------------------------------

    async def show_add_llr_dialog():
        with ui.dialog() as dialog, ui.card().classes(CLS_DIALOG_MD):
            ui.label(f"Add LLR to HLR {_short_refid(hlr_id)}").classes(CLS_DIALOG_TITLE)
            desc_input = ui.textarea("Description").classes("w-full")

            with ui.row().classes(CLS_DIALOG_ACTIONS):
                ui.button("Cancel", on_click=dialog.close).props("flat")

                async def do_create():
                    desc = desc_input.value.strip()
                    if not desc:
                        ui.notify("Description is required", type="warning")
                        return
                    new_refid = await asyncio.to_thread(create_llr, hlr_id, desc)
                    dialog.close()
                    ui.notify(f"Created LLR {_short_refid(new_refid)}", type="positive")
                    content.refresh()

                ui.button("Create", on_click=do_create).props("color=positive")

        dialog.open()

    # ---------------------------------------------------------------
    # Edit LLR description
    # ---------------------------------------------------------------

    async def show_edit_llr_dialog(llr_refid: str, current_description: str):
        with ui.dialog() as dialog, ui.card().classes(CLS_DIALOG_MD):
            ui.label(f"Edit LLR {_short_refid(llr_refid)}").classes(CLS_DIALOG_TITLE)
            desc_input = ui.textarea("Description", value=current_description or "").classes(
                "w-full"
            )

            with ui.row().classes(CLS_DIALOG_ACTIONS):
                ui.button("Cancel", on_click=dialog.close).props("flat")

                async def do_update():
                    desc = desc_input.value.strip()
                    if not desc:
                        ui.notify("Description is required", type="warning")
                        return
                    await asyncio.to_thread(update_llr, llr_refid, desc)
                    dialog.close()
                    ui.notify("LLR updated", type="positive")
                    content.refresh()

                ui.button("Save", on_click=do_update).props("color=positive")

        dialog.open()

    # ---------------------------------------------------------------
    # Delete LLR
    # ---------------------------------------------------------------

    async def confirm_delete_llr(llr_refid: str):
        with ui.dialog() as dialog, ui.card().classes(CLS_DIALOG_SM):
            ui.label(f"Delete LLR {_short_refid(llr_refid)}?").classes("text-lg font-bold")
            ui.label("This will also delete its verification methods.").classes(
                "text-sm text-gray-400 mt-1"
            )
            with ui.row().classes(CLS_DIALOG_ACTIONS):
                ui.button("Cancel", on_click=dialog.close).props("flat")

                async def do_delete():
                    await asyncio.to_thread(delete_llr, llr_refid)
                    dialog.close()
                    ui.notify(f"Deleted LLR {_short_refid(llr_refid)}", type="negative")
                    content.refresh()

                ui.button("Delete", on_click=do_delete).props("color=negative")

        dialog.open()

    # ---------------------------------------------------------------
    # Initial render
    # ---------------------------------------------------------------

    async def handle_node_dblclick(e):
        """On node double-click: navigate to the full node detail page."""
        args = e.args
        qn = args.get("qualified_name", "")
        if not qn:
            return
        node_id = await asyncio.to_thread(resolve_node_id_by_qualified_name, qn)
        if node_id:
            ui.navigate.to(f"/node/{node_id}")

    ui.on(hlr_config.dbltap_event, handle_node_dblclick)

    await content()