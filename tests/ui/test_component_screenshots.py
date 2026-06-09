"""Visual screenshot tests for the migrated component pages.

Uses Playwright to capture PNG screenshots of pages rendered with
mocked Neo4j data.  Screenshots are written to ``tests/ui/__screenshots__/``
(gitignored) so they can be visually inspected for layout regressions.

Run with::

    pytest tests/ui/test_component_screenshots.py -v

Each test:
1. Starts a NiceGUI server on port 19000 with all data mocked
2. Uses Playwright to navigate and capture a full-page PNG
3. Screenshots are saved to ``tests/ui/__screenshots__/{test_name}.png``
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import pytest
from playwright.sync_api import sync_playwright

from tests.ui.mocks import make_component
from tests.ui.conftest import PATCH_TARGETS as P, SCREENSHOT_DIR

# ---------------------------------------------------------------------------
# Shared mock data
# ---------------------------------------------------------------------------

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
# Server management
# ---------------------------------------------------------------------------

SERVER_PORT = 19000
_SERVER_SCRIPT = Path(__file__).parent / "_screenshot_server.py"


@pytest.fixture(scope="module")
def screenshot_server():
    """Start the NiceGUI screenshot server as a subprocess.

    The server applies all data-layer patches before importing pages,
    so no Neo4j or database connection is needed.  It listens on
    port 19000 and serves all migrated page routes.

    Yields the base URL (e.g. ``http://localhost:19000``).
    """
    # Start the server subprocess
    # NICEGUI_SCREEN_TEST_PORT must be set so ui.run() doesn't try to read
    # it from os.environ (which raises KeyError inside pytest).
    # Setting it to our chosen port satisfies the check.
    env = {**os.environ, "NICEGUI_SCREEN_TEST_PORT": str(SERVER_PORT)}
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
            urllib.request.urlopen(f"http://localhost:{SERVER_PORT}/components", timeout=1)
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
        raise RuntimeError(f"Server on port {SERVER_PORT} did not start within 20s")

    yield f"http://localhost:{SERVER_PORT}"

    # Cleanup
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


# ---------------------------------------------------------------------------
# Screenshot tests
# ---------------------------------------------------------------------------


@pytest.mark.screenshot
def test_components_list_screenshot(screenshot_server):
    """Capture a full-page screenshot of the /components list page."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        page.goto(f"{screenshot_server}/components", wait_until="networkidle")
        page.wait_for_timeout(1500)  # let async content finish rendering

        SCREENSHOT_DIR.mkdir(exist_ok=True)
        path = SCREENSHOT_DIR / "components_list.png"
        page.screenshot(path=str(path), full_page=True)

        browser.close()
        print(f"  Screenshot: {path}")


@pytest.mark.screenshot
def test_component_detail_screenshot(screenshot_server):
    """Capture a full-page screenshot of the /component/{refid} detail page."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        page.goto(f"{screenshot_server}/component/test::Calculator", wait_until="networkidle")
        page.wait_for_timeout(1500)

        SCREENSHOT_DIR.mkdir(exist_ok=True)
        path = SCREENSHOT_DIR / "component_detail.png"
        page.screenshot(path=str(path), full_page=True)

        browser.close()
        print(f"  Screenshot: {path}")