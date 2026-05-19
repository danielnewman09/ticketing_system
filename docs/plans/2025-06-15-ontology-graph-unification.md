# Ontology Graph Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify Cytoscape graph rendering across four pages and show cross-layer dependency/as-built nodes in the Design Intent view.

**Architecture:** Add a `GraphConfig` dataclass that encapsulates all rendering options (container ID, size, callbacks, etc.). Refactor `render_cytoscape_graph()` to own CDN injection, styling, and event wiring. Extend the data layer to include IMPLEMENTED_BY targets and add cross-layer tags. Each page switches to `GraphConfig` and removes duplicated setup logic.

**Tech Stack:** Python/NiceGUI (frontend), Neo4j/Cypher (data layer), Cytoscape.js (visualization)

---

### Task 1: Add cross-layer tags to `format_cytoscape_graph()`

**Files:**
- Modify: `backend/graph/__init__.py`
- Modify: `backend/graph/builders.py`
- Create: `tests/test_graph_cross_layer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_graph_cross_layer.py
"""Tests for cross-layer node tagging in format_cytoscape_graph."""

import pytest
from backend.graph import format_cytoscape_graph


class TestCrossLayerEdgeTagging:
    def test_cross_layer_edge_tagged(self):
        """Edges between nodes of different layers get is_cross_layer='true'."""
        raw = {
            "nodes": [
                {"qualified_name": "calc::Foo", "name": "Foo", "kind": "class", "layer": "design"},
                {"qualified_name": "fltk::Fl_Button", "name": "Fl_Button", "kind": "class", "layer": "dependency", "source": "FLTK"},
            ],
            "edges": [
                {"source": "calc::Foo", "target": "fltk::Fl_Button", "type": "USES"},
            ],
        }
        result = format_cytoscape_graph(raw)
        cross_edges = [e for e in result["edges"] if e["data"].get("is_cross_layer") == "true"]
        assert len(cross_edges) == 1
        assert cross_edges[0]["data"]["label"] == "USES"

    def test_same_layer_edge_not_tagged(self):
        """Edges between two design nodes are NOT tagged cross-layer."""
        raw = {
            "nodes": [
                {"qualified_name": "calc::Foo", "name": "Foo", "kind": "class", "layer": "design"},
                {"qualified_name": "calc::Bar", "name": "Bar", "kind": "class", "layer": "design"},
            ],
            "edges": [
                {"source": "calc::Foo", "target": "calc::Bar", "type": "COMPOSES"},
            ],
        }
        result = format_cytoscape_graph(raw)
        for e in result["edges"]:
            assert e["data"].get("is_cross_layer") != "true"

    def test_as_built_cross_layer_edge_tagged(self):
        """Edge from design to as-built node is cross-layer."""
        raw = {
            "nodes": [
                {"qualified_name": "calc::Foo", "name": "Foo", "kind": "class", "layer": "design"},
                {"qualified_name": "calc::FooImpl", "name": "FooImpl", "kind": "class", "layer": "as-built"},
            ],
            "edges": [
                {"source": "calc::Foo", "target": "calc::FooImpl", "type": "IMPLEMENTED_BY"},
            ],
        }
        result = format_cytoscape_graph(raw)
        cross_edges = [e for e in result["edges"] if e["data"].get("is_cross_layer") == "true"]
        assert len(cross_edges) == 1


class TestDependencyNodeTagging:
    def test_dependency_node_has_source(self):
        """Dependency node with source property gets has_source='true'."""
        raw = {
            "nodes": [
                {"qualified_name": "fltk::Fl_Button", "name": "Fl_Button", "kind": "class", "layer": "dependency", "source": "FLTK"},
            ],
            "edges": [],
        }
        result = format_cytoscape_graph(raw)
        node = result["nodes"][0]
        assert node["data"]["has_source"] == "true"

    def test_dependency_node_without_source_no_tag(self):
        """Dependency node without source property does not get has_source."""
        raw = {
            "nodes": [
                {"qualified_name": "std::vector", "name": "vector", "kind": "class", "layer": "dependency"},
            ],
            "edges": [],
        }
        result = format_cytoscape_graph(raw)
        node = result["nodes"][0]
        assert node["data"].get("has_source") != "true"

    def test_as_built_node_tagged(self):
        """As-built node gets is_as_built='true'."""
        raw = {
            "nodes": [
                {"qualified_name": "calc::Engine", "name": "Engine", "kind": "class", "layer": "as-built"},
            ],
            "edges": [],
        }
        result = format_cytoscape_graph(raw)
        node = result["nodes"][0]
        assert node["data"]["is_as_built"] == "true"

    def test_design_node_no_cross_layer_tags(self):
        """Design node gets no cross-layer tags."""
        raw = {
            "nodes": [
                {"qualified_name": "calc::Foo", "name": "Foo", "kind": "class", "layer": "design"},
            ],
            "edges": [],
        }
        result = format_cytoscape_graph(raw)
        node = result["nodes"][0]
        assert node["data"].get("has_source") is None
        assert node["data"].get("is_as_built") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_graph_cross_layer.py -v`
