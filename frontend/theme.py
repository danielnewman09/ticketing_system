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
    "base": "#1a1a2e",      # deepest background (graph canvas, drawer)
    "panel": "#0f172a",     # agent console, fixed panels
    "surface": "#1e293b",   # raised cards/alerts
    "border": "#334155",    # subtle borders
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
    "attribute": "#8b6914",
    "module": "#1abc9c",
    "function": "#27ae60",
    "constant": "#7f8c8d",
    "enum_value": "#c0392b",
    "primitive": "#95a5a6",
    "type_alias": "#e67e22",
    "variable": "#8b6914",
}

EDGE_COLORS = {
    "INHERITS_FROM": "#9b59b6",
    "IMPLEMENTED_BY": "#3b82f6",
    "TRACES_TO": "#e67e22",
    "default": "#555",
}

STATUS_COLORS = {
    "accepted": "#10b981",
    "rejected_stdlib": "#60a5fa",
    "rejected": "#6b7280",
    "selected": "#f1c40f",
    "requirement": "#e67e22",
    "requirement_border": "#d35400",
    "namespace": "#1abc9c",
}

LAYER_STYLES = {
    "design": {"border_style": "dashed", "opacity": 1.0},
    "as-built": {"border_style": "solid", "opacity": 0.7},
    "requirement": {"border_style": "solid", "opacity": 1.0, "shape": "diamond"},
}

BADGE_COLORS = {
    "hlr": "blue",
    "component": "grey",
    "llr": "positive",
    "llr_empty": "grey",
    "muted": "grey",
    "folder": "amber",
}

TEXT_HEX = {
    "muted": "#888",
    "dim": "#999",
    "light": "#ccc",
}

# ---------------------------------------------------------------------------
# Reusable Tailwind class strings
# ---------------------------------------------------------------------------

# --- Typography (no color — apply color separately via CLS_TEXT_*) ---

CLS_TEXT_XS = "text-xs"
CLS_TEXT_SM = "text-sm"
CLS_TEXT_LG = "text-lg font-bold"
CLS_MONO_XS = "text-xs font-mono"
CLS_MONO_SM = "text-sm font-mono"

# --- Semantic text colors (combine with typography above) ---

CLS_TEXT_MUTED = "text-gray-500"
CLS_TEXT_DIM = "text-gray-400"
CLS_TEXT_SECONDARY = "text-gray-300"
CLS_TEXT_BLUE = "text-blue-300"
CLS_TEXT_GREEN = "text-green-300"
CLS_TEXT_CYAN = "text-cyan-300"
CLS_TEXT_RED = "text-red-300"
CLS_TEXT_AMBER = "text-amber-400"

# --- Composite typography+color (high-frequency combinations) ---

CLS_SECTION_HEADER = "text-xs uppercase tracking-wider text-gray-400 mb-2"
CLS_SECTION_SUBHEADER = "text-xs text-gray-500 uppercase tracking-wider mb-1"
CLS_PAGE_TITLE = "text-2xl font-bold"
CLS_BREADCRUMB_LINK = "text-blue-400 text-sm no-underline"
CLS_BREADCRUMB_SEP = "text-gray-500 text-sm"
CLS_BREADCRUMB_CURRENT = "text-sm text-gray-300"

# --- Empty / placeholder state ---

CLS_EMPTY_STATE = "text-sm text-gray-500"

# --- Layout rows ---

CLS_ROW_CENTER = "items-center gap-2"
CLS_ROW_CENTER_COMPACT = "items-center gap-1"
CLS_ROW_SPACE_BETWEEN = "w-full items-start justify-between"
CLS_ROW_JUSTIFY_BETWEEN = "w-full justify-between mt-4"
CLS_ROW_JUSTIFY_END = "w-full justify-end gap-2 mt-4"

# --- Cards ---

CLS_CARD_FULL = "w-full"
CLS_CARD_FULL_MARGIN = "w-full mb-2"
CLS_CARD_SECTION = "w-full mx-2 mt-4"

# --- Dialogs ---

CLS_DIALOG_SM = "w-80"
CLS_DIALOG_MD = "w-96"
CLS_DIALOG_LG = "w-[480px]"
CLS_DIALOG_WIDE = "w-[540px] max-h-[80vh]"
CLS_DIALOG_TITLE = "text-lg font-bold mb-2"
CLS_DIALOG_ACTIONS = "w-full justify-end gap-2 mt-4"

# --- Breadcrumb ---

CLS_BREADCRUMB_ROW = "items-center gap-1 px-2 mt-4"

# --- Quasar props shortcuts ---

PROPS_ICON_BTN = "flat round size=sm"
PROPS_ICON_BTN_POSITIVE = "flat round size=sm color=positive"
PROPS_DENSE = "dense"
PROPS_TABLE_COMPACT = "dense flat"

# ---------------------------------------------------------------------------
# Cytoscape helpers
# ---------------------------------------------------------------------------

CYTOSCAPE_CDN = (
    '<script src="https://unpkg.com/cytoscape@3.30.4/dist/cytoscape.min.js"></script>'
    '<script src="https://unpkg.com/layout-base@2.0.1/layout-base.js"></script>'
    '<script src="https://unpkg.com/cose-base@2.2.0/cose-base.js"></script>'
    '<script src="https://unpkg.com/cytoscape-fcose@2.2.0/cytoscape-fcose.js"></script>'
)

