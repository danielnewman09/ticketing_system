"""Ticketing System — installable dashboard package.

This package provides the ``ticketing-dashboard`` CLI entry point and
the :func:`run_dashboard` factory that launches the NiceGUI
requirements dashboard for an arbitrary *project directory*.

Per-project behaviour
----------------------
The dashboard is designed to be instantiated from a project that
already uses *codegraph* for its Neo4j backend.  When launched with a
``--project-dir`` (default: the current working directory), it:

1. Reads the project's ``.doxygen-index.toml`` (or ``.codegraph.toml``)
   via :func:`codegraph.docker.load_container_config` to resolve the
   project name and Neo4j container settings.
2. Ensures the project-local Neo4j container (``neo4j-<project>``) is
   running — leveraging codegraph's per-project backend configuration.
3. Loads the project's ``.env`` (written by ``codegraph-db start``) so
   that ``NEO4J_URI`` / ``NEO4J_USER`` / ``NEO4J_PASSWORD`` point at
   that container.
4. Creates a project-local log directory under
   ``<project_dir>/.ticketing/`` for the dashboard's rotating logs.
5. Seeds the migrated ``ProjectMeta`` Neo4j singleton with the project
   name from the TOML config.

The dashboard uses the **migrated** backend exclusively —
:mod:`backend_migrated` (neomodel nodes via :mod:`codegraph.connection`)
and :mod:`frontend_migrated` (UI pages). There is no SQLite layer in
this path; all requirements, components, and project metadata live as
Neo4j nodes in the project-local container.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]