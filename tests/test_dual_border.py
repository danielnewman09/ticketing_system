"""Tests for dual-border UML label rendering.

Both borders are CSS-based:
- Outer border: border:Xpx dashed <status_color> (lifecycle)
- Inner border: outline:Xpx solid <kind_color> with outline-offset:-Xpx (entity kind)
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
    """STATUS_BORDER_COLORS maps change_status to outer border colors."""

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


class TestBuildUmlHtmlDualBorder:
    """_build_uml_html wraps content in a div with both CSS borders:
    outer dashed (status) and inner solid outline (kind)."""

    def test_class_inner_border(self):
        html = _build_uml_html(
            "Calculator", {}, is_dependency=False,
            owner_kind="class", change_status="new"
        )
        assert "outline:2.5px solid #4a90d9" in html
        assert "outline-offset:-2.5px" in html

    def test_class_outer_border_status_new(self):
        html = _build_uml_html(
            "Calculator", {}, is_dependency=False,
            owner_kind="class", change_status="new"
        )
        assert "border:3.5px dashed #10b981" in html

    def test_class_outer_border_default_status(self):
        html = _build_uml_html(
            "Calculator", {}, is_dependency=False,
            owner_kind="class", change_status=""
        )
        assert "border:3.5px dashed #4a5568" in html

    def test_interface_inner_border(self):
        html = _build_uml_html(
            "IHandler", {}, is_dependency=False,
            owner_kind="interface", change_status=""
        )
        assert "outline:2.5px solid #9b59b6" in html
        assert "outline-offset:-2.5px" in html

    def test_enum_inner_border(self):
        html = _build_uml_html(
            "Color", {}, is_dependency=False,
            owner_kind="enum", change_status="modified"
        )
        assert "outline:2.5px solid #e74c3c" in html
        assert "border:3.5px dashed #f59e0b" in html

    def test_unknown_kind_transparent_border(self):
        html = _build_uml_html(
            "mymodule", {}, is_dependency=False,
            owner_kind="module", change_status="new"
        )
        assert "outline:2.5px solid transparent" in html
        assert "border:3.5px dashed #10b981" in html

    def test_empty_kind_transparent_border(self):
        html = _build_uml_html(
            "Thing", {}, is_dependency=False,
            owner_kind="", change_status=""
        )
        assert "outline:2.5px solid transparent" in html
        assert "border:3.5px dashed #4a5568" in html

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

    def test_dependency_box_still_has_borders(self):
        """Dependency UML boxes still get both inner and outer borders."""
        html = _build_uml_html(
            "Fl_Button", {}, is_dependency=True,
            owner_kind="class", change_status=""
        )
        assert "outline:2.5px solid" in html
        assert "border:3.5px dashed" in html