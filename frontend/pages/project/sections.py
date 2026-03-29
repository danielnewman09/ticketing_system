"""Page sections for the project homepage — each renders one card/block."""

import asyncio
import os

from nicegui import ui

from frontend.layout import stat_card
from frontend.data import (
    fetch_project_meta,
    update_project_meta,
    fetch_requirements_data,
    fetch_pending_recommendations_summary,
    fetch_environment_data,
)
from frontend.pages.project.vscode import open_directory, open_file
from frontend.pages.project.file_tree import (
    scan_cmake_tree,
    scan_conan_files,
    get_conan_deps,
    project_exists,
    render_file_tree,
)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
_SCAFFOLD_SKILL = os.path.join(_REPO_ROOT, "skills", "cpp-project-scaffold")
_CONAN_DEP_SKILL = os.path.join(_REPO_ROOT, "skills", "add-conan-dependency")


# ---------------------------------------------------------------------------
# Project metadata
# ---------------------------------------------------------------------------


async def section_project_meta():
    """Project name, description, working directory with edit dialog."""

    @ui.refreshable
    async def card():
        meta = await asyncio.to_thread(fetch_project_meta)
        with ui.card().classes("w-full mx-2 mt-4").style(
            "background: #1e293b; border-left: 4px solid #5c7cfa;"
        ):
            with ui.row().classes("w-full items-start justify-between"):
                with ui.column().classes("flex-1 gap-1"):
                    ui.label(meta["name"] or "Untitled Project").classes("text-lg font-bold")
                    if meta["description"]:
                        ui.label(meta["description"]).classes("text-sm text-gray-400")
                    if meta["working_directory"]:
                        with ui.row().classes("items-center gap-1"):
                            ui.icon("folder", size="xs").classes("text-gray-500")
                            ui.label(meta["working_directory"]).classes(
                                "text-xs text-blue-400 font-mono cursor-pointer"
                            ).tooltip("Open in VS Code").on(
                                "click", lambda d=meta["working_directory"]: open_directory(d)
                            )
                ui.button(
                    icon="edit", on_click=lambda: _show_edit_dialog(meta, card),
                ).props("flat round size=sm")

    await card()


async def _show_edit_dialog(meta: dict, refreshable):
    from frontend.widgets import directory_picker

    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label("Project Settings").classes("text-lg font-bold mb-2")
        name_input = ui.input("Name", value=meta["name"]).classes("w-full")
        desc_input = ui.textarea("Description", value=meta["description"]).classes("w-full")

        with ui.row().classes("w-full items-end gap-2"):
            dir_input = ui.input(
                "Working Directory", value=meta["working_directory"],
            ).classes("flex-1 font-mono")
            dir_input.props("readonly")

            def open_picker():
                picker = directory_picker(
                    initial_path=dir_input.value,
                    on_select=lambda path: setattr(dir_input, "value", path),
                )
                picker.open()

            ui.button(icon="folder_open", on_click=open_picker).props(
                "flat round size=sm"
            ).tooltip("Browse…")

        with ui.row().classes("w-full justify-end gap-2 mt-4"):
            ui.button("Cancel", on_click=dialog.close).props("flat")

            async def do_save():
                await asyncio.to_thread(
                    update_project_meta,
                    name_input.value.strip(),
                    desc_input.value.strip(),
                    dir_input.value.strip(),
                )
                dialog.close()
                ui.notify("Project settings saved", type="positive")
                refreshable.refresh()

            ui.button("Save", on_click=do_save).props("color=primary")

    dialog.open()


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


async def section_stats():
    """Stat cards row."""
    data = await asyncio.to_thread(fetch_requirements_data)
    with ui.row().classes("w-full gap-4 flex-wrap px-2 mt-4"):
        stat_card("HLRs", data["total_hlrs"], "blue-5")
        stat_card("LLRs", data["total_llrs"], "green-5")
        stat_card("Components", len({
            h["component"] for h in data["hlrs"] if h["component"]
        }), "teal-5")
        stat_card("Ontology Nodes", data["total_nodes"], "purple-5")


# ---------------------------------------------------------------------------
# Dependency management
# ---------------------------------------------------------------------------


