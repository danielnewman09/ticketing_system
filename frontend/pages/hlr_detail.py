"""HLR detail page."""

import asyncio
import json

from nicegui import ui

from frontend.theme import KIND_COLORS, apply_theme
from frontend.layout import page_layout
from frontend.widgets import render_llr_table
from frontend.data import (
    fetch_hlr_detail,
    fetch_hlr_graph_data,
    fetch_components_options,
    update_hlr,
    delete_hlr,
    create_llr,
    update_llr,
    delete_llr,
    decompose_hlr,
)


@ui.page("/hlr/{hlr_id}")
async def hlr_detail_page(hlr_id: int):
    apply_theme()
    page_layout(f"HLR {hlr_id}")

    # Cytoscape CDN
    ui.add_head_html(
        '<script src="https://unpkg.com/cytoscape@3.30.4/dist/cytoscape.min.js"></script>'
        '<script src="https://unpkg.com/layout-base@2.0.1/layout-base.js"></script>'
        '<script src="https://unpkg.com/cose-base@2.2.0/cose-base.js"></script>'
        '<script src="https://unpkg.com/cytoscape-fcose@2.2.0/cytoscape-fcose.js"></script>'
    )
    kind_colors_js = json.dumps(KIND_COLORS)

    # ---------------------------------------------------------------
    # Refreshable content
    # ---------------------------------------------------------------

    @ui.refreshable
    async def content():
        hlr = await asyncio.to_thread(fetch_hlr_detail, hlr_id)
        if not hlr:
            ui.label("HLR not found").classes("text-xl text-red-400")
            return

        # Breadcrumb
        with ui.row().classes("items-center gap-1 px-2 mt-4"):
            ui.link("Requirements", "/").classes("text-blue-400 text-sm no-underline")
            ui.label("/").classes("text-gray-500 text-sm")
            ui.label(f"HLR {hlr['id']}").classes("text-sm text-gray-300")

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
                    ui.label("Description").classes("text-xs uppercase tracking-wider text-gray-400 mb-2")
                    ui.label(hlr["description"]).classes("text-sm")

                with ui.card().classes("w-full"):
                    with ui.row().classes("w-full items-center justify-between mb-2"):
                        ui.label("Low-Level Requirements").classes(
                            "text-xs uppercase tracking-wider text-gray-400"
                        )
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
                    if hlr["llrs"]:
                        render_llr_table(hlr["llrs"], on_delete=confirm_delete_llr, on_edit=show_edit_llr_dialog)
                    else:
                        ui.label("No low-level requirements yet.").classes("text-sm text-gray-500")

            with ui.column().classes("flex-1 gap-4"):
                with ui.card().classes("w-full"):
                    ui.label("Design Graph").classes(
                        "text-xs uppercase tracking-wider text-gray-400 mb-2"
                    )
                    cy = ui.element("div").style(
                        "height: 400px; background: #1a1a2e; border-radius: 8px;"
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
                        const KIND_COLORS = {kind_colors_js};
                        const container = document.getElementById('hlr-cy-container');
                        if (!container) return;
                        window._hlrCy = cytoscape({{
                            container: container,
                            elements: {elements_json},
                            style: [
                                {{
                                    selector: 'node[layer="design"]',
                                    style: {{
                                        'label': 'data(label)',
                                        'background-color': '#666',
                                        'color': '#fff',
                                        'text-valign': 'bottom',
                                        'text-halign': 'center',
                                        'font-size': '9px',
                                        'width': 30,
                                        'height': 30,
                                        'border-width': 2,
                                        'border-style': 'dashed',
                                        'border-color': '#aaa',
                                        'text-wrap': 'ellipsis',
                                        'text-max-width': '70px',
                                        'text-margin-y': 3,
                                    }}
                                }},
                                {{
                                    selector: 'node[has_members="true"]',
                                    style: {{
                                        'shape': 'roundrectangle',
                                        'text-valign': 'center',
                                        'text-halign': 'center',
                                        'text-wrap': 'wrap',
                                        'text-max-width': '200px',
                                        'font-size': '8px',
                                        'font-family': 'monospace',
                                        'text-justification': 'left',
                                        'width': 'label',
                                        'height': 'label',
                                        'padding': '10px',
                                        'border-style': 'solid',
                                        'border-width': 2,
                                        'text-margin-y': 0,
                                    }}
                                }},
                                {{
                                    selector: 'node[is_namespace="true"]',
                                    style: {{
                                        'shape': 'roundrectangle',
                                        'background-color': '#1a1a2e',
                                        'background-opacity': 0.6,
                                        'border-width': 2,
                                        'border-style': 'dashed',
                                        'border-color': '#1abc9c',
                                        'label': 'data(label)',
                                        'color': '#1abc9c',
                                        'text-valign': 'top',
                                        'text-halign': 'center',
                                        'font-size': '10px',
                                        'font-weight': 'bold',
                                        'padding': '16px',
                                        'text-margin-y': -4,
                                    }}
                                }},
                                ...Object.entries(KIND_COLORS).map(([kind, color]) => ({{
                                    selector: 'node[kind="' + kind + '"][layer="design"]',
                                    style: {{ 'background-color': color }}
                                }})),
                                {{
                                    selector: 'edge',
                                    style: {{
                                        'label': 'data(label)',
                                        'width': 1.5,
                                        'line-color': '#555',
                                        'target-arrow-color': '#555',
                                        'target-arrow-shape': 'triangle',
                                        'curve-style': 'bezier',
                                        'font-size': '7px',
                                        'color': '#999',
                                        'text-rotation': 'autorotate',
                                    }}
                                }},
                                {{
                                    selector: 'edge[label="INHERITS_FROM"]',
                                    style: {{
                                        'line-style': 'solid',
                                        'line-color': '#9b59b6',
                                        'target-arrow-color': '#9b59b6',
                                        'target-arrow-shape': 'triangle-tee',
                                    }}
                                }},
                                {{
                                    selector: ':selected',
                                    style: {{
                                        'border-width': 4,
                                        'border-color': '#f1c40f',
                                    }}
                                }},
                            ],
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

        with ui.dialog() as dialog, ui.card().classes("w-96"):
            ui.label(f"Edit HLR {hlr['id']}").classes("text-lg font-bold mb-2")
            desc_input = ui.textarea("Description", value=hlr["description"]).classes("w-full")
            comp_select = ui.select(comp_names, value=current_comp, label="Component").classes("w-full")

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
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
        with ui.dialog() as dialog, ui.card().classes("w-80"):
            ui.label(f"Delete HLR {hid}?").classes("text-lg font-bold")
            ui.label("This will also delete all child LLRs and their verifications.").classes(
                "text-sm text-gray-400 mt-1"
            )
            with ui.row().classes("w-full justify-end gap-2 mt-4"):
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
        with ui.dialog() as dialog, ui.card().classes("w-96"):
            ui.label(f"Decompose HLR {hlr_id}?").classes("text-lg font-bold")
            ui.label(
                "This will run the decomposition agent to generate low-level "
                "requirements and verification methods."
            ).classes("text-sm text-gray-400 mt-1")

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
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
    # Add LLR
    # ---------------------------------------------------------------

    async def show_add_llr_dialog():
        with ui.dialog() as dialog, ui.card().classes("w-96"):
            ui.label(f"Add LLR to HLR {hlr_id}").classes("text-lg font-bold mb-2")
            desc_input = ui.textarea("Description").classes("w-full")

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
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
        with ui.dialog() as dialog, ui.card().classes("w-96"):
            ui.label(f"Edit LLR {llr_id}").classes("text-lg font-bold mb-2")
            desc_input = ui.textarea("Description", value=current_description or "").classes("w-full")

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
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
        with ui.dialog() as dialog, ui.card().classes("w-80"):
            ui.label(f"Delete LLR {llr_id}?").classes("text-lg font-bold")
            ui.label("This will also delete its verification methods.").classes(
                "text-sm text-gray-400 mt-1"
            )
            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button("Cancel", on_click=dialog.close).props("flat")

                async def do_delete():
                    await asyncio.to_thread(delete_llr, llr_id)
                    dialog.close()
                    ui.notify(f"Deleted LLR {llr_id}", type="negative")
                    content.refresh()

                ui.button("Delete", on_click=do_delete).props("color=negative")

        dialog.open()

    # ---------------------------------------------------------------
    # Initial render
    # ---------------------------------------------------------------

    await content()