KIND_COLORS_JS = json.dumps(KIND_COLORS)


def cytoscape_base_styles(*, size: str = "small") -> str:
    """Return a JS array literal of common Cytoscape node/edge styles.

    *size* controls node dimensions:
      - ``"small"`` → 30px nodes, 9px text  (detail pages)
      - ``"large"`` → 40px nodes, 10px text (full graph page)
    """
    if size == "large":
        node_w, node_h, font, txt_max, txt_margin, pad_members = 40, 40, 10, 80, 4, 12
        req_w, req_h = 35, 35
        edge_font = 8
        ns_font, ns_pad = 11, 20
    else:
        node_w, node_h, font, txt_max, txt_margin, pad_members = 30, 30, 9, 70, 3, 10
        req_w, req_h = 30, 30
        edge_font = 7
        ns_font, ns_pad = 10, 16

    bg = BACKGROUNDS
    ec = EDGE_COLORS
    sc = STATUS_COLORS

    return f"""[
        {{
            selector: 'node[layer="design"]',
            style: {{
                'label': 'data(label)',
                'background-color': '#666',
                'color': '#fff',
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
        {{
            selector: 'node[layer="dependency"]',
            style: {{
                'label': 'data(label)',
                'background-color': '#555',
                'color': '#ccc',
                'text-valign': 'bottom',
                'text-halign': 'center',
                'font-size': '{font}px',
                'width': {node_w},
                'height': {node_h},
                'border-width': 2,
                'border-style': 'dashed',
                'border-color': '#009688',
                'text-wrap': 'ellipsis',
                'text-max-width': '{txt_max}px',
                'text-margin-y': {txt_margin},
            }}
        }},
        {{
            selector: 'node[has_members="true"]',
            style: {{
                'shape': 'roundrectangle',
                'text-valign': 'center',
                'text-halign': 'center',
                'text-wrap': 'wrap',
                'text-max-width': '200px',
                'font-size': '{font - 1}px',
                'font-family': 'monospace',
                'text-justification': 'left',
                'width': 'label',
                'height': 'label',
                'padding': '{pad_members}px',
                'border-style': 'solid',
                'border-width': 2,
                'text-margin-y': 0,
            }}
        }},
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
        ...Object.entries(KIND_COLORS).flatMap(([kind, color]) => [
            {{
                selector: 'node[kind="' + kind + '"][layer="design"]',
                style: {{ 'background-color': color }}
            }},
            {{
                selector: 'node[kind="' + kind + '"][layer="as-built"]',
                style: {{ 'background-color': color }}
            }},
            {{
                selector: 'node[kind="' + kind + '"][layer="dependency"]',
                style: {{ 'background-color': color }}
            }},
        ]),
        {{
            selector: 'node[layer="as-built"]',
            style: {{
                'label': 'data(label)',
                'background-color': '#555',
                'color': '#ccc',
                'text-valign': 'bottom',
                'text-halign': 'center',
                'font-size': '{font}px',
                'width': {node_w - 2},
                'height': {node_h - 2},
                'border-width': 2,
                'border-style': 'solid',
                'border-color': '#888',
                'text-wrap': 'ellipsis',
                'text-max-width': '{txt_max}px',
                'text-margin-y': {txt_margin},
            }}
        }},
        {{
            selector: 'node[layer="requirement"]',
            style: {{
                'label': 'data(label)',
                'background-color': '{sc["requirement"]}',
                'color': '#fff',
                'text-valign': 'bottom',
                'text-halign': 'center',
                'font-size': '{font}px',
                'shape': 'diamond',
                'width': {req_w},
                'height': {req_h},
                'border-width': 2,
                'border-color': '{sc["requirement_border"]}',
                'text-wrap': 'ellipsis',
                'text-max-width': '{txt_max}px',
                'text-margin-y': {txt_margin},
            }}
        }},
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
                'color': '#999',
                'text-rotation': 'autorotate',
            }}
        }},
        {{
            selector: 'edge[label="INHERITS_FROM"]',
            style: {{
                'line-style': 'solid',
                'line-color': '{ec["INHERITS_FROM"]}',
                'target-arrow-color': '{ec["INHERITS_FROM"]}',
                'target-arrow-shape': 'triangle-tee',
            }}
        }},
        {{
            selector: 'edge[label="IMPLEMENTED_BY"]',
            style: {{
                'line-style': 'dotted',
                'line-color': '{ec["IMPLEMENTED_BY"]}',
                'target-arrow-color': '{ec["IMPLEMENTED_BY"]}',
            }}
        }},
        {{
            selector: 'edge[label="TRACES_TO"]',
            style: {{
                'line-style': 'dashed',
                'line-color': '{ec["TRACES_TO"]}',
                'target-arrow-color': '{ec["TRACES_TO"]}',
            }}
        }},
        {{
            selector: ':selected',
            style: {{
                'border-width': 4,
                'border-color': '{sc["selected"]}',
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
