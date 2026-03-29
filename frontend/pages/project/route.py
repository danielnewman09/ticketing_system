"""Project homepage route."""

import asyncio
import os

from nicegui import ui

from frontend.theme import apply_theme
from frontend.layout import page_layout
from frontend.data import fetch_project_meta
from frontend.pages.project.sections import (
    section_project_meta,
    section_stats,
    section_dependencies,
    section_pending_recommendations,
    section_scaffold,
)


@ui.page("/")
async def project_page():
    apply_theme()
    page_layout("Project")

    await section_project_meta()

    meta = await asyncio.to_thread(fetch_project_meta)
    project_dir = (
        os.path.join(meta["working_directory"], meta["name"])
        if meta["working_directory"] and meta["name"]
        else ""
    )

    await section_stats()
    await section_dependencies(project_dir)
    await section_pending_recommendations()
    await section_scaffold(meta, project_dir)
