"""Standalone NiceGUI server for screenshot tests.

This script is launched as a subprocess by the ``screenshot_server``
fixture (defined in ``tests/ui/conftest.py``).  It applies all data-layer
mocks before importing the page modules and then starts the NiceGUI
server on port 19000.

The server stays running until the test fixture terminates the process.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Data-layer mocks
# ---------------------------------------------------------------------------

from tests.ui.mocks import make_component, make_llr_dict
from tests.ui.conftest import PATCH_TARGETS as P

# -- Component data --

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

# -- Requirements data --

MOCK_REQUIREMENTS_DATA = {
    "hlrs": [
        {
            "refid": "test::HLR-1",
            "id": "test::HLR-1",
            "description": "The system shall calculate accurately.",
            "component": "Calculator",
            "llrs": [
                make_llr_dict(refid="test::LLR-1-1", description="Verify addition"),
                make_llr_dict(refid="test::LLR-1-2", description="Verify subtraction"),
            ],
        },
        {
            "refid": "test::HLR-2",
            "id": "test::HLR-2",
            "description": "The system shall display results clearly.",
            "component": None,
            "llrs": [
                make_llr_dict(
                    refid="test::LLR-2-1",
                    description="Verify UI renders output",
                    verification_methods=[
                        {"type": "VerificationMethod", "method": "review"},
                    ],
                ),
            ],
        },
    ],
    "unlinked_llrs": [
        make_llr_dict(refid="test::LLR-ORPHAN", description="Orphaned LLR with no parent"),
    ],
    "total_hlrs": 2,
    "total_llrs": 3,
    "total_verifications": 5,
    "total_nodes": 8,
    "total_triples": 12,
}

# ---------------------------------------------------------------------------
# Apply patches BEFORE importing page modules
# ---------------------------------------------------------------------------

_patches = [
    # Component pages
    patch(P["fetch_components"], return_value=MOCK_COMPONENTS),
    patch(P["get_component"], return_value=MOCK_CALC_DETAIL),
    patch(P["add_dependency"], side_effect=NotImplementedError("stub")),
    patch(P["delete_dependency"], side_effect=NotImplementedError("stub")),
    patch(P["fetch_ontology_graph_data"], side_effect=NotImplementedError("stub")),
    patch(P["resolve_node_id_by_qualified_name"], side_effect=NotImplementedError("stub")),
    # Requirements page (route)
    patch(P["fetch_requirements_data"], return_value=MOCK_REQUIREMENTS_DATA),
    # Requirements page (dialogs) — stub mutations
    patch(P["create_hlr"], return_value="test::HLR-NEW"),
    patch(P["delete_hlr"], return_value=True),
    patch(P["decompose_hlr"], return_value={"llrs_created": 2, "verifications_created": 3}),
    patch(P["design_single_hlr"], side_effect=NotImplementedError("stub")),
    patch(P["create_llr"], return_value="test::LLR-NEW"),
    patch(P["fetch_components_for_dialog"], return_value=MOCK_COMPONENTS),
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