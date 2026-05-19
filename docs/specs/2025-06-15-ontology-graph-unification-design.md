# Ontology Graph Unification Design

## Problem

1. **Design Intent view hides cross-layer dependencies.** The Design Intent layer shows only Design nodes, even though dependency Compounds (FLTK, std::vector) and codebase Compounds are already linked in Neo4j. Users cannot see how `CalculatorButton` depends on `Fl_Button` without switching layers.

2. **Inconsistent visualization across pages.** Four pages render Cytoscape graphs — ontology graph, HLR detail, component detail, and node detail — each with its own setup logic. The HLR detail page uses inline JS with no tap/dbltap events, no theme consistency, and no detail panel. The others call `render_cytoscape_graph()` with different parameter signatures.

3. **No unified rendering path.** Adding a style, legend entry, or event means editing multiple pages independently.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Dependency depth | Direct edges only | Graph shows connection points, not transitive dependencies |
| Visualization approach | Unified render function, keep separate pages | Data retrieval differs; rendering is shared |
| Dependency node style | Source-tagged (badge per library) | Quick visual scan of which library each dependency comes from |
| Detail panel | Configurable via `on_node_tap` callback | Some pages need it, some don't |
| Show/hide dependencies toggle | On by default | Users should see connection points immediately |
| As-built linkage | IMPLEMENTED_BY edges only | No implicit matching — the edge is the contract |

## Section 1: Data Layer Changes

### 1.1 `fetch_design_graph()` — Add IMPLEMENTED_BY query

After the existing dependency Compound query, add a second query for codebase Compounds:

```cypher
MATCH (s:Design)-[r:IMPLEMENTED_BY]->(c:Compound)
WHERE <same design-node filters>
  AND (c.source IS NULL OR c.source = '')
RETURN s.qualified_name AS src, c, type(r) AS rel_type
```

This returns codebase Compounds linked by IMPLEMENTED_BY. Currently returns nothing (no IMPLEMENTED_BY edges exist in the data). When the design-to-code linking process creates those edges, as-built nodes will appear automatically.

The function already returns a flat `{"nodes": [...], "edges": [...]}` — both dependency and codebase Compounds are included alongside Design nodes.

### 1.2 `fetch_ontology_graph_data()` — Add `include_dependencies` parameter

New parameter `include_dependencies: bool = True`. When `False`, the function filters out:
- Nodes with `layer=="dependency"`
- Nodes with `layer=="as-built"` (from IMPLEMENTED_BY query)
- Edges where source and target have different `layer` values (cross-layer edges)

When `True` (default), the full graph is returned as before.

The existing `requirement_tags` parameter is unchanged.

### 1.3 Data formatting — Cross-layer tags

In `format_cytoscape_graph()` (or a post-processing step), tag edges and nodes:

- **Cross-layer edges**: When `source` node layer differs from `target` node layer, set `is_cross_layer: "true"` on the edge data.
- **Dependency nodes**: When `source` property is non-empty, set `has_source: "true"`.
- **As-built nodes**: When `layer=="as-built"` (no source property), set `is_as_built: "true"`.

These tags drive Cytoscape styling selectors.

### 1.4 Backward compatibility

`fetch_ontology_graph_data()` defaults to `include_dependencies=True`, so all existing callers get the same behavior plus the new cross-layer data. The HLR subgraph query and neighbourhood query are unchanged.

## Section 2: GraphConfig & Unified Render Function

### 2.1 `GraphConfig` dataclass

```python
@dataclass
class GraphConfig:
    container_id: str = "cy-container"
    cy_var: str = "_cy"
    size: str = "large"        # "large" for main page, "small" for detail panels
    layout: str = "fcose"
    animate: bool = True
    extra_styles: str | None = None
    on_node_tap: callable | None = None      # async callback(node_data: dict) — receives full Cytoscape node.data() dict
    on_node_dblclick: callable | None = None # async callback(qualified_name: str)
```

### 2.2 `render_cytoscape_graph()` refactor

Current signature:
```python
async def render_cytoscape_graph(elements, base_styles, *, container_id, cy_var, layout, animate, extra_styles)
```

New signature:
```python
async def render_cytoscape_graph(elements: list[dict], config: GraphConfig)
```

The function now owns:

1. **CDN injection** — Calls `add_cytoscape_cdn()` internally. Pages no longer call this.
2. **Style generation** — Calls `cytoscape_base_styles(size=config.size)`. Applies `extra_styles` if provided.
3. **Event wiring** — Always registers `tap` and `dbltap` handlers on the Cytoscape instance. These call the provided `on_node_tap` / `on_node_dblclick` callbacks, or fall back to no-op.
4. **Instance lifecycle** — Destroys previous Cytoscape instance (same as current), creates a new one.

### 2.3 Event flow change

**Before**: Pages register `ui.on("node_selected", ...)` and `ui.on("node_dblclick", ...)` globally. The ontology graph page has a `handle_node_selected` that fetches detail and refreshes the panel.

**After**: The render function emits events through the `config.on_node_tap` and `config.on_node_dblclick` callbacks. No global `ui.on()` listeners. The render function receives node data directly from the Cytoscape tap event and passes it to the callback.

This means:
- The ontology graph page passes `on_node_tap=handle_node_tap` where `handle_node_tap` fetches detail and refreshes the panel.
- The node detail page passes `on_node_dblclick=lambda qn: ui.navigate.to(f"/node/{resolve_id(qn)}")`.
- The HLR and component pages can pass either callback or leave both `None` for a display-only graph.

## Section 3: Page-by-Page Updates

