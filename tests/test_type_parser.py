"""Tests for the type signature parser (TypeRef extraction)."""

import pytest
from backend.codebase.type_parser import parse_type_refs, TypeRef


class TestParseSimpleTypes:
    def test_simple_class_name(self):
        refs = parse_type_refs("Calculator")
        assert len(refs) == 1
        assert refs[0].name == "Calculator"
        assert refs[0].template_args == []
        assert refs[0].is_builtin is False

    def test_qualified_name(self):
        refs = parse_type_refs("std::vector")
        assert len(refs) == 1
        assert refs[0].name == "std::vector"
        assert refs[0].template_args == []
        assert refs[0].is_builtin is False

    def test_builtin_int(self):
        refs = parse_type_refs("int")
        assert len(refs) == 1
        assert refs[0].name == "int"
        assert refs[0].is_builtin is True

    def test_builtin_double(self):
        refs = parse_type_refs("double")
        assert len(refs) == 1
        assert refs[0].name == "double"
        assert refs[0].is_builtin is True

    def test_builtin_void(self):
        refs = parse_type_refs("void")
        assert len(refs) == 0  # void is not a dependency

    def test_builtin_std_string(self):
        refs = parse_type_refs("std::string")
        assert len(refs) == 1
        assert refs[0].name == "std::string"
        assert refs[0].is_builtin is False  # not a primitive; it's a dependency


class TestParseTemplateTypes:
    def test_single_template_arg(self):
        refs = parse_type_refs("std::vector<std::string>")
        assert len(refs) == 2
        assert refs[0].name == "std::vector"
        assert len(refs[0].template_args) == 1
        assert refs[0].template_args[0].name == "std::string"
        assert refs[1].name == "std::string"

    def test_two_template_args(self):
        refs = parse_type_refs("std::map<std::string, double>")
        assert len(refs) == 3
        assert refs[0].name == "std::map"
        assert len(refs[0].template_args) == 2
        assert refs[0].template_args[0].name == "std::string"
        assert refs[0].template_args[1].name == "double"
        assert refs[0].template_args[1].is_builtin is True
        # The flattened list also has the inner refs
        assert refs[1].name == "std::string"
        assert refs[2].name == "double"

    def test_nested_template(self):
        refs = parse_type_refs("std::vector<std::map<std::string, double>>")
        assert len(refs) == 4
        assert refs[0].name == "std::vector"
        assert refs[0].template_args[0].name == "std::map"
        assert refs[0].template_args[0].template_args[0].name == "std::string"


class TestParseQualifiedTypes:
    def test_method_signature(self):
        refs = parse_type_refs("const std::string& operand1, const std::string& operand2")
        string_refs = [r for r in refs if r.name == "std::string"]
        assert len(string_refs) == 2

    def test_return_type_with_template(self):
        refs = parse_type_refs("std::vector<std::string>")
        assert refs[0].name == "std::vector"
        assert refs[0].template_args[0].name == "std::string"

    def test_pointer_type(self):
        refs = parse_type_refs("Fl_Output*")
        assert len(refs) == 1
        assert refs[0].name == "Fl_Output"

    def test_const_ref(self):
        refs = parse_type_refs("const CalculationResult&")
        assert len(refs) == 1
        assert refs[0].name == "CalculationResult"

    def test_ignores_void(self):
        refs = parse_type_refs("void")
        assert len(refs) == 0


class TestParseMethodArgsString:
    def test_argsstring_multiple_params(self):
        refs = parse_type_refs("(const std::string& operand1, const std::string& operand2)")
        string_refs = [r for r in refs if r.name == "std::string"]
        assert len(string_refs) == 2

    def test_no_params(self):
        refs = parse_type_refs("()")
        assert len(refs) == 0