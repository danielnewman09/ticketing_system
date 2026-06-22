"""Requirements page — dialog classes for HLR/LLR operations.

Each dialog encapsulates its own UI, validation, API call, and
notifications.  All accept an ``on_done`` callback that fires after
a successful action so the page can re-fetch and re-render.

All ``show()`` methods are **async** — they must be called from an
async NiceGUI event handler so the slot context is preserved for
UI element creation.  Calling ``show()`` from a sync handler or
via ``asyncio.create_task`` will raise a RuntimeError because the
NiceGUI slot context is lost.
"""

from __future__ import annotations

import asyncio
import logging
import traceback
from collections.abc import Callable

from nicegui import ui

from frontend_migrated.theme import (
    CLS_DIALOG_SM,
    CLS_DIALOG_MD,
    CLS_DIALOG_TITLE,
    CLS_DIALOG_ACTIONS,
)
from frontend_migrated.data.hlr import (
    create_hlr,
    delete_hlr,
    decompose_hlr,
    design_single_hlr,
)
from frontend_migrated.data.llr import create_llr
from frontend_migrated.data.components import fetch_components


class CreateHLRDialog:
    """Dialog for creating a new high-level requirement."""

    def __init__(self, on_done: Callable | None = None):
        self._on_done = on_done
        self._dialog = None
        self._desc = None
        self._comp = None

    async def show(self):
        """Build and open the dialog.  Must be called from an async handler."""
        components = await asyncio.to_thread(fetch_components)
        comp_names = ["(none)"] + [c.name for c in components]

        self._dialog = ui.dialog()
        with self._dialog, ui.card().classes(CLS_DIALOG_MD):
            ui.label("Create HLR").classes(CLS_DIALOG_TITLE)
            self._desc = ui.textarea("Description").classes("w-full")
            self._comp = ui.select(comp_names, value="(none)", label="Component").classes("w-full")
            with ui.row().classes(CLS_DIALOG_ACTIONS):
                ui.button("Cancel", on_click=self._dialog.close).props("flat")
                ui.button("Create", on_click=self._on_create).props("color=positive")

        self._dialog.open()

    async def _on_create(self):
        desc = self._desc.value.strip()
        if not desc:
            ui.notify("Description is required", type="warning")
            return
        comp_name = self._comp.value if self._comp.value != "(none)" else None
        new_refid = await asyncio.to_thread(create_hlr, desc, comp_name)
        short_id = new_refid[:8] + "…" if len(new_refid) > 8 else new_refid
        self._dialog.close()
        ui.notify(f"Created HLR {short_id}", type="positive")
        if self._on_done:
            self._on_done()


def _short_refid(refid: str) -> str:
    """Return a shortened display form of a hex refid."""
    if refid and len(refid) > 8:
        return f"{refid[:8]}…"
    return refid


class DeleteHLRDialog:
    """Confirmation dialog before deleting an HLR."""

    def __init__(self, hlr_refid: str, on_done: Callable | None = None):
        self._hlr_refid = hlr_refid
        self._on_done = on_done
        self._dialog = None

    async def show(self):
        """Build and open the dialog.  Must be called from an async handler."""
        self._dialog = ui.dialog()
        with self._dialog, ui.card().classes(CLS_DIALOG_SM):
            ui.label(f"Delete HLR {_short_refid(self._hlr_refid)}?").classes("text-lg font-bold")
            ui.label(
                "This will also delete all child LLRs and their verifications."
            ).classes("text-sm text-gray-400 mt-1")
            with ui.row().classes(CLS_DIALOG_ACTIONS):
                ui.button("Cancel", on_click=self._dialog.close).props("flat")
                ui.button("Delete", on_click=self._on_delete).props("color=negative")

        self._dialog.open()

    async def _on_delete(self):
        await asyncio.to_thread(delete_hlr, self._hlr_refid)
        self._dialog.close()
        ui.notify(f"Deleted HLR {_short_refid(self._hlr_refid)}", type="negative")
        if self._on_done:
            self._on_done()


