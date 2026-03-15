#!/usr/bin/env python
"""
NiceGUI frontend — requirements dashboard.

Run with:
    source .venv/bin/activate
    python nicegui_app.py

Then visit http://127.0.0.1:8081
"""

from nicegui import ui

from db import init_db
import frontend.pages  # noqa: F401 — registers all @ui.page routes

if __name__ in {"__main__", "__mp_main__"}:
    init_db()
    ui.run(
        title="Ticketing System",
        port=8081,
        reload=True,
        show=False,
    )
