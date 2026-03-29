#!/usr/bin/env python
"""
NiceGUI frontend — requirements dashboard.

Run with:
    source .venv/bin/activate
    python nicegui_app.py

Then visit http://127.0.0.1:8081
"""

import atexit
import logging

from nicegui import ui

from backend.db import init_db
import frontend.pages  # noqa: F401 — registers all @ui.page routes

log = logging.getLogger(__name__)

if __name__ in {"__main__", "__mp_main__"}:
    init_db()

    # Install agent log hooks for the dashboard console
    from frontend.agent_log import install_hooks
    install_hooks()

    # Neo4j constraints (best-effort)
    try:
        from backend.db.neo4j_constraints import ensure_neo4j_constraints
        from backend.db.neo4j import close_driver
        ensure_neo4j_constraints()
        atexit.register(close_driver)
    except Exception:
        log.warning("Neo4j not available at startup — graph features disabled", exc_info=True)

    ui.run(
        title="Ticketing System",
        port=8081,
        reload=True,
        show=False,
    )
