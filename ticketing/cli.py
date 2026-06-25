"""``ticketing-dashboard`` CLI entry point.

Launches the requirements dashboard for a *project directory*, reusing
codegraph's per-project Neo4j container configuration.

Usage::

    # from inside a project that has a .doxygen-index.toml
    ticketing-dashboard

    # pointing at an external project (e.g. the codegraph repo itself)
    ticketing-dashboard --project-dir ../codegraph

    # skip automatic Neo4j container management (use an external DB)
    ticketing-dashboard --no-start

    # development mode with auto-reload
    ticketing-dashboard --reload

    # stop a running dashboard (finds the process by port)
    ticketing-dashboard --stop --port 8082

The CLI resolves the project name and Neo4j settings from
``.doxygen-index.toml`` (or ``.codegraph.toml``) via
:func:`codegraph.docker.load_container_config`, ensures the
project-local ``neo4j-<project>`` container is running, loads the
project's ``.env`` so ``codegraph.config`` connects to *that* container,
and finally starts the NiceGUI dashboard with a project-local SQLite
database under ``<project_dir>/.ticketing/``.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import sys
import time
from pathlib import Path

log = logging.getLogger("ticketing.cli")


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Construct the ``ticketing-dashboard`` argument parser."""
    parser = argparse.ArgumentParser(
        prog="ticketing-dashboard",
        description=(
            "Launch the Ticketing System requirements dashboard for a "
            "project directory. Reads .doxygen-index.toml (via codegraph) "
            "to resolve the project name and Neo4j backend."
        ),
    )
    parser.add_argument(
        "--project-dir",
        default=".",
        help="Project root containing .doxygen-index.toml or .codegraph.toml "
        "(default: current directory).",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind host for the dashboard (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8082,
        help="Bind port for the dashboard (default: 8082).",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Parent directory for dashboard logs (default: "
        "<project_dir>/.ticketing).",
    )
    parser.add_argument(
        "--log-dir",
        default=None,
        help="Log directory (default: <data_dir>/logs).",
    )
    parser.add_argument(
        "--no-start",
        action="store_true",
        help="Do not start/verify the project's Neo4j container. Use this "
        "when Neo4j is already running or managed externally.",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable NiceGUI auto-reload (development).",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Open a browser tab on startup.",
    )
    parser.add_argument(
        "--stop",
        action="store_true",
        help="Stop a running dashboard instance by finding the process "
        "listening on --host/--port.",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose CLI logging.",
    )
    return parser


# ---------------------------------------------------------------------------
# Neo4j container bootstrap
# ---------------------------------------------------------------------------


def _ensure_neo4j_container(project_dir: Path) -> str:
    """Ensure the project's Neo4j container is running; return project name.

    Leverages codegraph's per-project container configuration.  If
    Docker is unavailable, we warn and fall back to whatever
    ``NEO4J_*`` environment is already set — the dashboard can still
    run against an external Neo4j instance.
    """
    from codegraph.persistence.docker import (
        docker_available,
        load_container_config,
        start_container,
        update_env_file,
    )

    cfg = load_container_config(project_dir)

    if not docker_available():
        log.warning(
            "Docker is not available — not managing the %s container. "
            "Ensure NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD are set (e.g. in "
            "%s/.env) or pass --no-start to silence this.",
            cfg.container_name,
            project_dir,
        )
        # Still make sure the .env (if present) will be honoured.
        return cfg.project_name

    # Make sure the project's .env reflects the container's connection
    # info even if the container is already running.
    update_env_file(cfg)
    start_container(cfg, wait=True)
    return cfg.project_name


def _is_port_open(host: str, port: int) -> bool:
    """Return True if *something* is listening on *host:port*."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1.0)
    try:
        sock.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _find_listener_pids(port: int) -> list[int]:
    """Find PIDs of processes listening on *port*.

    Iterates over accessible processes and checks their network
    connections.  This avoids ``psutil.net_connections()`` which
    requires root on macOS.

    In reload mode this returns the child worker; the caller should
    walk parents to find the reloader.
    """
    import psutil

    pids: list[int] = []
    for proc in psutil.process_iter(["pid"]):
        try:
            for conn in proc.net_connections(kind="inet"):
                if conn.status != psutil.CONN_LISTEN:
                    continue
                if conn.laddr and conn.laddr.port == port:
                    pids.append(proc.pid)
                    break  # one match per process is enough
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    return pids


def _is_ticketing_process(proc) -> bool:
    """Heuristic: does *proc* look like the ticketing dashboard?

    Matches Python processes whose command line references the
    ticketing dashboard, nicegui, or uvicorn.  This avoids matching
    shells whose working directory merely contains "ticketing".
    """
    import psutil

    try:
        parts = proc.cmdline()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False
    if not parts:
        return False
    # Must be a Python process.
    exe = parts[0].lower()
    if "python" not in exe:
        return False
    cmdline = " ".join(parts)
    return any(kw in cmdline for kw in ("ticketing", "nicegui", "uvicorn"))


def _stop_dashboard(host: str, port: int) -> int:
    """Stop a running dashboard instance listening on *host:port*.

    Discovery is port-based: we find the process (or its parent, in
    reload mode) that is listening on *port*, verify it looks like the
    ticketing dashboard, then send SIGTERM and wait up to 10 s for
    graceful shutdown.  If the process does not exit, we escalate to
    SIGKILL.

    Returns:
        0 on success, 1 if no dashboard was running, 2 on error.
    """
    import psutil

    # 1. Liveness check — is anything listening on the port at all?
    if not _is_port_open(host, port):
        print(
            f"Nothing is listening on {host}:{port} — dashboard is not running.",
            file=sys.stderr,
        )
        return 1

    # 2. Find the PID(s) listening on the port.
    listener_pids = _find_listener_pids(port)
    if not listener_pids:
        print(
            f"Port {port} is open but no listener PID found (permissions?). "
            "Try running as the same user that started the dashboard.",
            file=sys.stderr,
        )
        return 2

    # 3. Build the set of PIDs to signal.  In --reload mode the listener
    #    is the child worker; we need its parent (the uvicorn reloader)
    #    so the whole process tree exits cleanly.
    targets: list[psutil.Process] = []
    for pid in listener_pids:
        try:
            proc = psutil.Process(pid)
        except psutil.NoSuchProcess:
            continue
        if not _is_ticketing_process(proc):
            print(
                f"Process {pid} is listening on port {port} but does not look "
                f"like the ticketing dashboard (cmdline: {' '.join(proc.cmdline())}).",
                file=sys.stderr,
            )
            return 2
        targets.append(proc)

    # Walk up to the topmost parent that is also a ticketing/python process.
    # This catches the uvicorn reloader parent in --reload mode.  Always
    # include the original listener PID even if a parent is found.
    final_pids: list[int] = []
    for proc in targets:
        top = proc
        try:
            for parent in proc.parents():
                if _is_ticketing_process(parent):
                    top = parent
                else:
                    break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        if top.pid not in final_pids:
            final_pids.append(top.pid)
        # Also include the listener PID itself in case the parent is
        # the reloader and doesn’t propagate the signal to the child.
        if proc.pid not in final_pids:
            final_pids.append(proc.pid)

    # 4. SIGTERM the targets (parent first so the reloader cleans up children).
    for pid in final_pids:
        print(f"Stopping ticketing-dashboard (PID {pid})...", file=sys.stderr)
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass

    # 5. Wait up to 10 s for the port to free up (graceful shutdown).
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if not _is_port_open(host, port):
            print("Dashboard stopped.", file=sys.stderr)
            return 0
        time.sleep(0.25)

    # 6. Escalate to SIGKILL.
    print("Dashboard did not stop gracefully — sending SIGKILL.", file=sys.stderr)
    for pid in final_pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass

    # Give it a moment to die.
    time.sleep(0.5)
    print("Dashboard stopped.", file=sys.stderr)
    return 0


def _resolve_project_name(project_dir: Path) -> str:
    """Resolve just the project name from the TOML config (no Docker)."""
    from codegraph.persistence.docker import load_container_config

    return load_container_config(project_dir).project_name


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI dispatch for ``ticketing-dashboard``."""
    if argv is None:
        argv = sys.argv[1:]

    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s — %(message)s",
    )

    project_dir = Path(args.project_dir).resolve()
    if not project_dir.is_dir():
        print(f"Error: project directory not found: {project_dir}", file=sys.stderr)
        return 2

    # ── Stop mode: find and stop the dashboard by port ──
    if args.stop:
        return _stop_dashboard(args.host, args.port)

    # 1. Load the project's .env and sync codegraph.config BEFORE any
    #    codegraph import freezes a stale database_url. If the container
    #    was started previously, the .env already has the right NEO4J_*.
    from ticketing.app import sync_neo4j_config

    sync_neo4j_config(project_dir)

    # 2. Resolve project name + (optionally) start the Neo4j container.
    #    This must happen before importing ticketing.app's backend, because
    #    the app module imports backend_migrated.connection → codegraph.config,
    #    which reads NEO4J_* at import time. The container bootstrap writes
    #    those values into the project's .env.
    try:
        if args.no_start:
            project_name = _resolve_project_name(project_dir)
            log.info(
                "Project '%s' (Neo4j container management skipped).",
                project_name,
            )
        else:
            project_name = _ensure_neo4j_container(project_dir)
            log.info(
                "Project '%s' — Neo4j container ready.",
                project_name,
            )
    except SystemExit as exc:
        # codegraph's load_container_config calls sys.exit on missing
        # config — surface a clean error instead of a traceback.
        return int(exc.code or 1)

    # 3. Re-sync: start_container may have just written new NEO4J_* to the
    #    project's .env. codegraph.config was imported during step 2, so
    #    we must refresh its frozen database_url from the now-current env.
    sync_neo4j_config(project_dir)

    # 4. Launch the dashboard. The app factory syncs the config again
    #    (idempotent) right before importing the migrated backend.
    from ticketing.app import run_dashboard

    run_dashboard(
        project_dir,
        project_name,
        data_dir=args.data_dir,
        log_dir=args.log_dir,
        host=args.host,
        port=args.port,
        reload=args.reload,
        show=args.show,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())