Expected: FAIL — tags not yet added

- [ ] **Step 3: Add cross-layer tagging to `format_cytoscape_graph()`**

In `backend/graph/__init__.py`, modify `format_cytoscape_graph()` to add post-processing after `assign_namespace_parents`:

```python
def format_cytoscape_graph(raw: dict) -> dict:
    """Transform raw Neo4j query result into Cytoscape.js format.

    Input: {"nodes": [{flat properties}...], "edges": [{"source", "target", "type"}...]}
    Output: {"nodes": [{"data": {...}}...], "edges": [{"data": {"id", "source", "target", "label"}}...]}
    """
    nodes = [{"data": build_cytoscape_node(n)} for n in raw.get("nodes", [])]
    edges = [{"data": build_cytoscape_edge(e)} for e in raw.get("edges", [])]
    nodes, edges = collapse_members(nodes, edges)
    nodes, edges = assign_namespace_parents(nodes, edges)
    nodes, edges = tag_cross_layer(nodes, edges)
    return {"nodes": nodes, "edges": edges}


def tag_cross_layer(nodes: list[dict], edges: list[dict]) -> tuple[list[dict], list[dict]]:
    """Tag dependency/as-built nodes and cross-layer edges for Cytoscape styling.

    Adds data attributes:
    - has_source='true' on dependency nodes with a non-empty source property
    - is_as_built='true' on as-built layer nodes
    - is_cross_layer='true' on edges connecting nodes of different layers
    """
    node_layers = {}
    for n in nodes:
        d = n["data"]
        layer = d.get("layer", "")
        node_layers[d["id"]] = layer

        if d.get("source") and layer == "dependency":
            d["has_source"] = "true"

        if layer == "as-built":
            d["is_as_built"] = "true"

    for e in edges:
        d = e["data"]
        src_layer = node_layers.get(d.get("source", ""), "")
        tgt_layer = node_layers.get(d.get("target", ""), "")
        if src_layer and tgt_layer and src_layer != tgt_layer:
            d["is_cross_layer"] = "true"

    return nodes, edges
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_graph_cross_layer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/graph/__init__.py tests/test_graph_cross_layer.py
git commit -m "feat: add cross-layer node/edge tagging in format_cytoscape_graph"
```

---

### Task 2: Add IMPLEMENTED_BY query to `fetch_design_graph()`

**Files:**
- Modify: `backend/db/neo4j/queries/graph.py`
- Create: `tests/test_design_graph_queries.py` (unit test for query result processing)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_design_graph_queries.py
"""Tests for fetch_design_graph IMPLEMENTED_BY query integration.

These tests verify the data-shaping logic, not the Neo4j queries
(which are integration tests). We test that format_cytoscape_graph
correctly processes raw results that include IMPLEMENTED_BY edges.
"""

import pytest
from backend.graph import format_cytoscape_graph


class TestDesignGraphWithImplementedBy:
    def test_implemented_by_edge_includes_as_built_node(self):
        """When raw data includes an IMPLEMENTED_BY edge to an as-built Compound,
        the formatted graph includes the as-built node with is_as_built tag."""
        raw = {
            "nodes": [
                {"qualified_name": "calc::Foo", "name": "Foo", "kind": "class", "layer": "design"},
                {"qualified_name": "calc::Foo", "name": "Foo", "kind": "class", "layer": "as-built"},
            ],
            "edges": [
                {"source": "calc::Foo", "target": "calc::Foo", "type": "IMPLEMENTED_BY"},
            ],
        }
        result = format_cytoscape_graph(raw)

        # Both nodes should be present
        node_ids = [n["data"]["id"] for n in result["nodes"]]
        assert len(node_ids) == 2

        # The as-built node should have is_as_built tag
        as_built_nodes = [n for n in result["nodes"] if n["data"].get("is_as_built") == "true"]
        assert len(as_built_nodes) == 1

        # The edge should be cross-layer
        cross_edges = [e for e in result["edges"] if e["data"].get("is_cross_layer") == "true"]
        assert len(cross_edges) == 1
        assert cross_edges[0]["data"]["label"] == "IMPLEMENTED_BY"

    def test_dependency_and_as_built_together(self):
        """Both dependency and as-built nodes can appear in the same graph."""
        raw = {
            "nodes": [
                {"qualified_name": "calc::Foo", "name": "Foo", "kind": "class", "layer": "design"},
                {"qualified_name": "fltk::Fl_Button", "name": "Fl_Button", "kind": "class", "layer": "dependency", "source": "FLTK"},
                {"qualified_name": "calc::Foo", "name": "Foo", "kind": "class", "layer": "as-built"},
            ],
            "edges": [
                {"source": "calc::Foo", "target": "fltk::Fl_Button", "type": "USES"},
                {"source": "calc::Foo", "target": "calc::Foo", "type": "IMPLEMENTED_BY"},
            ],
        }
        result = format_cytoscape_graph(raw)

        # Both types tagged
        dep_nodes = [n for n in result["nodes"] if n["data"].get("has_source") == "true"]
        as_built_nodes = [n for n in result["nodes"] if n["data"].get("is_as_built") == "true"]
        assert len(dep_nodes) == 1
        assert len(as_built_nodes) == 1

        # Both edges cross-layer
        cross_edges = [e for e in result["edges"] if e["data"].get("is_cross_layer") == "true"]
        assert len(cross_edges) == 2
