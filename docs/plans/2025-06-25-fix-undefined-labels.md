# Plan: Fix "undefined" Node Labels and UML Content Loss in Cytoscape Graph

## Scope

Fix Bug #1 (undefined labels) and Bug #2 (UML content loss):
JS code reads `node.data('name')` which is `undefined` because Python
builders set `label`, not `name`. The resulting `undefined` value then
**replaces** the multi-line PlantUML label (from `_build_uml_label`),
destroying attribute/method compartments.

## Changes

Three one-line JS fixes across two files:

### 1. `frontend/widgets.py` — render_cytoscape_graph()

**Line 363:** Change `node.data('name')` → `node.data('label')`
```
- node.data('label', node.data('name') + '\\n[' + source + ']');
+ node.data('label', node.data('label') + '\\n[' + source + ']');
```

**Line 366:** Same fix for as-built badge
```
- node.data('label', node.data('name') + '\\n[as-built]');
+ node.data('label', node.data('label') + '\\n[as-built]');
```

### 2. `frontend/pages/ontology_graph.py` — load_graph() HLR overlay

**Line 104:** Change `node.data('name')` → `node.data('label')`
```
- const baseName = node.data('name');
+ const baseName = node.data('label');
```

## Why This Fixes Both Bugs

**Bug #1 (undefined labels):** `node.data('name')` returned `undefined`
because builders set `label`, not `name`. Fixing the key resolves the
immediate display error.

**Bug #2 (UML content loss):** The original JS did a **replace** —
`node.data('label', <new value>)` overwrites the entire label. When
the source was `undefined`, the full PlantUML multi-line label was
replaced with `undefined\n[eigen]`. Now `node.data('label')` returns
the existing label (containing UML compartments), and the badge is
**appended** to it rather than replacing it.

Example: `Fl_Button\n──────\n+ handle()` → `Fl_Button\n──────\n+ handle()\n[eigen]`

## Status: DONE ✓

All three JS sites fixed. No remaining `node.data('name')` references.