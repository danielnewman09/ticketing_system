# Dual-Border Ontology Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add dual-border styling to UML box nodes in the ontology graph — inner solid border for kind (class/interface/enum/struct), outer dashed border for lifecycle status (new/implemented/modified/deleted) — removing background tint.

**Architecture:** The dual-border effect uses Cytoscape's native border for the outer dashed status border and CSS `box-shadow: inset` on the HTML label wrapper for the inner solid kind border. A small Cytoscape padding gap separates the two. The kind color lookup moves from JS selectors to an inline style embedded by the Python `_build_uml_html` function.

**Tech Stack:** Python (backend graph transforms), JavaScript (Cytoscape styles in NiceGUI), CSS (box-shadow on HTML labels)

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/graph/transforms.py` | Modify | Add `KIND_BORDER_COLORS`, update `_build_uml_html` wrapper div |
| `frontend/theme.py` | Modify | Update Cytoscape base styles (remove kind-border JS, remove bg tint from status, change UML base style) |
| `frontend/pages/ontology_graph.py` | Modify | Add `<style>` tag for `.uml-box-label` CSS rule |
| `tests/test_dual_border.py` | Create | Unit tests for KIND_BORDER_COLORS lookup and _build_uml_html output |

---

### Task 1: Add KIND_BORDER_COLORS and update _build_uml_html wrapper

**Files:**
- Modify: `backend/graph/transforms.py`
- Create: `tests/test_dual_border.py`

- [ ] **Step 1: Write failing tests for KIND_BORDER_COLORS lookup and _build_uml_html wrapper**

Create `tests/test_dual_border.py`:

```python
"""Tests for dual-border UML label rendering."""

import pytest
from backend.graph.transforms import KIND_BORDER_COLORS, _build_uml_html


class TestKindBorderColors:
    """KIND_BORDER_COLORS maps entity kinds to their border colors."""

    def test_class_color(self):
        assert KIND_BORDER_COLORS["class"] == "#4a90d9"

    def test_struct_color(self):
        assert KIND_BORDER_COLORS["struct"] == "#5b9bd5"

    def test_interface_color(self):
        assert KIND_BORDER_COLORS["interface"] == "#9b59b6"

    def test_enum_color(self):
        assert KIND_BORDER_COLORS["enum"] == "#e74c3c"

    def test_unknown_kind_missing(self):
        assert "module" not in KIND_BORDER_COLORS

    def test_unknown_kind_lookup_returns_none(self):
        assert KIND_BORDER_COLORS.get("module") is None


