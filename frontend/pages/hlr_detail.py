"""HLR detail page."""

import asyncio
import json

from nicegui import ui

from frontend.theme import (
    BACKGROUNDS,
    CLS_DIALOG_SM,
    CLS_DIALOG_MD,
    CLS_DIALOG_TITLE,
    CLS_DIALOG_ACTIONS,
    KIND_COLORS_JS,
    add_cytoscape_cdn,
    cytoscape_base_styles,
    apply_theme,
)
from frontend.layout import page_layout
from frontend.widgets import render_llr_table, section_header, breadcrumb
from frontend.data.hlr import (
    fetch_hlr_detail,
    update_hlr,
    delete_hlr,
    decompose_hlr,
    design_single_hlr,
    delete_hlr_llrs,
)
from frontend.data.llr import create_llr, update_llr, delete_llr
from frontend.data.components import fetch_components_options
from frontend.data.ontology import fetch_hlr_graph_data


@ui.page("/hlr/{hlr_id}")
async def hlr_detail_page(hlr_id: int):
    apply_theme()
    page_layout(f"HLR {hlr_id}")

    add_cytoscape_cdn()
    base_styles = cytoscape_base_styles(size="small")

    # ---------------------------------------------------------------
    # Refreshable content
    # ---------------------------------------------------------------

    @ui.refreshable
    async def content():
        hlr = await asyncio.to_thread(fetch_hlr_detail, hlr_id)
        if not hlr:
            ui.label("HLR not found").classes("text-xl text-red-400")
            return

        breadcrumb(("Requirements", "/"), (f"HLR {hlr['id']}", None))

        # Header
        with ui.row().classes("w-full items-center justify-between px-2 mt-2 mb-4"):
            with ui.row().classes("items-center gap-3"):
                ui.label(f"HLR {hlr['id']}").classes("text-2xl font-bold")
                if hlr["component"]:
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
                    on_click=lambda: confirm_delete(hlr["id"]),
                ).props("color=negative size=sm")

        # Two-column layout
        with ui.row().classes("w-full gap-4 px-2 items-start"):
            with ui.column().classes("flex-1 gap-4"):
                with ui.card().classes("w-full"):
                    section_header("Description")
                    ui.label(hlr["description"]).classes("text-sm")

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
                                "Design",
                                icon="architecture",
                                on_click=lambda: confirm_design(),
                            ).props("flat size=xs color=secondary")
                            ui.button(
                                icon="add",
                                on_click=lambda: show_add_llr_dialog(),
                            ).props("flat round size=xs color=positive")
                            if hlr["llrs"]:
                                ui.button(
                                    icon="delete_sweep",
                                    on_click=lambda: confirm_wipe_llrs(),
                                ).props("flat round size=xs color=negative")
                    if hlr["llrs"]:
                        render_llr_table(hlr["llrs"], on_delete=confirm_delete_llr, on_edit=show_edit_llr_dialog)
                    else:
                        ui.label("No low-level requirements yet.").classes("text-sm text-gray-500")

            with ui.column().classes("flex-1 gap-4"):
                with ui.card().classes("w-full"):
                    section_header("Design Graph")
                    cy = ui.element("div").style(
                        f"height: 400px; background: {BACKGROUNDS['base']}; border-radius: 8px;"
                    ).classes("w-full")
                    cy._props["id"] = "hlr-cy-container"

                # Load graph data and render
                graph = await asyncio.to_thread(
                    fetch_hlr_graph_data, hlr_id, hlr["component_id"]
                )
                elements_json = json.dumps(graph["nodes"] + graph["edges"])
                if graph["nodes"]:
                    await ui.run_javascript(f"""
                        if (window._hlrCy) window._hlrCy.destroy();
                        const KIND_COLORS = {KIND_COLORS_JS};
                        const container = document.getElementById('hlr-cy-container');
                        if (!container) return;
                        window._hlrCy = cytoscape({{
                            container: container,
                            elements: {elements_json},
                            style: {base_styles},
                            layout: {{ name: 'fcose', animate: false }},
                        }});
                    """)

    # ---------------------------------------------------------------
    # Edit HLR dialog
    # ---------------------------------------------------------------

    async def show_edit_dialog(hlr):
        components = await asyncio.to_thread(fetch_components_options)
        comp_map = {c["name"]: c["id"] for c in components}
        comp_names = ["(none)"] + [c["name"] for c in components]
        current_comp = hlr["component"] if hlr["component"] else "(none)"

        with ui.dialog() as dialog, ui.card().classes(CLS_DIALOG_MD):
            ui.label(f"Edit HLR {hlr['id']}").classes(CLS_DIALOG_TITLE)
            desc_input = ui.textarea("Description", value=hlr["description"]).classes("w-full")
            comp_select = ui.select(comp_names, value=current_comp, label="Component").classes("w-full")

            with ui.row().classes(CLS_DIALOG_ACTIONS):
                ui.button("Cancel", on_click=dialog.close).props("flat")

                async def do_update():
                    desc = desc_input.value.strip()
                    if not desc:
                        ui.notify("Description is required", type="warning")
                        return
                    comp_id = comp_map.get(comp_select.value)
                    await asyncio.to_thread(update_hlr, hlr["id"], desc, comp_id)
                    dialog.close()
                    ui.notify("HLR updated", type="positive")
                    content.refresh()

                ui.button("Save", on_click=do_update).props("color=positive")

        dialog.open()

    # ---------------------------------------------------------------
    # Delete HLR
    # ---------------------------------------------------------------

    async def confirm_delete(hid: int):
        with ui.dialog() as dialog, ui.card().classes(CLS_DIALOG_SM):
            ui.label(f"Delete HLR {hid}?").classes("text-lg font-bold")
            ui.label("This will also delete all child LLRs and their verifications.").classes(
                "text-sm text-gray-400 mt-1"
            )
            with ui.row().classes(CLS_DIALOG_ACTIONS):
                ui.button("Cancel", on_click=dialog.close).props("flat")

                async def do_delete():
                    await asyncio.to_thread(delete_hlr, hid)
                    dialog.close()
                    ui.notify(f"Deleted HLR {hid}", type="negative")
                    ui.navigate.to("/")

                ui.button("Delete", on_click=do_delete).props("color=negative")

        dialog.open()

    # ---------------------------------------------------------------
    # Decompose HLR
    # ---------------------------------------------------------------

    async def confirm_decompose():
        with ui.dialog() as dialog, ui.card().classes(CLS_DIALOG_MD):
            ui.label(f"Decompose HLR {hlr_id}?").classes("text-lg font-bold")
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
                        ui.notify(
                            f"Created {result['llrs_created']} LLRs and "
                            f"{result['verifications_created']} verifications",
                            type="positive",
                        )
                        content.refresh()
                    except Exception as e:
                        ui.notify(f"Decomposition failed: {e}", type="negative")

                ui.button("Decompose", on_click=do_decompose).props("color=primary")

        dialog.open()

    # ---------------------------------------------------------------
    # Design HLR
    # ---------------------------------------------------------------

    async def confirm_design():
        with ui.dialog() as dialog, ui.card().classes(CLS_DIALOG_MD):
            ui.label(f"Design HLR {hlr_id}?").classes("text-lg font-bold")
            ui.label(
                "This will run the design agent to generate an OO design "
                "and ontology graph from the requirements."
            ).classes("text-sm text-gray-400 mt-1")

            with ui.row().classes(CLS_DIALOG_ACTIONS):
                ui.button("Cancel", on_click=dialog.close).props("flat")

                async def do_design():
                    dialog.close()
                    ui.notify("Designing — this may take a moment…", type="info")
                    try:
                        result = await asyncio.to_thread(design_single_hlr, hlr_id)
                        ui.notify(
                            f"Created {result['nodes_created']} nodes, "
                            f"{result['triples_created']} triples, "
                            f"{result['links_applied']} requirement links",
                            type="positive",
                        )
                        content.refresh()
                    except Exception as e:
                        ui.notify(f"Design failed: {e}", type="negative")

                ui.button("Design", on_click=do_design).props("color=secondary")

        dialog.open()

    # ---------------------------------------------------------------
    # Add LLR
    # ---------------------------------------------------------------

    async def show_add_llr_dialog():
        with ui.dialog() as dialog, ui.card().classes(CLS_DIALOG_MD):
            ui.label(f"Add LLR to HLR {hlr_id}").classes(CLS_DIALOG_TITLE)
            desc_input = ui.textarea("Description").classes("w-full")

            with ui.row().classes(CLS_DIALOG_ACTIONS):
                ui.button("Cancel", on_click=dialog.close).props("flat")

                async def do_create():
                    desc = desc_input.value.strip()
                    if not desc:
                        ui.notify("Description is required", type="warning")
                        return
                    new_id = await asyncio.to_thread(create_llr, hlr_id, desc)
                    dialog.close()
                    ui.notify(f"Created LLR {new_id}", type="positive")
                    content.refresh()

                ui.button("Create", on_click=do_create).props("color=positive")

        dialog.open()

    # ---------------------------------------------------------------
    # Edit LLR description
    # ---------------------------------------------------------------

    async def show_edit_llr_dialog(llr_id: int, current_description: str):
        with ui.dialog() as dialog, ui.card().classes(CLS_DIALOG_MD):
            ui.label(f"Edit LLR {llr_id}").classes(CLS_DIALOG_TITLE)
            desc_input = ui.textarea("Description", value=current_description or "").classes("w-full")

            with ui.row().classes(CLS_DIALOG_ACTIONS):
                ui.button("Cancel", on_click=dialog.close).props("flat")

                async def do_update():
                    desc = desc_input.value.strip()
                    if not desc:
                        ui.notify("Description is required", type="warning")
                        return
                    await asyncio.to_thread(update_llr, llr_id, desc)
                    dialog.close()
                    ui.notify("LLR updated", type="positive")
                    content.refresh()

                ui.button("Save", on_click=do_update).props("color=positive")

        dialog.open()

    # ---------------------------------------------------------------
    # Delete LLR
    # ---------------------------------------------------------------

    async def confirm_delete_llr(llr_id: int):
        with ui.dialog() as dialog, ui.card().classes(CLS_DIALOG_SM):
            ui.label(f"Delete LLR {llr_id}?").classes("text-lg font-bold")
            ui.label("This will also delete its verification methods.").classes(
                "text-sm text-gray-400 mt-1"
            )
            with ui.row().classes(CLS_DIALOG_ACTIONS):
                ui.button("Cancel", on_click=dialog.close).props("flat")

                async def do_delete():
                    await asyncio.to_thread(delete_llr, llr_id)
                    dialog.close()
                    ui.notify(f"Deleted LLR {llr_id}", type="negative")
                    content.refresh()

                ui.button("Delete", on_click=do_delete).props("color=negative")

        dialog.open()

    # ---------------------------------------------------------------
    # Wipe all LLRs
    # ---------------------------------------------------------------

    async def confirm_wipe_llrs():
        with ui.dialog() as dialog, ui.card().classes(CLS_DIALOG_MD):
            ui.label(f"Wipe all LLRs from HLR {hlr_id}?").classes("text-lg font-bold")
            ui.label(
                "This will permanently delete all low-level requirements "
                "and their verification methods."
            ).classes("text-sm text-gray-400 mt-1")
            with ui.row().classes(CLS_DIALOG_ACTIONS):
                ui.button("Cancel", on_click=dialog.close).props("flat")

                async def do_wipe():
                    count = await asyncio.to_thread(delete_hlr_llrs, hlr_id)
                    dialog.close()
                    ui.notify(f"Deleted {count} LLRs", type="negative")
                    content.refresh()

                ui.button("Wipe All", on_click=do_wipe).props("color=negative")

        dialog.open()

    # ---------------------------------------------------------------
    # Initial render
    # ---------------------------------------------------------------

    await content()
