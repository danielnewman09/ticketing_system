"""Ontology node detail page."""

import asyncio
import json

from nicegui import ui

from frontend.theme import KIND_COLORS, apply_theme
from frontend.layout import page_layout
from frontend.data import fetch_node_detail_full, update_member_type


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

                # Members documentation (Doxygen-style)
                if neo4j:
                    all_members = neo4j.get("members", [])
                    cb_members = neo4j.get("codebase_members", [])
                    if cb_members and not all_members:
                        all_members = cb_members
                    elif cb_members:
                        cb_by_name = {m["name"]: m for m in cb_members}
                        for m in all_members:
                            cb = cb_by_name.get(m["name"])
                            if cb:
                                if not m["type_signature"] and cb["type_signature"]:
                                    m["type_signature"] = cb["type_signature"]
                                if not m["argsstring"] and cb["argsstring"]:
                                    m["argsstring"] = cb["argsstring"]
                                if not m["description"] and cb["description"]:
                                    m["description"] = cb["description"]
                    if all_members:
                        _render_members_card(
                            all_members, node["kind"], content,
                        )

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

                # Relationships
                if neo4j:
                    # Relationships (non-COMPOSES)
                    if neo4j.get("outgoing"):
                        with ui.card().classes("w-full"):
                            ui.label("Relationships").classes(
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
                            ui.label("Incoming").classes(
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


def _render_members_card(members: list[dict], owner_kind: str, content_refreshable):
    """Render a Doxygen-style members documentation card.

    Groups members by visibility (public, protected, private), then by kind
    (attributes, methods). Each member shows an editable type field.
    """
    _VIS_ORDER = {"public": 0, "protected": 1, "private": 2, "": 3}
    _VIS_LABELS = {"public": "Public", "protected": "Protected", "private": "Private", "": "Unspecified"}
    _KIND_MAP = {"variable": "attribute", "function": "method"}

    # Group: visibility → kind → [members]
    grouped: dict[str, dict[str, list]] = {}
    for m in members:
        vis = m.get("visibility") or ""
        kind = _KIND_MAP.get(m["kind"], m["kind"])
        grouped.setdefault(vis, {}).setdefault(kind, []).append(m)

    with ui.card().classes("w-full"):
        ui.label("Member Documentation").classes(
            "text-xs uppercase tracking-wider text-gray-400 mb-3"
        )

        for vis in sorted(grouped.keys(), key=lambda v: _VIS_ORDER.get(v, 9)):
            by_kind = grouped[vis]
            vis_label = _VIS_LABELS.get(vis, vis.title())

            # Visibility section header
            ui.label(vis_label).classes(
                "text-sm font-semibold mt-3 mb-1 text-gray-300"
            )
            ui.separator().classes("mb-2")

            # Attributes
            attrs = by_kind.get("attribute", [])
            if attrs:
                ui.label("Attributes").classes(
                    "text-xs text-gray-500 uppercase tracking-wider mb-1 ml-2"
                )
                for a in sorted(attrs, key=lambda x: x["name"]):
                    _render_member_row(a, "attribute", content_refreshable)

            # Methods
            methods = by_kind.get("method", [])
            if methods:
                ui.label("Methods").classes(
                    "text-xs text-gray-500 uppercase tracking-wider mb-1 ml-2 mt-2"
                )
                for m in sorted(methods, key=lambda x: x["name"]):
                    _render_member_row(m, "method", content_refreshable)


def _render_member_row(member: dict, kind: str, content_refreshable):
    """Render a single member in Doxygen-style with editable type."""
    name = member["name"]
    type_sig = member.get("type_signature", "")
    args = member.get("argsstring", "")
    desc = member.get("description", "")
    qn = member.get("qualified_name", "")

    with ui.column().classes("ml-4 mb-3 w-full"):
        # Signature line
        with ui.row().classes("items-center gap-1 flex-wrap"):
            # Editable type field
            type_input = ui.input(
                value=type_sig,
                placeholder="type" if kind == "attribute" else "return type",
            ).classes("w-36").props("dense borderless input-class=text-blue-300")
            type_input.style(
                "font-family: monospace; font-size: 13px;"
            )

            # Name + args
            if kind == "method":
                sig_text = f"{name}{args or '()'}"
            else:
                sig_text = name
            ui.label(sig_text).classes("text-sm font-mono font-semibold")

            # Save on blur
            async def on_type_blur(e, _qn=qn, _input=type_input):
                new_val = _input.value.strip()
                if new_val != (member.get("type_signature") or ""):
                    success = await asyncio.to_thread(update_member_type, _qn, new_val)
                    if success:
                        ui.notify(f"Type updated for {name}", type="positive")
                    else:
                        ui.notify("Could not update type (node not in SQLite)", type="warning")

            type_input.on("blur", on_type_blur)

        # Description
        if desc:
            ui.label(desc).classes("text-xs text-gray-400 ml-1 mt-1")


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
