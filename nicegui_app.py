#!/usr/bin/env python
"""
NiceGUI frontend — requirements dashboard.

Run with:
    source .venv/bin/activate
    python nicegui_app.py

Then visit http://127.0.0.1:8081
"""

from dotenv import load_dotenv
load_dotenv()

import atexit
import logging
import os
from logging.handlers import RotatingFileHandler

# Configure file logging before any app imports so all backend/frontend
# loggers are captured from the moment they're first instantiated.
_LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(_LOG_DIR, exist_ok=True)
_file_handler = RotatingFileHandler(
    os.path.join(_LOG_DIR, "app.log"),
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8",
)
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
))
for _name in ("backend", "frontend", "agents", "__main__"):
    _logger = logging.getLogger(_name)
    _logger.addHandler(_file_handler)
    _logger.setLevel(logging.DEBUG)
    _logger.propagate = False

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

    log.info("Starting NiceGUI Application...")

    ui.run(
        title="Ticketing System",
        port=8081,
        reload=True,
        show=False,
    )
