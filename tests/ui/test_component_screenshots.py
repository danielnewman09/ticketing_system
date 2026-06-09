"""Visual screenshot tests for migrated component pages.

Uses Playwright to capture PNG screenshots of pages rendered with
mocked Neo4j data.  Screenshots are written to ``tests/ui/__screenshots__/``
(gitignored) so they can be visually inspected for layout regressions.

The ``screenshot_server`` fixture (session-scoped, defined in conftest.py)
starts a NiceGUI subprocess on port 19000 with all data mocked.

Run with::

    pytest tests/ui/test_component_screenshots.py -v
"""

from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright

from tests.ui.mocks import make_component
from tests.ui.conftest import SCREENSHOT_DIR

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