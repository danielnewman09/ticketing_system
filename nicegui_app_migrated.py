#!/usr/bin/env python
"""
Migrated NiceGUI frontend — test dashboard for frontend_migrated/.

This entry point uses the migrated UI modules (theme, widgets, layout,
graph formatting) and registers page routes. Neo4j connectivity is
provided by codegraph.connection via backend_migrated.connection.

Run with:
    source .venv/bin/activate
    python nicegui_app_migrated.py

Then visit http://127.0.0.1:8082
"""

from dotenv import load_dotenv

load_dotenv()

import logging
import os
from logging.handlers import RotatingFileHandler

# Configure file logging before any app imports so all backend/frontend
# loggers are captured from the moment they're first instantiated.
_LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(_LOG_DIR, exist_ok=True)
_file_handler = RotatingFileHandler(
    os.path.join(_LOG_DIR, "migrated_app.log"),
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8",
)
_file_handler.setFormatter(
    logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
)
for _name in ("frontend_migrated", "backend_migrated", "agents", "__main__"):
    _logger = logging.getLogger(_name)
    _logger.addHandler(_file_handler)
    _logger.setLevel(logging.DEBUG)
    _logger.propagate = False

from nicegui import app, ui

from backend_migrated.connection import Neo4jSessionManager

import frontend_migrated.pages  # noqa: F401 — registers all @ui.page routes

log = logging.getLogger(__name__)

app.neo4j = Neo4jSessionManager()


@app.on_startup
def on_startup() -> None:
    from frontend_migrated.agent_log import install_hooks

    install_hooks()
    log.info("Starting Migrated NiceGUI Application (frontend_migrated)...")


@app.on_shutdown
def on_shutdown() -> None:
    app.neo4j.close()
    log.info("Neo4j connection closed.")


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title="Ticketing System (migrated)",
        port=8082,
        reload=True,
        show=False,
    )