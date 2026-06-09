"""Standalone NiceGUI server for screenshot tests.

This script is launched as a subprocess by ``test_component_screenshots.py``.
It applies all data-layer mocks before importing the page modules and then
starts the NiceGUI server on the port specified by the ``NICEGUI_PORT``
environment variable (default 19000).

The server stays running until the test fixture terminates the process.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Data-layer mocks
# ---------------------------------------------------------------------------

from tests.ui.mocks import make_component
from tests.ui.conftest import PATCH_TARGETS as P

MOCK_COMPONENTS = [
    make_component(name="Environment", refid="test::Environment"),
    make_component(
        name="Calculator",
        refid="test::Calculator",
        namespace="calc::",
        description="Core calculation engine",
        hlr_count=3,
        node_count=10,
        language_name="C++",
        dep_names=["boost", "eigen"],
    ),
    make_component(
        name="UI",
        refid="test::UI",
        namespace="ui::",
        description="Frontend interface module",
        parent_name="Calculator",
        hlr_count=1,
        node_count=6,
        language_name="Python",
    ),
]

MOCK_CALC_DETAIL = make_component(
    name="Calculator",
    refid="test::Calculator",
    namespace="calc::",
    description="Core calculation engine with **markdown** support.",
    children_names=["MathCore", "Parser"],
    hlr_count=2,
    node_count=8,
    language_name="C++",
    dep_names=["boost", "eigen", "fmt"],
)

# ---------------------------------------------------------------------------
# Apply patches BEFORE importing page modules
# ---------------------------------------------------------------------------

_patches = [
    patch(P["fetch_components"], return_value=MOCK_COMPONENTS),
    patch(P["get_component"], return_value=MOCK_CALC_DETAIL),
    patch(P["add_dependency"], side_effect=NotImplementedError("stub")),
    patch(P["delete_dependency"], side_effect=NotImplementedError("stub")),
    patch(P["fetch_ontology_graph_data"], side_effect=NotImplementedError("stub")),
    patch(P["resolve_node_id_by_qualified_name"], side_effect=NotImplementedError("stub")),
]

for p in _patches:
    p.start()

# ---------------------------------------------------------------------------
# Start the server
# ---------------------------------------------------------------------------

from nicegui import ui  # noqa: E402 — must import after patches are applied

import frontend_migrated.pages  # noqa: F401, E402 — register @ui.page routes

PORT = int(os.environ.get("NICEGUI_PORT", "19000"))

if __name__ == "__main__":
    ui.run(port=PORT, show=False, reload=False, title="UI Screenshot Server")