async def section_dependencies(project_dir: str):
    """Dependency management card with integration status and conan files."""
    env_data = await asyncio.to_thread(fetch_environment_data)
    if not env_data:
        return

    integrate_state = {"name": ""}

    with ui.card().classes("w-full mx-2 mt-4"):
        ui.label("Dependency Management").classes("text-sm font-semibold mb-2")

        for lang in env_data:
            with ui.row().classes("w-full items-start gap-4 flex-wrap"):
                version_str = f" {lang['version']}" if lang["version"] else ""
                ui.badge(f"{lang['name']}{version_str}", color="blue").classes("text-xs")
                for bs in lang["build_systems"]:
                    ui.badge(bs["name"], color="grey").classes("text-xs")
                for tf in lang["test_frameworks"]:
                    ui.badge(tf["name"], color="grey").classes("text-xs")

            if lang["dependencies"]:
                conan_deps = get_conan_deps(project_dir) if project_dir else set()
                for dep in lang["dependencies"]:
                    integrated = dep["name"].lower() in conan_deps
                    with ui.row().classes("w-full items-center gap-2 mt-1 ml-2"):
                        version = f"=={dep['version']}" if dep["version"] else ""
                        color = "grey" if not dep["is_dev"] else "orange"
                        ui.badge(f"{dep['name']}{version}", color=color).classes("text-xs font-mono")
                        if integrated:
                            ui.badge("integrated", color="positive").classes("text-xs")
                        elif project_dir:
                            ui.badge("not in build", color="negative").classes("text-xs")
                            ui.button(
                                "Integrate", icon="add_circle",
                                on_click=lambda _, d=dep: _open_integrate(d),
                            ).props("flat size=xs").classes("text-blue-400")

        if project_dir:
            conan_files = scan_conan_files(project_dir)
            if conan_files:
                ui.separator().classes("my-2")
                render_file_tree(conan_files, project_dir)

    # --- Integrate dialog ---

    with ui.dialog() as integrate_dialog, ui.card().classes("w-[480px]"):
        ui.label("Integrate Dependency").classes("text-lg font-bold mb-2")
        ui.label(
            "Run the add-conan-dependency skill to create a Conan recipe "
            "and wire the dependency into the build."
        ).classes("text-sm text-gray-400 mb-3")

        int_dep_label = ui.label("").classes("text-sm font-semibold")
        int_source_url = ui.input("Source URL (git repo or download)").classes("w-full")
        int_version = ui.input("Version / git tag").classes("w-full")
        int_consuming_lib = ui.input("Consuming library").classes("w-full")

        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button("Cancel", on_click=integrate_dialog.close).props("flat size=sm")
            ui.button(
                "Integrate", icon="build",
                on_click=lambda: _run_integrate(),
            ).props("color=primary size=sm")

    def _open_integrate(dep: dict):
        integrate_state["name"] = dep["name"]
        int_dep_label.text = f"Dependency: {dep['name']}"
        int_version.value = dep.get("version", "")
        int_source_url.value = dep.get("github_url", "")
        int_consuming_lib.value = ""
        integrate_dialog.open()

    async def _run_integrate():
        dep_name = integrate_state["name"]
        source_url = int_source_url.value.strip()
        version = int_version.value.strip()
        consuming_lib = int_consuming_lib.value.strip()

        if not source_url or not version or not consuming_lib:
            ui.notify("All fields are required", type="warning")
            return

        integrate_dialog.close()
        ui.notify(f"Integrating {dep_name} — this may take a few minutes...", type="info")

        try:
            from llm_caller.skill_runner import run_skill
            user_msg = (
                f"Add `{dep_name}` as a locally-built Conan dependency.\n\n"
                f"**Library name:** `{dep_name}`\n"
                f"**Source URL:** `{source_url}`\n"
                f"**Version/tag:** `{version}`\n"
                f"**Consuming library:** `{consuming_lib}`\n\n"
                f"Follow the skill instructions: research the library, create the conan recipe, "
                f"register it, update VS Code tasks, wire into the consuming library, and verify "
                f"the build. Call task_complete when done."
            )
            result = await asyncio.to_thread(
                run_skill,
                skill_dir=_CONAN_DEP_SKILL,
                user_message=user_msg,
                working_directory=project_dir,
            )
            if result.get("build_success"):
                ui.notify(f"{dep_name} integrated and build verified!", type="positive")
            else:
                ui.notify(f"{dep_name} integrated (build not verified)", type="warning")
            ui.navigate.to("/")
        except Exception as e:
            ui.notify(f"Integration failed: {e}", type="negative")


# ---------------------------------------------------------------------------
# Pending recommendations
# ---------------------------------------------------------------------------


async def section_pending_recommendations():
    """Alert bar for pending dependency recommendations."""
    pending = await asyncio.to_thread(fetch_pending_recommendations_summary)
    if not pending:
        return

    with ui.card().classes("w-full mx-2 mt-4").style(
        "background: #1e293b; border-left: 4px solid #f59e0b;"
    ):
        with ui.row().classes("items-center gap-3"):
            ui.icon("science", color="warning", size="sm")
            with ui.column().classes("gap-0 flex-1"):
                ui.label("Dependency recommendations need review").classes(
                    "text-sm font-semibold text-amber-400"
                )
                for p in pending:
                    ui.label(
                        f"{p['component_name']}: {p['pending_count']} pending"
                    ).classes("text-xs text-gray-400")
            for p in pending:
                ui.button(
                    f"Review {p['component_name']}",
                    on_click=lambda _, c=p: ui.navigate.to(
                        f"/component/{c['component_id']}/dependencies/review"
                    ),
                ).props("size=sm color=warning outline")


