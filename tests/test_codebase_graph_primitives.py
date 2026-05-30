"""Tests for codebase graph primitives — constants, node models, and edge models."""

import pytest


class TestConstants:
    """Tests for constant values moved from db/models/ontology.py."""

    def test_compound_kinds(self):
        from backend.db.neo4j.models.constants import COMPOUND_KINDS
        assert "class" in COMPOUND_KINDS
        assert "interface" in COMPOUND_KINDS
        assert "enum" in COMPOUND_KINDS
        assert "method" not in COMPOUND_KINDS

    def test_member_kinds(self):
        from backend.db.neo4j.models.constants import MEMBER_KINDS
        assert "method" in MEMBER_KINDS
        assert "attribute" in MEMBER_KINDS
        assert "class" not in MEMBER_KINDS

    def test_namespace_kinds(self):
        from backend.db.neo4j.models.constants import NAMESPACE_KINDS
        assert "namespace" in NAMESPACE_KINDS
        assert "package" in NAMESPACE_KINDS

    def test_node_kinds_is_union(self):
        from backend.db.neo4j.models.constants import NODE_KINDS, COMPOUND_KINDS, MEMBER_KINDS, NAMESPACE_KINDS
        assert set(NODE_KINDS) == set(COMPOUND_KINDS + MEMBER_KINDS + NAMESPACE_KINDS)

    def test_type_kinds(self):
        from backend.db.neo4j.models.constants import TYPE_KINDS
        assert "class" in TYPE_KINDS
        assert "interface" in TYPE_KINDS
        assert "method" not in TYPE_KINDS

    def test_value_kinds(self):
        from backend.db.neo4j.models.constants import VALUE_KINDS
        assert "method" in VALUE_KINDS
        assert "attribute" in VALUE_KINDS
        assert "class" not in VALUE_KINDS

    def test_visibility_choices(self):
        from backend.db.neo4j.models.constants import VISIBILITY_CHOICES
        assert "public" in VISIBILITY_CHOICES
        assert "private" in VISIBILITY_CHOICES

    def test_layers(self):
        from backend.db.neo4j.models.constants import LAYERS
        assert LAYERS == ["design", "as-built", "dependency"]

    def test_predicates_list(self):
        from backend.db.neo4j.models.constants import PREDICATES
        assert "composes" in PREDICATES
        assert "aggregates" in PREDICATES
        assert "generalizes" in PREDICATES

    def test_predicate_to_rel_type_mapping(self):
        from backend.db.neo4j.models.constants import PREDICATE_TO_REL_TYPE
        assert PREDICATE_TO_REL_TYPE["composes"] == "COMPOSES"
        assert PREDICATE_TO_REL_TYPE["depends_on"] == "DEPENDS_ON"

    def test_valid_specializations_cpp(self):
        from backend.db.neo4j.models.constants import valid_specializations
        cpp_class = valid_specializations("cpp", "class")
        assert "struct" in cpp_class
        assert "abstract_class" in cpp_class

    def test_valid_specializations_unknown_language(self):
        from backend.db.neo4j.models.constants import valid_specializations
        assert valid_specializations("rust", "class") == set()

    def test_supported_languages(self):
        from backend.db.neo4j.models.constants import SUPPORTED_LANGUAGES
        assert "cpp" in SUPPORTED_LANGUAGES
        assert "python" in SUPPORTED_LANGUAGES
        assert "javascript" in SUPPORTED_LANGUAGES


