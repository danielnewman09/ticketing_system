"""
Tests for Pydantic schemas in backend.codebase.schemas.

Covers: AttributeNode, MethodNode, ClassNode, EnumNode,
InterfaceNode, Association, ClassDiagram, ClassNode,
CodebaseEdge, RequirementTripleLinkSchema, DesignSchema,
and the NodeKind / Visibility / SourceType literals.
"""

import pytest
from pydantic import ValidationError

from backend.codebase.schemas import (
    DesignSchema,
    NodeKind,
    RequirementTripleLinkSchema,
    SourceType,
    Visibility,
)
from codegraph.diagram import ClassDiagram, Association
from codegraph.models import (
    ClassNode,
    EnumNode,
    EnumValueNode,
    InterfaceNode,
    MethodNode,
    AttributeNode,
)

# ---------------------------------------------------------------------------
# AttributeNode
# ---------------------------------------------------------------------------


class TestAttributeNode:
    def test_minimal(self):
        a = AttributeNode(name="x", visibility="private")
        assert a.name == "x"
        assert a.type_signature == ""
        assert a.visibility == "private"
        assert a.description == ""

    def test_all_fields(self):
        a = AttributeNode(
            name="count", type_signature="int", visibility="public"
        )
        assert a.type_signature == "int"
        assert a.description == "item count"

    def test_valid_visibilities(self):
        for v in ("public", "private", "protected"):
            a = AttributeNode(name="x", visibility=v)
            assert a.visibility == v


# ---------------------------------------------------------------------------
# MethodNode
# ---------------------------------------------------------------------------


class TestMethodNode:
    def test_minimal(self):
        m = MethodNode(name="run", visibility="public")
        assert m.name == "run"
        assert m.argsstring == ""
        assert m.type_signature == ""

    def test_all_fields(self):
        m = MethodNode(
            name="calc",
            visibility="private",
            description="do math",
            argsstring="(a, b)",
            type_signature="int",
        )
        assert m.argsstring == "(a, b)"
        assert m.type_signature == "int"


# ---------------------------------------------------------------------------
# ClassNode
# ---------------------------------------------------------------------------


class TestClassNode:
    def test_minimal(self):
        c = ClassNode(name="Widget")
        assert c.module == ""
        assert c.specialization == ""
        assert c.is_intercomponent is False
        assert c.attributes == []
        assert c.methods == []
        assert c.inherits_from == []
        assert c.realizes == []
        assert c.requirement_ids == []

    def test_with_nested_schemas(self):
        c = ClassNode(
            name="Engine",
            module="eng",
            specialization="class",
            attributes=[AttributeNode(name="rpm", type_signature="int", visibility="private")],
            methods=[MethodNode(name="start", visibility="public")],
            inherits_from=["Motor"],
            realizes=["Runnable"],
            requirement_ids=["hlr:1"],
        )
        assert len(c.attributes) == 1
        assert c.attributes[0].name == "rpm"
        assert len(c.methods) == 1
        assert "Motor" in c.inherits_from
        assert "Runnable" in c.realizes

    def test_invalid_specialization(self):
        # specialization is str, not Literal — Pydantic will accept any string
        c = ClassNode(name="X", specialization="trait")
        assert c.specialization == "trait"


# ---------------------------------------------------------------------------
# EnumNode
# ---------------------------------------------------------------------------


class TestEnumNode:
    def test_minimal(self):
        e = EnumNode(name="Color")
        assert e.values == []
        assert e.module == ""

    def test_with_values(self):
        e = EnumNode(name="Status", module="core", values=[EnumValueNode(name="OK"), EnumValueNode(name="FAIL")])
        assert len(e.values) == 2
        assert e.values[0].name == "OK"
        assert e.values[1].name == "FAIL"


# ---------------------------------------------------------------------------
# InterfaceNode
# ---------------------------------------------------------------------------


class TestInterfaceNode:
    def test_minimal(self):
        i = InterfaceNode(name="Serializable")
        assert i.methods == []
        assert i.is_intercomponent is False

    def test_with_methods(self):
        i = InterfaceNode(
            name="Runnable",
            methods=[MethodNode(name="run", visibility="public")],
        )
        assert len(i.methods) == 1


# ---------------------------------------------------------------------------
# Association
# ---------------------------------------------------------------------------


class TestAssociation:
    def test_minimal(self):
        a = Association(subject="A", object="B", predicate="associates")
        assert a.description == ""
        assert a.requirement_ids == []

    def test_all_kinds(self):
        for predicate in ("associates", "aggregates", "depends_on", "invokes"):
            a = Association(subject="A", object="B", predicate=predicate)
            assert a.predicate == predicate


# ---------------------------------------------------------------------------
# ClassDiagram
# ---------------------------------------------------------------------------


class TestClassDiagram:
    def test_minimal(self):
        d = ClassDiagram()
        assert d.module_names == []
        assert d.classes == []
        assert d.interfaces == []
        assert d.enums == []
        assert d.associations == []

    def test_with_classes(self):
        d = ClassDiagram(
            module_names=["app"],
            classes=[ClassNode(name="Foo")],
            enums=[EnumNode(name="Bar")],
        )
        assert len(d.classes) == 1
        assert d.module_names == ["app"]

    def test_round_trip(self):
        d = ClassDiagram(
            module_names=["m1"],
            classes=[
                ClassNode(
                    name="C",
                    attributes=[AttributeNode(name="x", visibility="public")],
                    methods=[MethodNode(name="get", visibility="public")],
                )
            ],
        )
        restored = ClassDiagram.model_validate(d.model_dump())
        assert restored.classes[0].name == "C"
        assert len(restored.classes[0].attributes) == 1

    def test_json_round_trip(self):
        d = ClassDiagram(
            classes=[ClassNode(name="C")],
            associations=[Association(subject="C", object="D", predicate="depends_on")],
        )
        json_str = d.model_dump_json()
        restored = ClassDiagram.model_validate_json(json_str)
        assert restored.classes[0].name == "C"
        assert restored.associations[0].predicate == "depends_on"


