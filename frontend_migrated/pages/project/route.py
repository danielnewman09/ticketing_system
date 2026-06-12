"""Project homepage route — migrated backend.

Uses frontend_migrated data layer and theme to render the project
page. Project metadata is fetched via CodeGraphNode.serialize() through
the migrated ProjectMeta neomodel node.
"""

import asyncio
import os

from nicegui import ui

from frontend_migrated.theme import apply_theme
from frontend_migrated.layout import page_layout
from frontend_migrated.data.environment import sync_project_environment
from frontend_migrated.data.project import fetch_project_meta
from frontend_migrated.pages.project.sections import (
    section_project_meta,
    section_stats,
    section_pending_recommendations,
)
from frontend_migrated.pages.project.dependencies import section_dependencies
from frontend_migrated.pages.project.scaffold import section_scaffold


@ui.page("/")
async def project_page():
    apply_theme()
    page_layout("Project")

    await section_project_meta()

    # fetch_project_meta() returns the serialize() dict from the
    # ProjectMeta neomodel node — {type, name, description,
    # working_directory, edges, refid, source}.
    meta = await asyncio.to_thread(fetch_project_meta)
    project_dir = (
        os.path.join(meta.get("working_directory", ""), meta.get("name", ""))
        if meta.get("working_directory") and meta.get("name")
        else ""
    )

    # Repair any Component nodes that have empty refids (created
    # before the refid-autogeneration fix). Best-effort — don't
    # block the page if it fails.
    try:
        from frontend_migrated.data.components import repair_component_refids
        await asyncio.to_thread(repair_component_refids)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("repair_component_refids failed: %s", exc)

    # Sync project environment from filesystem to Neo4j.
    # This ensures Language, Component, and Dependency nodes exist
    # for any project that has been scaffolded on disk but whose
    # metadata hasn't yet been reflected in the graph database.
    if project_dir:
        try:
            await asyncio.to_thread(sync_project_environment, project_dir)
        except Exception as exc:
            # Sync is best-effort — don't block the page if it fails
            import logging
            logging.getLogger(__name__).warning("sync_project_environment failed: %s", exc)

    await section_stats()
    await section_dependencies(project_dir)
    section_pending_recommendations()
    await section_scaffold(meta, project_dir)