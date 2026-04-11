"""Reusable UI rendering helpers. No DB access — work with plain dicts."""

import logging

import json
from pathlib import Path

from nicegui import ui

from frontend.theme import (
    VERIFICATION_COLORS,
    CLS_SECTION_HEADER,
    CLS_SECTION_SUBHEADER,
    CLS_BREADCRUMB_LINK,
    CLS_BREADCRUMB_SEP,
    CLS_BREADCRUMB_CURRENT,
    KIND_COLORS_JS,
)

log = logging.getLogger(__name__)

def section_header(text: str):
    """Render a standard section header label (uppercase, small, gray)."""
    ui.label(text).classes(CLS_SECTION_HEADER)


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
    base_styles: str,
    *,
    container_id: str = "cy-container",
    cy_var: str = "_cy",
    layout: str = "fcose",
    animate: bool = True,
    extra_styles: str | None = None,
    timeout: float = 5.0,
):
    """Render a Cytoscape.js graph into a container, with tap/dbltap events.

    The container element must already exist with the given *container_id*.
    Emits ``node_selected`` on tap and ``node_dblclick`` on double-tap.
    *extra_styles* is an optional JS expression for additional style entries
    that get appended to the base styles array.
    """
    # Handle empty graph case
    if not elements:
        log.debug("Rendering empty graph - clearing container")
        await ui.run_javascript(f"""
            if (window.{cy_var}) window.{cy_var}.destroy();
            const container = document.getElementById('{container_id}');
            if (container) {{
                container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#888;font-size:1rem;">No nodes found</div>';
            }}
        """, timeout=2.0)
        return
    
    elements_json = json.dumps(elements)
    log.debug(f"Graph data: {len(elements)} elements")
    layout_name = f"window._cyLayout || '{layout}'" if animate else f"'{layout}'"
    animation_opts = "animate: true, animationDuration: 500" if animate else "animate: false"
    styles_expr = base_styles
    if extra_styles:
        styles_expr = f"[...{base_styles}, {extra_styles}]"
    
    result = await ui.run_javascript(f"""
        try {{
            console.log('Cytoscape render starting:', {{
                container_id: '{container_id}',
                elements_count: {len(elements)},
                layout: '{layout}'
            }});
            
            if (window.{cy_var}) window.{cy_var}.destroy();
            const KIND_COLORS = {KIND_COLORS_JS};
            const container = document.getElementById('{container_id}');
            if (!container) {{ 
                console.error('Container not found'); 
                return {{success: false, error: 'Container not found'}}; 
            }}
            
            window.{cy_var} = cytoscape({{
                container: container,
                elements: {elements_json},
                style: {styles_expr},
                layout: {{ name: {layout_name}, {animation_opts} }},
            }});
            
            window.{cy_var}.ready(function() {{ 
                console.log('Cytoscape ready, fitting graph');
                window.{cy_var}.fit(); 
            }});
            
            window.{cy_var}.on('tap', 'node', function(evt) {{
                const data = evt.target.data();
                if (data.qualified_name) {{
                    emitEvent('node_selected', data);
                }}
            }});
            
            window.{cy_var}.on('dbltap', 'node', function(evt) {{
                const data = evt.target.data();
                if (data.qualified_name) {{
                    emitEvent('node_dblclick', data);
                }}
            }});
            
            console.log('Cytoscape initialization complete');
            return {{success: true, elements: {len(elements)}}};
            
        }} catch (error) {{
            console.error('Cytoscape render failed:', error);
            return {{success: false, error: error.toString(), stack: error.stack}};
        }}
    """, timeout=timeout)
    
    if result and not result.get('success'):
        log.error(f"Cytoscape render failed: {result.get('error')}")
        log.error(f"Stack trace: {result.get('stack')}")
        raise RuntimeError(f"Cytoscape render failed: {result.get('error')}")
    
    log.debug(f"Cytoscape render successful: {result}")

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

    with ui.dialog().props("maximized=false") as dialog, \
         ui.card().classes("w-[540px] max-h-[80vh]"):
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
                    with ui.item(on_click=lambda _, p=current.parent: navigate(p)).classes("w-full"):
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
            ui.button(icon="check", on_click=create_folder).props("flat round size=sm color=positive")
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
                    ui.menu_item("View Details", on_click=lambda h=hlr_id: ui.navigate.to(f"/hlr/{h}"))
                    ui.menu_item("Add LLR", on_click=lambda h=hlr_id: ui.navigate.to(f"/hlr/{h}#add-llr"))
                    ui.separator()
                    ui.menu_item("Decompose", on_click=lambda h=hlr_id: ui.navigate.to(f"/hlr/{h}"))

        if hlr["llrs"]:
            with ui.expansion("Low-Level Requirements", icon="list").classes("w-full mt-2").props("dense"):
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
        rows.append({
            "id": llr["id"],
            "description": desc[:120] + ("..." if len(desc) > 120 else ""),
            "verification": ", ".join(llr["methods"]) if llr["methods"] else "-",
        })

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
                '       @click.stop="$parent.$emit(\'edit\', props.row.id)" />'
            )
        delete_btn = ""
        if on_delete:
            delete_btn = (
                '<q-btn flat round dense size="xs" icon="delete" color="negative"'
                '       @click.stop="$parent.$emit(\'delete\', props.row.id)" />'
            )
        table.add_slot(
            "body-cell-actions",
            f"<q-td :props=\"props\">{edit_btn}{delete_btn}</q-td>",
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
                    ui.label(c["member_qualified_name"]).classes("text-xs font-mono text-blue-300")
                    ui.label(c["operator"]).classes("text-xs text-gray-500")
                    ui.label(c["expected_value"]).classes("text-xs font-mono text-green-300")

        if v["actions"]:
            ui.separator().classes("my-2")
            ui.label("Actions").classes(CLS_SECTION_SUBHEADER)
            for i, a in enumerate(v["actions"], 1):
                with ui.row().classes("items-center gap-2"):
                    ui.badge(str(i), color="grey").props("rounded").classes("text-xs")
                    ui.label(a["description"]).classes("text-xs")
                    if a["member_qualified_name"]:
                        ui.label(a["member_qualified_name"]).classes("text-xs font-mono text-gray-500")

        if v["postconditions"]:
            ui.separator().classes("my-2")
            ui.label("Post-conditions").classes(CLS_SECTION_SUBHEADER)
            for c in v["postconditions"]:
                with ui.row().classes("items-center gap-1"):
                    ui.label(c["member_qualified_name"]).classes("text-xs font-mono text-blue-300")
                    ui.label(c["operator"]).classes("text-xs text-gray-500")
                    ui.label(c["expected_value"]).classes("text-xs font-mono text-green-300")


def render_triples_card(triples):
    """Render an ontology triples card from plain dicts."""
    with ui.card().classes("w-full"):
        ui.label("Ontology Triples").classes(
            CLS_SECTION_HEADER
        )
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
