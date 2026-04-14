"""Reusable Quasar table-slot HTML fragments.

These are raw HTML snippets for ``ui.table.add_slot()`` — they cannot use
NiceGUI widgets because they render inside Vue/Quasar virtual-DOM templates.
"""

_TABLE_BTN = (
    '<q-btn flat round dense size="xs"'
    ' icon="{icon}" color="{color}"'
    ' @click.stop="$parent.$emit(\'{event}\', props.row.id)" />'
)


def table_action_btn(icon: str, color: str, event: str) -> str:
    """Return a ``<q-btn>`` HTML fragment for a table action slot.

    Emits *event* on click with ``props.row.id`` as the payload.
    """
    return _TABLE_BTN.format(icon=icon, color=color, event=event)


TABLE_EDIT_BTN = table_action_btn("edit", "primary", "edit")
TABLE_DELETE_BTN = table_action_btn("delete", "negative", "delete")