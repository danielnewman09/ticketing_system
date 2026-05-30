"""Tests for the C++ skeleton generator — cpp templates and generate_skeleton."""

import tempfile
from pathlib import Path

from backend.ticketing_agent.skeleton_templates.cpp import (
    SkeletonResult,
    _cpp_type,
    _default_return_value,
    _format_param,
    _header_guard,
    _includes_for_type,
    _method_declaration,
    _method_definition,
    generate_class_skeleton,
    generate_enum_skeleton,
    generate_interface_skeleton,
    generate_module_skeleton,
    generate_skeleton_from_design,
    gather_includes_from_design,
)
from backend.ticketing_agent.generate_skeleton import generate_skeleton


# ---------------------------------------------------------------------------
# C++ type mapping
# ---------------------------------------------------------------------------


class TestCppTypeMapping:
    def test_builtin_types(self):
        assert _cpp_type("int") == "int"
        assert _cpp_type("float") == "float"
        assert _cpp_type("double") == "double"
        assert _cpp_type("bool") == "bool"
        assert _cpp_type("void") == "void"
        assert _cpp_type("char") == "char"

    def test_std_types(self):
        assert _cpp_type("string") == "std::string"
        assert _cpp_type("vector") == "std::vector"
        assert _cpp_type("unique_ptr") == "std::unique_ptr"
        assert _cpp_type("shared_ptr") == "std::shared_ptr"
        assert _cpp_type("optional") == "std::optional"
        assert _cpp_type("size_t") == "std::size_t"

    def test_qualified_passed_through(self):
        assert _cpp_type("std::vector<int>") == "std::vector<int>"
        assert _cpp_type("Fl_Window") == "Fl_Window"

    def test_project_types_passed_through(self):
        assert _cpp_type("Calculator") == "Calculator"
        assert _cpp_type("Engine") == "Engine"

    def test_empty_returns_void(self):
        assert _cpp_type("") == "void"

    def test_unknown_passed_through(self):
        assert _cpp_type("MyType") == "MyType"


class TestDefaultReturnValue:
    def test_void(self):
        assert _default_return_value("void") == ""

    def test_bool(self):
        assert _default_return_value("bool") == "false"

    def test_int(self):
        assert _default_return_value("int") == "0"

    def test_float(self):
        assert _default_return_value("float") == "0.0"

    def test_string(self):
        assert _default_return_value("std::string") == '""'

    def test_unique_ptr(self):
        assert _default_return_value("std::unique_ptr") == "{nullptr}"

    def test_vector(self):
        assert _default_return_value("std::vector") == "{}"

    def test_custom_type(self):
        assert _default_return_value("Calculator") == "{}"


class TestHeaderGuard:
    def test_simple_path(self):
        guard = _header_guard("src/calculator.hpp")
        assert guard == "SRC_CALCULATOR_HPP"

    def test_nested_path(self):
        guard = _header_guard("src/calc/engine.hpp")
        assert guard == "SRC_CALC_ENGINE_HPP"


class TestFormatParam:
    def test_simple_type(self):
        result = _format_param({"name": "x", "type_name": "int"})
        assert result == "int x"

    def test_string_ref(self):
        result = _format_param({"name": "name", "type_name": "std::string"})
        assert result == "const std::string& name"

    def test_vector_ref(self):
        result = _format_param({"name": "items", "type_name": "std::vector"})
        assert result == "const std::vector& items"

    def test_custom_type_ref(self):
        result = _format_param({"name": "other", "type_name": "Calculator"})
        assert result == "const Calculator& other"

    def test_legacy_string_param(self):
        result = _format_param("x")
        assert result == "x"


class TestIncludesForType:
    def test_std_string(self):
        assert _includes_for_type("std::string") == "<string>"

    def test_std_vector(self):
        assert _includes_for_type("std::vector") == "<vector>"

    def test_std_unique_ptr(self):
        assert _includes_for_type("std::unique_ptr") == "<memory>"

    def test_custom_type_no_include(self):
        assert _includes_for_type("Calculator") is None

    def test_empty(self):
        assert _includes_for_type("") is None


# ---------------------------------------------------------------------------
# Enum skeleton
# ---------------------------------------------------------------------------


class TestEnumSkeleton:
    def test_enum_with_values(self):
        src = generate_enum_skeleton({
            "name": "Operator",
            "values": ["Add", "Subtract", "Multiply", "Divide"],
            "description": "Arithmetic operators",
        })
        assert "enum class Operator {" in src
        assert "Add," in src
        assert "Divide" in src
        assert '/// Arithmetic operators' in src

    def test_enum_no_values(self):
        src = generate_enum_skeleton({
            "name": "Status",
            "values": [],
            "description": "",
        })
        assert "enum class Status {" in src
        assert "TODO: Add enum values" in src

    def test_enum_no_trailing_comma(self):
        src = generate_enum_skeleton({
            "name": "Color",
            "values": ["Red", "Green", "Blue"],
        })
        # Last value should not have a comma
        lines = src.strip().split("\n")
        last_value_line = [l for l in lines if "Blue" in l][0]
        assert last_value_line.strip() == "Blue"