```

- [ ] **Step 2: Run test to verify it passes**

Run: `python -m pytest tests/test_design_graph_queries.py -v`
Expected: PASS — these tests depend on `format_cytoscape_graph` which was already updated in Task 1

- [ ] **Step 3: Add IMPLEMENTED_BY query to `fetch_design_graph()`**

In `backend/db/neo4j/queries/graph.py`, after the existing `dep_result` loop (around line 110), add:

```python
        # As-built compounds linked via IMPLEMENTED_BY
        as_built_result = session.run(
            f"""
            MATCH (s:Design)-[r:IMPLEMENTED_BY]->(c:Compound)
            WHERE {where.replace("n:", "s:").replace("n.", "s.")}
              AND (c.source IS NULL OR c.source = '')
            RETURN s.qualified_name AS src, c, type(r) AS rel_type
            """,
            params,
        )
        for record in as_built_result:
            c = record["c"]
            qn = c.get("qualified_name", "")
            if qn not in node_qns:
                node_qns.add(qn)
                d = dict(c)
                d["layer"] = "as-built"
                nodes.append(d)
            edges.append(
                {
                    "source": record["src"],
                    "target": qn,
                    "type": record["rel_type"],
                }
            )
```

- [ ] **Step 4: Commit**

```bash
git add backend/db/neo4j/queries/graph.py
git commit -m "feat: add IMPLEMENTED_BY query to fetch_design_graph for as-built nodes"
```

---

### Task 3: Add `include_dependencies` parameter to data layer

**Files:**
- Modify: `frontend/data/ontology.py`
- Create: `tests/test_data_layer_filter.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_layer_filter.py
"""Tests for include_dependencies filtering in fetch_ontology_graph_data."""

import pytest
from frontend.data.ontology import filter_cross_layer_elements


