# Cytoscape Graph Rendering Bugs — Fix Design

## Problem

Four bugs in the Cytoscape.js dependency graph rendering:

1. **"undefined" node labels** on dependency and as-built layer nodes. JS code
   reads `node.data('name')` but Python builders only set `label` — no `name`
   key exists on the node data dict.

2. **UML content lost** — JS label override `node.data('label',
   node.data('name') + '\n[...]')` replaces the multi-line PlantUML label
   (built by `_build_uml_label` / `collapse_members`) with `undefined
   \n[eigen]`, destroying the attribute/method compartments.

3. **"Maximum call stack size exceeded"** in `is-binary.js` (cose-base@2.2.0,
   used by fcose layout). Root cause: dangling edges in the design layer
   query (`fetch_design_graph`) — edge targets are added to the `node_qns`
   set but **not** to the `nodes` list, creating Cytoscape edges pointing to
   non-existent nodes.  fcose issue #13 confirms dangling edges cause
   infinite recursion in the coarsening phase.  A secondary contributor is
   duplicate edge IDs from `build_cytoscape_edge()`, which generates IDs as
   `f"e_{source}_{target}_{type}"` — two edges with the same
   source/target/type get the same ID, corrupting Cytoscape internals.

4. **f-string navigation bug** — `f"/node/{{nid}}"` and
   `f"/node/{{node_id}}"` in `node_detail.py` and `hlr_detail.py` use
   double braces, producing literal `{nid}` / `{node_id}` URLs instead
   of the resolved variable value.  `component_detail.py` has the
   correct form.

## Root Cause Analysis

### Bug 1 & 2: JS reads `name`, Python sets `label`

**Data flow:**

```
Neo4j raw dict → build_cytoscape_node() → {"id", "label", "qualified_name", ...}
                                                  ↑
                                            no "name" key
```

Three JS sites read `node.data('name')`:

| File | Line | Code |
|------|------|------|
| `frontend/widgets.py` | 363 | `node.data('label', node.data('name') + '\n[' + source + ']')` |
| `frontend/widgets.py` | 366 | `node.data('label', node.data('name') + '\n[as-built]')` |
| `frontend/pages/ontology_graph.py` | 104–105 | `const baseName = node.data('name'); node.data('label', baseName + '\n' + badges)` |

`node.data('name')` returns `undefined`. The overwrite destroys the
existing `label` (which may contain the multi-line PlantUML content
from `collapse_members` / `_build_uml_label`).

### Bug 3: eval() return value causes socket.io stack overflow

**Actual root cause (confirmed via Playwright MCP diagnostics):**

When NiceGUI's `ui.run_javascript()` executes the Cytoscape rendering
code, it uses `eval(code)` on the client side. The last statement
in the rendering code is:

```javascript
window._cy.on('dbltap', 'node', function(evt) { ... });
```

The Cytoscape `.on()` method returns the Cytoscape instance (for
chaining). So `eval(code)` returns the Cytoscape instance, which has
circular references throughout its internal structure (e.g.,
`cy → elements → nodes → cy`, `cy → container → DOM → ...`).

When `run_javascript` is awaited, NiceGUI sends the eval result
back to the server via `window.socket.emit('javascript_response',
{result})`. Socket.io's `hasBinary` function recursively traverses
the result object to check for binary data, hits the circular
references in the Cytoscape instance, and overflows the call stack.

**Fix:** Add `void 0;` as the last statement in the JS code to
ensure `eval()` returns `undefined` instead of the Cytoscape instance.

**Secondary contributor — dangling edges:**

In `fetch_design_graph()` (second Cypher query):

```python
if tgt not in node_qns:
    node_qns.add(tgt)       # ← added to tracking set
    # ← NOT added to `nodes` list!
edges.append({"source": src, "target": tgt, "type": rel_type})
```

The target qualified name is added to `node_qns` (used for later
dedup checks) but never actually fetched from Neo4j or appended to
`nodes`.  Cytoscape receives an edge referencing a non-existent node,
which triggers infinite recursion in fcose's `isBinary()` coarsening
phase.

**Duplicate edge IDs:** `build_cytoscape_edge()` generates
`f"e_{source}_{target}_{type}"`.  When the same source→target pair has
multiple edges of the same type (from different query branches or
dedup failures), Cytoscape gets duplicate element IDs.

### Bug 4: Double-brace f-strings

Python f-strings use `{var}` for interpolation and `{{` / `}}` for
literal braces.  `f"/node/{{nid}}"` produces the string `/node/{nid}`
— the `/node/` route is never reached.

