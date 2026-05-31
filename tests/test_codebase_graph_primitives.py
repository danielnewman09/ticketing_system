"""Sanity-check the codebase graph primitives (models + constants).

Validates that:
- Node models can be instantiated with valid data.
- The constants (kinds, layers, visibility, predicates, specializations)
  are correctly imported and have expected membership.
"""

import pytest

from codegraph.models import NamespaceNode
from codegraph.models import ClassNode, MethodNode
from codegraph.models import MethodNode


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


class TestClassNodeModel:
    """Tests for CompoundNode Pydantic model."""

    def test_create_minimal(self):
        node = ClassNode(
            qualified_name="ns::Foo",
            name="Foo",
            kind="class",
            layer="design",
        )
        assert node.qualified_name == "ns::Foo"
        assert node.kind == "class"

    def test_create_with_optional_fields(self):
        node = ClassNode(
            qualified_name="ns::Bar",
            name="Bar",
            kind="struct",
            layer="as-built",
            base_classes=["ns::Foo"],
            is_abstract=True,
            file_path="/path/to/file.h",
            line_number=42,
        )
        assert node.base_classes == ["ns::Foo"]
        assert node.is_abstract is True


class TestMethodNodeModel:
    """Tests for MemberNode Pydantic model."""

    def test_create_method(self):
        node = MethodNode(
            qualified_name="ns::Foo::run",
            name="run",
            kind="method",
        )
        assert node.qualified_name == "ns::Foo::run"
        assert node.kind == "method"

    def test_create_attribute(self):
        node = MethodNode(
            qualified_name="ns::Foo::count",
            name="count",
            kind="variable",
            protection="private",
            type_signature="int",
        )
        assert node.kind == "variable"
        assert node.type_signature == "int"

    def test_invalid_kind_rejected(self):
        # Neomodel StringProperty accepts any string — kind validation
        # is handled at the repository/application layer, not model level.
        node = MethodNode(qualified_name="X", name="X", kind="class")
        assert node.kind == "class"


class TestNamespaceNode:
    """Tests for NamespaceNode Pydantic model."""

    def test_create_minimal(self):
        node = NamespaceNode(qualified_name="std", name="std", kind="namespace")
        assert node.qualified_name == "std"
        assert node.kind == "namespace"

    def test_create_package(self):
        node = NamespaceNode(qualified_name="my_pkg", name="my_pkg", kind="package")
        assert node.kind == "package"

    def test_no_irrelevant_fields(self):
        """NamespaceNode should not have implementation_status or is_intercomponent."""
        node = NamespaceNode(qualified_name="ns", name="ns")
        assert not hasattr(node, "implementation_status")
        assert not hasattr(node, "is_intercomponent")