class TestFilterCrossLayerElements:
    def test_removes_dependency_nodes_when_disabled(self):
        nodes = [
            {"data": {"id": "a", "layer": "design", "qualified_name": "a"}},
            {"data": {"id": "b", "layer": "dependency", "qualified_name": "b", "source": "FLTK"}},
        ]
        edges = [
            {"data": {"id": "e1", "source": "a", "target": "b", "label": "USES", "is_cross_layer": "true"}},
        ]
        result_nodes, result_edges = filter_cross_layer_elements(nodes, edges)
        assert len(result_nodes) == 1
        assert result_nodes[0]["data"]["layer"] == "design"
        assert len(result_edges) == 0

    def test_removes_as_built_nodes_when_disabled(self):
        nodes = [
            {"data": {"id": "a", "layer": "design", "qualified_name": "a"}},
            {"data": {"id": "b", "layer": "as-built", "qualified_name": "b", "is_as_built": "true"}},
        ]
        edges = [
            {"data": {"id": "e1", "source": "a", "target": "b", "label": "IMPLEMENTED_BY", "is_cross_layer": "true"}},
        ]
        result_nodes, result_edges = filter_cross_layer_elements(nodes, edges)
        assert len(result_nodes) == 1
        assert len(result_edges) == 0

    def test_keeps_all_when_enabled(self):
        nodes = [
            {"data": {"id": "a", "layer": "design", "qualified_name": "a"}},
            {"data": {"id": "b", "layer": "dependency", "qualified_name": "b"}},
            {"data": {"id": "c", "layer": "as-built", "qualified_name": "c"}},
        ]
        edges = [
            {"data": {"id": "e1", "source": "a", "target": "b", "label": "USES"}},
            {"data": {"id": "e2", "source": "a", "target": "c", "label": "IMPLEMENTED_BY"}},
        ]
        result_nodes, result_edges = filter_cross_layer_elements(nodes, edges)
        assert len(result_nodes) == 3
        assert len(result_edges) == 2

    def test_keeps_design_only_edges(self):
        nodes = [
            {"data": {"id": "a", "layer": "design", "qualified_name": "a"}},
            {"data": {"id": "b", "layer": "design", "qualified_name": "b"}},
            {"data": {"id": "c", "layer": "dependency", "qualified_name": "c"}},
        ]
        edges = [
            {"data": {"id": "e1", "source": "a", "target": "b", "label": "COMPOSES"}},
            {"data": {"id": "e2", "source": "a", "target": "c", "label": "USES", "is_cross_layer": "true"}},
        ]
        result_nodes, result_edges = filter_cross_layer_elements(nodes, edges)
        assert len(result_nodes) == 2
        assert len(result_edges) == 1
        assert result_edges[0]["data"]["label"] == "COMPOSES"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_data_layer_filter.py -v`
Expected: FAIL — `filter_cross_layer_elements` doesn't exist yet

- [ ] **Step 3: Implement `filter_cross_layer_elements` and add `include_dependencies` to `fetch_ontology_graph_data`**

Add to `frontend/data/ontology.py`:

```python
def filter_cross_layer_elements(
    nodes: list[dict], edges: list[dict]
) -> tuple[list[dict], list[dict]]:
    """Remove cross-layer nodes and edges (dependency and as-built).

    Used when include_dependencies=False to return a design-only graph.
    """
    cross_layer_ids = {
        n["data"]["id"]
        for n in nodes
        if n["data"].get("layer") in ("dependency", "as-built")
    }
    filtered_nodes = [n for n in nodes if n["data"]["id"] not in cross_layer_ids]
    filtered_edges = [
        e for e in edges
        if e["data"].get("source") not in cross_layer_ids
        and e["data"].get("target") not in cross_layer_ids
    ]
    return filtered_nodes, filtered_edges
```

Modify `fetch_ontology_graph_data` in `frontend/data/ontology.py` to add the parameter and apply the filter:

```python
def fetch_ontology_graph_data(
    layer: str = "design",
    kind_filter: str | None = None,
    search: str | None = None,
    component_id: int | None = None,
    source_filter: str | None = None,
    requirement_tags: str = "hlr",
    include_dependencies: bool = True,
) -> dict:
    # ... existing query logic ...
    formatted = format_cytoscape_graph(raw)

    if layer == "design" and requirement_tags != "none":
        enrich_with_requirement_tags(formatted["nodes"], mode=requirement_tags)

    if not include_dependencies:
        formatted["nodes"], formatted["edges"] = filter_cross_layer_elements(
            formatted["nodes"], formatted["edges"]
        )

    return formatted
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_data_layer_filter.py tests/test_graph_cross_layer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/data/ontology.py tests/test_data_layer_filter.py
git commit -m "feat: add include_dependencies filter to fetch_ontology_graph_data"
```

---

### Task 4: Add `GraphConfig` dataclass and refactor `render_cytoscape_graph()`

**Files:**
- Modify: `frontend/widgets.py`

- [ ] **Step 1: Add `GraphConfig` dataclass and refactor `render_cytoscape_graph()`**

In `frontend/widgets.py`, add the `GraphConfig` dataclass before `render_graph_detail_panel`:

```python
@dataclass
class GraphConfig:
    """Configuration for Cytoscape graph rendering."""

    container_id: str = "cy-container"
    cy_var: str = "_cy"
    size: str = "large"  # "large" for main page, "small" for detail panels
    layout: str = "fcose"
    animate: bool = True
    extra_styles: str | None = None
    on_node_tap: callable | None = None      # async callback(node_data: dict)
    on_node_dblclick: callable | None = None # async callback(qualified_name: str)