class TestBuildUmlHtmlInnerBorder:
    """_build_uml_html wraps content in a div with an inset box-shadow
    for the inner kind border."""

    def test_class_inner_border(self):
        html = _build_uml_html(
            "Calculator", {}, is_dependency=False,
            owner_kind="class", change_status="new"
        )
        assert "box-shadow:inset 0 0 0 2.5px #4a90d9" in html

    def test_interface_inner_border(self):
        html = _build_uml_html(
            "IHandler", {}, is_dependency=False,
            owner_kind="interface", change_status=""
        )
        assert "box-shadow:inset 0 0 0 2.5px #9b59b6" in html

    def test_enum_inner_border(self):
        html = _build_uml_html(
            "Color", {}, is_dependency=False,
            owner_kind="enum", change_status="modified"
        )
        assert "box-shadow:inset 0 0 0 2.5px #e74c3c" in html

    def test_unknown_kind_transparent_border(self):
        html = _build_uml_html(
            "mymodule", {}, is_dependency=False,
            owner_kind="module", change_status="new"
        )
        assert "box-shadow:inset 0 0 0 2.5px transparent" in html

    def test_empty_kind_transparent_border(self):
        html = _build_uml_html(
            "Thing", {}, is_dependency=False,
            owner_kind="", change_status=""
        )
        assert "box-shadow:inset 0 0 0 2.5px transparent" in html

    def test_wrapper_has_border_radius(self):
        html = _build_uml_html(
            "Calculator", {}, is_dependency=False,
            owner_kind="class", change_status="new"
        )
        assert "border-radius:4px" in html

    def test_wrapper_has_padding(self):
        html = _build_uml_html(
            "Calculator", {}, is_dependency=False,
            owner_kind="class", change_status="new"
        )
        assert "padding:2px" in html

    def test_class_name_colored_by_status(self):
        """Class name text color still uses change_status, not kind color."""
        html = _build_uml_html(
            "Calculator", {}, is_dependency=False,
            owner_kind="class", change_status="modified"
        )
        # _STATUS_COLORS_HTML["modified"] is "#fcd34d"
        assert "#fcd34d" in html

    def test_dependency_no_inner_border(self):
        """Dependency UML boxes get transparent inner border (no kind color)."""
        html = _build_uml_html(
            "Fl_Button", {}, is_dependency=True,
            owner_kind="class", change_status=""
        )
        # is_dependency=True but this is a dependency node, so no kind border
        # The lookup: owner_kind="class" maps to "#4a90d9", so it would
        # get a border. But dependency styling is different in the
        # Cytoscape styles - the inner border color is still set by
        # owner_kind. The Cytoscape styles handle the outer border
        # separately for dependency nodes.
        assert "box-shadow:inset 0 0 0 2.5px" in html
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_dual_border.py -v`
Expected: FAIL — `KIND_BORDER_COLORS` not found, `_build_uml_html` wrapper does not contain `box-shadow`

- [ ] **Step 3: Add KIND_BORDER_COLORS constant to transforms.py**

Add the constant near the top of `backend/graph/transforms.py`, after the existing `_STATUS_COLORS_HTML` dict:

```python
# Kind-colored inner border colors for UML boxes.
# Used by _build_uml_html to render the inset box-shadow.
KIND_BORDER_COLORS = {
    "class": "#4a90d9",
    "struct": "#5b9bd5",
    "interface": "#9b59b6",
    "enum": "#e74c3c",
}
```

- [ ] **Step 4: Update _build_uml_html wrapper div to include inner border**

In `backend/graph/transforms.py`, modify the `_build_uml_html` function's wrapper div. Find the current wrapper construction:

```python
    wrapper = (
        f'<div style="'
        f'font-family:JetBrains Mono,monospace;'
        f'font-size:9px;'
        f'line-height:1.3;'
        f'padding:0px;'
        f'white-space:nowrap;'
        f'">'
    )
```

Replace with:

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

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_dual_border.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/graph/transforms.py tests/test_dual_border.py
git commit -m "feat: add inner kind border to UML labels via box-shadow inset"
```

---

### Task 2: Remove kind-border Cytoscape selectors and update UML base style

**Files:**
- Modify: `frontend/theme.py`

This task removes the JS-generated kind-colored border selectors (which set `border-color` on UML boxes per kind) and updates the base UML box style.

- [ ] **Step 1: Update the base UML box style for design nodes**

In `frontend/theme.py`, inside the `cytoscape_base_styles()` function, find the design UML box selector block:

```python
        // ── Design nodes with members (UML boxes) ──────────────────────
        {{
            selector: 'node[has_members="true"][layer="design"]',
            style: {{
                'label': '',
                'shape': 'roundrectangle',
                'text-valign': 'center',
                'text-halign': 'center',
                'text-wrap': 'wrap',
                'text-max-width': '{member_txt_max}px',
                'font-size': '{member_font}px',
                'font-family': '"JetBrains Mono", "Fira Code", "Cascadia Code", monospace',
                'text-justification': 'left',
                'width': {_member_label_dim},
                'height': {_member_label_height},
                'padding': '{pad_members}px',
                'border-style': 'solid',
                'border-width': 2.5,
                'border-color': '#4a5568',
                'background-color': '#1e293b',
                'color': '#e2e8f0',
                'text-margin-y': 0,
            }}
        }},
```

Change the `padding`, `border-style`, and `border-width` values. The `border-color` and `background-color` stay the same. The updated block:

