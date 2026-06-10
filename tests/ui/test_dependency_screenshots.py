"""Visual screenshot tests for the migrated project dependency management page.

Uses Playwright to capture PNG screenshots of the ``/`` (project) page
rendered with mocked Neo4j data.  Screenshots are written to
``tests/ui/__screenshots__/`` (gitignored) so they can be visually
inspected for layout regressions.

The ``screenshot_server`` fixture (session-scoped, defined in conftest.py)
starts a NiceGUI subprocess on port 19000 with all data mocked.

Run with::

    pytest tests/ui/test_dependency_screenshots.py -v
"""

from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright

from tests.ui.conftest import SCREENSHOT_DIR


@pytest.mark.screenshot
def test_project_page_screenshot(screenshot_server):
    """Capture a full-page screenshot of the project page with dependencies."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        page.goto(f"{screenshot_server}/", wait_until="networkidle")
        page.wait_for_timeout(2000)  # let async content finish rendering

        SCREENSHOT_DIR.mkdir(exist_ok=True)
        path = SCREENSHOT_DIR / "project_dependencies.png"
        page.screenshot(path=str(path), full_page=True)

        browser.close()
        print(f"  Screenshot: {path}")


@pytest.mark.screenshot
def test_dependency_table_screenshot(screenshot_server):
    """Capture a screenshot zoomed into the dependency table.

    The dependency table is inside a card with the header
    'Dependency Management'.  We scope the screenshot to just that
    card to verify column layout, status badges, and action buttons.
    """
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        page.goto(f"{screenshot_server}/", wait_until="networkidle")
        page.wait_for_timeout(2000)

        # Find the dependency management card and capture just that element.
        dep_card = page.locator(".q-card").filter(has_text="Dependency Management")
        assert dep_card.is_visible(), "Dependency Management card not found"

        SCREENSHOT_DIR.mkdir(exist_ok=True)
        path = SCREENSHOT_DIR / "dependency_table.png"
        dep_card.screenshot(path=str(path))

        browser.close()
        print(f"  Screenshot: {path}")