```

Replace the existing `render_cytoscape_graph` function (starting around line 285) with:

```python
async def render_cytoscape_graph(
    elements: list[dict],
    config: GraphConfig,
):
    """Render a Cytoscape.js graph with consistent theme and event handling.

    All pages should use this function instead of inline Cytoscape JS.
    CDN injection, styling, and event wiring are handled centrally.
    """
    add_cytoscape_cdn()
    base_styles = cytoscape_base_styles(size=config.size)
    elements_json = json.dumps(elements)
    layout_name = f"window._cyLayout || '{config.layout}'" if config.animate else f"'{config.layout}'"
    animation_opts = "animate: true, animationDuration: 500" if config.animate else "animate: false"
    styles_expr = f"[...{base_styles}"
    if config.extra_styles:
        styles_expr += f", {config.extra_styles}"
    styles_expr += "]"
    # Ensure unique event names per instance
    tap_event = f"{config.cy_var}_tap"
    dbltap_event = f"{config.cy_var}_dbltap"

    await ui.run_javascript(f"""
        if (window.{config.cy_var}) window.{config.cy_var}.destroy();
        const KIND_COLORS = {KIND_COLORS_JS};
        const container = document.getElementById('{config.container_id}');
        if (!container) {{ console.error('{config.container_id} not found'); return; }}
        window.{config.cy_var} = cytoscape({{
            container: container,
            elements: {elements_json},
            style: {styles_expr},
            layout: {{ name: {layout_name}, {animation_opts} }},
        }});
        window.{config.cy_var}.ready(function() {{ window.{config.cy_var}.fit(); }});
        window.{config.cy_var}.on('tap', 'node', function(evt) {{
            const data = evt.target.data();
            if (data.qualified_name) {{
                emitEvent('{tap_event}', data);
            }}
        }});
        window.{config.cy_var}.on('dbltap', 'node', function(evt) {{
            const data = evt.target.data();
            if (data.qualified_name) {{
                emitEvent('{dbltap_event}', data);
            }}
        }});
    """)

    # Wire up callbacks
    if config.on_node_tap:
        ui.on(tap_event, config.on_node_tap)
    if config.on_node_dblclick:
        ui.on(dbltap_event, config.on_node_dblclick)
```

- [ ] **Step 2: Verify no syntax errors**

Run: `python -c "from frontend.widgets import GraphConfig, render_cytoscape_graph; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add frontend/widgets.py
git commit -m "feat: add GraphConfig and refactor render_cytoscape_graph"
```

---

### Task 5: Add Cytoscape style selectors for cross-layer elements

**Files:**
- Modify: `frontend/theme.py`

- [ ] **Step 1: Add style selectors to `cytoscape_base_styles()`**

In `frontend/theme.py`, inside the `cytoscape_base_styles()` function, add three new style entries before the `:selected` selector (which should remain last among node/edge selectors):

```python
    # Insert before the ':selected' selector block:
    {{
        selector: 'node[has_source="true"]',
        style: {{
            'border-color': '#009688',
            'border-style': 'dashed',
            'border-width': 2,
        }}
    }},
    {{
        selector: 'node[is_as_built="true"]',
        style: {{
            'border-color': '#3b82f6',
            'border-style': 'dotted',
            'border-width': 2,
        }}
    }},
    {{
        selector: 'edge[is_cross_layer="true"]',
        style: {{
            'line-style': 'dashed',
            'line-color': '#009688',
            'target-arrow-color': '#009688',
        }}
    }},
```

- [ ] **Step 2: Add color constants to `theme.py`**

Add to the `EDGE_COLORS` dict:

```python
EDGE_COLORS = {
    "INHERITS_FROM": "#9b59b6",
    "IMPLEMENTED_BY": "#3b82f6",
    "CROSS_LAYER": "#009688",
    "default": "#555",
}
```

- [ ] **Step 3: Verify no syntax errors**

Run: `python -c "from frontend.theme import cytoscape_base_styles; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add frontend/theme.py
git commit -m "feat: add Cytoscape style selectors for cross-layer nodes and edges"
```

---

### Task 6: Update ontology graph page with dependency toggle and `GraphConfig`

**Files:**
- Modify: `frontend/pages/ontology_graph.py`
- Modify: `frontend/widgets.py` (legend and controls)

- [ ] **Step 1: Update `GraphState` to add `show_dependencies`**

In `frontend/widgets.py`, add `show_dependencies: bool = True` to the `GraphState` dataclass.

- [ ] **Step 2: Update `render_ontology_graph_controls()` to add dependency toggle**

In `frontend/widgets.py`, add `on_toggle_deps` parameter and UI switch:

```python
def render_ontology_graph_controls(
    *,
    on_layer_change: callable,
    on_kind_change: callable,
    on_search: callable,
    on_layout_change: callable,
    on_fit: callable,
    on_toggle_req_tags=None,
    on_toggle_deps=None,
):
    # ... existing controls ...
    if on_toggle_deps:
        ui.switch("Deps", value=True, on_change=on_toggle_deps).props("dense")
