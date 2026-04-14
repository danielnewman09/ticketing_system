"""Reusable UI rendering helpers. No DB access — work with plain dicts."""

import asyncio
import json
import logging

from nicegui import ui

from frontend.theme import KIND_COLORS_JS
from frontend.widgets.cytoscape import _EMPTY_GRAPH_HTML, _JS_CLEAR_EMPTY, _JS_INIT_GRAPH
from frontend.widgets.nav import breadcrumb, section_header
from frontend.widgets.directory import directory_picker
from frontend.widgets.cards import (
    render_hlr_card,
    render_llr_table,
    render_triples_card,
    render_verification_card,
)
from frontend.widgets.layouts import (
    card_header_row,
    card_section,
    empty_state,
    render_condition_row,
)
from frontend.widgets.slots import table_action_btn, TABLE_EDIT_BTN, TABLE_DELETE_BTN

log = logging.getLogger(__name__)


async def render_cytoscape_graph(
    elements: list[dict],
    base_styles: str,
    *,
    container_id: str = "cy-container",
    cy_var: str = "_cy",
    layout: str = "fcose",
    animate: bool = True,
    extra_styles: str | None = None,
    timeout: float = 5.0,
):
    """Render a Cytoscape.js graph into a container, with tap/dbltap events.

    The container element must already exist with the given *container_id*.
    Emits ``node_selected`` on tap and ``node_dblclick`` on double-tap.
    *extra_styles* is an optional JS expression for additional style entries
    that get appended to the base styles array.
    """
    if not elements:
        log.debug("Rendering empty graph - clearing container")
        js = _JS_CLEAR_EMPTY.format(
            cy_var=cy_var, container_id=container_id, placeholder_html=_EMPTY_GRAPH_HTML
        )
        async with asyncio.timeout(timeout):
            await ui.run_javascript(js)
        return

    elements_json = json.dumps(elements)
    log.debug(f"Graph data: {len(elements)} elements")
    layout_name = f"window._cyLayout || '{layout}'" if animate else f"'{layout}'"
    animation_opts = "animate: true, animationDuration: 500" if animate else "animate: false"
    styles_expr = base_styles
    if extra_styles:
        styles_expr = f"[...{base_styles}, {extra_styles}]"

    js = _JS_INIT_GRAPH.format(
        container_id=container_id,
        elements_count=len(elements),
        layout=layout,
        cy_var=cy_var,
        kind_colors=KIND_COLORS_JS,
        elements_json=elements_json,
        styles_expr=styles_expr,
        layout_name=layout_name,
        animation_opts=animation_opts,
    )
    async with asyncio.timeout(timeout):
        result = await ui.run_javascript(js)

    if result and not result.get('success'):
        log.error(f"Cytoscape render failed: {result.get('error')}")
        log.error(f"Stack trace: {result.get('stack')}")
        raise RuntimeError(f"Cytoscape render failed: {result.get('error')}")

    log.debug(f"Cytoscape render successful: {result}")


__all__ = [
    "breadcrumb",
    "card_header_row",
    "card_section",
    "directory_picker",
    "empty_state",
    "render_condition_row",
    "render_cytoscape_graph",
    "render_hlr_card",
    "render_llr_table",
    "render_triples_card",
    "render_verification_card",
    "section_header",
    "table_action_btn",
    "TABLE_DELETE_BTN",
    "TABLE_EDIT_BTN",
]