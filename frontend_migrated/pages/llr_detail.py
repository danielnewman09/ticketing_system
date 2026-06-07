"""LLR detail page — stub."""

from nicegui import ui


@ui.page("/llr/{llr_id}")
async def llr_detail_page(llr_id: int):
    """STUB: LLR detail page showing verification methods, conditions, and actions."""
    raise NotImplementedError(f"llr_detail_page({llr_id}) — requires data layer reimplementation")