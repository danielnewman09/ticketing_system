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