```

- [ ] **Step 3: Update `render_ontology_graph_legend()` to include dependency nodes**

In `frontend/widgets.py`, add entries after the existing "Dependency" legend item:

```python
    with ui.row().classes("items-center gap-1"):
        ui.html(
            '<div style="width:10px;height:10px;border-radius:50%;background:#555;border:2px dashed #009688"></div>'
        )
        ui.label("Deps (source)").classes("text-xs")
    with ui.row().classes("items-center gap-1"):
        ui.html(
            '<div style="width:10px;height:10px;border-radius:50%;background:#555;border:2px dotted #3b82f6"></div>'
        )
        ui.label("As-built").classes("text-xs")
```

- [ ] **Step 4: Update `ontology_graph.py` to use `GraphConfig` and dependency toggle**

In `frontend/pages/ontology_graph.py`:

1. Remove `add_cytoscape_cdn()` call (now inside `render_cytoscape_graph`)
2. Remove `base_styles = cytoscape_base_styles(size="large")` (now inside render)
3. Add `from frontend.widgets import GraphConfig` to imports
4. Add `show_dependencies: bool = True` is already in GraphState
5. Update `load_graph()` to use `GraphConfig` and pass `include_dependencies`:

```python
    async def load_graph():
        layer = state.graph_layer
        search = state.search_text or ""

        if layer == "dependency" and not search.strip():
            await ui.run_javascript("""
                if (window._cy) window._cy.destroy();
                const container = document.getElementById('cy-container');
                if (container) {
                    container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#888;font-size:1.1rem;">Search for a class or namespace to explore dependencies</div>';
                }
            """)
            return

        requirement_tags = "hlr" if state.show_requirement_tags else "none"
        data = await asyncio.to_thread(
            fetch_ontology_graph_data,
            layer=layer,
            kind_filter=state.kind_filter,
            search=search or None,
            source_filter=state.source_filter,
            requirement_tags=requirement_tags,
            include_dependencies=state.show_dependencies,
        )

        config = GraphConfig(
            on_node_tap=handle_node_tap,
            on_node_dblclick=handle_node_dblclick,
        )
        await render_cytoscape_graph(data["nodes"] + data["edges"], config)

        # Overlay source badges on dependency nodes
        if layer == "design":
            if state.show_dependencies:
                await ui.run_javascript('''
                    if (window._cy) {
                        window._cy.nodes().forEach(function(node) {
                            const source = node.data('source');
                            const layer = node.data('layer');
                            if (source && layer === 'dependency') {
                                node.data('label', node.data('name') + '\\n[' + source + ']');
                            }
                            if (node.data('is_as_built') === 'true') {
                                node.data('label', node.data('name') + '\\n[as-built]');
                            }
                        });
                    }
                ''')

            if state.show_requirement_tags:
                await ui.run_javascript('''
                    if (window._cy) {
                        window._cy.nodes().forEach(function(node) {
                            const reqs = node.data('requirements');
                            if (reqs && reqs.length > 0) {
                                const badges = reqs.map(r => '[' + r.type + ' ' + r.id + ']').join(' ');
                                node.data('label', node.data('name') + '\\n' + badges);
                                node.addClass('has-requirements');
                            }
                        });
                    }
                ''')
```

6. Add `on_toggle_deps` to controls:

```python
    render_ontology_graph_controls(
        on_layer_change=on_layer_change,
        on_kind_change=on_kind_change,
        on_search=on_search,
        on_layout_change=on_layout_change,
        on_fit=lambda: ui.run_javascript("if(window._cy) window._cy.fit()"),
        on_toggle_req_tags=on_toggle_req_tags,
        on_toggle_deps=on_toggle_deps,
    )
```

7. Add toggle handler:

```python
    async def on_toggle_deps(e):
        state.show_dependencies = e.value
        await load_graph()
```

8. Remove `ui.on("node_selected", ...)` and `ui.on("node_dblclick", ...)` event registrations. Replace with the callback-based approach. Add handlers:

```python
    async def handle_node_tap(e):
        """On node click/tap: fetch detail and refresh the side panel."""
        data = e.args
        qn = data.get("qualified_name", "")
        if not qn:
            return
        layer = data.get("layer", "")
        detail = await asyncio.to_thread(fetch_graph_node_detail, qn)
        if detail and layer == "design":
            dep_links = await asyncio.to_thread(fetch_design_dependency_links_data, [qn])
            detail["dependency_links"] = dep_links.get("nodes", [])
        if detail:
            state.selected_node_data = detail
            render_graph_detail_panel.refresh()

    async def handle_node_dblclick(e):
        """On node double-click: navigate to the full node detail page."""
        data = e.args
        qn = data.get("qualified_name", "")
        if not qn:
            return
        node_id = await asyncio.to_thread(resolve_node_id_by_qualified_name, qn)
        if node_id:
            ui.navigate.to(f"/node/{node_id}")