```python
        // ── Design nodes with members (UML boxes) ──────────────────────
        {{
            selector: 'node[has_members="true"][layer="design"]',
            style: {{
                'label': '',
                'shape': 'roundrectangle',
                'text-valign': 'center',
                'text-halign': 'center',
                'text-wrap': 'wrap',
                'text-max-width': '{member_txt_max}px',
                'font-size': '{member_font}px',
                'font-family': '"JetBrains Mono", "Fira Code", "Cascadia Code", monospace',
                'text-justification': 'left',
                'width': {_member_label_dim},
                'height': {_member_label_height},
                'padding': '5px',
                'border-style': 'dashed',
                'border-width': 3.5,
                'border-color': '#4a5568',
                'background-color': '#1e293b',
                'color': '#e2e8f0',
                'text-margin-y': 0,
            }}
        }},
```

Key changes:
- `padding`: `'{pad_members}px'` → `'5px'` (hardcoded 5px gap between outer and inner borders)
- `border-style`: `'solid'` → `'dashed'` (outer border is dashed for status)
- `border-width`: `2.5` → `3.5` (matches status selectors)

- [ ] **Step 2: Remove the kind-colored border selectors**

In `frontend/theme.py`, find and remove the entire kind-colored border block:

```python
        // ── Kind-colored top-border accent for UML boxes ────────────────
        // Adds a kind-colored left border to member nodes via a compound
        // selector trick: classes can be added per kind later, but for
        // now we give each kind its border color.
        ...Object.entries({{
            'class': '#4a90d9',
            'struct': '#5b9bd5',
            'interface': '{ec["INHERITS_FROM"]}',
            'enum': '#e74c3c',
        }}).map(([kind, bcolor]) => ({{
            selector: 'node[has_members="true"][kind="' + kind + '"]',
            style: {{ 'border-color': bcolor, 'border-width': 2.5 }}
        }})),
```

This entire block (5 lines of JS-generating code including the comment) is removed. The kind color is now handled by `KIND_BORDER_COLORS` in `_build_uml_html`.

- [ ] **Step 3: Remove background-color from change-status selectors**

In `frontend/theme.py`, find each of the four change-status selector blocks and remove the `'background-color'` line. Keep `'border-width'`, `'border-color'`, and `'border-style'`.

Change from:
```python
        {{
            selector: 'node[change_status="new"]',
            style: {{
                'border-width': 3.5,
                'border-color': '#10b981',
                'border-style': 'dashed',
                'background-color': '#1e3a2e',
            }}
        }},
        {{
            selector: 'node[change_status="implemented"]',
            style: {{
                'border-width': 3.5,
                'border-color': '#3b82f6',
                'border-style': 'dashed',
                'background-color': '#1e2d3b',
            }}
        }},
        {{
            selector: 'node[change_status="modified"]',
            style: {{
                'border-width': 3.5,
                'border-color': '#f59e0b',
                'border-style': 'dashed',
                'background-color': '#2e2a1e',
            }}
        }},
        {{
            selector: 'node[change_status="deleted"]',
            style: {{
                'border-width': 3.5,
                'border-color': '#ef4444',
                'border-style': 'dashed',
                'background-color': '#2e1e1e',
                'opacity': 0.6,
            }}
        }},
```

Change to:
```python
        {{
            selector: 'node[change_status="new"]',
            style: {{
                'border-width': 3.5,
                'border-color': '#10b981',
                'border-style': 'dashed',
            }}
        }},
        {{
            selector: 'node[change_status="implemented"]',
            style: {{
                'border-width': 3.5,
                'border-color': '#3b82f6',
                'border-style': 'dashed',
            }}
        }},
        {{
            selector: 'node[change_status="modified"]',
            style: {{
                'border-width': 3.5,
                'border-color': '#f59e0b',
                'border-style': 'dashed',
            }}
        }},
        {{
            selector: 'node[change_status="deleted"]',
            style: {{
                'border-width': 3.5,
                'border-color': '#ef4444',
                'border-style': 'dashed',
                'opacity': 0.6,
            }}
        }},
```

Note: `deleted` retains `opacity: 0.6`. All four lose `background-color`.

