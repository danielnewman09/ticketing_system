"""Ontology node detail page."""

import asyncio
import json

from nicegui import ui

from frontend.theme import KIND_COLORS, apply_theme
from frontend.layout import page_layout
from frontend.data import fetch_node_detail_full


@ui.page("/node/{node_id}")
async def node_detail_page(node_id: int):
    apply_theme()
    page_layout("Node Detail")

    # Cytoscape CDN for the neighbourhood graph
    ui.add_head_html(
        '<script src="https://unpkg.com/cytoscape@3.30.4/dist/cytoscape.min.js"></script>'
        '<script src="https://unpkg.com/layout-base@2.0.1/layout-base.js"></script>'
        '<script src="https://unpkg.com/cose-base@2.2.0/cose-base.js"></script>'
        '<script src="https://unpkg.com/cytoscape-fcose@2.2.0/cytoscape-fcose.js"></script>'
    )
    kind_colors_js = json.dumps(KIND_COLORS)

    @ui.refreshable
    async def content():
        data = await asyncio.to_thread(fetch_node_detail_full, node_id)
        if not data:
            ui.label("Node not found").classes("text-xl text-red-400")
            return

        node = data["node"]
        neo4j = data["neo4j"]
        kind = node["kind"]
        color = KIND_COLORS.get(kind, "#666")

        # Breadcrumb
        with ui.row().classes("items-center gap-1 px-2 mt-4"):
            ui.link("Ontology", "/ontology").classes("text-blue-400 text-sm no-underline")
            ui.label("/").classes("text-gray-500 text-sm")
            ui.link("Graph", "/ontology/graph").classes("text-blue-400 text-sm no-underline")
            ui.label("/").classes("text-gray-500 text-sm")
            ui.label(node["name"]).classes("text-sm text-gray-300")

        # Header
        with ui.row().classes("w-full items-center justify-between px-2 mt-2 mb-4"):
            with ui.row().classes("items-center gap-3"):
                ui.html(
                    f'<div style="width:16px;height:16px;border-radius:50%;background:{color}"></div>'
                )
                ui.label(node["name"]).classes("text-2xl font-bold")
            ui.button(
                "Back to Graph",
                icon="arrow_back",
                on_click=lambda: ui.navigate.to("/ontology/graph"),
            ).props("flat size=sm")

        # Two-column layout
        with ui.row().classes("w-full gap-4 px-2 items-start"):
            # Left column — properties
            with ui.column().classes("flex-1 gap-4"):
                # Identity card
                with ui.card().classes("w-full"):
                    ui.label("Identity").classes(
                        "text-xs uppercase tracking-wider text-gray-400 mb-2"
                    )
                    _prop_row("Qualified Name", node["qualified_name"])
                    with ui.row().classes("gap-2 mt-2"):
                        ui.badge(kind, color="grey").style(
                            f"background:{color} !important"
                        )
                        if node["specialization"]:
                            ui.badge(node["specialization"], color="grey")
                        if node["visibility"]:
                            ui.badge(node["visibility"], color="grey")

                    if node["component"]:
                        _prop_row("Component", node["component"])

                # Description
                if node["description"]:
                    with ui.card().classes("w-full"):
                        ui.label("Description").classes(
                            "text-xs uppercase tracking-wider text-gray-400 mb-2"
                        )
                        ui.label(node["description"]).classes("text-sm")

                # Code details
                code_fields = [
                    ("Type Signature", node["type_signature"]),
                    ("Parameters", node["argsstring"]),
                    ("Definition", node["definition"]),
                    ("Source", _source_location(node["file_path"], node["line_number"])),
                ]
                visible_code = [(l, v) for l, v in code_fields if v]
                if visible_code:
                    with ui.card().classes("w-full"):
                        ui.label("Code Details").classes(
                            "text-xs uppercase tracking-wider text-gray-400 mb-2"
                        )
                        for label, value in visible_code:
                            _prop_row(label, value)

                # Flags
                flags = []
                for flag_name in ["is_static", "is_const", "is_virtual", "is_abstract", "is_final"]:
                    if node.get(flag_name):
                        flags.append(flag_name.replace("is_", ""))
                if flags:
                    with ui.card().classes("w-full"):
                        ui.label("Flags").classes(
                            "text-xs uppercase tracking-wider text-gray-400 mb-2"
                        )
                        with ui.row().classes("gap-2"):
                            for f in flags:
                                ui.badge(f, color="grey")

            # Right column — relationships + graph
            with ui.column().classes("flex-1 gap-4"):
                # Neighbourhood graph
                if neo4j:
                    with ui.card().classes("w-full"):
                        ui.label("Neighbourhood").classes(
                            "text-xs uppercase tracking-wider text-gray-400 mb-2"
                        )
                        cy = ui.element("div").style(
                            "height: 350px; background: #1a1a2e; border-radius: 8px;"
                        ).classes("w-full")
                        cy._props["id"] = "node-cy-container"

                    # Build neighbourhood graph from neo4j relationships
                    graph_nodes = []
                    graph_edges = []
                    seen = set()

                    # Center node
                    qn = node["qualified_name"]
                    center_id = f"center_{node_id}"
                    graph_nodes.append({
                        "data": {
                            "id": center_id,
                            "label": node["name"],
                            "kind": kind,
                            "layer": "design",
                            "qualified_name": qn,
                            "is_center": "true",
                        }
                    })
                    seen.add(center_id)

                    # Outgoing
                    for r in neo4j.get("outgoing", []):
                        tid = f"out_{r.get('target_qn', '')}"
                        if tid not in seen:
                            seen.add(tid)
                            graph_nodes.append({
                                "data": {
                                    "id": tid,
                                    "label": r.get("target_name") or r.get("target_qn", ""),
                                    "kind": "",
                                    "layer": "design",
                                    "qualified_name": r.get("target_qn", ""),
                                }
                            })
                        graph_edges.append({
                            "data": {
                                "id": f"e_out_{r['rel']}_{tid}",
                                "source": center_id,
                                "target": tid,
                                "label": r["rel"],
                            }
                        })

                    # Incoming
                    for r in neo4j.get("incoming", []):
                        sid = f"in_{r.get('source_qn', '')}"
                        if sid not in seen:
                            seen.add(sid)
                            graph_nodes.append({
                                "data": {
                                    "id": sid,
                                    "label": r.get("source_name") or r.get("source_qn", ""),
                                    "kind": "",
                                    "layer": "design",
                                    "qualified_name": r.get("source_qn", ""),
                                }
                            })
                        graph_edges.append({
                            "data": {
                                "id": f"e_in_{r['rel']}_{sid}",
                                "source": sid,
                                "target": center_id,
                                "label": r["rel"],
                            }
                        })

                    # Implemented-by
                    for impl in neo4j.get("implemented_by", []):
                        iid = f"impl_{impl.get('qualified_name', '')}"
                        if iid not in seen:
                            seen.add(iid)
                            graph_nodes.append({
                                "data": {
                                    "id": iid,
                                    "label": impl.get("name") or impl.get("qualified_name", ""),
                                    "kind": "",
                                    "layer": "as-built",
                                    "qualified_name": impl.get("qualified_name", ""),
                                }
                            })
                        graph_edges.append({
                            "data": {
                                "id": f"e_impl_{iid}",
                                "source": center_id,
                                "target": iid,
                                "label": "IMPLEMENTED_BY",
                            }
                        })

                    # Requirements
                    for req in neo4j.get("requirements", []):
                        rid = f"req_{req.get('name', '')}"
                        if rid not in seen:
                            seen.add(rid)
                            graph_nodes.append({
                                "data": {
                                    "id": rid,
                                    "label": req.get("name", ""),
                                    "kind": req["type"],
                                    "layer": "requirement",
                                    "qualified_name": "",
                                }
                            })
                        graph_edges.append({
                            "data": {
                                "id": f"e_req_{rid}",
                                "source": rid,
                                "target": center_id,
                                "label": req.get("relationship", "TRACES_TO"),
                            }
                        })

                    elements_json = json.dumps(graph_nodes + graph_edges)
                    if graph_nodes:
                        await ui.run_javascript(f"""
                            if (window._nodeCy) window._nodeCy.destroy();
                            const KIND_COLORS = {kind_colors_js};
                            const container = document.getElementById('node-cy-container');
                            if (!container) return;
                            window._nodeCy = cytoscape({{
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
                                    ...Object.entries(KIND_COLORS).map(([kind, color]) => ({{
                                        selector: 'node[kind="' + kind + '"][layer="design"]',
                                        style: {{ 'background-color': color }}
                                    }})),
                                    {{
                                        selector: 'node[is_center="true"]',
                                        style: {{
                                            'width': 45,
                                            'height': 45,
                                            'border-width': 3,
                                            'border-color': '#f1c40f',
                                            'border-style': 'solid',
                                        }}
                                    }},
                                    {{
                                        selector: 'node[layer="as-built"]',
                                        style: {{
                                            'label': 'data(label)',
                                            'background-color': '#555',
                                            'color': '#ccc',
                                            'text-valign': 'bottom',
                                            'text-halign': 'center',
                                            'font-size': '9px',
                                            'width': 28,
                                            'height': 28,
                                            'border-width': 2,
                                            'border-style': 'solid',
                                            'border-color': '#888',
                                            'opacity': 0.7,
                                            'text-wrap': 'ellipsis',
                                            'text-max-width': '70px',
                                            'text-margin-y': 3,
                                        }}
                                    }},
                                    {{
                                        selector: 'node[layer="requirement"]',
                                        style: {{
                                            'label': 'data(label)',
                                            'background-color': '#e67e22',
                                            'color': '#fff',
                                            'text-valign': 'bottom',
                                            'text-halign': 'center',
                                            'font-size': '9px',
                                            'shape': 'diamond',
                                            'width': 30,
                                            'height': 30,
                                            'border-width': 2,
                                            'border-color': '#d35400',
                                            'text-wrap': 'ellipsis',
                                            'text-max-width': '70px',
                                            'text-margin-y': 3,
                                        }}
                                    }},
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
                                        selector: 'edge[label="IMPLEMENTED_BY"]',
                                        style: {{
                                            'line-style': 'dotted',
                                            'line-color': '#3b82f6',
                                            'target-arrow-color': '#3b82f6',
                                        }}
                                    }},
                                    {{
                                        selector: 'edge[label="TRACES_TO"]',
                                        style: {{
                                            'line-style': 'dashed',
                                            'line-color': '#e67e22',
                                            'target-arrow-color': '#e67e22',
                                        }}
                                    }},
                                ],
                                layout: {{ name: 'fcose', animate: false }},
                            }});
                        """)

                # Relationships cards
                if neo4j:
                    if neo4j.get("outgoing"):
                        with ui.card().classes("w-full"):
                            ui.label("Outgoing Relationships").classes(
                                "text-xs uppercase tracking-wider text-gray-400 mb-2"
                            )
                            for r in neo4j["outgoing"]:
                                with ui.row().classes("items-center gap-2 py-1"):
                                    ui.badge(r["rel"], color="grey").classes("text-xs")
                                    ui.label(
                                        r.get("target_name") or r.get("target_qn", "")
                                    ).classes("text-sm")

                    if neo4j.get("incoming"):
                        with ui.card().classes("w-full"):
                            ui.label("Incoming Relationships").classes(
                                "text-xs uppercase tracking-wider text-gray-400 mb-2"
                            )
                            for r in neo4j["incoming"]:
                                with ui.row().classes("items-center gap-2 py-1"):
                                    ui.label(
                                        r.get("source_name") or r.get("source_qn", "")
                                    ).classes("text-sm")
                                    ui.badge(r["rel"], color="grey").classes("text-xs")

                    if neo4j.get("implemented_by"):
                        with ui.card().classes("w-full"):
                            ui.label("Implemented By").classes(
                                "text-xs uppercase tracking-wider text-gray-400 mb-2"
                            )
                            for impl in neo4j["implemented_by"]:
                                ui.label(
                                    impl.get("qualified_name", impl.get("name", ""))
                                ).classes("text-sm text-blue-300")

                    if neo4j.get("requirements"):
                        with ui.card().classes("w-full"):
                            ui.label("Traced Requirements").classes(
                                "text-xs uppercase tracking-wider text-gray-400 mb-2"
                            )
                            for req in neo4j["requirements"]:
                                with ui.row().classes("items-center gap-2 py-1"):
                                    req_type = req["type"]
                                    ui.badge(
                                        req_type,
                                        color="orange" if req_type == "HLR" else "amber",
                                    ).classes("text-xs")
                                    ui.label(req.get("name", "")).classes("text-sm")

    await content()


def _prop_row(label: str, value: str):
    """Render a label: value property row."""
    with ui.row().classes("items-start gap-2 py-1"):
        ui.label(label).classes("text-xs text-gray-400 min-w-[120px]")
        ui.label(value).classes("text-sm break-all")


def _source_location(file_path: str, line_number: int | None) -> str:
    """Format source location string."""
    if not file_path:
        return ""
    if line_number:
        return f"{file_path}:{line_number}"
    return file_path
