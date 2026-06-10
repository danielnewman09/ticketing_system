"""Components page — list of architectural components with add dialog."""

import asyncio

from nicegui import ui

from frontend_migrated.theme import (
    apply_theme,
    CLS_DIALOG_MD,
    CLS_DIALOG_TITLE,
    CLS_DIALOG_ACTIONS,
)
from frontend_migrated.layout import page_layout
from frontend_migrated.data.components import (
    fetch_components,
    fetch_languages,
    create_component,
)


def _is_environment(comp) -> bool:
    """Check if a component is an environment entry."""
    if comp.name == "Environment":
        return True
    parents = comp.parent.all()
    return any(p.name == "Environment" for p in parents)


def _render_component_card(comp):
    """Render a single component card."""
    with (
        ui.card()
        .classes("w-72 cursor-pointer")
        .on("click", lambda _, c=comp: ui.navigate.to(f"/component/{c.refid}"))
    ):
        with ui.row().classes("items-center justify-between w-full"):
            ui.label(comp.name).classes("text-lg font-semibold")
            langs = comp.language.all()
            if langs:
                ui.badge(langs[0].name, color="grey").classes("text-xs")

        if comp.namespace:
            ui.label(comp.namespace).classes("text-xs text-gray-500 font-mono")

        if comp.description:
            ui.label(comp.description[:80]).classes("text-xs text-gray-400")

        with ui.row().classes("gap-3 mt-2"):
            hlr_count = len(comp.requirements.all())
            with ui.row().classes("items-center gap-1"):
                ui.icon("description", size="xs").classes("text-gray-500")
                ui.label(f"{hlr_count} HLRs").classes("text-xs text-gray-400")
            node_count = len(comp.namespaces.all()) + len(comp.classes.all())
            with ui.row().classes("items-center gap-1"):
                ui.icon("hub", size="xs").classes("text-gray-500")
                ui.label(f"{node_count} nodes").classes("text-xs text-gray-400")


class AddComponentDialog:
    """Dialog for creating a new architectural component.

    Collects name, description, namespace, optional parent and language,
    then saves to Neo4j via :func:`create_component`.
    """

    def __init__(self, on_done=None):
        self._on_done = on_done
        self._dialog = None
        self._name_input = None
        self._desc_input = None
        self._ns_input = None
        self._parent_select = None
        self._lang_select = None
        self._all_components = []
        self._all_languages = []

    async def show(self):
        """Build and open the dialog. Must be called from an async handler."""
        try:
            self._all_components = await asyncio.to_thread(fetch_components)
            self._all_languages = await asyncio.to_thread(fetch_languages)
        except Exception:
            self._all_components = []
            self._all_languages = []

        # Filter out Environment pseudo-components for the parent dropdown
        parent_options = {
            c.refid: c.name
            for c in self._all_components
            if not _is_environment(c)
        }
        # Use a list of strings for language options so new_value_mode="add"
        # works without a key_generator (dict options require one).
        lang_options = [l.name for l in self._all_languages]

        self._dialog = ui.dialog()
        with self._dialog, ui.card().classes(CLS_DIALOG_MD):
            ui.label("Add Component").classes(CLS_DIALOG_TITLE)
            ui.label(
                "Create a new architectural component. Components map to "
                "libraries in the scaffolded project."
            ).classes("text-sm text-gray-400 mb-3")

            self._name_input = ui.input(
                "Name",
                placeholder="e.g. rendering_engine",
            ).classes("w-full")
            self._name_input.props('hint="Required — kebab-case or snake_case"')

            self._desc_input = ui.textarea(
                "Description",
                placeholder="What does this component do?",
            ).classes("w-full")

            self._ns_input = ui.input(
                "Namespace",
                placeholder="e.g. rendering_engine::",
            ).classes("w-full")
            self._ns_input.props('hint="C++ namespace for this component"')

            self._parent_select = ui.select(
                label="Parent component",
                options=parent_options,
                value=None,
                clearable=True,
            ).classes("w-full")
            self._parent_select.props('hint="Optional — for sub-components"')

            self._lang_select = ui.select(
                label="Language",
                options=lang_options,
                value=None,
                clearable=True,
                with_input=True,
                new_value_mode="add",
            ).classes("w-full")
            self._lang_select.props('hint="e.g. C++, Python — type to add a new language"')

            with ui.row().classes(CLS_DIALOG_ACTIONS):
                ui.button("Cancel", on_click=self._dialog.close).props("flat size=sm")
                ui.button(
                    "Create",
                    icon="add",
                    on_click=self._on_create,
                ).props("color=primary size=sm")

        self._dialog.open()

    async def _on_create(self):
        name = self._name_input.value.strip()
        if not name:
            ui.notify("Name is required", type="warning")
            return

        description = self._desc_input.value.strip()
        namespace = self._ns_input.value.strip()
        parent_refid = self._parent_select.value
        language_name = self._lang_select.value

        try:
            comp = await asyncio.to_thread(
                create_component,
                name=name,
                description=description,
                namespace=namespace,
                parent_refid=parent_refid,
                language_name=language_name or None,
            )
            ui.notify(f"Created component \"{comp.name}\"", type="positive")
            self._dialog.close()
            if self._on_done:
                self._on_done()
        except Exception as exc:
            ui.notify(f"Failed to create component: {exc}", type="negative")


@ui.page("/components")
async def components_page():
    """Components overview page."""
    apply_theme()
    page_layout("Components")

    all_components = await asyncio.to_thread(fetch_components)
    arch_components = [c for c in all_components if not _is_environment(c)]

    dialog = AddComponentDialog(
        on_done=lambda: page_refresh.refresh(),
    )

    @ui.refreshable
    async def page_refresh():
        nonlocal all_components, arch_components
        all_components = await asyncio.to_thread(fetch_components)
        arch_components = [c for c in all_components if not _is_environment(c)]

        # --- Architectural Components ---
        with ui.row().classes("w-full items-center justify-between px-2 mt-4 mb-4"):
            ui.label("Components").classes("text-xl font-semibold")
            ui.button(
                "Add Component",
                icon="add",
                on_click=lambda: dialog.show(),
            ).props("outline size=sm color=primary")

        if not arch_components:
            ui.label("No components defined yet.").classes("text-gray-500 px-2")
        else:
            with ui.row().classes("w-full gap-4 flex-wrap px-2"):
                for comp in arch_components:
                    _render_component_card(comp)

    await page_refresh()