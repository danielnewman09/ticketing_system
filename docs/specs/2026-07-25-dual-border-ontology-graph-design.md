# Design: Dual-Border Ontology Graph Nodes

**Date:** 2026-07-25  
**Status:** Approved

## Problem

Ontology graph UML boxes currently show a single border whose color and style convey
one piece of information at a time. When `change_status` is set, it replaces the
kind-colored solid border with a status-colored dashed border — you lose the kind
information. The goal is to show **both** borders simultaneously:

- **Inner solid border** — conveys the node type (class, struct, interface, enum)
- **Outer dashed border** — conveys the lifecycle status (new, implemented, modified, deleted)

The background tint that currently accompanies `change_status` should be removed;
status is conveyed entirely by the outer border color and class name text color.

Simple circle nodes (non-UML-box) are excluded from this change.

## Approach

Cytoscape.js supports only one native border per node. The dual-border effect is
achieved by splitting the visualization across two rendering layers:

1. **Cytoscape border** → outer dashed border (lifecycle status color)
2. **HTML label `box-shadow: inset`** → inner solid border (kind color)

A small padding gap (5px, adjustable) between the Cytoscape border and HTML content
creates visual separation between the two borders.

### Visual Stack

```
┌─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐   ← Cytoscape border:
│              (5px neutral-dark gap)                     │      dashed, status color
│   ┌─────────────────────────────────────────────────┐   │
│   │  ╔═══════════════════════════════════════════╗  │   │   ← CSS inset box-shadow:
│   │  ║  «class»                                 ║  │   │      solid, kind color
│   │  ║  ClassName                                ║  │   │
│   │  ║  ─────────────────────────────────────────║  │   │
│   │  ║  + method(): ◆ Result                    ║  │   │
│   │  ╚═══════════════════════════════════════════╝  │   │
│   └─────────────────────────────────────────────────┘   │
└─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘
```

From outside in:

1. Cytoscape dashed border — lifecycle status color, 3.5px
2. Padding gap — 5px of neutral dark (`#1e293b`) background
3. CSS inset box-shadow — solid kind color, 2.5px, on the HTML label wrapper
4. HTML content — stereotype, class name (colored by status), members

Background fill is always neutral dark — no tinting. Status is conveyed by outer
border color and class name text color alone.

## Data Flow

No new data fields needed. The pipeline remains:

```
Neo4j → build_cytoscape_node (kind, change_status already set)
      → collapse_members (_build_uml_html uses owner_kind for kind_border)
      → Cytoscape rendering (change_status → outer border, kind_border → inner)
```

The visual split changes:

| Visual element       | Before                              | After                             |
|----------------------|-------------------------------------|-----------------------------------|
| Outer border color   | kind color → change_status overrides| **change_status color** (always)  |
| Outer border style   | solid → change_status overrides     | **dashed** (for status nodes)    |
| Inner solid border   | doesn't exist                       | **kind color** via box-shadow    |
| Background tint      | change_status sets it               | **removed** — always `#1e293b`   |
| Class name text      | change_status colors it             | **no change**                     |

## Changes

### 1. `frontend/theme.py` — `cytoscape_base_styles()`

**Base UML box style** (`node[has_members="true"][layer="design"]`):

| Property         | Before  | After   | Reason                        |
|------------------|---------|---------|-------------------------------|
| `border-style`   | `solid` | `dashed`| Outer border is always status |
| `border-width`   | `2.5`   | `3.5`   | Match status selectors        |
| `padding`        | `2px`   | `5px`   | Gap between outer and inner   |
| `background-color`| `#1e293b`| `#1e293b`| Unchanged, never tinted      |

**Kind-colored border selectors** — REMOVED entirely. The entire JS-generated
block that sets `border-color` and `border-width` per kind on `node[has_members="true"][kind="..."]`
is deleted. Kind color now lives in the HTML label.

**Change-status selectors** — Remove `background-color` overrides. Keep `border-width`,
`border-color`, `border-style`. The `deleted` selector keeps its `opacity: 0.6`.

Example diff (repeated for all four statuses):
```python
# BEFORE:
{ 'border-width': 3.5, 'border-color': '#10b981',
  'border-style': 'dashed', 'background-color': '#1e3a2e' }
# AFTER:
{ 'border-width': 3.5, 'border-color': '#10b981',
  'border-style': 'dashed' }
```