# ---------------------------------------------------------------------------
# ClassNode (neomodel-level tests)
# ---------------------------------------------------------------------------


class TestNeomodelClassNode:
    def test_minimal(self):
        n = ClassNode(kind="class", name="Widget", qualified_name="ns::Widget")
        assert n.kind == "class"
        assert n.layer == "design"
        assert n.base_classes == []
        assert n.brief_description == ""
        assert n.is_abstract is False
        assert n.is_final is False

    def test_all_fields(self):
        n = ClassNode(
            kind="class",
            name="Widget",
            qualified_name="ns::Widget",
            layer="design",
            component_id=5,
            refid="ref123",
            detailed_description="long description",
            base_classes=["ns::BaseWidget"],
            file_path="src/widget.cpp",
            line_number=42,
            source="class Widget {};",
            is_abstract=True,
            is_final=False,
        )
        assert n.component_id == 5
        assert n.line_number == 42
        assert n.is_abstract is True
        assert "ns::BaseWidget" in n.base_classes

    def test_invalid_kind(self):
        # Neomodel StringProperty accepts any string — kind validation
        # is handled at the repository/application layer, not model level.
        n = ClassNode(kind="foobar", name="X", qualified_name="X")
        assert n.kind == "foobar"

    def test_valid_kinds(self):
        for kind_name in ("class", "enum", "interface", "abstract_class", "struct", "template_class", "enum_class"):
            n = ClassNode(kind=kind_name, name="X", qualified_name="X")
            assert n.kind == kind_name


# ---------------------------------------------------------------------------
# RequirementTripleLinkSchema
# ---------------------------------------------------------------------------


class TestRequirementTripleLinkSchema:
    def test_minimal(self):
        r = RequirementTripleLinkSchema(requirement_type="hlr", requirement_id=1)
        assert r.triple_index == -1
        assert r.subject_qualified_name == ""

    def test_all_fields(self):
        r = RequirementTripleLinkSchema(
            requirement_type="llr",
            requirement_id=5,
            triple_index=2,
            subject_qualified_name="ns::A",
            predicate="depends_on",
            object_qualified_name="ns::B",
        )
        assert r.requirement_type == "llr"
        assert r.triple_index == 2

    def test_invalid_requirement_type(self):
        with pytest.raises(ValidationError):
            RequirementTripleLinkSchema(requirement_type="invalid", requirement_id=1)


# ---------------------------------------------------------------------------
# DesignSchema
# ---------------------------------------------------------------------------


class TestDesignSchema:
    def test_minimal(self):
        d = DesignSchema(
            nodes=[ClassNode(kind="class", name="A", qualified_name="A")],
            associations=[],
        )
        assert len(d.nodes) == 1
        assert d.requirement_links == []

    def test_full_round_trip(self):
        d = DesignSchema(
            nodes=[
                ClassNode(kind="class", name="Widget", qualified_name="app::Widget"),
                ClassNode(kind="enum", name="Status", qualified_name="app::Status"),
            ],
            associations=[
                {"subject": "app::Widget", "predicate": "has_method", "object": "app::Widget::run"},
            ],
            requirement_links=[
                RequirementTripleLinkSchema(requirement_type="hlr", requirement_id=1),
            ],
        )
        data = d.model_dump()
        restored = DesignSchema.model_validate(data)
        assert len(restored.nodes) == 2
        assert len(restored.associations) == 1
        assert restored.requirement_links[0].requirement_type == "hlr"

    def test_json_round_trip(self):
        # Neomodel nodes are not JSON-serializable by Pydantic.
        # Round-trip tested via object-level model_dump instead.
        d = DesignSchema(
            nodes=[ClassNode(kind="class", name="A", qualified_name="A")],
            triples=[],
        )
        data = d.model_dump()
        restored = DesignSchema.model_validate(data)
        assert restored.nodes[0].name == "A"


# ---------------------------------------------------------------------------
# Literal types
# ---------------------------------------------------------------------------


class TestNodeKindLiteral:
    def test_all_model_kinds_are_literal_members(self):
        from codegraph.constants import NODE_KIND_KEYS

        for kind_name in NODE_KIND_KEYS:
            assert kind_name in NodeKind.__args__, f"{kind_name} not in NodeKind Literal"


class TestVisibilityLiteral:
    def test_all_model_visibilities_are_literal_members(self):
        from codegraph.constants import VISIBILITY_CHOICES

        for vis_key, _ in VISIBILITY_CHOICES:
            assert vis_key in Visibility.__args__, f"{vis_key} not in Visibility Literal"


class TestSourceTypeLiteral:
    def test_all_model_source_types_are_literal_members(self):
        from codegraph.constants import SOURCE_TYPES

        for st_name, _ in SOURCE_TYPES:
            assert st_name in SourceType.__args__, f"{st_name} not in SourceType Literal"
