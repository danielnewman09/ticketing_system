"""HLR detail page — stub."""

from nicegui import ui


@ui.page("/hlr/{hlr_id}")
async def hlr_detail_page(hlr_id: int):
    """STUB: HLR detail page showing requirements, LLR table, and graph."""
    raise NotImplementedError(f"hlr_detail_page({hlr_id}) — requires data layer reimplementation")