**Add `.uml-box-label` CSS rule** (appended via `add_cytoscape_cdn` or inline in the
graph page). This provides the inset border on the HTML label wrapper:

```css
.uml-box-label {
    border-radius: 4px;
    box-shadow: inset 0 0 0 2.5px var(--kind-border-color, transparent);
}
```

The `--kind-border-color` CSS variable is set inline on the HTML wrapper by
`_build_uml_html()`. Dependency/as-built boxes that shouldn't show an inner
border get `transparent` as the variable value, so no inner border appears.

### 2. `backend/graph/transforms.py` — `_build_uml_html()`

Add a `KIND_BORDER_COLORS` lookup dict at module level:

```python
KIND_BORDER_COLORS = {
    "class": "#4a90d9",
    "struct": "#5b9bd5",
    "interface": "#9b59b6",
    "enum": "#e74c3c",
}
```

Modify the wrapper `<div>` in `_build_uml_html()`:

```python
kind_border = KIND_BORDER_COLORS.get(owner_kind, "transparent")
wrapper = (
    f'<div style="'
    f'font-family:JetBrains Mono,monospace;'
    f'font-size:9px;'
    f'line-height:1.3;'
    f'padding:2px;'
    f'white-space:nowrap;'
    f'border-radius:4px;'
    f'box-shadow:inset 0 0 0 2.5px {kind_border};'
    f'">'
)
```

Changes from current wrapper:
- `padding:0px` → `padding:2px` (prevents text from touching inner border)
- Added `border-radius:4px` (matches Cytoscape roundrectangle)
- Added `box-shadow:inset 0 0 0 2.5px {kind_border}` (inner solid border)
- Kinds not in the lookup (dependency nodes, modules, etc.) get `"transparent"`,
  so the inner border is invisible

### 3. `backend/graph/builders.py` — No changes needed

The `change_status` and `kind` fields already flow correctly from Neo4j through
`_build_design_node`. No new data fields are required.

### 4. `frontend/widgets.py` — Legend stays as-is for now

The status legend section continues to show colored dots. A future update can
replace dots with small bordered rectangles and add a "inner = kind, outer = status"
annotation.

## Edge Cases

### HLR highlight and `has_requirements`

These selectors override the Cytoscape `border-color`, which is the outer border.
The inner kind-colored box-shadow is unaffected. No changes needed — the orange
highlight temporarily replaces the status border, which is correct behavior.

### `:selected` state

The gold selection overlay and wider border apply to the outer Cytoscape border only.
Inner border stays kind-colored. Works as-is.

### `change_status=""` (empty string)

All design nodes default to `change_status="new"` in `_build_design_node`. As a
fallback, the base UML box style uses `border-color: #4a5568` (neutral gray)
and `border-style: dashed`, so an empty-string status still renders sensibly.

### Kinds not in `KIND_BORDER_COLORS`

The lookup returns `"transparent"`, making the box-shadow invisible. The outer
border still renders correctly from status selectors. No visual breakage.

### Dependency and as-built UML boxes

Dependency UML boxes keep their current teal `double` border. No inner border
is added (`owner_kind` won't map, so `kind_border` is transparent). As-built
UML boxes have no specific `has_members` selector and are unaffected.

### Deleted nodes (`opacity: 0.6`)

Opacity applies to the entire Cytoscape node including the HTML overlay. Both
borders and text dim together. Correct behavior for indicating deletion.

## Files Changed

| File | Change |
|------|--------|
| `frontend/theme.py` | `cytoscape_base_styles()`: update base UML style, remove kind-border selectors, remove background-color from status selectors, add CSS for `.uml-box-label` |
| `backend/graph/transforms.py` | Add `KIND_BORDER_COLORS`, update `_build_uml_html()` wrapper div with `box-shadow`, `border-radius`, `padding` |
| `frontend/widgets.py` or `frontend/pages/ontology_graph.py` | Add `<style>` tag for `.uml-box-label` CSS rule |

## Not Changed

- `backend/graph/builders.py` — no data pipeline changes
- `backend/graph/__init__.py` — no transform pipeline changes
- `frontend/data/ontology.py` — no query changes
- Simple circle nodes — excluded from this change
- Legend — remains as colored dots for now
- Dependency/as-built node styling — unchanged