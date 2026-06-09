"""Dependency review page route — stub."""

from nicegui import ui


@ui.page("/component/{component_id}/dependencies/review")
async def dependency_review_page(component_id: str):
    """STUB: Dependency review page showing recommendations and research."""
    raise NotImplementedError(f"dependency_review_page({component_id}) — requires data layer reimplementation")