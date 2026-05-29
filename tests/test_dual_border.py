"""Tests for dual-border UML label rendering.

The outer border is rendered by Cytoscape (dashed, status-colored).
The inner border is rendered via CSS outline on the HTML wrapper (solid, kind-colored).
"""

import pytest
from backend.graph.transforms import (
    KIND_BORDER_COLORS,
    STATUS_BORDER_COLORS,
    _build_uml_html,
)


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


class TestStatusBorderColors:
    """STATUS_BORDER_COLORS maps change_status to outer border colors.

    These are used by Cytoscape selectors, not in the HTML wrapper directly.
    """

    def test_new_color(self):
        assert STATUS_BORDER_COLORS["new"] == "#10b981"

    def test_implemented_color(self):
        assert STATUS_BORDER_COLORS["implemented"] == "#3b82f6"

    def test_modified_color(self):
        assert STATUS_BORDER_COLORS["modified"] == "#f59e0b"

    def test_deleted_color(self):
        assert STATUS_BORDER_COLORS["deleted"] == "#ef4444"

    def test_default_color(self):
        assert STATUS_BORDER_COLORS[""] == "#4a5568"


class TestBuildUmlHtmlInnerBorder:
    """_build_uml_html wraps content with a CSS outline for the inner kind border.
    The outer dashed border is handled by Cytoscape node styling."""

    def test_class_inner_border(self):
        html = _build_uml_html(
            "Calculator", {}, is_dependency=False,
            owner_kind="class", change_status="new"
        )
        assert "outline:3px solid #4a90d9" in html
        assert "outline-offset:-2px" in html

    def test_interface_inner_border(self):
        html = _build_uml_html(
            "IHandler", {}, is_dependency=False,
            owner_kind="interface", change_status=""
        )
        assert "outline:3px solid #9b59b6" in html
        assert "outline-offset:-2px" in html

    def test_enum_inner_border(self):
        html = _build_uml_html(
            "Color", {}, is_dependency=False,
            owner_kind="enum", change_status="modified"
        )
        assert "outline:3px solid #e74c3c" in html

    def test_unknown_kind_transparent_border(self):
        html = _build_uml_html(
            "mymodule", {}, is_dependency=False,
            owner_kind="module", change_status="new"
        )
        assert "outline:3px solid transparent" in html

    def test_empty_kind_transparent_border(self):
        html = _build_uml_html(
            "Thing", {}, is_dependency=False,
            owner_kind="", change_status=""
        )
        assert "outline:3px solid transparent" in html

    def test_wrapper_has_border_radius(self):
        html = _build_uml_html(
            "Calculator", {}, is_dependency=False,
            owner_kind="class", change_status="new"
        )
        assert "border-radius:5px" in html

    def test_wrapper_has_padding(self):
        html = _build_uml_html(
            "Calculator", {}, is_dependency=False,
            owner_kind="class", change_status="new"
        )
        assert "padding:2px" in html

    def test_no_css_dashed_border(self):
        """Outer dashed border is handled by Cytoscape, not CSS."""
        html = _build_uml_html(
            "Calculator", {}, is_dependency=False,
            owner_kind="class", change_status="new"
        )
        assert "border:4px dashed" not in html
        assert "border-style" not in html

    def test_class_name_colored_by_status(self):
        """Class name text color still uses change_status, not kind color."""
        html = _build_uml_html(
            "Calculator", {}, is_dependency=False,
            owner_kind="class", change_status="modified"
        )
        assert "#fcd34d" in html

    def test_dependency_box_still_has_inner_border(self):
        """Dependency UML boxes still get the inner outline border."""
        html = _build_uml_html(
            "Fl_Button", {}, is_dependency=True,
            owner_kind="class", change_status=""
        )
        assert "outline:3px solid" in html