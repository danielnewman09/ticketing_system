"""NiceGUI dashboard factory — project-aware application launcher.

Refactors the behaviour of the standalone ``nicegui_app_migrated.py``
script into an importable, parameterised factory so the dashboard can
be instantiated for any project directory from the
``ticketing-dashboard`` CLI.

The factory uses the **migrated** backend exclusively —
:mod:`backend_migrated` (neomodel nodes backed by Neo4j via
:mod:`codegraph.connection`) and :mod:`frontend_migrated` (UI pages,
theme, widgets, agent log).  There is no SQLAlchemy/SQLite layer in
this path; all requirements, components, and project metadata live as
Neo4j nodes.

The factory intentionally **defers** all backend/frontend imports until
:func:`run_dashboard` is called.  This is critical because
:mod:`codegraph.config` reads ``NEO4J_URI`` / ``NEO4J_USER`` /
``NEO4J_PASSWORD`` from the environment **at import time**.  The CLI
must therefore load the project's ``.env`` *before* this module imports
``backend_migrated.connection``.  Deferring the imports keeps that
ordering under the caller's control and makes this module safe to
import in any environment.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

log = logging.getLogger(__name__)

#: Default NiceGUI port.
DEFAULT_PORT = 8082

#: Default bind host.
DEFAULT_HOST = "127.0.0.1"

#: Subdirectory (under the project dir) for dashboard logs.
DEFAULT_DATA_SUBDIR = ".ticketing"


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def resolve_log_dir(
    project_dir: Path | str,
    data_dir: Path | str | None = None,
    log_dir: Path | str | None = None,
) -> Path:
    """Return the log directory, creating it if needed.

    Args:
        project_dir: The project root (containing ``.doxygen-index.toml``).
        data_dir: Parent data dir override; defaults to
            ``<project>/.ticketing``.
        log_dir: Explicit log dir override; defaults to ``<data_dir>/logs``.
    """
    project_dir = Path(project_dir).resolve()
    if log_dir is not None:
        target = Path(log_dir).resolve()
    else:
        parent = Path(data_dir).resolve() if data_dir else project_dir / DEFAULT_DATA_SUBDIR
        target = parent / "logs"
    target.mkdir(parents=True, exist_ok=True)
    return target


# ---------------------------------------------------------------------------
# Neo4j config sync
# ---------------------------------------------------------------------------


def sync_neo4j_config(project_dir: Path | str) -> None:
    """Load the project's ``.env`` and refresh ``codegraph.config``.

    :mod:`codegraph.config` reads ``NEO4J_URI`` / ``NEO4J_USER`` /
    ``NEO4J_PASSWORD`` from the environment **at import time** and
    freezes ``config.database_url``.  If that module is imported before
    the project's ``.env`` is loaded — which happens when the CLI's
    container bootstrap imports ``codegraph.docker`` (and thus
    ``codegraph`` / ``codegraph.config``) — the frozen URL carries an
    empty password and neomodel fails with ``missing key 'credentials'``.

    This helper (re)loads the project ``.env`` with ``override=True``
    and recomputes ``config.database_url`` from the current
    environment so neomodel connects with the correct credentials.
    It is safe to call multiple times.
    """
    project_dir = Path(project_dir).resolve()
    load_dotenv(project_dir / ".env", override=True)

    import codegraph.config as cfg

    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "")
    bolt_host = uri.replace("bolt://", "")

    # Update the module-level values in case other modules captured them
    # by name, and recompute the frozen database_url.
    cfg.NEO4J_URI = uri
    cfg.NEO4J_USER = user
    cfg.NEO4J_PASSWORD = password
    cfg.config.database_url = f"bolt://{user}:{password}@{bolt_host}"
    log.debug("sync_neo4j_config: database_url refreshed for %s", project_dir)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def _configure_logging(log_dir: Path) -> None:
    """Attach a rotating file handler for the migrated backend/frontend loggers."""
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_dir / "dashboard.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-8s %(name)s — %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    for name in ("backend_migrated", "frontend_migrated", "agents", "ticketing", "__main__"):
        logger = logging.getLogger(name)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False


# ---------------------------------------------------------------------------
# Project metadata seeding (Neo4j singleton)
# ---------------------------------------------------------------------------


def _seed_project_meta(project_name: str) -> None:
    """Set the ProjectMeta singleton's name if it is currently blank.

    The migrated backend stores project metadata as a single Neo4j
    node (``refid = 'project'``).  We only fill in a blank name so we
    never clobber a name the user has set through the UI.

    Requires the migrated uniqueness constraint on ``ProjectMeta.refid``
    to exist, so this runs after :func:`_ensure_constraints`.
    """
    try:
        from backend_migrated.models import ProjectMeta
    except Exception:  # pragma: no cover — model import is environment-specific
        log.debug("ProjectMeta seeding skipped (models unavailable)", exc_info=True)
        return

    try:
        node = ProjectMeta.get_singleton()
        if not (node.name or "").strip():
            node.name = project_name
            node.save()
            log.info("Seeded ProjectMeta.name = %r", project_name)
    except Exception:  # pragma: no cover — Neo4j may be unreachable
        log.debug("ProjectMeta seeding failed", exc_info=True)


def _ensure_constraints() -> None:
    """Create migrated-node-type Neo4j constraints/indexes (idempotent)."""
    try:
        from backend_migrated.constraints import ensure_migrated_constraints

        ensure_migrated_constraints()
    except Exception:  # pragma: no cover — Neo4j may be unreachable
        log.debug("Migrated constraint setup skipped", exc_info=True)


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app(
    project_dir: Path | str,
    project_name: str,
    log_dir: Path | str,
) -> "object":
    """Build and return the configured NiceGUI ``app`` object.

    Does **not** call ``ui.run`` — call :func:`run_dashboard` for the
    full lifecycle, or call ``ui.run`` yourself on the returned app.

    Args:
        project_dir: Absolute project root (for reference / seeding).
        project_name: Project name from ``.doxygen-index.toml``.
        log_dir: Directory for rotating log files.
    """
    project_dir = Path(project_dir).resolve()
    log_dir = Path(log_dir).resolve()

    _configure_logging(log_dir)

    # Load the project's .env and refresh codegraph.config.database_url
    # *before* importing backend_migrated.connection (which imports
    # codegraph.config). This guarantees neomodel connects with the
    # project container's credentials even if codegraph.config was
    # imported earlier with a stale/empty password.
    sync_neo4j_config(project_dir)

    # Heavy imports happen *after* the config is synced so codegraph.config
    # picks up the project's Neo4j container connection info.
    from nicegui import app, ui

    from backend_migrated.connection import Neo4jSessionManager

    # Register all @ui.page routes as a side effect of import.
    import frontend_migrated.pages  # noqa: F401

    app.neo4j = Neo4jSessionManager()

    @app.on_startup
    def on_startup() -> None:
        # Ensure the migrated Neo4j constraints/indexes exist before any
        # node operations (e.g. the ProjectMeta singleton seeding below).
        _ensure_constraints()
        try:
            from frontend_migrated.agent_log import install_hooks

            install_hooks()
        except Exception:  # pragma: no cover — optional telemetry
            log.debug("agent_log hooks not installed", exc_info=True)
        _seed_project_meta(project_name)
        log.info(
            "Starting Ticketing dashboard for project '%s' (Neo4j backend)",
            project_name,
        )

    @app.on_shutdown
    def on_shutdown() -> None:
        try:
            app.neo4j.close()
        except Exception:  # pragma: no cover
            pass
        log.info("Neo4j connection closed.")

    return app


def run_dashboard(
    project_dir: Path | str,
    project_name: str,
    *,
    data_dir: Path | str | None = None,
    log_dir: Path | str | None = None,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    reload: bool = False,
    show: bool = False,
) -> None:
    """Instantiate and run the dashboard for *project_dir*.

    Args:
        project_dir: Project root containing ``.doxygen-index.toml``.
        project_name: Project name (from the TOML ``[project].name``).
        data_dir: Project-local data root for logs; defaults to
            ``<project_dir>/.ticketing``.
        log_dir: Log directory; defaults to ``<data_dir>/logs``.
        host: Bind host.
        port: Bind port.
        reload: Enable NiceGUI auto-reload (development).
        show: Auto-open a browser tab.
    """
    project_dir = Path(project_dir).resolve()
    resolved_log_dir = resolve_log_dir(project_dir, data_dir, log_dir)

    create_app(project_dir, project_name, resolved_log_dir)

    from nicegui import ui

    ui.run(
        title=f"Ticketing System — {project_name}",
        host=host,
        port=port,
        reload=reload,
        show=show,
    )