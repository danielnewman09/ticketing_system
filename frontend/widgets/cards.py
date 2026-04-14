"""Card renderers for HLR, LLR, verification, and ontology triples."""

from nicegui import ui

from frontend.theme import (
    VERIFICATION_COLORS,
    CLS_SECTION_SUBHEADER,
)


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
    from frontend.theme import CLS_SECTION_HEADER

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