# ---------------------------------------------------------------------------
# Interface skeleton
# ---------------------------------------------------------------------------


class TestInterfaceSkeleton:
    def test_interface_with_methods(self):
        src = generate_interface_skeleton({
            "name": "ICalculator",
            "methods": [
                {"name": "add", "parameters": [], "return_type": "float", "visibility": "public"},
                {"name": "clear", "parameters": [], "return_type": "void", "visibility": "public"},
            ],
            "description": "Calculator interface",
        })
        assert "class ICalculator {" in src
        assert "virtual ~ICalculator() = default;" in src
        assert "virtual float add() = 0;" in src
        assert "virtual void clear() = 0;" in src
        assert '/// Calculator interface' in src

    def test_interface_no_methods(self):
        src = generate_interface_skeleton({
            "name": "IHandler",
            "methods": [],
        })
        assert "TODO: Add pure virtual methods" in src


# ---------------------------------------------------------------------------
# Method declaration and definition
# ---------------------------------------------------------------------------


class TestMethodDeclaration:
    def test_simple_method(self):
        decl = _method_declaration({
            "name": "add",
            "parameters": [{"name": "a", "type_name": "float"}, {"name": "b", "type_name": "float"}],
            "return_type": "float",
            "visibility": "public",
        })
        assert "float add(float a, float b);" in decl

    def test_pure_virtual(self):
        decl = _method_declaration({
            "name": "compute",
            "parameters": [],
            "return_type": "void",
            "visibility": "public",
        }, is_pure_virtual=True)
        assert "virtual void compute() = 0;" in decl

    def test_const_method(self):
        decl = _method_declaration({
            "name": "get_value",
            "parameters": [],
            "return_type": "int",
            "visibility": "public",
            "is_const": True,
        })
        assert "int get_value() const;" in decl

    def test_void_return(self):
        decl = _method_declaration({
            "name": "reset",
            "parameters": [],
            "return_type": "void",
        })
        assert "void reset();" in decl


class TestMethodDefinition:
    def test_simple_definition(self):
        defn = _method_definition("Calculator", {
            "name": "add",
            "parameters": [{"name": "a", "type_name": "float"}, {"name": "b", "type_name": "float"}],
            "return_type": "float",
        })
        assert "float Calculator::add(float a, float b) {" in defn
        assert "return 0.0" in defn
        assert "TODO: Implement add" in defn

    def test_void_definition(self):
        defn = _method_definition("Engine", {
            "name": "start",
            "parameters": [],
            "return_type": "void",
        })
        assert "void Engine::start() {" in defn
        assert "TODO: Implement start" in defn
        # No return statement for void
        assert "return" not in defn.split("{")[1].split("}")[0] or "return" not in defn

    def test_definition_with_namespace(self):
        defn = _method_definition("Engine", {
            "name": "stop",
            "parameters": [],
            "return_type": "void",
        }, namespace="calculation_engine")
        assert "calculation_engine::Engine::stop()" in defn


# ---------------------------------------------------------------------------
# Class skeleton
# ---------------------------------------------------------------------------


class TestClassSkeleton:
    def test_class_with_methods(self):
        header, source = generate_class_skeleton({
            "name": "Calculator",
            "description": "A simple calculator",
            "methods": [
                {"name": "add", "parameters": [{"name": "a", "type_name": "float"}, {"name": "b", "type_name": "float"}], "return_type": "float"},
                {"name": "clear", "parameters": [], "return_type": "void"},
            ],
        })
        assert "class Calculator {" in header
        assert "Calculator() = default;" in header
        assert "float add(float a, float b);" in header
        assert "void clear();" in header
        # Source should have method definitions
        assert "Calculator::add" in source
        assert "Calculator::clear" in source

    def test_class_with_inheritance(self):
        header, source = generate_class_skeleton({
            "name": "ScientificCalc",
            "inherits_from": ["Calculator"],
            "methods": [],
        })
        assert "class ScientificCalc : Calculator {" in header

    def test_class_with_interface_realization(self):
        header, source = generate_class_skeleton({
            "name": "MyCalc",
            "realizes_interfaces": ["ICalculator"],
            "methods": [],
        })
        assert "ICalculator" in header

    def test_attribute_only_class_becomes_struct(self):
        header, source = generate_class_skeleton({
            "name": "DisplayState",
            "attributes": [
                {"name": "value", "type_name": "std::string", "visibility": "public"},
                {"name": "dirty", "type_name": "bool", "visibility": "public"},
            ],
            "methods": [],
        })
        assert "struct DisplayState {" in header
        assert "std::string value{};" in header
        assert "bool dirty{};" in header

    def test_class_with_private_attributes(self):
        header, source = generate_class_skeleton({
            "name": "Engine",
            "attributes": [
                {"name": "running", "type_name": "bool", "visibility": "private"},
            ],
            "methods": [
                {"name": "start", "parameters": [], "return_type": "void"},
            ],
        })
        assert "bool running_;" in header  # Private members get underscore suffix
        assert "void start();" in header

    def test_empty_class(self):
        header, source = generate_class_skeleton({
            "name": "Empty",
            "methods": [],
        })
        assert "class Empty {" in header
        # Should still have default constructor/destructor


