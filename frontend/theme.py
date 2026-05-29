"""Theme constants and application."""

import json

from nicegui import ui

# ---------------------------------------------------------------------------
# Semantic color palette
# ---------------------------------------------------------------------------

COLORS = {
    "primary": "#5c7cfa",
    "secondary": "#16213e",
    "accent": "#0f3460",
    "positive": "#10b981",
    "negative": "#ef4444",
    "warning": "#f59e0b",
    "info": "#3b82f6",
}

# ---------------------------------------------------------------------------
# Dark-theme background surfaces
# ---------------------------------------------------------------------------

BACKGROUNDS = {
    "base": "#1a1a2e",  # deepest background (graph canvas, drawer)
    "panel": "#0f172a",  # agent console, fixed panels
    "surface": "#1e293b",  # raised cards/alerts
    "border": "#334155",  # subtle borders
}

# ---------------------------------------------------------------------------
# Domain-specific color maps
# ---------------------------------------------------------------------------

VERIFICATION_COLORS = {
    "automated": "positive",
    "review": "warning",
    "inspection": "info",
}

KIND_COLORS = {
    "class": "#4a90d9",
    "struct": "#5b9bd5",
    "interface": "#9b59b6",
    "enum": "#e74c3c",
    "method": "#2ecc71",
    "attribute": "#d4a843",
    "module": "#1abc9c",
    "function": "#27ae60",
    "constant": "#7f8c8d",
    "primitive": "#95a5a6",
    "type_alias": "#e67e22",
    "variable": "#d4a843",
}

EDGE_COLORS = {
    "INHERITS_FROM": "#9b59b6",
    "IMPLEMENTED_BY": "#3b82f6",
    "CROSS_LAYER": "#009688",
    "HAS_ARGUMENT": "#5dade2",
    "RETURNS": "#58d68d",
    "REFERENCES": "#f0b27a",
    "DEPENDS_ON": "#e59866",
    "AGGREGATES": "#af7ac5",
    "COMPOSES": "#7f8c8d",
    "default": "#555",
}

STATUS_COLORS = {
    "accepted": "#10b981",
    "rejected_stdlib": "#60a5fa",
    "rejected": "#6b7280",
    "selected": "#f1c40f",
    "hlr_highlight": "#e67e22",
    "namespace": "#1abc9c",
}

LAYER_STYLES = {
    "design": {"border_style": "dashed", "opacity": 1.0},
    "as-built": {"border_style": "solid", "opacity": 0.7},
}

# Change-status colors — for future use when design modifies existing objects
CHANGE_STATUS_COLORS = {
    "new": "#10b981",        # green border glow
    "implemented": "#3b82f6",   # blue - already exists in codebase
    "modified": "#f59e0b",     # amber border glow
    "deleted": "#ef4444",      # red strikethrough / dashed
}

# ---------------------------------------------------------------------------
# Reusable Tailwind class strings
# ---------------------------------------------------------------------------

CLS_SECTION_HEADER = "text-xs uppercase tracking-wider text-gray-400 mb-2"
CLS_SECTION_SUBHEADER = "text-xs text-gray-500 uppercase tracking-wider mb-1"
CLS_PAGE_TITLE = "text-2xl font-bold"
CLS_BREADCRUMB_LINK = "text-blue-400 text-sm no-underline"
CLS_BREADCRUMB_SEP = "text-gray-500 text-sm"
CLS_BREADCRUMB_CURRENT = "text-sm text-gray-300"
CLS_CARD_FULL = "w-full"
CLS_CARD_SECTION = "w-full mx-2 mt-4"
CLS_DIALOG_SM = "w-80"
CLS_DIALOG_MD = "w-96"
CLS_DIALOG_LG = "w-[480px]"
CLS_DIALOG_TITLE = "text-lg font-bold mb-2"
CLS_DIALOG_ACTIONS = "w-full justify-end gap-2 mt-4"

# ---------------------------------------------------------------------------
# Cytoscape helpers
# ---------------------------------------------------------------------------

CYTOSCAPE_CDN = (
    '<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">'
    '<script src="https://unpkg.com/cytoscape@3.30.4/dist/cytoscape.min.js"></script>'
    '<script src="https://unpkg.com/layout-base@2.0.1/layout-base.js"></script>'
    '<script src="https://unpkg.com/cose-base@2.2.0/cose-base.js"></script>'
    '<script src="https://unpkg.com/cytoscape-fcose@2.2.0/cytoscape-fcose.js"></script>'
    '<script src="https://cdn.jsdelivr.net/npm/cytoscape-node-html-label@1.2.2/dist/cytoscape-node-html-label.js"></script>'
)

