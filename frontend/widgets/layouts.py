"""Reusable graphical layout primitives for cards and panels."""

from nicegui import ui

from frontend.theme import (
    CLS_ROW_CENTER,
    CLS_ROW_CENTER_COMPACT,
    CLS_ROW_JUSTIFY_BETWEEN,
    CLS_TEXT_XS,
    CLS_TEXT_SM,
    CLS_MONO_XS,
    CLS_TEXT_MUTED,
    CLS_TEXT_BLUE,
    CLS_TEXT_GREEN,
    CLS_EMPTY_STATE,
    CLS_SECTION_SUBHEADER,
)


def card_header_row(
    title: str,
    *,
    badges: list[tuple[str, str]] | None = None,
    secondary_text: str | None = None,
) -> ui.row:
    """Render a card header: title + optional badges + secondary text.

    Returns the outer ``ui.row`` so callers can add right-side action buttons
    inside the same row via ``with result: ...``.

    *badges* is a list of ``(label, color)`` tuples.
    """
    if badges is None:
        badges = []
    row = ui.row().classes(CLS_ROW_JUSTIFY_BETWEEN)
    with row:
        with ui.column().classes("gap-0"):
            with ui.row().classes(CLS_ROW_CENTER):
                ui.label(title).classes(f"{CLS_TEXT_SM} font-semibold")
                for label, color in badges:
                    ui.badge(label, color=color).classes(CLS_TEXT_XS)
            if secondary_text:
                ui.label(secondary_text).classes(f"{CLS_TEXT_XS} {CLS_TEXT_MUTED}")
    return row


def card_section(
    title: str,
    items: list,
    render_fn,
    *,
    header_class: str | None = None,
    enumerated: bool = False,
):
    """Render a guarded card section: separator + header + loop over items.

    Renders nothing if *items* is empty.  For each item, calls
    ``render_fn(item)`` inside the active NiceGUI context.

    If *enumerated* is True, *render_fn* receives ``(index, item)`` instead
    (1-indexed).  *header_class* defaults to :data:`CLS_SECTION_SUBHEADER`.
    """
    if not items:
        return
    ui.separator().classes("my-2")
    ui.label(title).classes(header_class or CLS_SECTION_SUBHEADER)
    if enumerated:
        for i, item in enumerate(items, 1):
            render_fn(i, item)
    else:
        for item in items:
            render_fn(item)


def empty_state(text: str, extra_classes: str = ""):
    """Render a muted placeholder label for an empty collection."""
    ui.label(text).classes(f"{CLS_EMPTY_STATE} {extra_classes}".strip())


def render_condition_row(
    member_qualified_name: str,
    operator: str,
    expected_value: str,
):
    """Render a condition row: ``qualified_name  operator  expected_value``."""
    with ui.row().classes(CLS_ROW_CENTER_COMPACT):
        ui.label(member_qualified_name).classes(f"{CLS_MONO_XS} {CLS_TEXT_BLUE}")
        ui.label(operator).classes(f"{CLS_TEXT_XS} {CLS_TEXT_MUTED}")
        ui.label(expected_value).classes(f"{CLS_MONO_XS} {CLS_TEXT_GREEN}")