"""Shared nav helpers: section headers and breadcrumb trails."""

from nicegui import ui

from frontend.theme import (
    CLS_SECTION_HEADER,
    CLS_BREADCRUMB_LINK,
    CLS_BREADCRUMB_SEP,
    CLS_BREADCRUMB_CURRENT,
    CLS_BREADCRUMB_ROW,
)


def section_header(text: str):
    ui.label(text).classes(CLS_SECTION_HEADER)


def breadcrumb(*parts: tuple[str, str | None]):
    """Render a breadcrumb trail.

    Each *part* is ``(label, href)`` — if *href* is ``None`` the part is
    rendered as plain text (the current page).
    """
    with ui.row().classes(CLS_BREADCRUMB_ROW):
        for i, (label, href) in enumerate(parts):
            if i > 0:
                ui.label("/").classes(CLS_BREADCRUMB_SEP)
            if href is not None:
                ui.link(label, href).classes(CLS_BREADCRUMB_LINK)
            else:
                ui.label(label).classes(CLS_BREADCRUMB_CURRENT)