## Approaches

### Approach A: Move all label decoration to Python, remove JS overrides

**Principle:** Labels are a data concern, not a rendering concern.
All badge/suffix annotation (source, as-built, HLR) is done in the
Python pipeline.  JS never mutates `node.data('label')`.

**Changes:**

| Component | Change |
|-----------|--------|
| `_build_dependency_node()` | Append `\n[source_name]` to `label` when `source` is non-empty |
| `_build_compound_node()` | Append `\n[as-built]` to `label` when `layer == "as-built"` |
| `tag_cross_layer()` | Append source badge and as-built badge to label (centralised location) |
| `enrich_with_requirement_tags()` | Append `\n[HLR 1] [HLR 2]` to `label` and set `is_hlr_highlight` |
| `tag_direct_nodes_only()` | Same badge append for HLR subgraph nodes |
| `render_cytoscape_graph()` JS | **Remove** all `node.data('label', ...)` overrides |
| `ontology_graph.py` `load_graph()` | **Remove** HLR overlay JS block |
| `fetch_design_graph()` | Fix dangling edges — fetch missing edge-target nodes or skip edges whose target isn't in `nodes` |
| `build_cytoscape_edge()` | Add index counter or UUID suffix for uniqueness |
| `node_detail.py` / `hlr_detail.py` | Fix f-string double-brace bug |

**Pros:**
- Single source of truth for labels — all in Python, no split logic
- UML label content naturally preserved (badge appended to the *end* of the label)
- No "undefined" issue since JS doesn't touch labels
- Simpler JS code (fewer lines, fewer bugs)
- All four bugs fixed

**Cons:**
- HLR badge toggle requires Python-side `load_graph()` call (already true — the toggle handler does `await load_graph()`)
- Source badge is less "dynamic" — but it's data, not UI state, so shouldn't be dynamic
- Minor: appending badges at the end of a UML label may not match standard UML notation (badge appears below the last compartment rather than in the class name header)

### Approach B: Fix JS to use `label` key, append instead of replace

**Principle:** Keep JS label decoration but fix it to use the correct
data key and preserve existing content by appending.

**Changes:**

| Component | Change |
|-----------|--------|
| `render_cytoscape_graph()` JS | Replace `node.data('name')` with `node.data('label').split('\\n')[0]` for the base name; append badge instead of replacing full label |
| `ontology_graph.py` JS | Same fix for HLR overlay |
| `fetch_design_graph()` | Fix dangling edges (same as Approach A) |
| `build_cytoscape_edge()` | Fix duplicate IDs (same as Approach A) |
| `node_detail.py` / `hlr_detail.py` | Fix f-string bug (same as Approach A) |

**Pros:**
- Smaller diff — fewer Python files changed
- Dynamic label manipulation stays in JS

**Cons:**
- Label decoration logic is still split across Python (UML collapse) and JS (badges) — two sources of truth
- JS parsing `label.split('\n')[0]` is fragile — depends on label format convention
- UML label header gets the badge (looks odd: `ClassName\n──────` becomes `ClassName [eigen]\n──────`) — but only the first line is extracted, so it would be `ClassName [eigen]\n──────` which is actually fine
- Future label modifications in Python (e.g. new badge types) may conflict with JS overrides

### Approach C: Add `name` key to all builders as alias, fix JS to preserve label

**Principle:** Give JS the `name` key it expects, and change JS to
append to the existing label rather than replace it.

**Changes:**

| Component | Change |
|-----------|--------|
| `_build_design_node()` | Add `"name": d.get("name", "")` |
| `_build_dependency_node()` | Add `"name": d.get("name", "")` |
| `_build_compound_node()` | Add `"name": d.get("name", "")` |
| `render_cytoscape_graph()` JS | Change `node.data('name')` → `node.data('name')` (now works); but change replace to append: `node.data('label', node.data('label') + '\n[' + source + ']')` |
| `ontology_graph.py` JS | Same: `node.data('label', node.data('label') + '\n' + badges)` |
| `fetch_design_graph()` | Fix dangling edges (same as A) |
| `build_cytoscape_edge()` | Fix duplicate IDs (same as A) |
| `node_detail.py` / `hlr_detail.py` | Fix f-string bug (same as A) |

**Pros:**
- Minimal disruption — JS keeps its pattern, just uses correct key
- `name` is a natural key for node data (matches Cytoscape convention)
- UML content preserved by appending instead of replacing

