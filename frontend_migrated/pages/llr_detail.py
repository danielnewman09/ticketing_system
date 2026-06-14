"""LLR detail page — detail view for a single low-level requirement.

Uses the LLR's ``refid`` (auto-generated hex UUID) as the URL key.
The route parameter is a string because refids are not integers.
"""

from nicegui import ui


def _short_refid(refid: str) -> str:
    """Return a shortened display form of a hex refid."""
    if refid and len(refid) > 8:
        return f"{refid[:8]}…"
    return refid


@ui.page("/llr/{llr_id}")
async def llr_detail_page(llr_id: str):
    """LLR detail page showing verification methods, conditions, and actions.

    ``llr_id`` is the LLR's ``refid`` — a hex UUID string.
    """
    apply_theme = None  # placeholder — will be imported when implemented
    ui.label(f"LLR {_short_refid(llr_id)} — detail page coming soon").classes("text-xl")