KIND_COLORS_JS = json.dumps(KIND_COLORS)
EDGE_COLORS_JS = json.dumps(EDGE_COLORS)
CHANGE_STATUS_COLORS_JS = json.dumps(CHANGE_STATUS_COLORS)


def cytoscape_base_styles(*, size: str = "small") -> str:
    """Return a JS array literal of common Cytoscape node/edge styles.

    *size* controls node dimensions:
      - ``"small"`` -> 30px nodes, 9px text  (detail pages)
      - ``"large"`` -> 40px nodes, 10px text (full graph page)

    Visual design principles:
    - Member-bearing nodes use monospace labels with kind-colored borders
    - Non-member nodes are circles with kind-colored fill
    - Design nodes: dashed border with kind color; Dependency: dotted teal;
      As-built: solid blue-dotted
    - Edge colors distinguish relationship semantics (inheritance, argument,
      return, reference, dependency, aggregation)
    - UML stereotypes (<<class>>, <<interface>>, <<enumeration>>) in labels
    - Type-origin markers (\u25cf builtin, \u25c6 linked, \u25b8 dependency) inline
    - Change-status borders ready for new/modified/deleted design nodes
    """
    if size == "large":
        node_w, node_h, font, txt_max, txt_margin = 40, 40, 10, 80, 4
        pad_members, member_font, member_txt_max = 2, 9, 280
        edge_font = 8
        ns_font, ns_pad = 11, 20
    else:
        node_w, node_h, font, txt_max, txt_margin = 30, 30, 9, 70, 3
        pad_members, member_font, member_txt_max = 2, 8, 220
        edge_font = 7
        ns_font, ns_pad = 10, 16

    bg = BACKGROUNDS
    ec = EDGE_COLORS
    sc = STATUS_COLORS

    # Font metrics helper for function-style width/height (replaces deprecated 'label' value)
    _member_label_dim = f"""function(ele) {{
                const ctx = document.createElement('canvas').getContext('2d');
                ctx.font = '{member_font}px "JetBrains Mono", monospace';
                const label = ele.data('label') || '';
                const lines = label.split('\\n');
                let maxW = 0;
                lines.forEach(l => {{ maxW = Math.max(maxW, ctx.measureText(l).width); }});
                // HTML rendering expands text width by ~1.35-1.45x due to syntax
                // markup, type annotations, and member prefixes not in plain label.
                return Math.max(Math.ceil(maxW * 1.45), 50);
            }}"""
    _member_label_height = f"""function(ele) {{
                const label = ele.data('label') || '';
                const lines = label.split('\\n');
                // ~15px per line covers 9px font × 1.3 line-height plus HTML
                // markup expansion.  Flat +18 covers stereotype, class name, and
                // hr separators that don't scale with line count.
                return Math.max(lines.length * 15 + 18, 40);
            }}"""

    # Kind-specific border colors for member-bearing design nodes
    # These give the UML box a colored header-like appearance
    kind_border_map = {
        "class": ec.get("default", "#aaa"),
        "struct": "#5b9bd5",
        "interface": ec.get("INHERITS_FROM", "#9b59b6"),
        "enum": ec.get("AGGREGATES", "#e74c3c"),
    }

    return f"""[
        // ── Design nodes (no members) ─────────────────────────────────
        {{
            selector: 'node[layer="design"][!has_members]',
            style: {{
                'label': 'data(label)',
                'background-color': '#666',
                'color': '#ddd',
                'text-valign': 'bottom',
                'text-halign': 'center',
                'font-size': '{font}px',
                'width': {node_w},
                'height': {node_h},
                'border-width': 2,
                'border-style': 'dashed',
                'border-color': '#aaa',
                'text-wrap': 'ellipsis',
                'text-max-width': '{txt_max}px',
                'text-margin-y': {txt_margin},
            }}
        }},
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
                'padding': '2px',
                'border-style': 'none',
                'border-width': 0,
                'border-color': 'transparent',
                'background-color': '#1e293b',
                'color': '#e2e8f0',
                'text-margin-y': 0,
            }}
        }},
        // ── Dependency nodes (no members) ───────────────────────────────
        {{
            selector: 'node[layer="dependency"][!has_members]',
            style: {{
                'label': 'data(label)',
                'background-color': '#2d3748',
                'color': '#a0aec0',
                'text-valign': 'bottom',
                'text-halign': 'center',
                'font-size': '{font}px',
                'width': {node_w},
                'height': {node_h},
                'border-width': 2,
                'border-style': 'dotted',
                'border-color': '#009688',
                'text-wrap': 'ellipsis',
                'text-max-width': '{txt_max}px',
                'text-margin-y': {txt_margin},
            }}
        }},
        // ── Dependency nodes with members ─────────────────────────────
        {{
            selector: 'node[has_members="true"][layer="dependency"]',
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
                'border-style': 'double',
                'border-width': 3,
                'border-color': '#009688',
                'background-color': '#1a2332',
                'color': '#b0bec5',
                'text-margin-y': 0,
            }}
        }},
        // ── Namespace containers ───────────────────────────────────────
        {{
            selector: 'node[is_namespace="true"]',
            style: {{
                'shape': 'roundrectangle',
                'background-color': '{bg["base"]}',
                'background-opacity': 0.6,
                'border-width': 2,
                'border-style': 'dashed',
                'border-color': '{sc["namespace"]}',
                'label': 'data(label)',
                'color': '{sc["namespace"]}',
                'text-valign': 'top',
                'text-halign': 'center',
                'font-size': '{ns_font}px',
                'font-weight': 'bold',
                'padding': '{ns_pad}px',
                'text-margin-y': -4,
            }}
        }},
        // ── As-built nodes ──────────────────────────────────────────────
        {{
            selector: 'node[layer="as-built"]',
            style: {{
                'label': 'data(label)',
                'background-color': '#2d3748',
                'color': '#a0aec0',
                'text-valign': 'bottom',
                'text-halign': 'center',
                'font-size': '{font}px',
                'width': {node_w - 2},
                'height': {node_h - 2},
                'border-width': 2,
                'border-style': 'solid',
                'border-color': '#3b82f6',
                'text-wrap': 'ellipsis',
                'text-max-width': '{txt_max}px',
                'text-margin-y': {txt_margin},
            }}
        }},
        // ── Kind-specific fills (design, as-built, dependency) ─────────
        ...Object.entries(KIND_COLORS).flatMap(([kind, color]) => [
            {{
                selector: 'node[kind="' + kind + '"][layer="design"][!has_members]',
                style: {{ 'background-color': color }}
            }},
            {{
                selector: 'node[kind="' + kind + '"][layer="as-built"]',
                style: {{ 'background-color': color, 'background-blacken': 0.3 }}
            }},
            {{
                selector: 'node[kind="' + kind + '"][layer="dependency"][!has_members]',
                style: {{ 'background-color': color, 'background-blacken': 0.25 }}
            }},
        ]),
        // ── Requirement highlight ────────────────────────────────────────
        {{
            selector: 'node[is_hlr_highlight = "true"]',
            style: {{
                'border-width': 3,
                'border-color': '{sc["hlr_highlight"]}',
                'border-style': 'solid',
            }}
        }},
        {{
            selector: 'node[has_requirements]',
            style: {{
                'border-color': '#e67e22',
                'border-width': 3,
            }}
        }},
        {{
            selector: 'node.has-requirements',
            style: {{
                'font-size': '{font + 1}px',
            }}
        }},
        // ── Dependency source badge ─────────────────────────────────────
        {{
            selector: 'node[has_source="true"]',
            style: {{
                'border-color': '#009688',
                'border-style': 'dotted',
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
        // ── Change-status styles ──────────────────────────────────────
        // For UML boxes (has_members), the outer dashed border is CSS-rendered
        // in the HTML label. These selectors only affect simple circle nodes.
        {{
            selector: 'node[change_status="new"][!has_members]',
            style: {{
                'border-width': 2,
                'border-color': '#10b981',
                'border-style': 'dashed',
            }}
        }},
        {{
            selector: 'node[change_status="implemented"][!has_members]',
            style: {{
                'border-width': 2,
                'border-color': '#3b82f6',
                'border-style': 'dashed',
            }}
        }},
        {{
            selector: 'node[change_status="modified"][!has_members]',
            style: {{
                'border-color': '#f59e0b',
                'border-style': 'dashed',
                'border-width': 2,
            }}
        }},
        {{
            selector: 'node[change_status="deleted"][!has_members]',
            style: {{
                'border-width': 2,
                'border-color': '#ef4444',
                'border-style': 'dashed',
                'opacity': 0.6,
            }}
        }},
        // ── Edges (global) ───────────────────────────────────────────────
        {{
            selector: 'edge',
            style: {{
                'label': 'data(label)',
                'width': 1.5,
                'line-color': '{ec["default"]}',
                'target-arrow-color': '{ec["default"]}',
                'target-arrow-shape': 'triangle',
                'curve-style': 'bezier',
                'font-size': '{edge_font}px',
                'color': '#718096',
                'text-rotation': 'autorotate',
                'text-outline-color': '{bg["base"]}',
                'text-outline-width': 2,
                'text-outline-opacity': 0.8,
            }}
        }},
        // ── INHERITS_FROM ────────────────────────────────────────────────
        {{
            selector: 'edge[label="INHERITS_FROM"]',
            style: {{
                'line-style': 'solid',
                'line-color': '{ec["INHERITS_FROM"]}',
                'target-arrow-color': '{ec["INHERITS_FROM"]}',
                'target-arrow-shape': 'triangle-tee',
                'width': 2,
            }}
        }},
        // ── IMPLEMENTED_BY ───────────────────────────────────────────────
        {{
            selector: 'edge[label="IMPLEMENTED_BY"]',
            style: {{
                'line-style': 'dotted',
                'line-color': '{ec["IMPLEMENTED_BY"]}',
                'target-arrow-color': '{ec["IMPLEMENTED_BY"]}',
                'width': 1,
            }}
        }},
        // ── HAS_ARGUMENT ────────────────────────────────────────────────
        {{
            selector: 'edge[label="HAS_ARGUMENT"]',
            style: {{
                'line-style': 'dashed',
                'line-color': '{ec["HAS_ARGUMENT"]}',
                'target-arrow-color': '{ec["HAS_ARGUMENT"]}',
                'target-arrow-shape': 'diamond',
                'width': 1.5,
            }}
        }},
        // ── RETURNS ──────────────────────────────────────────────────────
        {{
            selector: 'edge[label="RETURNS"]',
            style: {{
                'line-style': 'dashed',
                'line-color': '{ec["RETURNS"]}',
                'target-arrow-color': '{ec["RETURNS"]}',
                'target-arrow-shape': 'triangle-cross',
                'width': 1.5,
            }}
        }},
        // ── REFERENCES ──────────────────────────────────────────────────
        {{
            selector: 'edge[label="REFERENCES"]',
            style: {{
                'line-style': 'dashed',
                'line-color': '{ec["REFERENCES"]}',
                'target-arrow-color': '{ec["REFERENCES"]}',
                'width': 1.5,
            }}
        }},
        // ── DEPENDS_ON ──────────────────────────────────────────────────
        {{
            selector: 'edge[label="DEPENDS_ON"]',
            style: {{
                'line-style': 'dashed',
                'line-color': '{ec["DEPENDS_ON"]}',
                'target-arrow-color': '{ec["DEPENDS_ON"]}',
                'width': 1.5,
            }}
        }},
        // ── AGGREGATES ──────────────────────────────────────────────────
        {{
            selector: 'edge[label="AGGREGATES"]',
            style: {{
                'line-style': 'solid',
                'line-color': '{ec["AGGREGATES"]}',
                'target-arrow-color': '{ec["AGGREGATES"]}',
                'target-arrow-shape': 'diamond',
                'width': 2,
            }}
        }},
        // ── Cross-layer edges ──────────────────────────────────────────
        {{
            selector: 'edge[is_cross_layer="true"]',
            style: {{
                'line-style': 'dashed',
                'line-color': '{ec["CROSS_LAYER"]}',
                'target-arrow-color': '{ec["CROSS_LAYER"]}',
                'width': 1,
            }}
        }},
        // ── Selected node ───────────────────────────────────────────────
        {{
            selector: ':selected',
            style: {{
                'border-width': 4,
                'border-color': '{sc["selected"]}',
                'overlay-padding': 5,
                'overlay-color': '{sc["selected"]}',
                'overlay-opacity': 0.35,
            }}
        }},
    ]"""


def add_cytoscape_cdn():
    """Add Cytoscape and fcose layout CDN scripts to the page head."""
    ui.add_head_html(CYTOSCAPE_CDN)


def apply_theme():
    """Apply consistent dark theme."""
    ui.colors(**COLORS)
    ui.dark_mode(True)
