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

# -- Project data --

MOCK_PROJECT_META = {
    "name": "Calculator",
    "description": "Core calculation engine for engineering tasks",
    "working_directory": "/home/dev/projects/Calculator",
    "refid": "test::Calculator",
}

MOCK_ENV_DATA = [
    {
        "name": "C++",
        "version": "20",
        "dependencies": [
            {
                "refid": "conan::boost",
                "id": "conan::boost",
                "name": "boost",
                "github_url": "https://github.com/boostorg/boost",
                "version": "1.82.0",
                "is_dev": False,
                "manager_name": "conan",
                "index_file_patterns": "*.h *.hpp",
                "index_subdir": "",
                "index_exclude_patterns": "",
                "index_recursive": True,
                "tags": ["integrated"],
                "components": [{"name": "Calculator"}, {"name": "UI"}],
            },
            {
                "refid": "conan::eigen",
                "id": "conan::eigen",
                "name": "eigen",
                "github_url": "https://gitlab.com/libeigen/eigen",
                "version": "3.4.0",
                "is_dev": False,
                "manager_name": "conan",
                "index_file_patterns": "*.h",
                "index_subdir": "Eigen",
                "index_exclude_patterns": "",
                "index_recursive": True,
                "tags": ["indexed"],
                "components": [{"name": "Calculator"}],
            },
            {
                "refid": "conan::fmt",
                "id": "conan::fmt",
                "name": "fmt",
                "github_url": "https://github.com/fmtlib/fmt",
                "version": "10.2.1",
                "is_dev": True,
                "manager_name": "conan",
                "index_file_patterns": "*.h",
                "index_subdir": "fmt",
                "index_exclude_patterns": "",
                "index_recursive": False,
                "tags": ["missing"],
                "components": [],
            },
        ],
        "build_systems": [],
        "test_frameworks": [],
        "dependency_managers": [],
    },
]

MOCK_REQUIREMENTS_DATA_FOR_PROJECT = {
    "hlrs": [],
    "unlinked_llrs": [],
    "total_hlrs": 5,
    "total_llrs": 12,
    "total_verifications": 8,
    "total_nodes": 23,
    "total_triples": 47,
}

# ---------------------------------------------------------------------------
# Apply patches BEFORE importing page modules
# ---------------------------------------------------------------------------

# -- Mock ontology graph data (from integration_test_graph.json) --

import json
from pathlib import Path as _Path

# Build Cytoscape-formatted graph data from the test fixture
# by deserializing into a LayerGraph and converting.
_DATA_DIR = _Path(__file__).parent.parent / "data"

try:
    from codegraph.graph import LayerGraph
    from frontend_migrated.graph.format import layer_graph_to_cytoscape

    _graph_json_path = _DATA_DIR / "integration_test_graph.json"
    with open(_graph_json_path) as _f:
        _graph_data = json.load(_f)
    _layer_graph = LayerGraph.deserialize(_graph_data)
    _cytoscape_raw = layer_graph_to_cytoscape(_layer_graph)

    # Filter out edges whose source or target doesn't exist as a Cytoscape node.
    # Cytoscape fails if edges reference non-existent node IDs.
    # Collapsed members (methods, attributes) emit edges but aren't
    # separate Cy nodes, and FileNode targets are also omitted.
    _node_ids = {n["data"]["id"] for n in _cytoscape_raw["nodes"]}
    _cytoscape_data = {
        "nodes": _cytoscape_raw["nodes"],
        "edges": [
            e for e in _cytoscape_raw["edges"]
            if e["data"]["source"] in _node_ids and e["data"]["target"] in _node_ids
        ],
    }
except Exception:
    # Fallback: minimal empty graph if deserialization fails
    _cytoscape_data = {"nodes": [], "edges": []}


MOCK_ONTOLOGY_GRAPH_DATA = _cytoscape_data

MOCK_NODE_DETAIL = {
    "properties": {
        "name": "CalculatorEngine",
        "qualified_name": "calc::CalculatorEngine",
        "kind": "class",
        "layer": "design",
        "source": "calculator",
        "component_id": None,
        "visibility": "public",
        "description": "The core calculator engine class that performs arithmetic operations.",
        "brief_description": "The core calculator engine class",
        "type_signature": "",
        "argsstring": "",
        "definition": "",
        "file_path": "",
        "line_number": None,
        "source_type": "",
        "is_static": False,
        "is_const": False,
        "is_virtual": False,
        "is_abstract": False,
        "is_final": False,
        "specialization": "",
    },
    "outgoing": [
        {"rel": "DEPENDS_ON", "target_qn": "calc::CalculatorResult", "target_name": "CalculatorResult", "target_labels": ["ClassNode"]},
        {"rel": "REALIZES", "target_qn": "calc::ICalculator", "target_name": "ICalculator", "target_labels": ["InterfaceNode"]},
    ],
    "incoming": [],
    "implemented_by": [],
    "members": [
        {"name": "add", "qualified_name": "calc::CalculatorEngine::add", "kind": "method", "visibility": "public", "type_signature": "CalculatorResult", "argsstring": "(double a, double b)"},
        {"name": "validateInput", "qualified_name": "calc::CalculatorEngine::validateInput", "kind": "method", "visibility": "public", "type_signature": "bool", "argsstring": "(string input)"},
        {"name": "precision", "qualified_name": "calc::CalculatorEngine::precision", "kind": "attribute", "visibility": "public", "type_signature": "int"},
    ],
    "codebase_members": [],
    "available_types": [],
}

MOCK_DEPS_LINKS = {"nodes": [], "edges": []}

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
    # Project page — stats
    patch(P["fetch_project_meta"], return_value=MOCK_PROJECT_META),
    patch(P["fetch_project_meta_route"], return_value=MOCK_PROJECT_META),
    patch(P["fetch_requirements_data_sections"], return_value=MOCK_REQUIREMENTS_DATA_FOR_PROJECT),
    patch(P["fetch_components_sections"], return_value=MOCK_COMPONENTS),
    # Project page — dependencies
    patch(P["fetch_environment_data"], return_value=MOCK_ENV_DATA),
    patch(P["delete_dependency_dep"], side_effect=NotImplementedError("stub")),
    patch(P["update_dependency_index_config"], side_effect=NotImplementedError("stub")),
    # Project page — route-level syncs (must not hit Neo4j)
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

# -- Mock ProjectFileTree for dependencies and scaffold --

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

from nicegui import ui  # noqa: E402 — must import after patches are applied

import frontend_migrated.pages  # noqa: F401, E402 — register @ui.page routes

PORT = int(os.environ.get("NICEGUI_PORT", "19000"))

if __name__ == "__main__":
    ui.run(port=PORT, show=False, reload=False, title="UI Screenshot Server")