"""Project homepage — project settings and scaffold."""

import asyncio
import os
import subprocess

from nicegui import ui

from frontend.theme import apply_theme
from frontend.layout import page_layout
from frontend.data import (
    fetch_project_meta,
    update_project_meta,
    fetch_requirements_data,
    fetch_pending_recommendations_summary,
    fetch_environment_data,
)


@ui.page("/")
async def project_page():
    apply_theme()
    page_layout("Project")

    # ---------------------------------------------------------------
    # Project metadata section
    # ---------------------------------------------------------------

    @ui.refreshable
    async def project_meta_section():
        meta = await asyncio.to_thread(fetch_project_meta)

        with ui.card().classes("w-full mx-2 mt-4").style(
            "background: #1e293b; border-left: 4px solid #5c7cfa;"
        ):
            with ui.row().classes("w-full items-start justify-between"):
                with ui.column().classes("flex-1 gap-1"):
                    ui.label(meta["name"] or "Untitled Project").classes(
                        "text-lg font-bold"
                    )
                    if meta["description"]:
                        ui.label(meta["description"]).classes(
                            "text-sm text-gray-400"
                        )
                    if meta["working_directory"]:
                        with ui.row().classes("items-center gap-1"):
                            ui.icon("folder", size="xs").classes("text-gray-500")
                            ui.label(meta["working_directory"]).classes(
                                "text-xs text-blue-400 font-mono cursor-pointer"
                            ).tooltip("Open in VS Code").on(
                                "click", lambda d=meta["working_directory"]: open_in_vscode(d)
                            )
                ui.button(icon="edit", on_click=lambda: show_edit_project_dialog(meta)).props(
                    "flat round size=sm"
                )

    async def show_edit_project_dialog(meta: dict):
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
                    def on_select(path: str):
                        dir_input.value = path

                    picker = directory_picker(
                        initial_path=dir_input.value,
                        on_select=on_select,
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
                    project_meta_section.refresh()

                ui.button("Save", on_click=do_save).props("color=primary")

        dialog.open()

    await project_meta_section()

    # ---------------------------------------------------------------
    # Quick stats
    # ---------------------------------------------------------------

    meta = await asyncio.to_thread(fetch_project_meta)
    project_dir = os.path.join(meta["working_directory"], meta["name"]) if meta["working_directory"] and meta["name"] else ""

    data = await asyncio.to_thread(fetch_requirements_data)

    with ui.row().classes("w-full gap-4 flex-wrap px-2 mt-4"):
        from frontend.layout import stat_card
        stat_card("HLRs", data["total_hlrs"], "blue-5")
        stat_card("LLRs", data["total_llrs"], "green-5")
        stat_card("Components", len(set(
            h["component"] for h in data["hlrs"] if h["component"]
        )), "teal-5")
        stat_card("Ontology Nodes", data["total_nodes"], "purple-5")

    # ---------------------------------------------------------------
    # Dependency management
    # ---------------------------------------------------------------

    env_data = await asyncio.to_thread(fetch_environment_data)
    if env_data:
        with ui.card().classes("w-full mx-2 mt-4"):
            ui.label("Dependency Management").classes("text-sm font-semibold mb-2")
            for lang in env_data:
                with ui.row().classes("w-full items-start gap-4 flex-wrap"):
                    version_str = f" {lang['version']}" if lang["version"] else ""
                    ui.badge(f"{lang['name']}{version_str}", color="blue").classes("text-xs")
                    for bs in lang["build_systems"]:
                        ui.badge(f"{bs['name']}", color="grey").classes("text-xs")
                    for tf in lang["test_frameworks"]:
                        ui.badge(f"{tf['name']}", color="grey").classes("text-xs")

                if lang["dependencies"]:
                    conan_deps = _get_conan_deps(project_dir) if project_dir else set()
                    for dep in lang["dependencies"]:
                        integrated = dep["name"].lower() in conan_deps
                        with ui.row().classes("w-full items-center gap-2 mt-1 ml-2"):
                            version = f"=={dep['version']}" if dep["version"] else ""
                            color = "grey" if not dep["is_dev"] else "orange"
                            ui.badge(
                                f"{dep['name']}{version}", color=color,
                            ).classes("text-xs font-mono")
                            if integrated:
                                ui.badge("integrated", color="positive").classes("text-xs")
                            elif project_dir:
                                ui.badge("not in build", color="negative").classes("text-xs")
                                ui.button(
                                    "Integrate", icon="add_circle",
                                    on_click=lambda _, d=dep: open_integrate_dialog(d),
                                ).props("flat size=xs").classes("text-blue-400")

            # Conan files
            if project_dir:
                conan_files = _scan_conan_files(project_dir)
                if conan_files:
                    ui.separator().classes("my-2")
                    _render_file_tree(conan_files, project_dir)

    # ---------------------------------------------------------------
    # Integrate dependency dialog
    # ---------------------------------------------------------------

    with ui.dialog() as integrate_dialog, ui.card().classes("w-[480px]"):
        ui.label("Integrate Dependency").classes("text-lg font-bold mb-2")
        ui.label(
            "This will run the add-conan-dependency skill to create a Conan recipe "
            "and wire the dependency into your build."
        ).classes("text-sm text-gray-400 mb-3")

        int_dep_label = ui.label("").classes("text-sm font-semibold")
        int_source_url = ui.input("Source URL (git repo or download)").classes("w-full")
        int_version = ui.input("Version / git tag").classes("w-full")
        int_consuming_lib = ui.input(
            "Consuming library (which project lib uses this)",
        ).classes("w-full")

        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button("Cancel", on_click=integrate_dialog.close).props("flat size=sm")
            ui.button(
                "Integrate", icon="build",
                on_click=lambda: run_integrate(),
            ).props("color=primary size=sm")

    _integrate_dep = {"name": ""}

    def open_integrate_dialog(dep: dict):
        _integrate_dep["name"] = dep["name"]
        int_dep_label.text = f"Dependency: {dep['name']}"
        int_version.value = dep.get("version", "")
        int_source_url.value = dep.get("github_url", "")
        int_consuming_lib.value = ""
        integrate_dialog.open()

    async def run_integrate():
        dep_name = _integrate_dep["name"]
        source_url = int_source_url.value.strip()
        version = int_version.value.strip()
        consuming_lib = int_consuming_lib.value.strip()

        if not source_url:
            ui.notify("Source URL is required", type="warning")
            return
        if not version:
            ui.notify("Version is required", type="warning")
            return
        if not consuming_lib:
            ui.notify("Consuming library is required", type="warning")
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

            skill_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "skills", "add-conan-dependency",
            )

            result = await asyncio.to_thread(
                run_skill,
                skill_dir=skill_dir,
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

    # ---------------------------------------------------------------
    # Pending recommendations alert
    # ---------------------------------------------------------------

    pending = await asyncio.to_thread(fetch_pending_recommendations_summary)
    if pending:
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

    # ---------------------------------------------------------------
    # Scaffold section
    # ---------------------------------------------------------------

    scaffolded = _project_exists(meta["working_directory"], meta["name"])

    with ui.card().classes("w-full mx-2 mt-4"):
        with ui.row().classes("w-full items-center justify-between"):
            with ui.column().classes("gap-0"):
                ui.label("Project Scaffold").classes("text-sm font-semibold")
                if scaffolded:
                    ui.label("Project has been scaffolded").classes(
                        "text-xs text-green-400"
                    )
                else:
                    ui.label("Generate the C++ project skeleton").classes(
                        "text-xs text-gray-400"
                    )
            if scaffolded:
                with ui.row().classes("gap-2 items-center"):
                    ui.badge("Created", color="positive").classes("text-xs")
                    ui.button(
                        "Open in VS Code", icon="open_in_new",
                        on_click=lambda: open_in_vscode(project_dir),
                    ).props("flat size=sm").classes("text-blue-400")
            else:
                ui.button(
                    "Create Scaffold", icon="construction",
                    on_click=lambda: open_scaffold_dialog(),
                ).props("color=primary size=sm")

        # Show project file tree when scaffolded
        if scaffolded and project_dir:
            ui.separator().classes("my-2")
            tree = await asyncio.to_thread(_scan_project_tree, project_dir)
            _render_file_tree(tree, project_dir)

    async def open_scaffold_dialog():
        from frontend.data import fetch_components_options
        components = await asyncio.to_thread(fetch_components_options)
        # Filter out "Environment" and its children
        lib_names = [
            c["name"] for c in components
            if c["name"] != "Environment" and not c["name"].startswith("Environment:")
        ]
        libs_input.value = ", ".join(lib_names)
        scaffold_dialog.open()

    # ---------------------------------------------------------------
    # Scaffold dialog
    # ---------------------------------------------------------------

    with ui.dialog() as scaffold_dialog, ui.card().classes("w-[480px]"):
        ui.label("Create Project Scaffold").classes("text-lg font-bold mb-2")
        ui.label(
            "This will generate a complete C++ project skeleton in the working directory. "
            "The project name and directory come from your project settings above."
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
                on_click=lambda: run_scaffold(),
            ).props("color=primary size=sm")

    async def run_scaffold():
        meta = await asyncio.to_thread(fetch_project_meta)
        if not meta["name"]:
            ui.notify("Set a project name first", type="warning")
            return
        if not meta["working_directory"]:
            ui.notify("Set a working directory first", type="warning")
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
                skill_dir=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "skills", "cpp-project-scaffold"),
                project_name=meta["name"],
                libraries=libraries,
                working_directory=meta["working_directory"],
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


