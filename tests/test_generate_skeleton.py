"""Tests for the skeleton generator — python templates and generate_skeleton."""

import tempfile
from pathlib import Path

from backend.ticketing_agent.skeleton_templates.python import (
    generate_class_skeleton,
    generate_method_skeleton,
    generate_module_skeleton,
    generate_skeleton_from_design,
    SkeletonResult,
)
from backend.ticketing_agent.generate_skeleton import generate_skeleton


class TestMethodSkeleton:
    def test_simple_method(self):
        src = generate_method_skeleton({
            "name": "add",
            "parameters": ["a", "b"],
            "return_type": "float",
            "visibility": "public",
        })
        assert "def add(self, a, b) -> float:" in src
        assert "pass" in src

    def test_method_with_description(self):
        src = generate_method_skeleton({
            "name": "divide",
            "parameters": ["a", "b"],
            "return_type": "float",
            "description": "Divide a by b",
        })
        assert '"""Divide a by b"""' in src

    def test_void_return(self):
        src = generate_method_skeleton({
            "name": "reset",
            "parameters": [],
            "return_type": "void",
        })
        assert "def reset(self) -> None:" in src


class TestClassSkeleton:
    def test_class_with_methods(self):
        src = generate_class_skeleton({
            "name": "Calculator",
            "description": "A simple calculator",
            "methods": [
                {"name": "add", "parameters": ["a", "b"], "return_type": "float"},
            ],
        })
        assert "class Calculator:" in src
        assert '"""A simple calculator"""' in src
        assert "def add(self, a, b) -> float:" in src

    def test_class_with_inheritance(self):
        src = generate_class_skeleton({
            "name": "ScientificCalc",
            "inherits_from": ["Calculator"],
            "methods": [],
        })
        assert "class ScientificCalc(Calculator):" in src

    def test_class_with_interface_realization(self):
        src = generate_class_skeleton({
            "name": "MyCalc",
            "realizes_interfaces": ["ICalculator"],
            "methods": [],
        })
        assert "class MyCalc(ICalculator):" in src

    def test_class_with_attributes(self):
        src = generate_class_skeleton({
            "name": "Calculator",
            "attributes": [
                {"name": "display", "type_name": "str", "visibility": "private"},
            ],
            "methods": [
                {"name": "compute", "parameters": [], "return_type": "float"},
            ],
        })
        assert "def __init__(self, display: str):" in src
        assert "self._display = display" in src

    def test_empty_class_has_pass(self):
        src = generate_class_skeleton({
            "name": "Empty",
        })
        assert "class Empty:" in src
        assert "pass" in src


class TestModuleSkeleton:
    def test_module_with_classes(self):
        result = generate_module_skeleton(
            classes=[
                {"name": "Foo", "methods": []},
                {"name": "Bar", "methods": [
                    {"name": "do_something", "parameters": [], "return_type": "void"},
                ]},
            ],
            module_name="example",
        )
        assert "class Foo:" in result.content
        assert "class Bar:" in result.content
        assert '"""example module."""' in result.content
        assert result.file_path == "src/example.py"
        assert result.classes_generated == ["Foo", "Bar"]


class TestBatchSkeleton:
    def test_groups_by_module(self):
        design = {
            "classes": [
                {"name": "A", "module": "calc", "methods": []},
                {"name": "B", "module": "calc", "methods": []},
                {"name": "C", "module": "gui", "methods": []},
            ],
        }
        results = generate_skeleton_from_design(design)
        assert len(results) == 2
        modules = {r.file_path for r in results}
        assert "src/calc.py" in modules
        assert "src/gui.py" in modules

    def test_colon_namespace(self):
        design = {
            "classes": [
                {"name": "Engine", "module": "calc::engine", "methods": []},
            ],
        }
        results = generate_skeleton_from_design(design)
        assert len(results) == 1
        assert "src/calc/engine.py" in results[0].file_path


class TestGenerateSkeleton:
    def test_writes_to_disk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            design = {
                "classes": [
                    {
                        "name": "Calculator",
                        "module": "calc",
                        "methods": [
                            {
                                "name": "add",
                                "parameters": ["a", "b"],
                                "return_type": "float",
                            },
                        ],
                    },
                ],
            }
            results = generate_skeleton(design, workspace_dir=tmpdir)
            assert len(results) == 1

            src_file = Path(tmpdir) / results[0].file_path
            assert src_file.exists()
            content = src_file.read_text()
            assert "class Calculator:" in content
            assert "def add(self, a, b) -> float:" in content


class TestPythonTypeMapping:
    def test_common_types(self):
        from backend.ticketing_agent.skeleton_templates.python import _python_type
        assert _python_type("int") == "int"
        assert _python_type("float") == "float"
        assert _python_type("str") == "str"
        assert _python_type("bool") == "bool"
        assert _python_type("void") == "None"
        assert _python_type("string") == "str"
        assert _python_type("any") == "Any"
        assert _python_type("CustomType") == "CustomType"
        assert _python_type("") == "Any"
