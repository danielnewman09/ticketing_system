"""Card renderers for HLR, LLR, verification, and ontology triples."""

from nicegui import ui

from frontend.theme import (
    BADGE_COLORS,
    VERIFICATION_COLORS,
    CLS_CARD_FULL,
    CLS_CARD_FULL_MARGIN,
    CLS_ROW_CENTER,
    CLS_ROW_JUSTIFY_BETWEEN,
    CLS_TEXT_XS,
    CLS_MONO_SM,
    CLS_TEXT_SECONDARY,
    CLS_TEXT_DIM,
    CLS_TEXT_CYAN,
    CLS_TEXT_MUTED,
    CLS_SECTION_HEADER,
    CLS_SECTION_SUBHEADER,
    PROPS_ICON_BTN,
    PROPS_DENSE,
    PROPS_TABLE_COMPACT,
)
from frontend.widgets.layouts import (
    card_section,
    empty_state,
    render_condition_row,
)
from frontend.widgets.slots import TABLE_EDIT_BTN, TABLE_DELETE_BTN


def render_hlr_card(hlr):
    """Render a single HLR as an expandable card with its LLR table."""
    llr_count = len(hlr["llrs"])

    with ui.card().classes(CLS_CARD_FULL_MARGIN):
        with ui.row().classes("w-full items-start justify-between"):
            with ui.column().classes("flex-1 gap-0"):
                with ui.row().classes(CLS_ROW_CENTER):
                    ui.badge(f"HLR {hlr['id']}", color=BADGE_COLORS["hlr"]).props("outline")
                    if hlr["component"]:
                        ui.badge(hlr["component"], color=BADGE_COLORS["component"])
                    ui.badge(
                        f"{llr_count} LLR{'s' if llr_count != 1 else ''}",
                        color=BADGE_COLORS["llr"] if llr_count > 0 else BADGE_COLORS["llr_empty"],
                    ).classes(CLS_TEXT_XS)
                ui.label(hlr["description"]).classes(f"{CLS_TEXT_SM} mt-1")

            hlr_id = hlr["id"]
            with ui.button(icon="more_vert").props(PROPS_ICON_BTN):
                with ui.menu():
                    ui.menu_item("View Details", on_click=lambda h=hlr_id: ui.navigate.to(f"/hlr/{h}"))
                    ui.menu_item("Add LLR", on_click=lambda h=hlr_id: ui.navigate.to(f"/hlr/{h}#add-llr"))
                    ui.separator()
                    ui.menu_item("Decompose", on_click=lambda h=hlr_id: ui.navigate.to(f"/hlr/{h}"))

        if hlr["llrs"]:
            with ui.expansion("Low-Level Requirements", icon="list").classes("w-full mt-2").props(PROPS_DENSE):
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

    table = ui.table(columns=columns, rows=rows, row_key="id").classes(CLS_CARD_FULL)
    table.props(PROPS_TABLE_COMPACT)
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
        edit_btn = TABLE_EDIT_BTN if on_edit else ""
        delete_btn = TABLE_DELETE_BTN if on_delete else ""
        table.add_slot(
            "body-cell-actions",
            f"<q-td :props=\"props\">{edit_btn}{delete_btn}</q-td>",
        )
        if on_edit:
            table.on("edit", lambda e: on_edit(e.args, full_descriptions.get(e.args)))
        if on_delete:
            table.on("delete", lambda e: on_delete(e.args))


def _render_action_row(index: int, a: dict):
    with ui.row().classes(CLS_ROW_CENTER):
        ui.badge(str(index), color=BADGE_COLORS["muted"]).props("rounded").classes(CLS_TEXT_XS)
        ui.label(a["description"]).classes(CLS_TEXT_XS)
        if a["member_qualified_name"]:
            ui.label(a["member_qualified_name"]).classes(f"{CLS_TEXT_XS} {CLS_TEXT_MUTED}")


def render_verification_card(v):
    """Render a single verification method as a card with conditions/actions."""
    color = VERIFICATION_COLORS.get(v["method"], BADGE_COLORS["muted"])

    with ui.card().classes(CLS_CARD_FULL):
        with ui.row().classes(CLS_ROW_JUSTIFY_BETWEEN):
            with ui.row().classes(CLS_ROW_CENTER):
                ui.badge(v["method"], color=color).classes(CLS_TEXT_XS)
                if v["test_name"]:
                    ui.label(v["test_name"]).classes(f"{CLS_MONO_SM} {CLS_TEXT_SECONDARY}")

        if v["description"]:
            ui.label(v["description"]).classes(f"{CLS_TEXT_XS} {CLS_TEXT_DIM} mt-1")

        card_section(
            "Pre-conditions", v.get("preconditions") or [],
            lambda c: render_condition_row(c["member_qualified_name"], c["operator"], c["expected_value"]),
        )
        card_section(
            "Actions", v.get("actions") or [],
            _render_action_row,
            enumerated=True,
        )
        card_section(
            "Post-conditions", v.get("postconditions") or [],
            lambda c: render_condition_row(c["member_qualified_name"], c["operator"], c["expected_value"]),
        )


def render_triples_card(triples):
    """Render an ontology triples card from plain dicts."""
    with ui.card().classes(CLS_CARD_FULL):
        ui.label("Ontology Triples").classes(CLS_SECTION_HEADER)
        if triples:
            triple_cols = [
                {"name": "subject", "label": "Subject", "field": "subject", "align": "left"},
                {"name": "predicate", "label": "Predicate", "field": "predicate", "align": "left"},
                {"name": "object", "label": "Object", "field": "object", "align": "left"},
            ]
            t = ui.table(columns=triple_cols, rows=triples).classes(CLS_CARD_FULL)
            t.props(PROPS_TABLE_COMPACT)
            t.add_slot(
                "body-cell-predicate",
                f'<q-td :props="props"><code class="{CLS_TEXT_CYAN}">{{{{ props.value }}}}</code></q-td>',
            )
        else:
            empty_state("No triples linked.")