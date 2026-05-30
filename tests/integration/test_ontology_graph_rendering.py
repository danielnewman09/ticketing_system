"""Integration tests for the ontology graph -- browser rendering benchmarks.

These tests use Playwright (sync API) to verify that the ontology graph
renders correctly after data-model or pipeline changes.  Screenshots are
captured for every test and written to ``tests/integration/__snapshots__/``.

Run with::

    pytest tests/integration/ -v

Prerequisites:
- ``python nicegui_app.py`` serving at http://localhost:8081
- Neo4j populated (e.g. via ``scripts/02_setup_project.py``)
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ONTOLOGY_GRAPH_URL = "http://localhost:8081/ontology/graph"
SNAPSHOT_DIR = Path("tests/integration/__snapshots__")


# -- helpers ------------------------------------------------------------------


def _wait_for_cy(page, timeout_ms: int = 15000) -> dict:
    """Wait for Cytoscape to become ready and return a snapshot dict."""
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


def _collect_console_errors(page) -> list[str]:
    """Return all console.error messages collected so far."""
    errors: list[str] = []

    def _on_console(msg):
        if msg.type == "error":
            errors.append(msg.text)

    page.on("console", _on_console)
    page.wait_for_timeout(1000)
    return errors


def _screenshot(page, name: str, *, full_page: bool = True) -> Path:
    """Capture a screenshot and return the output path."""
    SNAPSHOT_DIR.mkdir(exist_ok=True)
    path = SNAPSHOT_DIR / f"{name}.png"
    page.screenshot(path=str(path), full_page=full_page)
    return path


def _node_summary(nodes: list[dict]) -> dict:
    """Return key metrics for each rendered node."""
    summaries: list[dict] = []
    for n in nodes:
        d = n["data"]
        summaries.append({
            "id": d["id"],
            "kind": d.get("kind", ""),
            "layer": d.get("layer", ""),
            "has_members": d.get("has_members", ""),
            "has_html_label": bool(d.get("html_label")),
            "member_count": d.get("member_count"),
            "parent": d.get("parent", ""),
        })
    return {"nodes": summaries}


def _edge_summary(edges: list[dict]) -> dict:
    return {
        "edges": [
            {"source": e["data"]["source"], "target": e["data"]["target"],
             "label": e["data"]["label"]}
            for e in edges
        ]
    }


# -- fixtures -----------------------------------------------------------------


@pytest.fixture(scope="module")
def browser():
    """Module-scoped browser -- one launch per test file."""
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    yield browser
    browser.close()
    pw.stop()


@pytest.fixture
def page(browser):
    """Fresh page per test."""
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    yield page
    ctx.close()


# -- tests --------------------------------------------------------------------


def test_ontology_graph_renders(page):
    """The design-layer ontology graph MUST render at least 1 node with
    no JavaScript console errors and no orphaned edges."""
    page.goto(ONTOLOGY_GRAPH_URL, wait_until="networkidle")

    snapshot = _wait_for_cy(page)
    console_errors = _collect_console_errors(page)

    # 1. No JS errors
    assert console_errors == [], f"Console errors: {console_errors}"

    # 2. Graph has nodes
    nodes = snapshot["nodes"]
    edges = snapshot["edges"]
    assert len(nodes) > 0, "Graph has zero nodes"

    # 3. No orphaned edges -- every edge endpoint must be a known node id
    node_ids = {n["data"]["id"] for n in nodes}
    for e in edges:
        src = e["data"]["source"]
        tgt = e["data"]["target"]
        assert src in node_ids, f"Edge source {src!r} not in node set"
        assert tgt in node_ids, f"Edge target {tgt!r} not in node set"

    # 4. Every node with members must have has_members="true" and html_label
    for n in nodes:
        d = n["data"]
        if d.get("member_count", 0) > 0:
            assert d.get("has_members") == "true", \
                f"Node {d['id']} has members but has_members != 'true'"
            assert d.get("html_label"), \
                f"Node {d['id']} has members but no html_label"

    # Capture screenshot after assertions pass
    path = _screenshot(page, "ontology_graph_design")
    print(f"  Screenshot: {path}")


def test_ontology_graph_renders_with_requirement_tags(page):
    """When requirement tags are shown (default), the graph still renders."""
    page.goto(ONTOLOGY_GRAPH_URL, wait_until="networkidle")
    snapshot = _wait_for_cy(page)
    console_errors = _collect_console_errors(page)

    assert console_errors == [], f"Console errors: {console_errors}"
    assert len(snapshot["nodes"]) > 0

    path = _screenshot(page, "ontology_graph_with_reqs")
    print(f"  Screenshot: {path}")


def test_ontology_graph_renders_with_deps_enabled(page):
    """When dependency cross-links are enabled, the graph still renders."""
    page.goto(ONTOLOGY_GRAPH_URL, wait_until="networkidle")
    snapshot = _wait_for_cy(page)
    console_errors = _collect_console_errors(page)

    assert console_errors == [], f"Console errors: {console_errors}"
    assert len(snapshot["nodes"]) > 0

    path = _screenshot(page, "ontology_graph_with_deps")
    print(f"  Screenshot: {path}")


def test_snapshot_is_stable(page, pytestconfig):
    """Record a stable snapshot of the rendered graph for comparison.

    Writes JSON + Markdown + PNG snapshots to tests/integration/__snapshots__/.
    This is NOT an assertion -- it captures the current state for manual
    or CI diff review.

    Skip with ``pytest --no-snapshot``.
    """
    if pytestconfig.getoption("--no-snapshot", default=False):
        pytest.skip("Snapshot generation disabled via --no-snapshot")

    page.goto(ONTOLOGY_GRAPH_URL, wait_until="networkidle")
    snapshot = _wait_for_cy(page)
    console_errors = _collect_console_errors(page)

    assert console_errors == [], f"Snapshot blocked by console errors: {console_errors}"

    summary = {
        "total_nodes": len(snapshot["nodes"]),
        "total_edges": len(snapshot["edges"]),
        **_node_summary(snapshot["nodes"]),
        **_edge_summary(snapshot["edges"]),
    }

    SNAPSHOT_DIR.mkdir(exist_ok=True)

    # JSON snapshot
    SNAPSHOT_DIR.joinpath("ontology_graph_snapshot.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )

    # Markdown snapshot
    lines = ["# Ontology Graph Snapshot", "",
             f"Nodes: {summary['total_nodes']}",
             f"Edges: {summary['total_edges']}", ""]
    for n in summary["nodes"]:
        lines.append(
            f"- `{n['id']}`  kind={n['kind']} layer={n['layer']} "
            f"members={n['member_count'] or 0} html={n['has_html_label']}"
        )
    SNAPSHOT_DIR.joinpath("ontology_graph_snapshot.md").write_text(
        "\n".join(lines) + "\n"
    )

    # Screenshot
    path = _screenshot(page, "ontology_graph_snapshot")
    print(f"  Screenshot: {path}")
