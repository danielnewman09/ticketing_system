"""Ontology node detail page."""

import asyncio
import json

from nicegui import ui

from frontend.theme import (
    KIND_COLORS,
    BACKGROUNDS,
    STATUS_COLORS,
    CLS_SECTION_HEADER,
    CLS_SECTION_SUBHEADER,
    KIND_COLORS_JS,
    add_cytoscape_cdn,
    cytoscape_base_styles,
    apply_theme,
)
from frontend.widgets import breadcrumb
from frontend.layout import page_layout
from frontend.data.ontology import fetch_node_detail_full, fetch_neighbourhood_graph_data, update_member_type


@ui.page("/node/{node_id}")
async def node_detail_page(node_id: int):
    apply_theme()
    page_layout("Node Detail")

    add_cytoscape_cdn()
    base_styles = cytoscape_base_styles(size="small")

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

        breadcrumb(
            ("Ontology", "/ontology"),
            ("Graph", "/ontology/graph"),
            (node["name"], None),
        )

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
                    ui.label("Identity").classes(CLS_SECTION_HEADER)
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
                        ui.label("Description").classes(CLS_SECTION_HEADER)
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
                        available_types = neo4j.get("available_types", [])
                        _render_members_card(
                            all_members, available_types, content,
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
                        ui.label("Code Details").classes(CLS_SECTION_HEADER)
                        for label, value in visible_code:
                            _prop_row(label, value)

                # Flags
                flags = []
                for flag_name in ["is_static", "is_const", "is_virtual", "is_abstract", "is_final"]:
                    if node.get(flag_name):
                        flags.append(flag_name.replace("is_", ""))
                if flags:
                    with ui.card().classes("w-full"):
                        ui.label("Flags").classes(CLS_SECTION_HEADER)
                        with ui.row().classes("gap-2"):
                            for f in flags:
                                ui.badge(f, color="grey")

            # Right column — relationships + graph
            with ui.column().classes("flex-1 gap-4"):
                # Neighbourhood graph
                if neo4j:
                    with ui.card().classes("w-full"):
                        ui.label("Neighbourhood").classes(CLS_SECTION_HEADER)
                        cy = ui.element("div").style(
                            f"height: calc(100vh - 280px); min-height: 400px; background: {BACKGROUNDS['base']}; border-radius: 8px;"
                        ).classes("w-full")
                        cy._props["id"] = "node-cy-container"

                    # Fetch neighbourhood with collapsed members
                    graph = await asyncio.to_thread(
                        fetch_neighbourhood_graph_data, node["qualified_name"],
                    )
                    elements_json = json.dumps(graph["nodes"] + graph["edges"])
                    if graph["nodes"]:
                        # Add center-node highlight on top of base styles
                        center_style = f"""{{
                            selector: 'node[is_center="true"]',
                            style: {{
                                'border-width': 3,
                                'border-color': '{STATUS_COLORS["selected"]}',
                                'border-style': 'solid',
                            }}
                        }}"""
                        await ui.run_javascript(f"""
                            if (window._nodeCy) window._nodeCy.destroy();
                            const KIND_COLORS = {KIND_COLORS_JS};
                            const container = document.getElementById('node-cy-container');
                            if (!container) return;
                            const styles = {base_styles};
                            styles.push({center_style});
                            window._nodeCy = cytoscape({{
                                container: container,
                                elements: {elements_json},
                                style: styles,
                                layout: {{ name: 'fcose', animate: false }},
                            }});
                        """)

                if neo4j:
                    if neo4j.get("implemented_by"):
                        with ui.card().classes("w-full"):
                            ui.label("Implemented By").classes(CLS_SECTION_HEADER)
                            for impl in neo4j["implemented_by"]:
                                ui.label(
                                    impl.get("qualified_name", impl.get("name", ""))
                                ).classes("text-sm text-blue-300")

                    if neo4j.get("requirements"):
                        with ui.card().classes("w-full"):
                            ui.label("Traced Requirements").classes(CLS_SECTION_HEADER)
                            for req in neo4j["requirements"]:
                                with ui.row().classes("items-center gap-2 py-1"):
                                    req_type = req["type"]
                                    ui.badge(
                                        req_type,
                                        color="orange" if req_type == "HLR" else "amber",
                                    ).classes("text-xs")
                                    ui.label(req.get("name", "")).classes("text-sm")

    await content()


def _render_members_card(
    members: list[dict],
    available_types: list[str],
    content_refreshable,
):
    """Render a Doxygen-style members documentation card.

    Groups members by visibility (public, protected, private), then by kind
    (attributes, methods). Each member shows an editable type field with
    autocomplete from available_types.
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
            CLS_SECTION_HEADER
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
                    CLS_SECTION_SUBHEADER + " ml-2"
                )
                for a in sorted(attrs, key=lambda x: x["name"]):
                    _render_member_row(a, "attribute", available_types, content_refreshable)

            # Methods
            methods = by_kind.get("method", [])
            if methods:
                ui.label("Methods").classes(
                    CLS_SECTION_SUBHEADER + " ml-2 mt-2"
                )
                for m in sorted(methods, key=lambda x: x["name"]):
                    _render_member_row(m, "method", available_types, content_refreshable)


def _render_member_row(
    member: dict, kind: str, available_types: list[str], content_refreshable,
):
    """Render a single member in Doxygen-style with editable type + autocomplete."""
    name = member["name"]
    type_sig = member.get("type_signature", "")
    args = member.get("argsstring", "")
    desc = member.get("description", "")
    qn = member.get("qualified_name", "")

    with ui.column().classes("ml-4 mb-3 w-full"):
        # Signature line
        with ui.row().classes("items-center gap-1 flex-wrap"):
            # Editable type field with autocomplete
            type_input = ui.input(
                value=type_sig,
                placeholder="type" if kind == "attribute" else "return type",
                autocomplete=available_types,
            ).classes("w-48").props("dense borderless input-class=text-blue-300")
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
            async def on_type_blur(e, _qn=qn, _input=type_input, _name=name):
                new_val = _input.value.strip()
                if new_val != (member.get("type_signature") or ""):
                    success = await asyncio.to_thread(update_member_type, _qn, new_val)
                    if success:
                        ui.notify(f"Type updated for {_name}", type="positive")
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
