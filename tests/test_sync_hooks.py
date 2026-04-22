"""Tests for backend.pipeline.sync_hooks — design-code comparison and test coverage."""

import tempfile
from pathlib import Path

from backend.pipeline.sync_hooks import (
    check_design_against_code,
    check_test_coverage,
)


class TestDesignCodeSync:
    def test_matching_design_and_code(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "src/calc.py"
            src.parent.mkdir(parents=True, exist_ok=True)
            src.write_text(
                "class Calculator:\n"
                "    def add(self, a, b) -> float:\n"
                "        pass\n"
            )
            design = {
                "classes": [
                    {
                        "name": "Calculator",
                        "methods": [
                            {"name": "add", "parameters": ["a", "b"], "return_type": "float"},
                        ],
                    },
                ],
            }
            report = check_design_against_code(design, [str(src)])
            assert report.clean
            assert report.missing_classes == []
            assert report.missing_methods == {}

    def test_missing_class(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "src/calc.py"
            src.parent.mkdir(parents=True, exist_ok=True)
            src.write_text("class Engine:\n    pass\n")
            design = {
                "classes": [{"name": "Calculator", "methods": []}],
            }
            report = check_design_against_code(design, [str(src)])
            assert not report.clean
            assert "Calculator" in report.missing_classes

    def test_missing_method(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "src/calc.py"
            src.parent.mkdir(parents=True, exist_ok=True)
            src.write_text("class Calculator:\n    pass\n")
            design = {
                "classes": [{
                    "name": "Calculator",
                    "methods": [{"name": "add", "parameters": [], "return_type": ""}],
                }],
            }
            report = check_design_against_code(design, [str(src)])
            assert not report.clean
            assert "Calculator" in report.missing_methods
            assert "add" in report.missing_methods["Calculator"]

    def test_file_not_found_graceful(self):
        design = {"classes": [{"name": "Foo", "methods": []}]}
        report = check_design_against_code(design, ["/nonexistent/file.py"])
        # Should not crash, just report the class as missing
        assert "Foo" in report.missing_classes


class TestTestCoverage:
    def test_all_tested(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tf = Path(tmpdir) / "tests/test_calc.py"
            tf.parent.mkdir(parents=True, exist_ok=True)
            tf.write_text(
                "def test_add():\n    pass\n\n"
                "def test_subtract():\n    pass\n"
            )
            report = check_test_coverage(
                ["test_add", "test_subtract"],
                [str(tf)],
            )
            assert report.clean

    def test_untested_verification(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tf = Path(tmpdir) / "tests/test_calc.py"
            tf.parent.mkdir(parents=True, exist_ok=True)
            tf.write_text("def test_add():\n    pass\n")
            report = check_test_coverage(
                ["test_add", "test_divide_by_zero"],
                [str(tf)],
            )
            assert not report.clean
            assert "test_divide_by_zero" in report.untested_verifications

    def test_empty_test_names(self):
        report = check_test_coverage([], [])
        assert report.clean