class DecomposeHLRDialog:
    """Confirmation dialog before running the decomposition agent."""

    def __init__(self, hlr_refid: str, on_done: Callable | None = None):
        self._hlr_refid = hlr_refid
        self._on_done = on_done
        self._dialog = None

    async def show(self):
        """Build and open the dialog.  Must be called from an async handler."""
        self._dialog = ui.dialog()
        with self._dialog, ui.card().classes(CLS_DIALOG_MD):
            ui.label(f"Decompose HLR {_short_refid(self._hlr_refid)}?").classes("text-lg font-bold")
            ui.label(
                "This will run the decomposition agent to generate low-level "
                "requirements and verification methods."
            ).classes("text-sm text-gray-400 mt-1")
            with ui.row().classes(CLS_DIALOG_ACTIONS):
                ui.button("Cancel", on_click=self._dialog.close).props("flat")
                ui.button("Decompose", on_click=self._on_decompose).props("color=primary")

        self._dialog.open()

    async def _on_decompose(self):
        self._dialog.close()
        ui.notify("Decomposing — this may take a moment…", type="info")
        try:
            result = await asyncio.to_thread(decompose_hlr, self._hlr_refid)
            llrs = result.get("llrs_created", 0)
            vms = result.get("verifications_created", 0)
            ui.notify(
                f"Created {llrs} LLRs and {vms} verifications",
                type="positive",
            )
        except Exception as e:
            logging.getLogger(__name__).error("Decomposition failed for HLR %s:\n%s", self._hlr_refid, traceback.format_exc())
            ui.notify(f"Decomposition failed: {e}", type="negative")
        if self._on_done:
            self._on_done()


class DesignHLRDialog:
    """Confirmation dialog before running the design agent."""

    def __init__(self, hlr_refid: str, on_done: Callable | None = None):
        self._hlr_refid = hlr_refid
        self._on_done = on_done
        self._dialog = None

    async def show(self):
        """Build and open the dialog.  Must be called from an async handler."""
        self._dialog = ui.dialog()
        with self._dialog, ui.card().classes(CLS_DIALOG_MD):
            ui.label(f"Design HLR {_short_refid(self._hlr_refid)}?").classes("text-lg font-bold")
            ui.label(
                "This will run the design agent to generate an OO design "
                "and ontology graph from the requirements."
            ).classes("text-sm text-gray-400 mt-1")
            with ui.row().classes(CLS_DIALOG_ACTIONS):
                ui.button("Cancel", on_click=self._dialog.close).props("flat")
                ui.button("Design", on_click=self._on_design).props("color=secondary")

        self._dialog.open()

    async def _on_design(self):
        self._dialog.close()
        ui.notify("Designing — this may take a moment…", type="info")
        try:
            result = await asyncio.to_thread(design_single_hlr, self._hlr_refid)
            updated = result.get('nodes_updated', 0)
            created = result.get('nodes_created', 0)
            verifs = result.get('verifications_resolved', 0)
            links = result.get('links_applied', 0)
            scaffold_cleaned = result.get('scaffold_cleaned', 0)
            ui.notify(
                f"Design complete: {updated} scaffold nodes promoted to design, "
                f"{created} new nodes, "
                f"{verifs} verifications preserved, "
                f"{links} COMPOSES links"
                + (f", {scaffold_cleaned} scaffold cleaned" if scaffold_cleaned else ""),
                type="positive",
            )
        except NotImplementedError:
            ui.notify(
                "Design agent not yet migrated to backend_migrated",
                type="warning",
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            ui.notify(f"Design failed: {e}", type="negative")
        if self._on_done:
            self._on_done()


class AddLLRDialog:
    """Dialog for adding a low-level requirement to an HLR."""

    def __init__(self, hlr_refid: str, on_done: Callable | None = None):
        self._hlr_refid = hlr_refid
        self._on_done = on_done
        self._dialog = None
        self._desc = None

    async def show(self):
        """Build and open the dialog.  Must be called from an async handler."""
        self._dialog = ui.dialog()
        with self._dialog, ui.card().classes(CLS_DIALOG_MD):
            ui.label(f"Add LLR to HLR {_short_refid(self._hlr_refid)}").classes(CLS_DIALOG_TITLE)
            self._desc = ui.textarea("Description").classes("w-full")
            with ui.row().classes(CLS_DIALOG_ACTIONS):
                ui.button("Cancel", on_click=self._dialog.close).props("flat")
                ui.button("Create", on_click=self._on_create).props("color=positive")

        self._dialog.open()

    async def _on_create(self):
        desc = self._desc.value.strip()
        if not desc:
            ui.notify("Description is required", type="warning")
            return
        new_refid = await asyncio.to_thread(create_llr, self._hlr_refid, desc)
        short_id = new_refid[:8] + "…" if len(new_refid) > 8 else new_refid
        self._dialog.close()
        ui.notify(f"Created LLR {short_id}", type="positive")
        if self._on_done:
            self._on_done()