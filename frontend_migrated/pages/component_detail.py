"""Component detail page — stub."""

from nicegui import ui


@ui.page("/component/{component_id}")
async def component_detail_page(component_id: int):
    """STUB: Component detail page showing environment, dependencies, and ontology nodes."""
    raise NotImplementedError(f"component_detail_page({component_id}) — requires data layer reimplementation")