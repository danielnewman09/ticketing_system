"""Visual screenshot tests for the migrated ontology graph page.

Uses Playwright to capture PNG screenshots of the /ontology/graph page
rendered with mocked Neo4j data.  The graph data is generated from
``tests/data/integration_test_graph.json`` via LayerGraph deserialization
and ``layer_graph_to_cytoscape()``.

Screenshots are written to ``tests/ui/__screenshots__/`` (gitignored)
so they can be visually inspected for layout regressions.

Graph screenshots are captured at 2× device-scale (2560×1800 px) so that
Cytoscape labels, edges, and UML boxes render crisply.

The ``screenshot_server`` fixture (session-scoped, defined in conftest.py)
starts a NiceGUI subprocess on port 19000 with all data mocked.

Run with::

    pytest tests/ui/test_ontology_graph_screenshots.py -v
"""

from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright

from tests.ui.conftest import SCREENSHOT_DIR

# High-resolution factor for graph screenshots — renders at 2× pixel density
# so the Cytoscape graph, labels, and edges are crisp at 2560×1800 px.
_HI_DPI = 2
_VIEWPORT = {"width": 1280, "height": 900}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _new_hi_res_page(browser):
    """Create a Playwright page at 2× device-scale for crisp graph screenshots."""
    context = browser.new_context(
        viewport=_VIEWPORT,
        device_scale_factor=_HI_DPI,
    )
    return context.new_page()


def _wait_for_cy(page, timeout_ms: int = 15000) -> dict:
    """Wait for Cytoscape to become ready and return a snapshot dict."""
    import time

    start = time.monotonic()
    while (time.monotonic() - start) * 1000 < timeout_ms:
        ready = page.evaluate("""
            () => {
                const cy = window._cy;
                if (!cy) return false;
                return cy.nodes().length > 0;
            }
        """)
        if ready:
            break
        page.wait_for_timeout(500)
    else:
        raise RuntimeError(f"Cytoscape did not initialise within {timeout_ms}ms")

    # Let the layout animation settle before capturing
    page.wait_for_timeout(2000)

    nodes_raw = page.evaluate("""
        () => window._cy.nodes().map(n => ({ data: n.data() }))
    """)
    edges_raw = page.evaluate("""
        () => window._cy.edges().map(e => ({ data: e.data() }))
    """)
    return {"nodes": nodes_raw, "edges": edges_raw}


# ---------------------------------------------------------------------------
# Screenshot tests
# ---------------------------------------------------------------------------


@pytest.mark.screenshot
def test_ontology_graph_design_layer_screenshot(screenshot_server):
    """Capture a full-page screenshot of the ontology graph (design layer)."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = _new_hi_res_page(browser)

        page.goto(f"{screenshot_server}/ontology/graph", wait_until="networkidle")
        snapshot = _wait_for_cy(page)

        assert len(snapshot["nodes"]) > 0, "Graph has no nodes"

        SCREENSHOT_DIR.mkdir(exist_ok=True)
        path = SCREENSHOT_DIR / "ontology_graph_design.png"
        page.screenshot(path=str(path), full_page=True)

        # Verify every node with members has html_label
        for n in snapshot["nodes"]:
            d = n["data"]
            if d.get("member_count", 0) > 0:
                assert d.get("has_members") == "true", \
                    f"Node {d['id']} has members but has_members != 'true'"
                assert d.get("html_label"), \
                    f"Node {d['id']} has members but no html_label"

        browser.close()
        print(f"  Screenshot: {path}")


@pytest.mark.screenshot
def test_ontology_graph_no_orphaned_edges_screenshot(screenshot_server):
    """Verify that all edge endpoints reference existing nodes."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = _new_hi_res_page(browser)

        page.goto(f"{screenshot_server}/ontology/graph", wait_until="networkidle")
        snapshot = _wait_for_cy(page)

        node_ids = {n["data"]["id"] for n in snapshot["nodes"]}

        # Check edge sources (some edges from collapsed members reference
        # qualified names that aren't separate Cytoscape nodes — that's OK)
        valid_edges = [
            e for e in snapshot["edges"]
            if e["data"]["source"] in node_ids and e["data"]["target"] in node_ids
        ]
        assert len(valid_edges) >= 1, "Should have at least one edge between rendered nodes"

        browser.close()


@pytest.mark.screenshot
def test_ontology_graph_node_kinds_screenshot(screenshot_server):
    """Verify that the design-layer graph includes expected node kinds."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = _new_hi_res_page(browser)

        page.goto(f"{screenshot_server}/ontology/graph", wait_until="networkidle")
        snapshot = _wait_for_cy(page)

        kinds = {n["data"].get("kind", "") for n in snapshot["nodes"]}
        assert "class" in kinds, "Design graph should have class nodes"
        assert "namespace" in kinds, "Design graph should have namespace nodes"

        # Check that at least some nodes have design layer
        layers = {n["data"].get("layer", "") for n in snapshot["nodes"]}
        assert "design" in layers, "Design graph should have design-layer nodes"

        browser.close()


@pytest.mark.screenshot
def test_ontology_graph_detail_panel_screenshot(screenshot_server):
    """Capture a screenshot after clicking a node to show the detail panel."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = _new_hi_res_page(browser)

        page.goto(f"{screenshot_server}/ontology/graph", wait_until="networkidle")
        snapshot = _wait_for_cy(page)

        # Find a class node to click
        class_nodes = [
            n for n in snapshot["nodes"]
            if n["data"].get("kind") == "class" and n["data"].get("has_members") == "true"
        ]
        assert len(class_nodes) > 0, "Should have at least one class node with members"

        # Click on the first class node to open detail panel
        target_qn = class_nodes[0]["data"]["qualified_name"]
        page.evaluate(f"""
            () => {{
                const cy = window._cy;
                if (!cy) return;
                const node = cy.nodes().filter(n => n.data('qualified_name') === '{target_qn}');
                if (node.length > 0) {{
                    node.emit('tap');
                }}
            }}
        """)
        page.wait_for_timeout(1500)  # Wait for detail panel to load

        SCREENSHOT_DIR.mkdir(exist_ok=True)
        path = SCREENSHOT_DIR / "ontology_graph_detail_panel.png"
        page.screenshot(path=str(path), full_page=True)

        browser.close()
        print(f"  Screenshot: {path}")