# ---------------------------------------------------------------------------
# Module skeleton (full .hpp/.cpp pair)
# ---------------------------------------------------------------------------


class TestModuleSkeleton:
    def test_module_with_classes(self):
        results = generate_module_skeleton(
            classes=[
                {"name": "Foo", "methods": [{"name": "do_thing", "parameters": [], "return_type": "void"}]},
                {
                    "name": "Bar",
                    "methods": [
                        {"name": "compute", "parameters": [{"name": "x", "type_name": "int"}], "return_type": "int"},
                    ],
                },
            ],
            interfaces=[],
            enums=[],
            module_name="engine",
            namespace="calc::engine",
        )
        assert len(results) == 2  # .hpp and .cpp
        hpp = [r for r in results if r.file_path.endswith(".hpp")][0]
        cpp = [r for r in results if r.file_path.endswith(".cpp")][0]

        assert "class Foo" in hpp.content
        assert "class Bar" in hpp.content
        assert "namespace calc::engine" in hpp.content
        assert "#ifndef" in hpp.content  # Header guard
        assert '#include "engine.hpp"' in cpp.content

    def test_module_with_interfaces(self):
        results = generate_module_skeleton(
            classes=[],
            interfaces=[{
                "name": "IHandler",
                "methods": [{"name": "handle", "parameters": [], "return_type": "void"}],
            }],
            enums=[],
            module_name="handler",
            namespace="app::handler",
        )
        hpp = [r for r in results if r.file_path.endswith(".hpp")][0]
        assert "class IHandler {" in hpp.content
        assert "virtual void handle() = 0;" in hpp.content

    def test_module_with_enums(self):
        results = generate_module_skeleton(
            classes=[],
            interfaces=[],
            enums=[{
                "name": "Status",
                "values": ["OK", "Error", "Pending"],
            }],
            module_name="types",
            namespace="app::types",
        )
        hpp = [r for r in results if r.file_path.endswith(".hpp")][0]
        assert "enum class Status" in hpp.content

    def test_module_no_methods_no_cpp(self):
        """If a module only has interfaces (pure virtual) and enums, there should be
        no .cpp file since there's nothing to define."""
        results = generate_module_skeleton(
            classes=[],
            interfaces=[{
                "name": "IListener",
                "methods": [{"name": "on_event", "parameters": [], "return_type": "void"}],
            }],
            enums=[{"name": "EventType", "values": ["Click", "Key"]}],
            module_name="events",
            namespace="app::events",
        )
        hpp_files = [r for r in results if r.file_path.endswith(".hpp")]
        cpp_files = [r for r in results if r.file_path.endswith(".cpp")]
        assert len(hpp_files) == 1
        # No method definitions to put in .cpp since interfaces are pure virtual
        assert len(cpp_files) == 0


# ---------------------------------------------------------------------------
# Batch skeleton from design
# ---------------------------------------------------------------------------


