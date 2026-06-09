"""Requirements page — HLR card renderer.

Stateless — takes an HLR dict and callback functions as parameters.
Menu actions are only shown when the corresponding callback is provided.
"""

from __future__ import annotations

from collections.abc import Callable

from nicegui import ui

from frontend_migrated.widgets import render_llr_table


def render_hlr_card(
    hlr,
    *,
    on_add_llr: Callable | None = None,
    on_decompose: Callable | None = None,
    on_design: Callable | None = None,
    on_delete: Callable | None = None,
):
    """Render a single HLR card with action menu.

    Each callback receives ``hlr_refid`` as its only argument and is
    called from the corresponding menu item's ``on_click`` handler.
    Menu items are only rendered when their callback is provided.
    """
    llr_count = len(hlr["llrs"])
    hlr_refid = hlr["refid"]

    with ui.card().classes("w-full mb-2"):
        with ui.row().classes("w-full items-start justify-between"):
            with ui.column().classes("flex-1 gap-0"):
                with ui.row().classes("items-center gap-2"):
                    ui.badge(f"HLR {hlr_refid}", color="blue").props("outline")
                    if hlr["component"]:
                        ui.badge(hlr["component"], color="grey")
                    ui.badge(
                        f"{llr_count} LLR{'s' if llr_count != 1 else ''}",
                        color="green" if llr_count > 0 else "grey",
                    ).classes("text-xs")
                ui.label(hlr["description"]).classes("text-sm mt-1")

            with ui.button(icon="more_vert").props("flat round size=sm"):
                with ui.menu():
                    ui.menu_item(
                        "View Details",
                        on_click=lambda h=hlr_refid: ui.navigate.to(f"/hlr/{h}"),
                    )
                    if on_add_llr:
                        ui.menu_item(
                            "Add LLR",
                            on_click=lambda h=hlr_refid: on_add_llr(h),
                        )
                    if on_decompose:
                        ui.menu_item(
                            "Decompose",
                            on_click=lambda h=hlr_refid: on_decompose(h),
                        )
                    if on_design:
                        ui.menu_item(
                            "Design",
                            on_click=lambda h=hlr_refid: on_design(h),
                        )
                    if on_delete:
                        ui.separator()
                        ui.menu_item(
                            "Delete",
                            on_click=lambda h=hlr_refid: on_delete(h),
                        )

        if hlr["llrs"]:
            with (
                ui.expansion("Low-Level Requirements", icon="list")
                .classes("w-full mt-2")
                .props("dense")
            ):
                render_llr_table(hlr["llrs"])