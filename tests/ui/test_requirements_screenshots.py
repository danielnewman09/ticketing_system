"""Visual screenshot tests for the migrated requirements page.

Uses Playwright to capture PNG screenshots of the /requirements page
rendered with mocked Neo4j data.  Screenshots are written to
``tests/ui/__screenshots__/`` (gitignored) so they can be visually
inspected for layout regressions.

The ``screenshot_server`` fixture (session-scoped, defined in conftest.py)
starts a NiceGUI subprocess on port 19000 with all data mocked.

Run with::

    pytest tests/ui/test_requirements_screenshots.py -v
"""

from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright

from tests.ui.conftest import SCREENSHOT_DIR


@pytest.mark.screenshot
def test_requirements_dashboard_screenshot(screenshot_server):
    """Capture a full-page screenshot of the /requirements dashboard."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        page.goto(f"{screenshot_server}/requirements", wait_until="networkidle")
        page.wait_for_timeout(1500)  # let async content finish rendering

        SCREENSHOT_DIR.mkdir(exist_ok=True)
        path = SCREENSHOT_DIR / "requirements_dashboard.png"
        page.screenshot(path=str(path), full_page=True)

        browser.close()
        print(f"  Screenshot: {path}")


@pytest.mark.screenshot
def test_requirements_hlr_expanded_screenshot(screenshot_server):
    """Capture a screenshot with the first HLR's LLR expansion opened.

    The page has multiple ``.q-expansion-item`` elements (Agent Console
    at the top, then one per HLR card that has LLRs).  A naive
    ``.q-expansion-item:first`` would click the Agent Console, not the
    HLR card.  The fix is to scope the selector to the card identified
    by its badge text (``HLR test::HLR-1``) before finding the expansion
    inside it.
    """
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        page.goto(f"{screenshot_server}/requirements", wait_until="networkidle")
        page.wait_for_timeout(1500)

        # Scope to the first HLR card (identified by its badge text) and
        # open its "Low-Level Requirements" expansion.
        hlr_card = page.locator(".q-card").filter(has_text="HLR test::HLR-1")
        expansion = hlr_card.locator(".q-expansion-item")
        expansion.click()
        page.wait_for_timeout(500)  # wait for Quasar expand animation

        # Assert the expansion content is actually visible before capturing.
        content = expansion.locator(".q-expansion-item__content")
        assert content.is_visible(), "LLR expansion did not open"

        SCREENSHOT_DIR.mkdir(exist_ok=True)
        path = SCREENSHOT_DIR / "requirements_hlr_expanded.png"
        page.screenshot(path=str(path), full_page=True)

        browser.close()
        print(f"  Screenshot: {path}")