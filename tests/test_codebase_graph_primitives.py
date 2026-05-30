"""Sanity-check the codebase graph primitives (models + constants).

Validates that:
- Node models can be instantiated with valid data.
- The constants (kinds, layers, visibility, predicates, specializations)
  are correctly imported and have expected membership.
"""

import pytest

from codegraph.nodes import CompoundNode, MemberNode


class TestNodeKindImport:
    def test_compound_kinds(self):
        from codegraph.constants import COMPOUND_KINDS
        keys = {k for k, _ in COMPOUND_KINDS}
        assert "class" in keys
        assert "interface" in keys
        assert "enum" in keys
        assert "method" not in keys

    def test_member_kinds(self):
        from codegraph.constants import MEMBER_KINDS
        keys = {k for k, _ in MEMBER_KINDS}
        assert "method" in keys
        assert "variable" in keys
        assert "class" not in keys

    def test_namespace_kinds(self):
        from codegraph.constants import NAMESPACE_KINDS
        keys = {k for k, _ in NAMESPACE_KINDS}
        assert "namespace" in keys
        assert "package" in keys

    def test_node_kinds_is_union(self):
        from codegraph.constants import NODE_KINDS, COMPOUND_KINDS, MEMBER_KINDS, NAMESPACE_KINDS, UNCLASSIFIED_KINDS
        assert set(NODE_KINDS) == set(COMPOUND_KINDS + MEMBER_KINDS + NAMESPACE_KINDS + UNCLASSIFIED_KINDS)

    def test_type_kinds(self):
        from codegraph.constants import TYPE_KINDS
        assert "class" in TYPE_KINDS
        assert "interface" in TYPE_KINDS
        assert "method" not in TYPE_KINDS

    def test_value_kinds(self):
        from codegraph.constants import VALUE_KINDS
        assert "method" in VALUE_KINDS
        assert "variable" in VALUE_KINDS
        assert "class" not in VALUE_KINDS

    def test_visibility_choices(self):
        from codegraph.constants import VISIBILITY_CHOICES
        keys = {k for k, _ in VISIBILITY_CHOICES}
        assert "public" in keys
        assert "private" in keys

    def test_layers(self):
        from codegraph.constants import LAYERS
        assert LAYERS == ["design", "as-built", "dependency"]

    def test_predicates_list(self):
        from codegraph.constants import PREDICATES
        assert "composes" in PREDICATES
        assert "aggregates" in PREDICATES
        assert "generalizes" in PREDICATES

    def test_predicate_to_rel_type_mapping(self):
        from codegraph.constants import PREDICATE_TO_REL_TYPE
        assert PREDICATE_TO_REL_TYPE["composes"] == "COMPOSES"
        assert PREDICATE_TO_REL_TYPE["depends_on"] == "DEPENDS_ON"

    def test_valid_specializations_cpp(self):
        from codegraph.constants import valid_specializations
        cpp_class = valid_specializations("cpp", "class")
        assert "struct" in cpp_class
        assert "abstract_class" in cpp_class

    def test_valid_specializations_unknown_language(self):
        from codegraph.constants import valid_specializations
        assert valid_specializations("rust", "class") == set()

    def test_supported_languages(self):
        from codegraph.constants import SUPPORTED_LANGUAGES
        assert "cpp" in SUPPORTED_LANGUAGES
        assert "python" in SUPPORTED_LANGUAGES
        assert "javascript" in SUPPORTED_LANGUAGES


class TestGraphPrimitiveModels:
    """Lightweight validation of graph primitive model instantiation.

    Full round-trip tests live in tests/test_codebase_schemas.py.
    """

    def test_compound_node_minimal(self):
        node = CompoundNode(
            kind="class",
            name="MyClass",
            qualified_name="ns::MyClass",
            layer="design",
        )
        assert node.kind == "class"
        assert node.name == "MyClass"
        assert node.qualified_name == "ns::MyClass"
        assert node.layer == "design"

    def test_compound_node_defaults(self):
        node = CompoundNode(
            kind="class",
            name="MyClass",
            qualified_name="ns::MyClass",
            layer="design",
        )
        assert node.visibility == "public"
        assert node.specialization is None
        assert node.source is None
        assert node.members == []

    def test_member_node_minimal(self):
        node = MemberNode(
            kind="method",
            name="my_method",
            qualified_name="ns::MyClass::my_method",
            layer="design",
        )
        assert node.kind == "method"
        assert node.params == []

    def test_member_node_with_params(self):
        node = MemberNode(
            kind="function",
            name="my_func",
            qualified_name="ns::my_func",
            layer="design",
            params=[
                {"name": "x", "type": "int", "is_reference": False, "default_value": None},
                {"name": "y", "type": "float", "is_reference": True, "default_value": "0.0"},
            ],
        )
        assert len(node.params) == 2
        assert node.params[0]["name"] == "x"
        assert node.params[1]["is_reference"] is True