**Cons:**
- Redundant data: `name` and `label` hold the same pre-UML value — but `label` gets replaced by UML content, so they diverge, which is correct (`name` = class name, `label` = full UML label)
- Adding `name` is a mild violation of "single source of truth" for the initial name — but it's a standard Cytoscape key that the JS legitimately uses
- Badge appended below UML compartments (minor layout oddity)

## Recommendation

**Approach A** — move all label decoration to Python and remove JS overrides.

Rationale:
1. The HLR badge toggle already triggers a full `load_graph()` call, so
   there is no performance benefit from JS-side label updates.
2. Source and as-built badges are data properties, not UI toggle state —
   they belong in the data pipeline.
3. Removing JS label overrides eliminates an entire class of bugs
   (`name` vs `label` key mismatches, overwrite vs append, UML
   destruction).
4. The Python pipeline already owns label construction
   (`_build_uml_label`) — extending it to include badges is natural and
   consistent.
5. The minor UML notation oddity (badge at bottom instead of header) is
   an acceptable trade-off for correctness, and can be refined later
   with a helper that inserts the badge into the first line of the
   multi-line label.

## Specification

### 0. Fix eval() return value causing socket.io stack overflow

**File:** `frontend/widgets.py` → `render_cytoscape_graph()`

The last statement in the `ui.run_javascript()` code block is
`window.{cy_var}.on(...)` which returns the Cytoscape instance (for
chaining). When `eval()` captures this return value, NiceGUI sends it
back to the server via `window.socket.emit('javascript_response',
{result})`. Socket.io's `hasBinary` traverses the Cytoscape instance,
hits its internal circular references, and overflows the call stack.

**Fix:** Add `void 0;` as the last statement so `eval()` returns
`undefined`:

```javascript
        }} else {{
            console.error('{config.container_id} not found');
        }}
        void 0;  // prevent eval returning the cy instance (circular refs)
```

**This is the primary fix for Bug #3** — the stack overflow error
observed in the browser console.

### 1. Fix dangling edges in `fetch_design_graph()`

**File:** `backend/db/neo4j/queries/graph.py`

In the second Cypher query result loop, when `tgt not in node_qns`,
the target must be fetched and added to `nodes`, not just to `node_qns`.
Alternatively, edges whose target is not in `node_qns` (i.e. not in the
initial node set) should be filtered out.

**Chosen method:** Filter out edges whose target isn't in the initial
node set.  This avoids an extra N+1 query pattern.  The current code
*adds* `tgt` to `node_qns` (the dedup set) without fetching the node —
this is the bug.  The fix simply removes that `node_qns.add(tgt)` line
and adds a guard: only append the edge when `tgt in node_qns` (i.e.
both endpoints are in the node list).

**Before:**
```python
if tgt not in node_qns:
    node_qns.add(tgt)
edges.append({"source": src, "target": tgt, "type": rel_type})
```

**After:**
```python
if src in node_qns and tgt in node_qns:
    edges.append({"source": src, "target": tgt, "type": rel_type})
```

This filters edges to only those where both endpoints are already in
the fetched node set.  If the search/filter is narrow enough that a
node appears only as an edge target but not as a query match, the edge
is dropped.  This is correct — a dangling edge is worse for the
visualisation than a missing edge.

### 2. Fix duplicate edge IDs in `build_cytoscape_edge()`

**File:** `backend/graph/builders.py`

Add a global counter to disambiguate edges with the same
source/target/type triple.

**Before:**
```python
def build_cytoscape_edge(e: dict) -> dict:
    return {
        "id": f"e_{e.get('source', '')}_{e.get('target', '')}_{e.get('type', '')}",
        ...
    }
```

**After:**
```python
_edge_counter = 0

def build_cytoscape_edge(e: dict) -> dict:
    global _edge_counter
    _edge_counter += 1
    return {
        "id": f"e_{_edge_counter}_{e.get('source', '')}_{e.get('target', '')}_{e.get('type', '')}",
        ...
    }
```

The counter resets per Python process reload, which is fine — edge IDs
only need to be unique within a single graph render.

### 3. Move label decoration from JS to Python

#### 3a. Source badge on dependency nodes

**File:** `backend/graph/__init__.py` → `tag_cross_layer()`

After setting `has_source='true'`, also append `\n[source_value]` to the
node's label:

```python
if d.get("source") and layer == "dependency":
    d["has_source"] = "true"
    d["label"] = d["label"] + "\n[" + d["source"] + "]"
```

This runs *after* `collapse_members()` / `_build_uml_label()`, so it
appends to the full UML label, preserving the member compartments.

