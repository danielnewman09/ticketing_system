"""Shared fixtures for agent UI screenshot tests.

Provides:

- ``agent_data_dir``: Path to ``tests/agents/__data__/``.
- ``decompose_hlr_data``: Parsed JSON from the agent test artifacts.
- ``screenshot_server``: NiceGUI subprocess with mock requirements data
  derived from the agent decomposition.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Data directory — agent artifacts
# ---------------------------------------------------------------------------

AGENT_DATA_DIR = Path(__file__).resolve().parents[1] / "agents" / "__data__"
SCREENSHOT_DIR = Path(__file__).parent / "__screenshots__"


# ---------------------------------------------------------------------------
# Helpers — construct mock requirements data from LLM decomposition output
# ---------------------------------------------------------------------------

def _build_requirements_data(raw_decomposition: dict, *, component: str = "") -> dict:
    """Build a ``fetch_requirements_data()`` dict from the raw LLM decomposition.

    Takes the ``DecomposedRequirement`` JSON (the parsed result saved as
    ``06_raw_response.json``) and constructs the dict that the requirements
    page expects.  Each verification stub is converted from the LLM's
    flat format (``preconditions``/``actions``/``postconditions``) to the
    nested ``composes`` format that the UI renders.
    """
    hlr_id = "test::HLR-AGENT-1"
    hlr = {
        "refid": hlr_id,
        "id": hlr_id,
        "description": raw_decomposition["description"],
        "component": component or None,
        "name": "",
        "layer": "design",
        "tags": ["design"],
        "source": "",
        "llrs": [],
    }

    for i, llr_data in enumerate(raw_decomposition.get("low_level_requirements", [])):
        llr_id = f"test::LLR-AGENT-{i+1}"
        llr = {
            "refid": llr_id,
            "id": llr_id,
            "description": llr_data["description"],
            "name": "",
            "layer": "design",
            "tags": ["design"],
            "source": "",
            "hlr_id": hlr_id,
            "composes": [],
        }

        for v in llr_data.get("verifications", []):
            vm = {
                "type": "VerificationMethod",
                "refid": f"test::VM-AGENT-{i+1}-{len(llr['composes'])+1}",
                "name": "",
                "method": v.get("method", ""),
                "test_name": v.get("test_name", ""),
                "description": v.get("description", ""),
                "layer": "design",
                "source": "",
                "preconditions": v.get("preconditions", []),
                "actions": v.get("actions", []),
                "postconditions": v.get("postconditions", []),
            }
            llr["composes"].append(vm)

        hlr["llrs"].append(llr)

    return {
        "hlrs": [hlr],
        "unlinked_llrs": [],
        "total_hlrs": 1,
        "total_llrs": len(hlr["llrs"]),
        "total_verifications": sum(len(v.get("verifications", [])) for v in raw_decomposition.get("low_level_requirements", [])),
        "total_nodes": 0,
        "total_triples": 0,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def decompose_hlr_data():
    """Load the raw decomposition JSON from agent test artifacts.

    Skips if the artifact doesn't exist (agent tests haven't been run).
    """
    path = AGENT_DATA_DIR / "decompose_hlr" / "06_raw_response.json"
    if not path.exists():
        pytest.skip("No agent artifact — run tests/agents/ first")
    raw = json.loads(path.read_text())
    if "description" not in raw:
        pytest.skip("Agent artifact is not a valid decomposition — run tests/agents/ first")
    return raw


@pytest.fixture(scope="session")
def screenshot_server(decompose_hlr_data):
    """Start a NiceGUI server with the decomposed HLR data mocked in.

    The server patches ``fetch_requirements_data`` to return the
    decomposed HLR from the agent test artifacts, then starts on
    port 19001.

    Yields the base URL (e.g. ``http://localhost:19001``).
    """
    from tests.ui.mocks import make_component, make_llr_dict
    from tests.ui.conftest import PATCH_TARGETS as P

    # Build mock data from the decomposition
    requirements_data = _build_requirements_data(
        decompose_hlr_data,
        component="Calculation Engine",
    )

    # Mock components for the sidebar
    mock_components = [
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

    # Start the server subprocess
    server_script = Path(__file__).parent / "_screenshot_server.py"
    port = 19001
    env = {**os.environ, "NICEGUI_SCREEN_TEST_PORT": str(port)}

    # Pass the mock data via environment variable (JSON-encoded)
    env["AGENT_REQUIREMENTS_DATA"] = json.dumps(requirements_data)

    proc = subprocess.Popen(
        [sys.executable, str(server_script)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )

    # Wait for server to respond
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://localhost:{port}/requirements", timeout=1)
            break
        except (urllib.error.URLError, ConnectionRefusedError):
            if proc.poll() is not None:
                stdout, stderr = proc.communicate(timeout=5)
                raise RuntimeError(
                    f"Server exited ({proc.returncode}):\n"
                    f"stderr: {stderr.decode()}\nstdout: {stdout.decode()}"
                )
            time.sleep(0.5)
    else:
        proc.terminate()
        raise RuntimeError(f"Server on port {port} did not start within 30s")

    yield f"http://localhost:{port}"

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture()
def screenshot_dir() -> Path:
    """Return the screenshot output directory, creating it if needed."""
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    return SCREENSHOT_DIR