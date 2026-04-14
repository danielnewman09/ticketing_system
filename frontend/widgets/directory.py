"""Directory-picker dialog and its helper functions."""

from pathlib import Path

from nicegui import ui


def _list_dirs(path: Path) -> list[Path]:
    try:
        return sorted(
            [p for p in path.iterdir() if p.is_dir() and not p.name.startswith(".")],
            key=lambda p: p.name.lower(),
        )
    except PermissionError:
        return []


def _render_dir_listing(dir_container, current: Path, navigate) -> None:
    dir_container.clear()
    dirs = _list_dirs(current)
    with dir_container:
        if current.parent != current:
            with ui.item(on_click=lambda _, p=current.parent: navigate(p)).classes("w-full"):
                with ui.item_section().props("side"):
                    ui.icon("arrow_upward", size="sm").classes("text-gray-500")
                with ui.item_section():
                    ui.item_label("..").classes("font-mono text-gray-400")

        if not dirs:
            ui.label("No subdirectories").classes("text-sm text-gray-500 px-4 py-2")
        for d in dirs:
            with ui.item(on_click=lambda _, p=d: navigate(p)).classes("w-full"):
                with ui.item_section().props("side"):
                    ui.icon("folder", size="sm", color="amber")
                with ui.item_section():
                    ui.item_label(d.name).classes("font-mono text-sm")


def _add_new_folder_row(state: dict, navigate) -> tuple:
    with ui.row().classes("w-full items-center gap-2 mt-2") as new_folder_row:
        new_folder_input = ui.input("New folder name").classes("flex-1").props("dense")

        def create_folder():
            name = new_folder_input.value.strip()
            if not name:
                return
            target = state["current"] / name
            try:
                target.mkdir(parents=True, exist_ok=True)
                ui.notify(f"Created {target.name}", type="positive")
                new_folder_input.value = ""
                new_folder_row.set_visibility(False)
                navigate(target)
            except OSError as e:
                ui.notify(f"Failed: {e}", type="negative")

        new_folder_input.on("keydown.enter", create_folder)
        ui.button(icon="check", on_click=create_folder).props("flat round size=sm color=positive")
        ui.button(
            icon="close",
            on_click=lambda: new_folder_row.set_visibility(False),
        ).props("flat round size=sm")
    new_folder_row.set_visibility(False)
    return new_folder_row, new_folder_input


def _add_action_buttons(dialog, state: dict, on_select, show_new_folder) -> None:
    with ui.row().classes("w-full justify-between mt-4"):
        ui.button("New Folder", icon="create_new_folder", on_click=show_new_folder).props(
            "flat size=sm"
        )
        with ui.row().classes("gap-2"):
            ui.button("Cancel", on_click=dialog.close).props("flat")

            def confirm():
                result = str(state["current"])
                dialog.close()
                if on_select:
                    on_select(result)

            ui.button("Select", on_click=confirm).props("color=primary")


def directory_picker(
    initial_path: str = "",
    *,
    on_select: callable = None,
) -> ui.dialog:
    """Open a dialog that browses the server filesystem for a directory.

    Supports navigation, path entry, and creating new folders.
    Calls *on_select(path_str)* when the user confirms.
    """
    start = Path(initial_path).expanduser() if initial_path else Path.home()
    if not start.is_dir():
        start = Path.home()

    state = {"current": start}

    with ui.dialog().props("maximized=false") as dialog, \
         ui.card().classes("w-[540px] max-h-[80vh]"):
        ui.label("Select Directory").classes("text-lg font-bold mb-2")

        path_input = ui.input("Path", value=str(start)).classes("w-full font-mono text-xs")
        dir_container = ui.column().classes("w-full overflow-auto").style("max-height: 400px;")
        selected_label = ui.label(f"Selected: {start}").classes(
            "text-xs text-gray-400 font-mono mt-2 truncate w-full"
        )

        def navigate(path: Path):
            if not path.is_dir():
                ui.notify(f"Not a directory: {path}", type="warning")
                return
            state["current"] = path
            path_input.value = str(path)
            selected_label.text = f"Selected: {path}"
            _render_dir_listing(dir_container, state["current"], navigate)

        path_input.on("keydown.enter", lambda: navigate(Path(path_input.value.strip()).expanduser()))

        new_folder_row, _new_folder_input = _add_new_folder_row(state, navigate)

        _add_action_buttons(dialog, state, on_select, lambda: new_folder_row.set_visibility(True))

        _render_dir_listing(dir_container, state["current"], navigate)

    return dialog