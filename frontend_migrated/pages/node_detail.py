"""Ontology node detail page — stub."""

from nicegui import ui


@ui.page("/ontology/node/{qualified_name:path}")
async def node_detail_page(qualified_name: str):
    """STUB: Ontology node detail page showing properties, references, and members."""
    raise NotImplementedError(f"node_detail_page({qualified_name}) — requires data layer reimplementation")