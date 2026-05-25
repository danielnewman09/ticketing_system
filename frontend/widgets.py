"""Reusable UI rendering helpers and shared state types.

No DB access — functions here work with plain dicts passed in from
the data layer, or with simple state objects like ``GraphState``.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from nicegui import ui

from frontend.theme import (
    VERIFICATION_COLORS,
    KIND_COLORS,
    CLS_SECTION_HEADER,
    CLS_SECTION_SUBHEADER,
    CLS_BREADCRUMB_LINK,
    CLS_BREADCRUMB_SEP,
    CLS_BREADCRUMB_CURRENT,
    KIND_COLORS_JS,
    cytoscape_base_styles,
)


def section_header(text: str):
    """Render a standard section header label (uppercase, small, gray)."""
    ui.label(text).classes(CLS_SECTION_HEADER)


def render_detail_section(
    title: str,
    items: list[dict],
    *,
    badge_key: str | None = None,
    badge_color: str = "grey",
    badge_color_fn=None,
    label_key: str = "name",
    label_fallback_key: str | None = None,
    label_cls: str = "text-xs",
    badge_first: bool = True,
    max_items: int | None = None,
):
    """Render a detail-panel section: separator, header, and item rows.

    Each item row shows an optional badge and a label.
    If *items* is empty, nothing is rendered.

    - *badge_key*: dict key for badge text, or ``None`` for badge-less rows.
    - *badge_color*: default badge color (used when *badge_color_fn* is absent).
    - *badge_color_fn*: optional callable(item) -> color string (overrides *badge_color*).
    - *label_key*: primary dict key for label text.
    - *label_fallback_key*: fallback key when *label_key* value is empty/falsy.
    - *label_cls*: CSS classes applied to each label.
    - *badge_first*: if ``True``, badge precedes label; if ``False``, label first.
    - *max_items*: cap on number of items shown.
    """
    if not items:
        return

    ui.separator().classes("my-2")
    section_header(title)

    shown = items[:max_items] if max_items else items
    for item in shown:
        label_text = item.get(label_key, "")
        if not label_text and label_fallback_key:
            label_text = item.get(label_fallback_key, "")

        with ui.row().classes("items-center gap-1"):
            if badge_key is not None:
                badge_text = str(item.get(badge_key, ""))
                color = badge_color_fn(item) if badge_color_fn else badge_color
                if badge_first:
                    ui.badge(badge_text, color=color).classes("text-xs")
                    ui.label(label_text).classes(label_cls)
                else:
                    ui.label(label_text).classes(label_cls)
                    ui.badge(badge_text, color=color).classes("text-xs")
            else:
                ui.label(label_text).classes(label_cls)


@ui.refreshable
def render_graph_detail_panel(state: "GraphState"):
    """Render the ontology-graph node detail panel.

    *state* is a `GraphState` instance whose ``selected_node_data`` attribute
    holds node detail info (or ``None`` when no node is selected). Call
    ``render_graph_detail_panel.refresh()`` after updating
    ``state.selected_node_data``.
    """
    with ui.card().classes("w-80 ml-2 overflow-auto").style("max-height: 100%"):
        d = state.selected_node_data
        if not d:
            ui.label("Click a node to see details").classes("text-gray-400 text-sm")
            return

        props = d["properties"]
        kind = props.get("kind", "")
        color = KIND_COLORS.get(kind, "#666")

        ui.label(props.get("name", "")).classes("text-lg font-bold")
        ui.label(props.get("qualified_name", "")).classes("text-xs text-gray-400 break-all")
        with ui.row().classes("gap-2 mt-1"):
            ui.badge(kind, color="grey").style(f"background:{color} !important")
            if props.get("visibility"):
                ui.badge(props["visibility"], color="grey")

        if props.get("description"):
            ui.separator().classes("my-2")
            ui.label(props["description"]).classes("text-sm")

        # Outgoing relationships
        render_detail_section(
            "Outgoing",
            d.get("outgoing") or [],
            badge_key="rel",
            label_key="target_name",
            label_fallback_key="target_qn",
        )

        # Incoming relationships
        render_detail_section(
            "Incoming",
            d.get("incoming") or [],
            badge_key="rel",
            label_key="source_name",
            label_fallback_key="source_qn",
            badge_first=False,
        )

        # Implemented by
        render_detail_section(
            "Implemented By",
            d.get("implemented_by") or [],
            label_key="qualified_name",
            label_fallback_key="name",
            label_cls="text-xs text-blue-300",
        )

        # Requirements
        render_detail_section(
            "Traced Requirements",
            d.get("requirements") or [],
            badge_key="type",
            badge_color_fn=lambda r: "orange" if r["type"] == "HLR" else "amber",
            label_key="name",
        )

        # Dependency links (shown for design nodes)
        dep_links = d.get("dependency_links")
        if dep_links:
            deps = [dep.get("data", dep) for dep in dep_links]
            render_detail_section(
                "Dependencies",
                deps,
                badge_key="source",
                badge_color="teal",
                label_key="qualified_name",
                label_fallback_key="label",
                label_cls="text-xs text-teal-300",
            )

        # Design links (shown for dependency nodes)
        render_detail_section(
            "Referenced by Design",
            d.get("design_links") or [],
            badge_key="rel",
            label_key="design_name",
            label_fallback_key="design_qn",
            label_cls="text-xs text-blue-300",
        )

        # Members (shown for dependency compound nodes)
        if d.get("members") and props.get("layer") == "dependency":
            render_detail_section(
                "Members",
                d["members"],
                badge_key="kind",
                label_key="name",
                max_items=20,
            )

        # Source library (shown for dependency nodes)
        if props.get("source"):
            ui.separator().classes("my-2")
            with ui.row().classes("items-center gap-1"):
                ui.label("Source:").classes("text-xs text-gray-400")
                ui.badge(props["source"], color="teal").classes("text-xs")


@dataclass
class GraphState:
    """Mutable state for the ontology-graph page.

    Used as a single object passed by reference so that mutations
    (e.g. ``state.graph_layer = "codebase"``) are visible to
    refreshable UI functions like `render_graph_detail_panel`.
    """

    kind_filter: str | None = None
    search_text: str = ""
    selected_node_data: dict | None = None
    graph_layer: str = "design"  # "design", "codebase", or "dependency"
    source_filter: str | None = None  # dependency source filter (e.g. "eigen")
    show_requirement_tags: bool = True  # toggle HLR badges on/off
    show_dependencies: bool = True  # toggle cross-layer dependency nodes


@dataclass
class GraphConfig:
    """Configuration for Cytoscape graph rendering."""

    container_id: str = "cy-container"
    cy_var: str = "_cy"
    size: str = "large"  # "large" for main page, "small" for detail panels
    layout: str = "fcose"
    animate: bool = True
    extra_styles: str | None = None

    @property
    def tap_event(self) -> str:
        """JS event name for node tap (register with ``ui.on()``)."""
        return f"{self.cy_var}_tap"

    @property
    def dbltap_event(self) -> str:
        """JS event name for node double-tap (register with ``ui.on()``)."""
        return f"{self.cy_var}_dbltap"


def render_ontology_graph_controls(
    *,
    on_layer_change: callable,
    on_kind_change: callable,
    on_search: callable,
    on_layout_change: callable,
    on_fit: callable,
    on_toggle_req_tags=None,
    on_toggle_deps=None,
):
    """Render the ontology-graph toolbar: layer, kind, search, layout, and fit.

    All callbacks receive a NiceGUI event object (``e``) except *on_fit*,
    which is called with no arguments.
    """
    with ui.row().classes("w-full gap-4 px-2 mb-2 items-end"):
        ui.select(
            {
                "design": "Design Intent",
                "codebase": "As-Built Codebase",
                "dependency": "Dependencies",
            },
            value="design",
            label="Layer",
            on_change=on_layer_change,
        ).classes("w-44")
        kind_options = ["all"] + sorted(KIND_COLORS.keys())
        ui.select(kind_options, value="all", label="Kind", on_change=on_kind_change).classes("w-36")
        ui.input("Search", on_change=on_search).classes("w-48")
        ui.select(
            ["fcose", "breadthfirst", "circle", "grid", "concentric"],
            value="fcose",
            label="Layout",
            on_change=on_layout_change,
        ).classes("w-36")
        ui.button("Fit", on_click=on_fit).props("flat dense")
        if on_toggle_req_tags:
            ui.switch("Reqs", value=True, on_change=on_toggle_req_tags).props("dense")
        if on_toggle_deps:
            ui.switch("Deps", value=True, on_change=on_toggle_deps).props("dense")


def render_ontology_graph_legend():
    """Render the ontology-graph legend showing kind colors and special node types."""
    with ui.row().classes("px-2 mb-2 gap-3 flex-wrap"):
        for kind, color in sorted(KIND_COLORS.items()):
            with ui.row().classes("items-center gap-1"):
                ui.html(
                    f'<div style="width:10px;height:10px;border-radius:50%;background:{color}"></div>'
                )
                ui.label(kind).classes("text-xs")
        with ui.row().classes("items-center gap-1"):
            ui.html(
                '<div style="width:10px;height:10px;border-radius:50%;background:#e67e22;border:3px solid #e67e22"></div>'
            )
            ui.label("Requirement").classes("text-xs")
        with ui.row().classes("items-center gap-1"):
            ui.html(
                '<div style="width:10px;height:10px;border-radius:50%;background:#009688;border:2px dashed #4db6ac"></div>'
            )
            ui.label("Dependency").classes("text-xs")
        with ui.row().classes("items-center gap-1"):
            ui.html(
                '<div style="width:10px;height:10px;border-radius:50%;background:#555;border:2px dashed #009688"></div>'
            )
            ui.label("Deps (source)").classes("text-xs")
        with ui.row().classes("items-center gap-1"):
            ui.html(
                '<div style="width:10px;height:10px;border-radius:50%;background:#555;border:2px dotted #3b82f6"></div>'
            )
            ui.label("As-built").classes("text-xs")


def breadcrumb(*parts: tuple[str, str | None]):
    """Render a breadcrumb trail.

    Each *part* is ``(label, href)`` — if *href* is ``None`` the part is
    rendered as plain text (the current page).
    """
    with ui.row().classes("items-center gap-1 px-2 mt-4"):
        for i, (label, href) in enumerate(parts):
            if i > 0:
                ui.label("/").classes(CLS_BREADCRUMB_SEP)
            if href is not None:
                ui.link(label, href).classes(CLS_BREADCRUMB_LINK)
            else:
                ui.label(label).classes(CLS_BREADCRUMB_CURRENT)


async def render_cytoscape_graph(
    elements: list[dict],
    config: GraphConfig,
):
    """Render a Cytoscape.js graph with consistent theme and event handling.

    All pages should use this function instead of inline Cytoscape JS.
    Styling and event wiring are handled centrally.

    IMPORTANT: Pages must call ``add_cytoscape_cdn()`` before calling this
    function, to ensure the Cytoscape scripts are loaded in the browser.
    """
    base_styles = cytoscape_base_styles(size=config.size)
    elements_json = json.dumps(elements)
    layout_name = f"window._cyLayout || '{config.layout}'" if config.animate else f"'{config.layout}'"
    animation_opts = "animate: true, animationDuration: 500" if config.animate else "animate: false"
    # Build style expression — only wrap in spread when extending with extra_styles
    if config.extra_styles:
        styles_expr = f"[...{base_styles}, {config.extra_styles}]"
    else:
        styles_expr = base_styles
    # Ensure unique event names per instance
    tap_event = f"{config.cy_var}_tap"
    dbltap_event = f"{config.cy_var}_dbltap"

    await ui.run_javascript(f"""
        if (window.{config.cy_var}) window.{config.cy_var}.destroy();
        const KIND_COLORS = {KIND_COLORS_JS};
        const container = document.getElementById('{config.container_id}');
        if (container) {{
            window.{config.cy_var} = cytoscape({{
                container: container,
                elements: {elements_json},
                style: {styles_expr},
                layout: {{ name: {layout_name}, {animation_opts} }},
            }});
            window.{config.cy_var}.ready(function() {{ window.{config.cy_var}.fit(); }});
            window.{config.cy_var}.on('tap', 'node', function(evt) {{
                const data = evt.target.data();
                if (data.qualified_name) {{
                    emitEvent('{tap_event}', data);
                }}
            }});
            window.{config.cy_var}.on('dbltap', 'node', function(evt) {{
                const data = evt.target.data();
                if (data.qualified_name) {{
                    emitEvent('{dbltap_event}', data);
                }}
            }});
        }} else {{
            console.error('{config.container_id} not found');
        }}
        void 0;  // prevent eval returning the cy instance (circular refs)
    """, timeout=30)


def directory_picker(
    initial_path: str = "",
    *,
    on_select: callable = None,
) -> ui.dialog:
    """Open a dialog that browses the server filesystem for a directory.

    Supports navigation, path entry, and creating new folders.
    Calls *on_select(path_str)* when the user confirms.
    """
    start = Path(initial_path).expanduser() if initial_path else Path.home()
    if not start.is_dir():
        start = Path.home()

    state = {"current": start}

    def _list_dirs(path: Path) -> list[Path]:
        try:
            return sorted(
                [p for p in path.iterdir() if p.is_dir() and not p.name.startswith(".")],
                key=lambda p: p.name.lower(),
            )
        except PermissionError:
            return []

    with (
        ui.dialog().props("maximized=false") as dialog,
        ui.card().classes("w-[540px] max-h-[80vh]"),
    ):
        ui.label("Select Directory").classes("text-lg font-bold mb-2")

        # Path breadcrumb / manual entry
        path_input = ui.input("Path", value=str(start)).classes("w-full font-mono text-xs")

        dir_container = ui.column().classes("w-full overflow-auto").style("max-height: 400px;")

        selected_label = ui.label(f"Selected: {start}").classes(
            "text-xs text-gray-400 font-mono mt-2 truncate w-full"
        )

        def navigate(path: Path):
            if not path.is_dir():
                ui.notify(f"Not a directory: {path}", type="warning")
                return
            state["current"] = path
            path_input.value = str(path)
            selected_label.text = f"Selected: {path}"
            _refresh_listing()

        def _refresh_listing():
            dir_container.clear()
            current = state["current"]
            dirs = _list_dirs(current)
            with dir_container:
                # Parent directory entry
                if current.parent != current:
                    with ui.item(on_click=lambda _, p=current.parent: navigate(p)).classes(
                        "w-full"
                    ):
                        with ui.item_section().props("side"):
                            ui.icon("arrow_upward", size="sm").classes("text-gray-500")
                        with ui.item_section():
                            ui.item_label("..").classes("font-mono text-gray-400")

                if not dirs:
                    ui.label("No subdirectories").classes("text-sm text-gray-500 px-4 py-2")
                for d in dirs:
                    with ui.item(on_click=lambda _, p=d: navigate(p)).classes("w-full"):
                        with ui.item_section().props("side"):
                            ui.icon("folder", size="sm", color="amber")
                        with ui.item_section():
                            ui.item_label(d.name).classes("font-mono text-sm")

        # Navigate when user presses Enter in the path input
        def on_path_enter():
            p = Path(path_input.value.strip()).expanduser()
            navigate(p)

        path_input.on("keydown.enter", on_path_enter)

        # New folder creation
        def show_new_folder():
            new_folder_row.set_visibility(True)

        def create_folder():
            name = new_folder_input.value.strip()
            if not name:
                return
            target = state["current"] / name
            try:
                target.mkdir(parents=True, exist_ok=True)
                ui.notify(f"Created {target.name}", type="positive")
                new_folder_input.value = ""
                new_folder_row.set_visibility(False)
                navigate(target)
            except OSError as e:
                ui.notify(f"Failed: {e}", type="negative")

        with ui.row().classes("w-full items-center gap-2 mt-2") as new_folder_row:
            new_folder_input = ui.input("New folder name").classes("flex-1").props("dense")
            new_folder_input.on("keydown.enter", create_folder)
            ui.button(icon="check", on_click=create_folder).props(
                "flat round size=sm color=positive"
            )
            ui.button(
                icon="close",
                on_click=lambda: new_folder_row.set_visibility(False),
            ).props("flat round size=sm")
        new_folder_row.set_visibility(False)

        # Action buttons
        with ui.row().classes("w-full justify-between mt-4"):
            ui.button("New Folder", icon="create_new_folder", on_click=show_new_folder).props(
                "flat size=sm"
            )
            with ui.row().classes("gap-2"):
                ui.button("Cancel", on_click=dialog.close).props("flat")

                def confirm():
                    result = str(state["current"])
                    dialog.close()
                    if on_select:
                        on_select(result)

                ui.button("Select", on_click=confirm).props("color=primary")

        _refresh_listing()

    return dialog


def render_hlr_card(hlr):
    """Render a single HLR as an expandable card with its LLR table."""
    llr_count = len(hlr["llrs"])

    with ui.card().classes("w-full mb-2"):
        with ui.row().classes("w-full items-start justify-between"):
            with ui.column().classes("flex-1 gap-0"):
                with ui.row().classes("items-center gap-2"):
                    ui.badge(f"HLR {hlr['id']}", color="blue").props("outline")
                    if hlr["component"]:
                        ui.badge(hlr["component"], color="grey")
                    ui.badge(
                        f"{llr_count} LLR{'s' if llr_count != 1 else ''}",
                        color="green" if llr_count > 0 else "grey",
                    ).classes("text-xs")
                ui.label(hlr["description"]).classes("text-sm mt-1")

            hlr_id = hlr["id"]
            with ui.button(icon="more_vert").props("flat round size=sm"):
                with ui.menu():
                    ui.menu_item(
                        "View Details", on_click=lambda h=hlr_id: ui.navigate.to(f"/hlr/{h}")
                    )
                    ui.menu_item(
                        "Add LLR", on_click=lambda h=hlr_id: ui.navigate.to(f"/hlr/{h}#add-llr")
                    )
                    ui.separator()
                    ui.menu_item("Decompose", on_click=lambda h=hlr_id: ui.navigate.to(f"/hlr/{h}"))

        if hlr["llrs"]:
            with (
                ui.expansion("Low-Level Requirements", icon="list")
                .classes("w-full mt-2")
                .props("dense")
            ):
                render_llr_table(hlr["llrs"])


def render_llr_table(llrs, on_delete=None, on_edit=None):
    """Render an LLR table from plain dicts.

    If *on_edit* is provided, an edit button is shown per row.
    If *on_delete* is provided, a delete button is shown per row.
    """
    columns = [
        {"name": "id", "label": "ID", "field": "id", "align": "left", "sortable": True},
        {"name": "description", "label": "Description", "field": "description", "align": "left"},
        {"name": "verification", "label": "Verification", "field": "verification", "align": "left"},
    ]
    if on_edit or on_delete:
        columns.append({"name": "actions", "label": "", "field": "id", "align": "right"})

    # Keep full descriptions for edit callbacks, truncated for display.
    full_descriptions = {}
    rows = []
    for llr in llrs:
        desc = llr["description"]
        full_descriptions[llr["id"]] = desc
        rows.append(
            {
                "id": llr["id"],
                "description": desc[:120] + ("..." if len(desc) > 120 else ""),
                "verification": ", ".join(llr["methods"]) if llr["methods"] else "-",
            }
        )

    table = ui.table(columns=columns, rows=rows, row_key="id").classes("w-full")
    table.props("dense flat")
    table.on("row-click", lambda e: ui.navigate.to(f"/llr/{e.args[1]['id']}"))

    table.add_slot(
        "body-cell-verification",
        """
        <q-td :props="props">
            <template v-for="method in props.value.split(', ')">
                <q-badge v-if="method !== '-'"
                    :color="method === 'automated' ? 'positive' : method === 'review' ? 'warning' : 'info'"
                    :label="method"
                    class="q-mr-xs text-xs"
                />
                <span v-else class="text-grey">-</span>
            </template>
        </q-td>
        """,
    )

    if on_edit or on_delete:
        edit_btn = ""
        if on_edit:
            edit_btn = (
                '<q-btn flat round dense size="xs" icon="edit" color="primary"'
                "       @click.stop=\"$parent.$emit('edit', props.row.id)\" />"
            )
        delete_btn = ""
        if on_delete:
            delete_btn = (
                '<q-btn flat round dense size="xs" icon="delete" color="negative"'
                "       @click.stop=\"$parent.$emit('delete', props.row.id)\" />"
            )
        table.add_slot(
            "body-cell-actions",
            f'<q-td :props="props">{edit_btn}{delete_btn}</q-td>',
        )
        if on_edit:
            table.on("edit", lambda e: on_edit(e.args, full_descriptions.get(e.args)))
        if on_delete:
            table.on("delete", lambda e: on_delete(e.args))


def render_verification_card(v):
    """Render a single verification method as a card with conditions/actions."""
    color = VERIFICATION_COLORS.get(v["method"], "grey")

    with ui.card().classes("w-full"):
        with ui.row().classes("w-full items-center justify-between"):
            with ui.row().classes("items-center gap-2"):
                ui.badge(v["method"], color=color).classes("text-xs")
                if v["test_name"]:
                    ui.label(v["test_name"]).classes("text-sm font-mono text-gray-300")

        if v["description"]:
            ui.label(v["description"]).classes("text-xs text-gray-400 mt-1")

        if v["preconditions"]:
            ui.separator().classes("my-2")
            ui.label("Pre-conditions").classes(CLS_SECTION_SUBHEADER)
            for c in v["preconditions"]:
                with ui.row().classes("items-center gap-1"):
                    ui.label(c["subject_qualified_name"]).classes("text-xs font-mono text-blue-300")
                    ui.label(c["operator"]).classes("text-xs text-gray-500")
                    ui.label(c["expected_value"]).classes("text-xs font-mono text-green-300")

        if v["actions"]:
            ui.separator().classes("my-2")
            ui.label("Actions").classes(CLS_SECTION_SUBHEADER)
            for i, a in enumerate(v["actions"], 1):
                with ui.row().classes("items-center gap-2"):
                    ui.badge(str(i), color="grey").props("rounded").classes("text-xs")
                    ui.label(a["description"]).classes("text-xs")
                    if a["callee_qualified_name"]:
                        ui.label(a["callee_qualified_name"]).classes(
                            "text-xs font-mono text-gray-500"
                        )

        if v["postconditions"]:
            ui.separator().classes("my-2")
            ui.label("Post-conditions").classes(CLS_SECTION_SUBHEADER)
            for c in v["postconditions"]:
                with ui.row().classes("items-center gap-1"):
                    ui.label(c["subject_qualified_name"]).classes("text-xs font-mono text-blue-300")
                    ui.label(c["operator"]).classes("text-xs text-gray-500")
                    ui.label(c["expected_value"]).classes("text-xs font-mono text-green-300")


def render_triples_card(triples):
    """Render an ontology triples card from plain dicts."""
    with ui.card().classes("w-full"):
        ui.label("Ontology Triples").classes(CLS_SECTION_HEADER)
        if triples:
            triple_cols = [
                {"name": "subject", "label": "Subject", "field": "subject", "align": "left"},
                {"name": "predicate", "label": "Predicate", "field": "predicate", "align": "left"},
                {"name": "object", "label": "Object", "field": "object", "align": "left"},
            ]
            t = ui.table(columns=triple_cols, rows=triples).classes("w-full")
            t.props("dense flat")
            t.add_slot(
                "body-cell-predicate",
                '<q-td :props="props"><code class="text-cyan-300">{{ props.value }}</code></q-td>',
            )
        else:
            ui.label("No triples linked.").classes("text-sm text-gray-500")
