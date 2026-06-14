"""Screenshot tests for agent-decomposed requirements.

Loads the decomposition data from ``tests/agents/__data__/`` and renders
the HLR card, each LLR, and each verification method as screenshots.

These tests depend on the agent integration tests having run first
(to produce the artifact data).  If artifacts are missing, they skip.

Run::

    pytest tests/agents_ui/ -v -s
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from tests.agents_ui.conftest import (
    AGENT_DATA_DIR,
    SCREENSHOT_DIR,
    _build_requirements_data,
)


# ---------------------------------------------------------------------------
# Helper: high-res page creation
# ---------------------------------------------------------------------------

def _new_hi_res_page(browser, width=2560, height=1800):
    """Create a new page at 2× DPI for detailed screenshots."""
    context = browser.new_context(
        viewport={"width": width, "height": height},
        device_scale_factor=2,
    )
    return context.new_page()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.screenshot
class TestAgentRequirementScreenshots:
    """Screenshot tests that render agent-decomposed requirements in the UI.

    These tests depend on ``tests/agents/__data__/decompose_hlr/06_raw_response.json``
    being present (i.e. the agent integration test has run).  If the file
    is missing or contains an error, the tests are skipped.
    """

    def test_requirements_dashboard_screenshot(self, screenshot_server, decompose_hlr_data, screenshot_dir):
        """Capture a full-page screenshot of the /requirements dashboard with decomposed data."""
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = _new_hi_res_page(browser)

            page.goto(f"{screenshot_server}/requirements", wait_until="networkidle")
            page.wait_for_timeout(2000)  # let async content finish rendering

            # Expand the first HLR's LLR section
            hlr_card = page.locator(".q-card").filter(has_text="HLR test::HLR-AGENT-1")
            expansion = hlr_card.locator(".q-expansion-item")
            if expansion.count() > 0:
                expansion.click()
                page.wait_for_timeout(500)

            path = screenshot_dir / "agent_requirements_dashboard.png"
            page.screenshot(path=str(path), full_page=True)
            print(f"  Screenshot: {path}")

            browser.close()

    def test_hlr_card_screenshot(self, screenshot_server, decompose_hlr_data, screenshot_dir):
        """Capture a screenshot of the HLR card with its LLR table expanded."""
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = _new_hi_res_page(browser)

            page.goto(f"{screenshot_server}/requirements", wait_until="networkidle")
            page.wait_for_timeout(2000)

            # Find and expand the HLR card — use the specific badge text
            hlr_card = page.locator(".q-card").filter(has_text="HLR test::HLR-AGENT-1")
            expansion = hlr_card.locator(".q-expansion-item")
            if expansion.count() > 0:
                expansion.click()
                page.wait_for_timeout(500)

            path = screenshot_dir / "agent_hlr_card_expanded.png"
            hlr_card.screenshot(path=str(path))
            print(f"  Screenshot: {path}")

            browser.close()

    def test_individual_llr_screenshots(self, screenshot_server, decompose_hlr_data, screenshot_dir):
        """Capture individual screenshots of each LLR's verification details.

        Navigates to the /requirements page and captures each LLR card.
        Since the current UI shows LLRs in a table (not as separate cards),
        this test captures the full page showing all LLRs.
        """
        llrs = decompose_hlr_data.get("low_level_requirements", [])
        if not llrs:
            pytest.skip("No LLRs in decomposition data")

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = _new_hi_res_page(browser)

            page.goto(f"{screenshot_server}/requirements", wait_until="networkidle")
            page.wait_for_timeout(2000)

            # Expand the HLR's LLR section
            hlr_card = page.locator(".q-card").filter(has_text="HLR")
            expansion = hlr_card.locator(".q-expansion-item")
            if expansion.count() > 0:
                expansion.click()
                page.wait_for_timeout(500)

            # Save the full page showing all LLRs
            path = screenshot_dir / "agent_llr_table.png"
            page.screenshot(path=str(path), full_page=True)
            print(f"  Screenshot: {path}")

            browser.close()

    def test_verification_detail_screenshots(self, screenshot_server, decompose_hlr_data, screenshot_dir):
        """Capture verification method detail screenshots.

        Clicks into the LLR detail page for each LLR in the decomposition
        and screenshots the verification cards.
        """
        llrs = decompose_hlr_data.get("low_level_requirements", [])
        if not llrs:
            pytest.skip("No LLRs in decomposition data")

        # Count total verifications
        total_vms = sum(len(llr.get("verifications", [])) for llr in llrs)
        if total_vms == 0:
            pytest.skip("No verification methods in decomposition data")

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = _new_hi_res_page(browser)

            page.goto(f"{screenshot_server}/requirements", wait_until="networkidle")
            page.wait_for_timeout(2000)

            # Expand the HLR's LLR section
            hlr_card = page.locator(".q-card").filter(has_text="HLR")
            expansion = hlr_card.locator(".q-expansion-item")
            if expansion.count() > 0:
                expansion.click()
                page.wait_for_timeout(500)

            # Full page screenshot showing verification methods in the LLR table
            path = screenshot_dir / "agent_verification_details.png"
            page.screenshot(path=str(path), full_page=True)
            print(f"  Screenshot: {path}")

            browser.close()

    def test_decomposition_summary(self, screenshot_dir, decompose_hlr_data):
        """Save a summary JSON of the decomposition alongside the screenshots."""
        summary = {
            "description": decompose_hlr_data.get("description", "")[:200],
            "num_llrs": len(decompose_hlr_data.get("low_level_requirements", [])),
            "total_verifications": sum(
                len(llr.get("verifications", []))
                for llr in decompose_hlr_data.get("low_level_requirements", [])
            ),
            "llr_summaries": [
                {
                    "description": llr.get("description", "")[:120],
                    "verifications": len(llr.get("verifications", [])),
                }
                for llr in decompose_hlr_data.get("low_level_requirements", [])
            ],
        }
        path = screenshot_dir / "agent_decomposition_summary.json"
        path.write_text(json.dumps(summary, indent=2))
        print(f"  Summary: {path}")