def _project_exists(working_directory: str, project_name: str) -> bool:
    """Check if the scaffold has already been created."""
    if not working_directory or not project_name:
        return False
    project_dir = os.path.join(working_directory, project_name)
    return os.path.isfile(os.path.join(project_dir, "CMakeLists.txt"))


def open_in_vscode(path: str):
    """Open a directory or file in VS Code."""
    try:
        subprocess.Popen(["code", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        try:
            subprocess.Popen(
                ["open", "-a", "Visual Studio Code", path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            ui.notify("Could not open VS Code", type="warning")


def open_file_in_vscode(project_dir: str, file_path: str):
    """Open a specific file in an existing VS Code window for the project."""
    full_path = os.path.join(project_dir, file_path)
    try:
        # --goto opens in existing window; -r reuses the window for the folder
        subprocess.Popen(
            ["code", "--goto", full_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        try:
            subprocess.Popen(
                ["open", "-a", "Visual Studio Code", full_path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            ui.notify("Could not open VS Code", type="warning")


_IGNORED_DIRS = {"build", ".git", "__pycache__", ".venv", "installs", ".vscode", "node_modules"}
_CMAKE_FILES = {"CMakeLists.txt", "CMakeUserPresets.json"}
_CONAN_FILES = {"conanfile.py", "conanfile.txt"}


def _scan_filtered_tree(root: str, allowed_files: set[str], rel: str = "") -> list[dict]:
    """Scan directory tree, returning only files matching allowed_files."""
    full = os.path.join(root, rel) if rel else root
    try:
        items = sorted(os.listdir(full))
    except OSError:
        return []

    dirs = []
    files = []
    for name in items:
        path = os.path.join(full, name)
        rel_path = os.path.join(rel, name) if rel else name
        if os.path.isdir(path) and name not in _IGNORED_DIRS and not name.startswith("."):
            children = _scan_filtered_tree(root, allowed_files, rel_path)
            if children:
                dirs.append({"name": name, "path": rel_path, "is_dir": True, "children": children})
        elif name in allowed_files:
            files.append({"name": name, "path": rel_path, "is_dir": False})

    return dirs + files


def _scan_project_tree(root: str) -> list[dict]:
    return _scan_filtered_tree(root, _CMAKE_FILES)


def _scan_conan_files(root: str) -> list[dict]:
    """Scan for conanfile.py/txt at root + full conan/ directory contents."""
    entries = []
    for name in _CONAN_FILES:
        if os.path.isfile(os.path.join(root, name)):
            entries.append({"name": name, "path": name, "is_dir": False})
    conan_dir = os.path.join(root, "conan")
    if os.path.isdir(conan_dir):
        children = _scan_all_files(root, "conan")
        if children:
            entries.append({"name": "conan", "path": "conan", "is_dir": True, "children": children})
    return entries


def _scan_all_files(root: str, rel: str) -> list[dict]:
    """Scan a directory recursively, returning all files."""
    full = os.path.join(root, rel)
    try:
        items = sorted(os.listdir(full))
    except OSError:
        return []

    dirs = []
    files = []
    for name in items:
        path = os.path.join(full, name)
        rel_path = os.path.join(rel, name)
        if os.path.isdir(path) and not name.startswith("."):
            children = _scan_all_files(root, rel_path)
            if children:
                dirs.append({"name": name, "path": rel_path, "is_dir": True, "children": children})
        elif not name.startswith("."):
            files.append({"name": name, "path": rel_path, "is_dir": False})

    return dirs + files


def _get_conan_deps(project_dir: str) -> set[str]:
    """Parse conanfile.py to find integrated dependency names (lowercase)."""
    conanfile = os.path.join(project_dir, "conanfile.py")
    if not os.path.isfile(conanfile):
        return set()
    try:
        import re
        with open(conanfile) as f:
            content = f.read()
        # Match self.requires("name/version") and self.build_requires("name/version")
        # Also match requires = "name/version" style
        deps = set()
        for m in re.finditer(r'self\.(?:build_)?requires\(\s*["\']([^/"\'"]+)', content):
            deps.add(m.group(1).lower())
        # Also check conan/ directory for local recipes
        conan_dir = os.path.join(project_dir, "conan")
        if os.path.isdir(conan_dir):
            for name in os.listdir(conan_dir):
                if os.path.isdir(os.path.join(conan_dir, name)):
                    deps.add(name.lower())
        return deps
    except Exception:
        return set()


def _render_file_tree(tree: list[dict], project_dir: str, depth: int = 0):
    """Render a file tree with clickable files and expandable directories."""
    for entry in tree:
        indent = f"padding-left: {depth * 16 + 4}px;"
        if entry["is_dir"]:
            with ui.expansion(
                entry["name"], icon="folder",
            ).classes("w-full").props("dense").style(indent):
                _render_file_tree(entry["children"], project_dir, depth + 1)
        else:
            ui.label(entry["name"]).classes(
                "text-xs font-mono text-blue-400 cursor-pointer py-0.5"
            ).style(indent).on(
                "click",
                lambda _, p=entry["path"]: open_file_in_vscode(project_dir, p),
            ).tooltip(entry["path"])