### 3.1 Ontology Graph (`/ontology/graph`)

- Add `show_dependencies: bool = True` to `GraphState`
- Add "Dependencies" toggle switch to `render_ontology_graph_controls()` (alongside existing "HLR Tags" switch)
- `load_graph()` passes `include_dependencies=state.show_dependencies` to `fetch_ontology_graph_data()`
- Replace current `render_cytoscape_graph()` call with `GraphConfig(on_node_tap=handle_node_tap, on_node_dblclick=handle_node_dblclick)`
- Remove `ui.on("node_selected", ...)` and `ui.on("node_dblclick", ...)` registrations. Events are now handled via callbacks.
- Remove manual `add_cytoscape_cdn()` call (now inside render)
- Update legend to include dependency nodes and cross-layer edges

### 3.2 HLR Detail (`/hlr/{hlr_id}`)

- Remove inline Cytoscape JS entirely (~20 lines of JS)
- Remove manual `add_cytoscape_cdn()` and `cytoscape_base_styles()` calls
- Use `render_cytoscape_graph()` with `GraphConfig(container_id="hlr-cy-container", cy_var="_hlrCy", size="small", on_node_dblclick=handle_node_dblclick)`
- HLR page gets dblclick navigation for free

### 3.3 Component Detail (`/component/{component_id}`)

- Replace positional args with `GraphConfig(container_id="comp-cy-container", cy_var="_compCy", size="small", animate=False)`
- Remove manual `add_cytoscape_cdn()` call
- Keep existing `handle_node_dblclick` → pass as `on_node_dblclick`

### 3.4 Node Detail (`/node/{node_id}`)

- Replace positional args with `GraphConfig(container_id="node-cy-container", cy_var="_nodeCy", size="small", animate=False, extra_styles=center_style)`
- Remove manual `add_cytoscape_cdn()` call
- Extra styles for center-node highlighting passed via `config.extra_styles`

## Section 4: Styling — Source-Tagged Dependency Nodes

### 4.1 Source badges on dependency nodes

Dependency nodes with a `source` property get their label updated after rendering via JavaScript, appending the source as a second line:

```
Fl_Button
[FLTK]
```

This mirrors the existing HLR tag overlay pattern (already done in `load_graph()`). A new JS snippet after Cytoscape init:

```javascript
if (window._cy) {
    window._cy.nodes().forEach(function(node) {
        const source = node.data('source');
        const layer = node.data('layer');
        if (source && layer === 'dependency') {
            node.data('label', node.data('name') + '\n[' + source + ']');
        }
    });
}
```

### 4.2 As-built badge on codebase nodes

Similar pattern for IMPLEMENTED_BY targets:

```javascript
if (window._cy) {
    window._cy.nodes().forEach(function(node) {
        if (node.data('is_as_built') === 'true') {
            node.data('label', node.data('name') + '\n[as-built]');
        }
    });
}
```

### 4.3 Cytoscape style selectors

Add to `cytoscape_base_styles()`:

```css
/* Dependency nodes with source badge */
{
    selector: 'node[has_source="true"]',
    style: {
        'border-color': '#009688',
        'border-style': 'dashed',
        'border-width': 2,
    }
},

/* As-built nodes */
{
    selector: 'node[is_as_built="true"]',
    style: {
        'border-color': '#3b82f6',
        'border-style': 'dotted',
        'border-width': 2,
    }
},

/* Cross-layer edges (design -> dependency / as-built) */
{
    selector: 'edge[is_cross_layer="true"]',
    style: {
        'line-color': '#009688',
        'target-arrow-color': '#009688',
        'line-style': 'dashed',
    }
}
```

### 4.4 Legend update

Add to `render_ontology_graph_legend()`:
- Dependency node: teal dashed circle with source badge
- As-built node: blue dotted circle with "[as-built]" badge
- Cross-layer edge: teal dashed arrow

### 4.5 Toggle filter

When "Show Dependencies" is off, `load_graph()` passes `include_dependencies=False` to `fetch_ontology_graph_data()`. The data layer strips dependency and as-built nodes + cross-layer edges. The graph reverts to Design-only, identical to current behavior.

## Files Changed

| File | Change |
|------|--------|
| `frontend/widgets.py` | Add `GraphConfig`, refactor `render_cytoscape_graph()`, update legend |
| `frontend/theme.py` | Add `has_source`, `is_as_built`, `is_cross_layer` style selectors to `cytoscape_base_styles()` |
| `frontend/pages/ontology_graph.py` | Add dependency toggle, use `GraphConfig`, remove global event listeners, remove manual CDN call |
| `frontend/pages/hlr_detail.py` | Replace inline JS with `render_cytoscape_graph()` + `GraphConfig` |
| `frontend/pages/component_detail.py` | Use `GraphConfig`, remove manual CDN call |
| `frontend/pages/node_detail.py` | Use `GraphConfig` with `extra_styles`, remove manual CDN call |
| `frontend/data/ontology.py` | Add `include_dependencies` parameter to `fetch_ontology_graph_data()` |
| `backend/db/neo4j/queries/graph.py` | Add IMPLEMENTED_BY query to `fetch_design_graph()` |
| `backend/graph/__init__.py` | Add cross-layer edge tagging in `format_cytoscape_graph()` |

## Out of Scope

- Creating IMPLEMENTED_BY edges in Neo4j (separate concern — this design shows them when they exist)
- Unified data pipeline (each page keeps its own data-fetching logic)
- HLR detail page detail panel (not in scope — display-only graph is sufficient)
- Namespace grouping for cross-layer nodes (dependency/as-built nodes stay in their own namespace context)