# ---------------------------------------------------------------------------
# Scaffold
# ---------------------------------------------------------------------------


async def section_scaffold(meta: dict, project_dir: str):
    """Scaffold card with file tree and create/open actions."""
    scaffolded = project_exists(meta["working_directory"], meta["name"])

    with ui.card().classes("w-full mx-2 mt-4"):
        with ui.row().classes("w-full items-center justify-between"):
            with ui.column().classes("gap-0"):
                ui.label("Project Scaffold").classes("text-sm font-semibold")
                if scaffolded:
                    ui.label("Project has been scaffolded").classes("text-xs text-green-400")
                else:
                    ui.label("Generate the C++ project skeleton").classes("text-xs text-gray-400")

            if scaffolded:
                with ui.row().classes("gap-2 items-center"):
                    ui.badge("Created", color="positive").classes("text-xs")
                    ui.button(
                        "Open in VS Code", icon="open_in_new",
                        on_click=lambda: open_directory(project_dir),
                    ).props("flat size=sm").classes("text-blue-400")
            else:
                ui.button(
                    "Create Scaffold", icon="construction",
                    on_click=lambda: _open_scaffold_dialog(),
                ).props("color=primary size=sm")

        if scaffolded and project_dir:
            ui.separator().classes("my-2")
            tree = await asyncio.to_thread(scan_cmake_tree, project_dir)
            render_file_tree(tree, project_dir)

    # --- Scaffold dialog ---

    with ui.dialog() as scaffold_dialog, ui.card().classes("w-[480px]"):
        ui.label("Create Project Scaffold").classes("text-lg font-bold mb-2")
        ui.label(
            "Generate a complete C++ project skeleton in the working directory. "
            "The project name and directory come from project settings."
        ).classes("text-sm text-gray-400 mb-3")

        libs_input = ui.input(
            "Libraries (comma-separated)",
            placeholder="e.g. core, physics, rendering",
        ).classes("w-full")
        deps_input = ui.input(
            "Extra Conan dependencies (optional)",
            placeholder="e.g. eigen/3.4.0, spdlog/1.14.1",
        ).classes("w-full")
        cpp_select = ui.select(
            {20: "C++20", 23: "C++23", 26: "C++26"},
            value=20, label="C++ Standard",
        ).classes("w-full")

        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button("Cancel", on_click=scaffold_dialog.close).props("flat size=sm")
            ui.button(
                "Scaffold", icon="construction",
                on_click=lambda: _run_scaffold(),
            ).props("color=primary size=sm")

    async def _open_scaffold_dialog():
        from frontend.data import fetch_components_options
        components = await asyncio.to_thread(fetch_components_options)
        lib_names = [
            c["name"] for c in components
            if c["name"] != "Environment" and not c["name"].startswith("Environment:")
        ]
        libs_input.value = ", ".join(lib_names)
        scaffold_dialog.open()

    async def _run_scaffold():
        m = await asyncio.to_thread(fetch_project_meta)
        if not m["name"] or not m["working_directory"]:
            ui.notify("Set project name and working directory first", type="warning")
            return

        lib_names = [s.strip() for s in libs_input.value.split(",") if s.strip()]
        if not lib_names:
            ui.notify("Specify at least one library", type="warning")
            return

        libraries = [{"name": name} for name in lib_names]
        extra_deps = [s.strip() for s in deps_input.value.split(",") if s.strip()] or None

        scaffold_dialog.close()
        ui.notify("Scaffolding project — this may take a few minutes...", type="info")

        try:
            from backend.ticketing_agent.design.scaffold_project import scaffold_project
            result = await asyncio.to_thread(
                scaffold_project,
                skill_dir=_SCAFFOLD_SKILL,
                project_name=m["name"],
                libraries=libraries,
                working_directory=m["working_directory"],
                extra_dependencies=extra_deps,
                cpp_standard=cpp_select.value,
            )
            if result.get("build_success"):
                ui.notify("Project scaffolded and build verified!", type="positive")
            else:
                ui.notify("Project scaffolded (build not verified)", type="warning")
            ui.navigate.to("/")
        except Exception as e:
            ui.notify(f"Scaffold failed: {e}", type="negative")
