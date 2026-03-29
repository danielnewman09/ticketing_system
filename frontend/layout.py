"""Shared page layout: header, drawer navigation, stat cards."""

from nicegui import ui

_NAV_ITEMS = [
    ("Project", "/"),
    ("Requirements", "/requirements"),
    ("Components", "/components"),
    ("Ontology", "/ontology"),
    ("Ontology Graph", "/ontology/graph"),
]

_PIPELINE_ITEMS = [
    ("Run Demo Pipeline", "/pipeline"),
]


def page_layout(title: str = ""):
    """Create the shared page shell with a left drawer nav."""
    with ui.header().classes("items-center justify-between px-6"):
        with ui.row().classes("items-center gap-4"):
            ui.button(
                icon="menu", on_click=lambda: drawer.toggle()
            ).props("flat round color=white")
            ui.link("Ticketing System", "/").classes(
                "text-white text-lg font-bold no-underline"
            )

        with ui.row().classes("gap-2 hidden md:flex"):
            for label, href in _NAV_ITEMS:
                ui.link(label, href).classes("text-white/80 hover:text-white no-underline text-sm px-2")

    drawer = ui.left_drawer(value=False).classes("bg-[#1a1a2e]").props("width=220 breakpoint=960")
    with drawer:
        ui.label("Navigation").classes("text-white/60 text-xs uppercase tracking-wider px-4 pt-4 pb-2")
        for label, href in _NAV_ITEMS:
            with ui.link(target=href).classes("no-underline"):
                ui.item(label).classes("text-white/90")
        ui.separator().classes("my-2")
        ui.label("Pipeline").classes("text-white/60 text-xs uppercase tracking-wider px-4 pt-2 pb-2")
        for label, href in _PIPELINE_ITEMS:
            with ui.link(target=href).classes("no-underline"):
                ui.item(label).classes("text-white/90")

    return drawer


def stat_card(label: str, value, color: str = "primary"):
    """Compact stat card."""
    with ui.card().classes("p-4 min-w-[140px]"):
        ui.label(str(value)).classes(f"text-3xl font-bold text-{color}")
        ui.label(label).classes("text-xs text-gray-400 uppercase tracking-wider mt-1")
