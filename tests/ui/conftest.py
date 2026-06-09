"""NiceGUI UI test fixtures and patch-target registry.

Provides:

- ``user`` fixture: NiceGUI ``User`` for in-process simulation (no browser).
- ``PATCH_TARGETS``: canonical import-site patch paths for data-layer
  functions, so tests patch at the usage site (not the definition site).
- ``SCREENSHOT_DIR``: output directory for screenshot tests (gitignored).
"""

from __future__ import annotations

from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Screenshot output directory (gitignored)
# ---------------------------------------------------------------------------

SCREENSHOT_DIR = Path(__file__).parent / "__screenshots__"

# ---------------------------------------------------------------------------
# Patch-target registry
# ---------------------------------------------------------------------------
# Patch at the **import site** (the page module), not the definition site
# (the data module), so that ``asyncio.to_thread`` calls see the mock.
# ---------------------------------------------------------------------------

PATCH_TARGETS = {
    # Component list page
    "fetch_components": "frontend_migrated.pages.components.fetch_components",
    # Component detail page
    "get_component": "frontend_migrated.pages.component_detail.get_component",
    "add_dependency": "frontend_migrated.pages.component_detail.add_dependency",
    "delete_dependency": "frontend_migrated.pages.component_detail.delete_dependency",
    "fetch_ontology_graph_data": "frontend_migrated.pages.component_detail.fetch_ontology_graph_data",
    "resolve_node_id_by_qualified_name": "frontend_migrated.pages.component_detail.resolve_node_id_by_qualified_name",
}


# ---------------------------------------------------------------------------
# User fixture (no browser, in-process simulation)
# ---------------------------------------------------------------------------


@pytest.fixture
async def user():
    """Yield a NiceGUI User connected to an in-process app (no browser).

    Uses an empty root function so no database initialisation runs.
    Page routes are registered inside the simulation context after
    ``nicegui_reset_globals`` clears them.
    """
    from nicegui.testing import User, user_simulation

    async with user_simulation(root=lambda: None) as test_user:
        import frontend_migrated.pages  # noqa: F401
        yield test_user