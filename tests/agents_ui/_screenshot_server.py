"""NiceGUI screenshot server for agent UI tests.

Reads mock requirements data from the ``AGENT_REQUIREMENTS_DATA`` environment
variable (set by the conftest.py fixture) and patches the data layer before
starting the server on port 19001.
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

from tests.ui.mocks import make_component
from tests.ui.conftest import PATCH_TARGETS as P

# ---------------------------------------------------------------------------
# Load requirements data from environment
# ---------------------------------------------------------------------------

_requirements_json = os.environ.get("AGENT_REQUIREMENTS_DATA", "{}")
MOCK_REQUIREMENTS_DATA = json.loads(_requirements_json)

MOCK_COMPONENTS = [
    make_component(name="Environment", refid="test::Environment"),
    make_component(
        name="Calculator",
        refid="test::Calculator",
        namespace="calc::",
        description="Core calculation engine",
        hlr_count=1,
        node_count=10,
        language_name="C++",
        dep_names=["boost", "eigen"],
    ),
]

MOCK_PROJECT_META = {
    "name": "Calculator",
    "description": "Core calculation engine for engineering tasks",
    "working_directory": "/home/dev/projects/Calculator",
    "refid": "test::Calculator",
}

MOCK_ENV_DATA = []
MOCK_DEPS_LINKS = {"nodes": [], "edges": []}

# Minimal ontology graph data (empty graph — we're testing requirements)
MOCK_ONTOLOGY_GRAPH_DATA = {"nodes": [], "edges": []}
MOCK_NODE_DETAIL = {
    "properties": {
        "name": "CalculatorEngine",
        "qualified_name": "calc::CalculatorEngine",
        "kind": "class",
        "layer": "design",
        "source": "calculator",
    },
    "outgoing": [],
    "incoming": [],
    "implemented_by": [],
    "members": [],
    "codebase_members": [],
    "available_types": [],
}

# ---------------------------------------------------------------------------
# Apply patches BEFORE importing page modules
# ---------------------------------------------------------------------------

_patches = [
    # Component pages
    patch(P["fetch_components"], return_value=MOCK_COMPONENTS),
    patch(P["get_component"], return_value=MOCK_COMPONENTS[1]),
    patch(P["add_dependency"], side_effect=NotImplementedError("stub")),
    patch(P["delete_dependency"], side_effect=NotImplementedError("stub")),
    patch(P["fetch_ontology_graph_data"], side_effect=NotImplementedError("stub")),
    patch(P["resolve_node_id_by_qualified_name"], side_effect=NotImplementedError("stub")),
    # Requirements page
    patch(P["fetch_requirements_data"], return_value=MOCK_REQUIREMENTS_DATA),
    # Requirements dialogs — stub mutations
    patch(P["create_hlr"], return_value="test::HLR-NEW"),
    patch(P["delete_hlr"], return_value=True),
    patch(P["decompose_hlr"], return_value={"llrs_created": 2, "verifications_created": 3}),
    patch(P["design_single_hlr"], side_effect=NotImplementedError("stub")),
    patch(P["create_llr"], return_value="test::LLR-NEW"),
    patch(P["fetch_components_for_dialog"], return_value=MOCK_COMPONENTS),
    # Project page
    patch(P["fetch_project_meta"], return_value=MOCK_PROJECT_META),
    patch(P["fetch_project_meta_route"], return_value=MOCK_PROJECT_META),
    patch(P["fetch_requirements_data_sections"], return_value=MOCK_REQUIREMENTS_DATA),
    patch(P["fetch_components_sections"], return_value=MOCK_COMPONENTS),
    # Project dependencies
    patch(P["fetch_environment_data"], return_value=MOCK_ENV_DATA),
    patch(P["delete_dependency_dep"], side_effect=NotImplementedError("stub")),
    patch(P["update_dependency_index_config"], side_effect=NotImplementedError("stub")),
    # Sync hooks
    patch("frontend_migrated.data.tags.sync_all_tags", return_value={"dependencies": 0, "components": 0, "languages": 0, "project": 0}),
    patch("frontend_migrated.data.environment.sync_project_environment", return_value=[]),
    # Project page — scaffold
    patch(P["fetch_project_meta_scaffold"], return_value=MOCK_PROJECT_META),
    patch(P["fetch_components_scaffold"], return_value=MOCK_COMPONENTS),
    # Ontology graph page
    patch(P["fetch_ontology_graph_data_og"], return_value=MOCK_ONTOLOGY_GRAPH_DATA),
    patch(P["fetch_graph_node_detail_og"], return_value=MOCK_NODE_DETAIL),
    patch(P["resolve_node_id_by_qualified_name_og"], return_value=999999),
    patch(P["fetch_design_dependency_links_data_og"], return_value=MOCK_DEPS_LINKS),
]

# Mock ProjectFileTree
_mock_tree = MagicMock()
_mock_tree.cmake_tree.return_value = []
_mock_tree.project_exists = True
_mock_tree.project_dir = "/home/dev/projects/Calculator"
_patches.append(
    patch("frontend_migrated.pages.project.dependencies.ProjectFileTree", return_value=_mock_tree)
)
_patches.append(
    patch("frontend_migrated.pages.project.scaffold.ProjectFileTree", return_value=_mock_tree)
)

for p in _patches:
    p.start()

# ---------------------------------------------------------------------------
# Start the server
# ---------------------------------------------------------------------------

from nicegui import ui  # noqa: E402

import frontend_migrated.pages  # noqa: F401, E402

PORT = int(os.environ.get("NICEGUI_SCREEN_TEST_PORT", os.environ.get("NICEGUI_PORT", "19001")))

if __name__ == "__main__":
    ui.run(port=PORT, show=False, reload=False, title="Agent UI Screenshot Server")