"""Directory-picker dialog and its helper functions."""

from pathlib import Path

from nicegui import ui

from frontend.theme import (
    BADGE_COLORS,
    CLS_CARD_FULL,
    CLS_DIALOG_WIDE,
    CLS_DIALOG_TITLE,
    CLS_ROW_JUSTIFY_BETWEEN,
    CLS_TEXT_XS,
    CLS_TEXT_SM,
    CLS_TEXT_MUTED,
    CLS_TEXT_DIM,
    CLS_MONO_XS,
    CLS_MONO_SM,
    CLS_EMPTY_STATE,
    PROPS_ICON_BTN,
    PROPS_ICON_BTN_POSITIVE,
    PROPS_DENSE,
)


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
            with ui.item(on_click=lambda _, p=current.parent: navigate(p)).classes(CLS_CARD_FULL):
                with ui.item_section().props("side"):
                    ui.icon("arrow_upward", size="sm").classes(CLS_TEXT_MUTED)
                with ui.item_section():
                    ui.item_label("..").classes(f"{CLS_MONO_SM} {CLS_TEXT_DIM}")

        if not dirs:
            ui.label("No subdirectories").classes(f"{CLS_EMPTY_STATE} px-4 py-2")
        for d in dirs:
            with ui.item(on_click=lambda _, p=d: navigate(p)).classes(CLS_CARD_FULL):
                with ui.item_section().props("side"):
                    ui.icon("folder", size="sm", color=BADGE_COLORS["folder"])
                with ui.item_section():
                    ui.item_label(d.name).classes(CLS_MONO_SM)


def _add_new_folder_row(state: dict, navigate) -> tuple:
    with ui.row().classes(f"{CLS_CARD_FULL} items-center gap-2 mt-2") as new_folder_row:
        new_folder_input = ui.input("New folder name").classes("flex-1").props(PROPS_DENSE)

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
        ui.button(icon="check", on_click=create_folder).props(PROPS_ICON_BTN_POSITIVE)
        ui.button(
            icon="close",
            on_click=lambda: new_folder_row.set_visibility(False),
        ).props(PROPS_ICON_BTN)
    new_folder_row.set_visibility(False)
    return new_folder_row, new_folder_input


def _add_action_buttons(dialog, state: dict, on_select, show_new_folder) -> None:
    with ui.row().classes(CLS_ROW_JUSTIFY_BETWEEN):
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
         ui.card().classes(CLS_DIALOG_WIDE):
        ui.label("Select Directory").classes(CLS_DIALOG_TITLE)

        path_input = ui.input("Path", value=str(start)).classes(f"{CLS_CARD_FULL} {CLS_MONO_XS}")
        dir_container = ui.column().classes(f"{CLS_CARD_FULL} overflow-auto").style("max-height: 400px;")
        selected_label = ui.label(f"Selected: {start}").classes(
            f"{CLS_MONO_XS} {CLS_TEXT_DIM} mt-2 truncate {CLS_CARD_FULL}"
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