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

    def test_dependency_box_still_has_border(self):
        """Dependency UML boxes still get an inner border from kind lookup."""
        html = _build_uml_html(
            "Fl_Button", {}, is_dependency=True,
            owner_kind="class", change_status=""
        )
        assert "box-shadow:inset 0 0 0 2.5px" in html