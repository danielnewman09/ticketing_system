"""Component detail page."""

import asyncio
import json

from nicegui import ui

from frontend.theme import KIND_COLORS, apply_theme
from frontend.layout import page_layout
from frontend.data import (
    fetch_component_detail,
    fetch_ontology_graph_data,
    ensure_component_language,
    create_dependency_manager,
    add_dependency,
    delete_dependency,
    delete_dependency_manager,
)


@ui.page("/component/{component_id}")
async def component_detail_page(component_id: int):
    apply_theme()
    page_layout("Component Detail")

    # Cytoscape CDN
    ui.add_head_html(
        '<script src="https://unpkg.com/cytoscape@3.30.4/dist/cytoscape.min.js"></script>'
        '<script src="https://unpkg.com/layout-base@2.0.1/layout-base.js"></script>'
        '<script src="https://unpkg.com/cose-base@2.2.0/cose-base.js"></script>'
        '<script src="https://unpkg.com/cytoscape-fcose@2.2.0/cytoscape-fcose.js"></script>'
    )
    kind_colors_js = json.dumps(KIND_COLORS)

    data_ref = {"data": await asyncio.to_thread(fetch_component_detail, component_id)}

    async def refresh_data():
        data_ref["data"] = await asyncio.to_thread(fetch_component_detail, component_id)

    data = data_ref["data"]
    if not data:
        ui.label("Component not found").classes("text-xl text-red-400 mt-4 px-2")
        return

    # Breadcrumb
    with ui.row().classes("items-center gap-1 px-2 mt-4"):
        ui.link("Components", "/components").classes("text-blue-400 text-sm no-underline")
        if data["parent"]:
            ui.label("/").classes("text-gray-500 text-sm")
            ui.link(
                data["parent"]["name"],
                f"/component/{data['parent']['id']}",
            ).classes("text-blue-400 text-sm no-underline")
        ui.label("/").classes("text-gray-500 text-sm")
        ui.label(data["name"]).classes("text-sm text-gray-300")

    # Header
    with ui.row().classes("w-full items-center justify-between px-2 mt-2 mb-4"):
        with ui.column().classes("gap-0"):
            ui.label(data["name"]).classes("text-2xl font-bold")
            if data["namespace"]:
                ui.label(data["namespace"]).classes("text-sm font-mono text-gray-400")
        ui.button(
            "All Components", icon="arrow_back",
            on_click=lambda: ui.navigate.to("/components"),
        ).props("flat size=sm")

    # Description
    if data["description"]:
        with ui.card().classes("w-full mx-2 mb-4"):
            ui.markdown(data["description"])

    # Two-column layout
    with ui.row().classes("w-full gap-4 px-2 items-start"):
        # Left column
        with ui.column().classes("flex-1 gap-4"):
            # Sub-components
            if data["children"]:
                with ui.card().classes("w-full"):
                    ui.label("Sub-Components").classes(
                        "text-xs uppercase tracking-wider text-gray-400 mb-2"
                    )
                    with ui.row().classes("gap-3 flex-wrap"):
                        for child in data["children"]:
                            with ui.card().classes("w-56 cursor-pointer").on(
                                "click",
                                lambda _, c=child: ui.navigate.to(f"/component/{c['id']}"),
                            ):
                                ui.label(child["name"]).classes("font-semibold")
                                if child.get("namespace"):
                                    ui.label(child["namespace"]).classes(
                                        "text-xs font-mono text-gray-500"
                                    )
                                with ui.row().classes("gap-2 mt-1"):
                                    ui.label(f"{child['hlr_count']} HLRs").classes(
                                        "text-xs text-gray-400"
                                    )
                                    ui.label(f"{child['node_count']} nodes").classes(
                                        "text-xs text-gray-400"
                                    )

            # Requirements (HLRs)
            if data["hlrs"]:
                with ui.card().classes("w-full"):
                    ui.label("Requirements").classes(
                        "text-xs uppercase tracking-wider text-gray-400 mb-2"
                    )
                    for hlr in data["hlrs"]:
                        with ui.row().classes("items-start gap-2 py-2 w-full"):
                            ui.link(
                                f"HLR {hlr['id']}",
                                f"/hlr/{hlr['id']}",
                            ).classes("text-blue-400 text-sm no-underline min-w-[60px]")
                            ui.label(hlr["description"]).classes("text-sm flex-1")
                            ui.badge(
                                f"{hlr['llr_count']} LLRs", color="grey",
                            ).classes("text-xs")
                        ui.separator()

            # --- Dependency manager handlers ---

            async def show_setup_dialog():
                """Setup language + dependency manager in one dialog."""
                with ui.dialog() as dialog, ui.card().classes("w-96"):
                    ui.label("Setup Dependencies").classes("text-lg font-bold mb-2")
                    lang_input = ui.input("Language (e.g. C++, Python)").classes("w-full")
                    lang_ver = ui.input("Language version (optional)").classes("w-full")
                    ui.separator().classes("my-2")
                    dm_name = ui.input("Dependency manager (e.g. conan, pip, vcpkg)").classes("w-full")
                    dm_manifest = ui.input("Manifest file (e.g. conanfile.txt)").classes("w-full")

                    with ui.row().classes("w-full justify-end gap-2 mt-4"):
                        ui.button("Cancel", on_click=dialog.close).props("flat")

                        async def do_setup():
                            lang = lang_input.value.strip()
                            name = dm_name.value.strip()
                            manifest = dm_manifest.value.strip()
                            if not lang or not name or not manifest:
                                ui.notify("Language, manager name, and manifest are required", type="warning")
                                return
                            lang_id = await asyncio.to_thread(
                                ensure_component_language,
                                component_id, lang, lang_ver.value.strip(),
                            )
                            await asyncio.to_thread(
                                create_dependency_manager,
                                lang_id, name, manifest,
                            )
                            dialog.close()
                            ui.notify(f"Created {name} for {lang}", type="positive")
                            await refresh_data()
                            await dep_section.refresh()

                        ui.button("Save", on_click=do_setup).props("color=positive")
                dialog.open()

            async def do_add_dep(manager_id, name_input, ver_input, dev_checkbox):
                name = name_input.value.strip()
                if not name:
                    ui.notify("Package name is required", type="warning")
                    return
                await asyncio.to_thread(
                    add_dependency, manager_id, name, ver_input.value.strip(), dev_checkbox.value,
                )
                ui.notify(f"Added {name}", type="positive")
                name_input.value = ""
                ver_input.value = ""
                dev_checkbox.value = False
                await refresh_data()
                await dep_section.refresh()

            async def do_delete_dep(dep_id):
                await asyncio.to_thread(delete_dependency, dep_id)
                ui.notify("Dependency removed", type="info")
                await refresh_data()
                await dep_section.refresh()

            # Dependency Manager (one per component)
            @ui.refreshable
            async def dep_section():
                d = data_ref["data"]
                env = d["environment"]
                dm = None
                if env and env["dependency_managers"]:
                    dm = env["dependency_managers"][0]

                with ui.card().classes("w-full"):
                    ui.label("Dependency Manager").classes(
                        "text-xs uppercase tracking-wider text-gray-400 mb-2"
                    )

                    if not dm:
                        ui.label(
                            "No dependency manager configured."
                        ).classes("text-sm text-gray-500 mb-2")
                        ui.button(
                            "Setup Dependencies", icon="add",
                            on_click=show_setup_dialog,
                        ).props("flat size=sm color=primary")
                    else:
                        # Manager header
                        with ui.row().classes("items-center gap-2 mb-3"):
                            ui.label(dm["name"]).classes("text-sm font-semibold")
                            ui.label(dm["manifest_file"]).classes(
                                "text-xs text-gray-500 font-mono"
                            )
                            if env:
                                ui.badge(env["language"], color="grey").classes("text-xs")

                        # Dependencies list
                        for dep in dm["dependencies"]:
                            with ui.row().classes("items-center gap-2 py-1 w-full"):
                                ui.label(dep["name"]).classes("text-sm font-mono flex-1")
                                ui.label(dep["version"] or "-").classes(
                                    "text-xs text-gray-400 font-mono"
                                )
                                if dep["is_dev"]:
                                    ui.badge("dev", color="warning").classes("text-xs")
                                ui.button(
                                    icon="close",
                                    on_click=lambda _, did=dep["id"]: do_delete_dep(did),
                                ).props("flat round size=xs color=negative")

                        # Add dependency row
                        ui.separator().classes("my-2")
                        with ui.row().classes("items-end gap-2 w-full"):
                            dep_name = ui.input("Package").classes("flex-1").props("dense")
                            dep_ver = ui.input("Version").classes("w-24").props("dense")
                            dep_dev = ui.checkbox("Dev").classes("text-xs")
                            ui.button(
                                "Add",
                                on_click=lambda _, mid=dm["id"], n=dep_name, v=dep_ver, dv=dep_dev: do_add_dep(mid, n, v, dv),
                            ).props("flat size=xs color=positive")

            await dep_section()

        # Right column — ontology graph
        with ui.column().classes("flex-1 gap-4"):
            with ui.card().classes("w-full"):
                ui.label("Design Graph").classes(
                    "text-xs uppercase tracking-wider text-gray-400 mb-2"
                )
                cy = ui.element("div").style(
                    "height: calc(100vh - 280px); min-height: 400px; "
                    "background: #1a1a2e; border-radius: 8px;"
                ).classes("w-full")
                cy._props["id"] = "comp-cy-container"

            # Load graph filtered to this component
            graph = await asyncio.to_thread(
                fetch_ontology_graph_data, component_id=data["id"],
            )
            elements_json = json.dumps(graph["nodes"] + graph["edges"])
            if graph["nodes"]:
                await ui.run_javascript(f"""
                    if (window._compCy) window._compCy.destroy();
                    const KIND_COLORS = {kind_colors_js};
                    const container = document.getElementById('comp-cy-container');
                    if (!container) return;
                    window._compCy = cytoscape({{
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


def _render_table(headers: list[str], rows: list[list[str]]):
    """Render a simple table with headers and rows."""
    columns = [{"name": h, "label": h, "field": h, "align": "left"} for h in headers]
    table_rows = [{h: v for h, v in zip(headers, row)} for row in rows]
    ui.table(columns=columns, rows=table_rows).classes("w-full").props("dense flat")