```

9. Remove the old `handle_node_selected` and `handle_node_dblclick` functions and their `ui.on()` registrations.

- [ ] **Step 5: Verify the app starts**

Run: `python -m frontend` or the project's start command. Navigate to `/ontology/graph` and verify the page loads without errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/pages/ontology_graph.py frontend/widgets.py
git commit -m "feat: update ontology graph page with GraphConfig and dependency toggle"
```

---

### Task 7: Refactor HLR detail page to use `GraphConfig`

**Files:**
- Modify: `frontend/pages/hlr_detail.py`

- [ ] **Step 1: Replace inline Cytoscape JS with `render_cytoscape_graph()`**

In `frontend/pages/hlr_detail.py`:

1. Remove `add_cytoscape_cdn()` and `base_styles = cytoscape_base_styles(size="small")` calls from the page function
2. Add `from frontend.widgets import GraphConfig` import (update existing `render_cytoscape_graph` import to include `GraphConfig`)
3. Remove the `import json` and `KIND_COLORS_JS` imports (no longer needed)
4. Remove the inline `await ui.run_javascript(f"""...""")` block that creates Cytoscape
5. Replace with:

```python
                graph = await asyncio.to_thread(fetch_hlr_graph_data, hlr_id, hlr["component_id"], requirement_tags="hlr")
                if graph["nodes"]:
                    config = GraphConfig(
                        container_id="hlr-cy-container",
                        cy_var="_hlrCy",
                        size="small",
                        animate=False,
                    )
                    await render_cytoscape_graph(graph["nodes"] + graph["edges"], config)
```

6. Add `handle_node_dblclick` handler:

```python
    async def handle_node_dblclick(e):
        data = e.args
        qn = data.get("qualified_name", "")
        if not qn:
            return
        node_id = await asyncio.to_thread(resolve_node_id_by_qualified_name, qn)
        if node_id:
            ui.navigate.to(f"/node/{node_id}")
```

And pass it in the config inside the `content()` function:

```python
                    config = GraphConfig(
                        container_id="hlr-cy-container",
                        cy_var="_hlrCy",
                        size="small",
                        animate=False,
                        on_node_dblclick=handle_node_dblclick,
                    )
```

- [ ] **Step 2: Verify the HLR detail page works**

Navigate to `/hlr/{id}` and verify the graph renders and dblclick navigates to node detail.

- [ ] **Step 3: Commit**

```bash
git add frontend/pages/hlr_detail.py
git commit -m "refactor: replace inline Cytoscape JS in HLR detail with GraphConfig"
```

---

### Task 8: Refactor component detail and node detail pages

**Files:**
- Modify: `frontend/pages/component_detail.py`
- Modify: `frontend/pages/node_detail.py`

- [ ] **Step 1: Update component detail page**

In `frontend/pages/component_detail.py`:

1. Remove `from frontend.theme import add_cytoscape_cdn, cytoscape_base_styles` and `import json` — no longer needed
2. Add `GraphConfig` to the `frontend.widgets` import
3. Remove `add_cytoscape_cdn()` and `base_styles = cytoscape_base_styles(size="small")` calls
4. Replace the `render_cytoscape_graph` call with:

```python
        config = GraphConfig(
            container_id="comp-cy-container",
            cy_var="_compCy",
            size="small",
            animate=False,
            on_node_dblclick=handle_node_dblclick,
        )
        await render_cytoscape_graph(graph["nodes"] + graph["edges"], config)
```

5. Remove the `ui.on("node_dblclick", handle_node_dblclick)` registration at the bottom of the page — it's now handled by the GraphConfig callback.

- [ ] **Step 2: Update node detail page**

In `frontend/pages/node_detail.py`:

