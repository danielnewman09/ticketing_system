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
    # Project stats (sections.py imports separately)
    "fetch_components_sections": "frontend_migrated.pages.project.sections.fetch_components",
    # Component detail page
    "get_component": "frontend_migrated.pages.component_detail.get_component",
    "add_dependency": "frontend_migrated.pages.component_detail.add_dependency",
    "delete_dependency": "frontend_migrated.pages.component_detail.delete_dependency",
    "fetch_ontology_graph_data": "frontend_migrated.pages.component_detail.fetch_ontology_graph_data",
    "resolve_node_id_by_qualified_name": "frontend_migrated.pages.component_detail.resolve_node_id_by_qualified_name",
    # Requirements page (route)
    "fetch_requirements_data": "frontend_migrated.pages.requirements.route.fetch_requirements_data",
    # Requirements page (dialogs)
    "create_hlr": "frontend_migrated.pages.requirements.dialogs.create_hlr",
    "delete_hlr": "frontend_migrated.pages.requirements.dialogs.delete_hlr",
    "decompose_hlr": "frontend_migrated.pages.requirements.dialogs.decompose_hlr",
    "design_single_hlr": "frontend_migrated.pages.requirements.dialogs.design_single_hlr",
    "create_llr": "frontend_migrated.pages.requirements.dialogs.create_llr",
    "fetch_components_for_dialog": "frontend_migrated.pages.requirements.dialogs.fetch_components",
    # Dependencies page (DependencyPanel)
    "fetch_environment_data": "frontend_migrated.pages.project.dependencies.fetch_environment_data",
    "delete_dependency_dep": "frontend_migrated.pages.project.dependencies.delete_dependency",
    "update_dependency_index_config": "frontend_migrated.pages.project.dependencies.update_dependency_index_config",
    # Project page (sections)
    "fetch_project_meta": "frontend_migrated.pages.project.sections.fetch_project_meta",
    "fetch_project_meta_route": "frontend_migrated.pages.project.route.fetch_project_meta",
    "fetch_requirements_data_sections": "frontend_migrated.pages.project.sections.fetch_requirements_data",
    # Project page (scaffold)
    "fetch_project_meta_scaffold": "frontend_migrated.pages.project.scaffold.fetch_project_meta",
    "fetch_components_scaffold": "frontend_migrated.pages.project.scaffold.fetch_components",
    "project_file_tree_scaffold": "frontend_migrated.pages.project.scaffold.ProjectFileTree",
    # Ontology graph page
    "fetch_ontology_graph_data_og": "frontend_migrated.pages.ontology_graph.fetch_ontology_graph_data",
    "fetch_graph_node_detail_og": "frontend_migrated.pages.ontology_graph.fetch_graph_node_detail",
    "resolve_node_id_by_qualified_name_og": "frontend_migrated.pages.ontology_graph.resolve_node_id_by_qualified_name",
    "fetch_design_dependency_links_data_og": "frontend_migrated.pages.ontology_graph.fetch_design_dependency_links_data",
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


# ---------------------------------------------------------------------------
# Screenshot server fixture (shared by all screenshot test files)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def screenshot_server():
    """Start the NiceGUI screenshot server as a subprocess.

    The server applies all data-layer patches before importing pages,
    so no Neo4j or database connection is needed.  It listens on
    port 19000 and serves all migrated page routes.

    Yields the base URL (e.g. ``http://localhost:19000``).
    """
    import os
    import subprocess
    import sys
    import time
    import urllib.error
    import urllib.request
    from pathlib import Path

    _SERVER_SCRIPT = Path(__file__).parent / "_screenshot_server.py"
    _SERVER_PORT = 19000

    # Start the server subprocess
    env = {**os.environ, "NICEGUI_SCREEN_TEST_PORT": str(_SERVER_PORT)}
    proc = subprocess.Popen(
        [sys.executable, str(_SERVER_SCRIPT)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )

    # Wait for the server to respond
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://localhost:{_SERVER_PORT}/components", timeout=1)
            break
        except (urllib.error.URLError, ConnectionRefusedError):
            if proc.poll() is not None:
                stdout, stderr = proc.communicate(timeout=5)
                raise RuntimeError(
                    f"Server process exited ({proc.returncode}):\n"
                    f"stderr: {stderr.decode()}\n"
                    f"stdout: {stdout.decode()}"
                )
            time.sleep(0.5)
    else:
        proc.terminate()
        raise RuntimeError(f"Server on port {_SERVER_PORT} did not start within 20s")

    yield f"http://localhost:{_SERVER_PORT}"

    # Cleanup
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()