class TestBatchFromDesign:
    def test_groups_by_module(self):
        design = {
            "classes": [
                {"name": "A", "module": "calc", "methods": [{"name": "do", "parameters": [], "return_type": "void"}]},
                {"name": "B", "module": "calc", "methods": []},
                {"name": "C", "module": "gui", "methods": [{"name": "draw", "parameters": [], "return_type": "void"}]},
            ],
            "interfaces": [],
            "enums": [],
        }
        results = generate_skeleton_from_design(design)
        # At least one .hpp per module (calc and gui)
        hpp_files = [r for r in results if r.file_path.endswith(".hpp")]
        modules = set()
        for r in hpp_files:
            # File path contains the module name
            modules.add(r.file_path)
        assert len(modules) >= 2

    def test_includes_project_namespace(self):
        design = {
            "classes": [
                {"name": "Engine", "module": "core", "methods": []},
            ],
            "interfaces": [],
            "enums": [],
        }
        results = generate_skeleton_from_design(design, project_name="calculator_engine")
        hpp = [r for r in results if r.file_path.endswith(".hpp")][0]
        assert "namespace calculator_engine::core" in hpp.content

    def test_colon_namespace(self):
        design = {
            "classes": [
                {"name": "Engine", "module": "calc::engine", "methods": []},
            ],
            "interfaces": [],
            "enums": [],
        }
        results = generate_skeleton_from_design(design)
        hpp = [r for r in results if r.file_path.endswith(".hpp")][0]
        assert "namespace" in hpp.content

    def test_includes_std_headers(self):
        design = {
            "classes": [
                {
                    "name": "Calculator",
                    "module": "calc",
                    "methods": [
                        {"name": "get_name", "parameters": [], "return_type": "std::string"},
                    ],
                },
            ],
            "interfaces": [],
            "enums": [],
        }
        results = generate_skeleton_from_design(design)
        hpp = [r for r in results if r.file_path.endswith(".hpp")][0]
        assert "#include <string>" in hpp.content

    def test_full_design_with_interfaces_and_enums(self):
        design = {
            "modules": ["calc"],
            "classes": [
                {
                    "name": "Calculator",
                    "module": "calc",
                    "methods": [
                        {"name": "add", "parameters": [{"name": "a", "type_name": "float"}, {"name": "b", "type_name": "float"}], "return_type": "float"},
                    ],
                },
            ],
            "interfaces": [
                {
                    "name": "ICalculator",
                    "module": "calc",
                    "methods": [
                        {"name": "compute", "parameters": [], "return_type": "void"},
                    ],
                },
            ],
            "enums": [
                {
                    "name": "Operation",
                    "module": "calc",
                    "values": ["Add", "Subtract", "Multiply", "Divide"],
                },
            ],
        }
        results = generate_skeleton_from_design(design)
        hpp = [r for r in results if r.file_path.endswith(".hpp")][0]
        assert "class Calculator" in hpp.content
        assert "class ICalculator" in hpp.content
        assert "enum class Operation" in hpp.content


# ---------------------------------------------------------------------------
# Integration: generate_skeleton with language switch
# ---------------------------------------------------------------------------


class TestGenerateSkeletonCpp:
    def test_writes_hpp_and_cpp_to_disk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            design = {
                "classes": [
                    {
                        "name": "Calculator",
                        "module": "calc",
                        "methods": [
                            {"name": "add", "parameters": [{"name": "a", "type_name": "float"}, {"name": "b", "type_name": "float"}], "return_type": "float"},
                        ],
                    },
                ],
                "interfaces": [],
                "enums": [],
            }
            results = generate_skeleton(design, workspace_dir=tmpdir, language="cpp", project_name="calc")
            assert len(results) >= 2  # .hpp and .cpp

            hpp_files = [r for r in results if r.file_path.endswith(".hpp")]
            cpp_files = [r for r in results if r.file_path.endswith(".cpp")]
            assert len(hpp_files) == 1
            assert len(cpp_files) == 1

            # Check files exist on disk
            hpp_path = Path(tmpdir) / hpp_files[0].file_path
            assert hpp_path.exists()
            content = hpp_path.read_text()
            assert "class Calculator" in content
            assert "namespace" in content

    def test_python_language_still_works(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            design = {
                "classes": [
                    {
                        "name": "Calculator",
                        "module": "calc",
                        "methods": [
                            {"name": "add", "parameters": ["a", "b"], "return_type": "float"},
                        ],
                    },
                ],
            }
            results = generate_skeleton(design, workspace_dir=tmpdir, language="python")
            assert len(results) >= 1
            py_file = Path(tmpdir) / results[0].file_path
            assert py_file.exists()
            content = py_file.read_text()
            assert "class Calculator:" in content

    def test_unsupported_language_raises(self):
        import pytest
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError, match="Unsupported language"):
                generate_skeleton({}, workspace_dir=tmpdir, language="rust")


# ---------------------------------------------------------------------------
# Gather includes
# ---------------------------------------------------------------------------


class TestGatherIncludes:
    def test_gathers_from_attributes(self):
        design = {
            "classes": [
                {
                    "name": "Foo",
                    "attributes": [
                        {"name": "data", "type_name": "std::string", "visibility": "private"},
                    ],
                    "methods": [],
                },
            ],
        }
        includes = gather_includes_from_design(design)
        assert "<string>" in includes

    def test_gathers_from_return_types(self):
        design = {
            "classes": [
                {
                    "name": "Foo",
                    "methods": [
                        {"name": "get_items", "parameters": [], "return_type": "std::vector"},
                    ],
                },
            ],
        }
        includes = gather_includes_from_design(design)
        assert "<vector>" in includes

    def test_skips_custom_types(self):
        design = {
            "classes": [
                {
                    "name": "Foo",
                    "methods": [
                        {"name": "get_calc", "parameters": [], "return_type": "Calculator"},
                    ],
                },
            ],
        }
        includes = gather_includes_from_design(design)
        # No standard library includes for Calculator
        assert "<Calculator>" not in includes