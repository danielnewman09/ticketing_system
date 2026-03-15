"""Theme constants and application."""

from nicegui import ui

COLORS = {
    "primary": "#1a1a2e",
    "secondary": "#16213e",
    "accent": "#0f3460",
    "positive": "#10b981",
    "negative": "#ef4444",
    "warning": "#f59e0b",
    "info": "#3b82f6",
}

VERIFICATION_COLORS = {
    "automated": "positive",
    "review": "warning",
    "inspection": "info",
}

KIND_COLORS = {
    "class": "#4a90d9",
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
}


def apply_theme():
    """Apply consistent dark theme."""
    ui.colors(**COLORS)
    ui.dark_mode(True)