class TestCompoundNode:
    """Tests for CompoundNode Pydantic model."""

    def test_create_minimal(self):
        from backend.db.neo4j.models.nodes.compound import CompoundNode
        node = CompoundNode(qualified_name="ns::Foo", name="Foo", kind="class")
        assert node.qualified_name == "ns::Foo"
        assert node.name == "Foo"
        assert node.kind == "class"
        assert node.layer == "design"
        assert node.specialization == ""
        assert node.visibility == ""
        assert node.description == ""
        assert node.implementation_status == "designed"

    def test_create_all_fields(self):
        from backend.db.neo4j.models.nodes.compound import CompoundNode
        node = CompoundNode(
            qualified_name="ns::Foo",
            name="Foo",
            kind="struct",
            layer="as-built",
            specialization="template_class",
            visibility="public",
            description="A struct",
            type_signature="int",
            argsstring="(int x)",
            definition="int Foo::calc(int x)",
            refid="classns_1_1Foo",
            file_path="src/foo.h",
            line_number=42,
            is_static=True,
            is_const=False,
            is_virtual=False,
            is_abstract=False,
            is_final=False,
            component_id=1,
            is_intercomponent=True,
            implementation_status="implemented",
            source_file="src/foo.cpp",
            test_file="test_foo.cpp",
        )
        assert node.kind == "struct"
        assert node.layer == "as-built"
        assert node.is_static is True
        assert node.is_intercomponent is True
        assert node.file_path == "src/foo.h"
        assert node.line_number == 42

    def test_invalid_kind_rejected(self):
        from backend.db.neo4j.models.nodes.compound import CompoundNode
        with pytest.raises(Exception):
            CompoundNode(qualified_name="X", name="X", kind="method")

    def test_invalid_layer_rejected(self):
        from backend.db.neo4j.models.nodes.compound import CompoundNode
        with pytest.raises(Exception):
            CompoundNode(qualified_name="X", name="X", kind="class", layer="invalid")

    def test_dependency_layer(self):
        from backend.db.neo4j.models.nodes.compound import CompoundNode
        node = CompoundNode(qualified_name="std::vector", name="vector", kind="class", layer="dependency",
                           is_intercomponent=True, description="Standard library: std::vector")
        assert node.layer == "dependency"
        assert node.is_intercomponent is True


class TestMemberNode:
    """Tests for MemberNode Pydantic model."""

    def test_create_minimal(self):
        from backend.db.neo4j.models.nodes.member import MemberNode
        node = MemberNode(qualified_name="ns::Foo::calculate", name="calculate", kind="method")
        assert node.qualified_name == "ns::Foo::calculate"
        assert node.kind == "method"
        assert node.layer == "design"

    def test_create_attribute(self):
        from backend.db.neo4j.models.nodes.member import MemberNode
        node = MemberNode(
            qualified_name="ns::Foo::count",
            name="count",
            kind="attribute",
            visibility="private",
            type_signature="int",
        )
        assert node.kind == "attribute"
        assert node.type_signature == "int"

    def test_invalid_kind_rejected(self):
        from backend.db.neo4j.models.nodes.member import MemberNode
        with pytest.raises(Exception):
            MemberNode(qualified_name="X", name="X", kind="class")


class TestNamespaceNode:
    """Tests for NamespaceNode Pydantic model."""

    def test_create_minimal(self):
        from backend.db.neo4j.models.nodes.namespace import NamespaceNode
        node = NamespaceNode(qualified_name="std", name="std", kind="namespace")
        assert node.qualified_name == "std"
        assert node.kind == "namespace"

    def test_create_package(self):
        from backend.db.neo4j.models.nodes.namespace import NamespaceNode
        node = NamespaceNode(qualified_name="my_pkg", name="my_pkg", kind="package")
        assert node.kind == "package"

    def test_no_irrelevant_fields(self):
        """NamespaceNode should not have implementation_status or is_intercomponent."""
        from backend.db.neo4j.models.nodes.namespace import NamespaceNode
        node = NamespaceNode(qualified_name="ns", name="ns")
        assert not hasattr(node, "implementation_status")
        assert not hasattr(node, "is_intercomponent")


class TestCodebaseEdge:
    """Tests for CodebaseEdge model and PREDICATES."""

    def test_create_basic_edge(self):
        from backend.db.neo4j.models.edges import CodebaseEdge
        edge = CodebaseEdge(
            subject_qualified_name="ns::Foo",
            predicate="composes",
            object_qualified_name="ns::Foo::calculate",
        )
        assert edge.predicate == "composes"
        assert edge.mechanism == ""
        assert edge.position is None

    def test_create_edge_with_mechanism(self):
        from backend.db.neo4j.models.edges import CodebaseEdge
        edge = CodebaseEdge(
            subject_qualified_name="ns::Car",
            predicate="aggregates",
            object_qualified_name="ns::Wheel",
            mechanism="std::vector",
        )
        assert edge.mechanism == "std::vector"

    def test_create_edge_with_type_argument(self):
        from backend.db.neo4j.models.edges import CodebaseEdge
        edge = CodebaseEdge(
            subject_qualified_name="std::vector",
            predicate="type_argument",
            object_qualified_name="std::string",
            position=0,
            display_name="std::string",
        )
        assert edge.position == 0
        assert edge.display_name == "std::string"

    def test_predicates_matches_constant(self):
        from backend.db.neo4j.models.edges import CodebaseEdge, PREDICATES
        assert len(PREDICATES) > 0
        assert "composes" in PREDICATES