1. Remove `from frontend.theme import add_cytoscape_cdn, cytoscape_base_styles` and `import json` — no longer needed (check they're not used elsewhere in the file first)
2. Add `GraphConfig` to the `frontend.widgets` import
3. Remove `add_cytoscape_cdn()` and `base_styles = cytoscape_base_styles(size="small")` calls
4. Build the `center_style` string for the `extra_styles` parameter
5. Replace the `render_cytoscape_graph` call with:

```python
        center_style = (
            f'{{"selector": \'node[is_center="true"]\', '
            f'"style": {{"border-width": 3, "border-color": "{STATUS_COLORS["selected"]}", "border-style": "solid"}}}}'
        )
        config = GraphConfig(
            container_id="node-cy-container",
            cy_var="_nodeCy",
            size="small",
            animate=False,
            extra_styles=center_style,
        )
        await render_cytoscape_graph(graph["nodes"] + graph["edges"], config)
```

6. Remove the `ui.on("node_dblclick", handle_node_dblclick)` registration — now handled by GraphConfig callback.

- [ ] **Step 3: Verify both pages work**

Navigate to `/component/{id}` and `/node/{id}` and verify graphs render correctly.

- [ ] **Step 4: Commit**

```bash
git add frontend/pages/component_detail.py frontend/pages/node_detail.py
git commit -m "refactor: switch component and node detail pages to GraphConfig"
```

---

### Task 9: Source badge overlay for dependency and as-built nodes

**Files:**
- Modify: `frontend/widgets.py` (update `render_cytoscape_graph` to include badge overlay in JS)

- [ ] **Step 1: Add badge overlay JS to `render_cytoscape_graph()`**

After the Cytoscape `ready` callback in the JavaScript template within `render_cytoscape_graph()`, add the source/as-built badge overlay logic. This replaces the ad-hoc JS in `ontology_graph.py`.

Find the `window.{cy_var}.ready(function() {{ window.{cy_var}.fit(); }});` line and add after it:

```javascript
        window.{config.cy_var}.nodes().forEach(function(node) {{
            const source = node.data('source');
            const layer = node.data('layer');
            if (source && layer === 'dependency') {{
                node.data('label', node.data('name') + '\\n[' + source + ']');
            }}
            if (node.data('is_as_built') === 'true') {{
                node.data('label', node.data('name') + '\\n[as-built]');
            }}
        }});
```

This means the full JS template in `render_cytoscape_graph` now includes badge overlays centrally. Remove the overlay JS from `ontology_graph.py`'s `load_graph()` function since it's now handled by the render function.

- [ ] **Step 2: Remove duplicate overlay JS from ontology graph page**

In `frontend/pages/ontology_graph.py`, remove the source badge and HLR badge overlay JavaScript from `load_graph()`. The badge logic is now centralized in `render_cytoscape_graph()`. Keep only the `has-requirements` class-adding JS that's specific to HLR tags:

```python
        if state.show_requirement_tags:
            await ui.run_javascript('''
                if (window._cy) {
                    window._cy.nodes().forEach(function(node) {
                        const reqs = node.data('requirements');
                        if (reqs && reqs.length > 0) {
                            const badges = reqs.map(r => '[' + r.type + ' ' + r.id + ']').join(' ');
                            node.data('label', node.data('name') + '\\n' + badges);
                            node.addClass('has-requirements');
                        }
                    });
                }
            ''')
```

Note: The HLR badge overlay runs AFTER `render_cytoscape_graph` to prepend requirements info to the label. Since render already appends source/as-built badges, the HLR overlay should use `node.data('name')` (original name, not the current label which already has the source badge). Actually, source badges and HLR tags can both be on design nodes. The source badge logic only runs on `layer='dependency'` and `is_as_built`, so there's no conflict. The HLR logic only runs on design nodes that have `requirements`. These are different nodes, so no conflict.

- [ ] **Step 3: Verify overlay works on all pages**

Check the ontology graph page shows source badges on dependency nodes and "[as-built]" on IMPLEMENTED_BY targets (when they exist). Check HLR tag overlay still works.

- [ ] **Step 4: Commit**

```bash
git add frontend/widgets.py frontend/pages/ontology_graph.py
git commit -m "feat: centralize source/as-built badge overlay in render_cytoscape_graph"
```

---

### Task 10: Final integration test and cleanup

**Files:**
- All modified files

- [ ] **Step 1: Run all existing tests**

Run: `python -m pytest tests/ -v`
Expected: All existing tests pass, new tests pass

- [ ] **Step 2: Visual verification checklist**

Manually verify:

1. `/ontology/graph` — Design Intent view loads, dependency toggle works, source badges appear on dependency nodes, cross-layer edges shown with dashed teal style
2. `/ontology/graph` — Toggle "Deps" OFF hides dependency nodes, toggle ON shows them again
3. `/ontology/graph` — Click on a node shows detail panel (tap), double-click navigates to node detail
4. `/hlr/{id}` — Graph renders, no inline JS, double-click navigates to node detail
5. `/component/{id}` — Graph renders with GraphConfig, double-click works
6. `/node/{id}` — Graph renders with center-node highlighting, double-click works
7. Legend shows all node types including "Deps (source)" and "As-built"

- [ ] **Step 3: Clean up any unused imports**

In all modified page files, remove unused imports for `add_cytoscape_cdn`, `cytoscape_base_styles`, `KIND_COLORS_JS`, `json`, and `BACKGROUNDS` if no longer referenced.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: clean up unused imports from graph page refactoring"
```