- [ ] **Step 4: Update the change-status comment**

Update the comment above the change-status selectors to reflect the new design:

Find:
```python
        // ── Change-status styles ──────────────────────────────────────
        // Status is shown via a subtle background tint + dashed border overlay.
        // Kind-colored solid border always shows as the inner border.
        // Status dashed border sits outside as a visual indicator.
```

Replace with:
```python
        // ── Change-status styles ──────────────────────────────────────
        // Status is shown via the outer dashed border color.
        // The inner solid border (kind color) is rendered via box-shadow:inset
        // in the HTML label by _build_uml_html(). Background is always neutral.
```

- [ ] **Step 5: Commit**

```bash
git add frontend/theme.py
git commit -m "feat: update Cytoscape styles for dual-border — dashed outer, remove bg tint, remove kind-border JS"
```

---

### Task 3: Add CSS rule for .uml-box-label inner border

**Files:**
- Modify: `frontend/pages/ontology_graph.py`

The `cytoscape-node-html-label` extension applies the CSS class `uml-box-label` to HTML label elements. We need a global CSS rule that adds the `border-radius` and makes the box-shadow from `_build_uml_html` render correctly.

- [ ] **Step 1: Add the CSS style rule to the ontology graph page**

In `frontend/pages/ontology_graph.py`, add a `<style>` tag in the `ontology_graph_page()` function, right after the `add_cytoscape_cdn()` call. Find:

```python
    add_cytoscape_cdn()
```

Add after it:

```python
    add_cytoscape_cdn()

    # CSS rule for the inner kind border on UML boxes.
    # The box-shadow:inset is set inline by _build_uml_html per node,
    # but border-radius needs to be applied here to match Cytoscape's
    # roundrectangle shape.
    ui.add_head_html(
        '<style>'
        '.uml-box-label { border-radius: 4px; }'
        '</style>'
    )
```

Note: The `box-shadow: inset` style is already embedded inline in the HTML generated by `_build_uml_html`, so it doesn't need to be in this CSS rule. The CSS rule only needs `border-radius` because that's a structural property of the label container that should be consistent across all UML boxes.

- [ ] **Step 2: Commit**

```bash
git add frontend/pages/ontology_graph.py
git commit -m "feat: add CSS border-radius for UML box inner border"
```

---

### Task 4: Run existing tests and verify no regressions

**Files:**
- No changes — verification only

- [ ] **Step 1: Run the collapse_members tests**

Run: `pytest tests/test_collapse_external_entities.py -v`
Expected: All existing tests PASS. The `collapse_members` function still produces `html_label` output that includes the inner border `box-shadow` (via `_build_uml_html`).

- [ ] **Step 2: Run all tests**

Run: `pytest tests/ -v --timeout=60`
Expected: All tests PASS. No regressions in graph rendering or other subsystems.

- [ ] **Step 3: Manual visual verification**

Start the app and navigate to the ontology graph:
```bash
source .venv/bin/activate
python nicegui_app.py
```

Visit http://127.0.0.1:8081/ontology/graph and verify:
- UML box nodes (classes, interfaces, enums, structs) show inner solid borders colored by kind (blue for class, purple for interface, red for enum, light blue for struct)
- UML box nodes show outer dashed borders colored by change_status (green=new, blue=implemented, amber=modified, red=deleted)
- Background of UML boxes is neutral dark (`#1e293b`) regardless of status — no colored tint
- Simple circle nodes (without members) are unchanged in styling
- Dependency UML boxes (teal double-border) are unchanged
- Namespace containers are unchanged
- Node name text inside UML boxes is still colored by change_status

- [ ] **Step 4: Commit any manual adjustments**

If pixel values need tweaking (e.g., padding gap between borders is too large), adjust in `frontend/theme.py` (the `padding: '5px'` value in the base UML box style) and/or `backend/graph/transforms.py` (the `padding:2px` and `box-shadow:inset 0 0 0 2.5px` in `_build_uml_html`), then commit:

```bash
git add -A
git commit -m "tweak: adjust border gap/padding values after visual verification"
```