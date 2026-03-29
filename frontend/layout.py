"""Shared page layout: header, drawer navigation, stat cards, agent console."""

import time

from nicegui import ui

from frontend.agent_log import agent_log

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

    # --- Agent console (bottom panel) ---
    _agent_console()

    return drawer


def _agent_console():
    """Collapsible bottom panel showing agent request/response log."""
    with ui.expansion("Agent Console", icon="terminal").classes(
        "w-full fixed bottom-0 left-0 right-0 z-50"
    ).style(
        "background: #0f172a; border-top: 1px solid #334155;"
    ).props("dense") as panel:
        panel.classes("text-gray-300")
        log_widget = ui.log(max_lines=200).classes(
            "w-full h-48 text-xs font-mono"
        ).style("background: #0f172a; color: #94a3b8;")

        last_version = {"v": 0}

        def poll_log():
            current = agent_log.version
            if current == last_version["v"]:
                return
            new_entries = agent_log.entries(since_version=last_version["v"])
            last_version["v"] = current
            for entry in new_entries:
                ts = time.strftime("%H:%M:%S", time.localtime(entry.timestamp))
                kind_tag = {
                    "request": "\u2192 REQ",
                    "response": "\u2190 RES",
                    "turn": "\u21bb TURN",
                    "info": "\u2139 INFO",
                }.get(entry.kind, entry.kind)
                line = f"[{ts}] {kind_tag}  {entry.summary}"
                if entry.detail:
                    # Show first line of detail
                    first_line = entry.detail.split("\n")[0][:120]
                    line += f"  |  {first_line}"
                log_widget.push(line)

        ui.timer(1.0, poll_log)

        with ui.row().classes("w-full justify-end px-2 py-1"):
            ui.button("Clear", on_click=lambda: (agent_log.clear(), log_widget.clear())).props(
                "flat size=xs"
            ).classes("text-gray-500")


def stat_card(label: str, value, color: str = "primary"):
    """Compact stat card."""
    with ui.card().classes("p-4 min-w-[140px]"):
        ui.label(str(value)).classes(f"text-3xl font-bold text-{color}")
        ui.label(label).classes("text-xs text-gray-400 uppercase tracking-wider mt-1")