#### 3b. As-built badge

Same function, when `is_as_built`:

```python
if layer == "as-built":
    d["is_as_built"] = "true"
    d["label"] = d["label"] + "\n[as-built]"
```

#### 3c. HLR requirement badges

**File:** `backend/requirements/services/graph_tags.py`

In `enrich_with_requirement_tags()`, after setting `node["requirements"]`,
also append badge text to the label:

```python
if qn in qn_to_reqs:
    node["requirements"] = qn_to_reqs[qn]
    badges = " ".join(f"[{r['type']} {r['id']}]" for r in qn_to_reqs[qn])
    node["label"] = node["label"] + "\n" + badges
```

In `tag_direct_nodes_only()`, similarly append badges:

```python
if qn in seed_qns:
    node["is_hlr_highlight"] = "true"
    req = {"id": hlr_id, "type": "HLR", "description": hlr_desc}
    node.setdefault("requirements", []).append(req)
    node["label"] = node.get("label", "") + f"\n[HLR {hlr_id}]"
```

#### 3d. Remove JS label overrides

**File:** `frontend/widgets.py` → `render_cytoscape_graph()`

Remove the `window.{cy_var}.nodes().forEach(...)` block that mutates
labels.  The block is:
```javascript
window.{cy_var}.nodes().forEach(function(node) {{
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

**File:** `frontend/pages/ontology_graph.py` → `load_graph()`

Remove the HLR overlay JS block:
```javascript
if (window._cy) {
    window._cy.nodes().forEach(function(node) {
        const reqs = node.data('requirements');
        if (reqs && reqs.length > 0) {
            const badges = reqs.map(r => '[' + r.type + ' ' + r.id + ']').join(' ');
            const baseName = node.data('name');
            node.data('label', baseName + '\\n' + badges);
            node.addClass('has-requirements');
        }
    });
}
```

The `addClass('has-requirements')` logic can be moved to the Python
pipeline as a data attribute (`"has_requirements": "true"`) with a
corresponding Cytoscape style selector.

### 4. Fix f-string navigation bugs

**File:** `frontend/pages/node_detail.py`

```python
# Before:
ui.navigate.to(f"/node/{{nid}}")
# After:
ui.navigate.to(f"/node/{nid}")
```

**File:** `frontend/pages/hlr_detail.py`

```python
# Before:
ui.navigate.to(f"/node/{{node_id}}")
# After:
ui.navigate.to(f"/node/{node_id}")
```

### 5. Add `has-requirements` Cytoscape style

**File:** `frontend/theme.py`

Add a Cytoscape style for nodes with `has_requirements: "true"`:

```python
{
    "selector": "node[has_requirements]",
    "style": {
        "border-color": "#e67e22",
        "border-width": 3,
    },
},
```

This replaces the JS `addClass('has-requirements')` logic with a
declarative style driven by the `has_requirements` data attribute
set in Python.

## Implementation Plan

| Step | File(s) | Change | Bug Fixed |
|------|---------|--------|-----------|
| 0 | `frontend/widgets.py` | Add `void 0;` to `render_cytoscape_graph()` JS to prevent eval returning cy instance | #3 (stack overflow — primary fix) |
| 1 | `backend/db/neo4j/queries/graph.py` | Fix dangling edges — filter edges to both-endpoints-in-set | #3 (data integrity) |
| 2 | `backend/graph/builders.py` | Add counter to `build_cytoscape_edge()` for unique IDs | #3 (data integrity) |
| 3 | `backend/graph/__init__.py` | Append source/as-built badges to label in `tag_cross_layer()` | #1, #2 |
| 4 | `backend/requirements/services/graph_tags.py` | Append HLR badges to label; set `has_requirements` attribute; fix Cytoscape node data access (`n["data"]`) | #1, #2 |
| 5 | `frontend/widgets.py` | Remove JS `node.data('label', ...)` overrides | #1, #2 |
| 6 | `frontend/pages/ontology_graph.py` | Remove HLR overlay JS block | #1, #2 |
| 7 | `frontend/theme.py` | Add `has-requirements` Cytoscape style selector | #2 (visual) |
| 8 | `frontend/pages/node_detail.py` | Fix f-string `{{nid}}` → `{nid}` | #4 |
| 9 | `frontend/pages/hlr_detail.py` | Fix f-string `{{node_id}}` → `{node_id}` | #4 |
| 10 | Test | Verify: no "undefined" labels, UML preserved, no stack overflow, navigation works | All |