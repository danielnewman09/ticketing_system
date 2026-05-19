"""
Tests for Pydantic schemas in backend.codebase.schemas.

Covers: AttributeSchema, MethodSchema, ClassSchema, EnumSchema,
InterfaceSchema, AssociationSchema, OODesignSchema, OntologyNodeSchema,
OntologyTripleSchema, RequirementTripleLinkSchema, DesignSchema,
and the NodeKind / Visibility / SourceType literals.
"""

import pytest
from pydantic import ValidationError

from backend.codebase.schemas import (
    AssociationSchema,
    AttributeSchema,
    ClassSchema,
    DesignSchema,
    EnumSchema,
    InterfaceSchema,
    MethodSchema,
    NodeKind,
    OODesignSchema,
    OntologyNodeSchema,
    OntologyTripleSchema,
    RequirementTripleLinkSchema,
    SourceType,
    Visibility,
)


# ---------------------------------------------------------------------------
# AttributeSchema
# ---------------------------------------------------------------------------

class TestAttributeSchema:
    def test_minimal(self):
        a = AttributeSchema(name="x", visibility="private")
        assert a.name == "x"
        assert a.type_name == ""
        assert a.visibility == "private"
        assert a.description == ""

    def test_all_fields(self):
        a = AttributeSchema(
            name="count", type_name="int", visibility="public", description="item count"
        )
        assert a.type_name == "int"
        assert a.description == "item count"

    def test_invalid_visibility(self):
        with pytest.raises(ValidationError):
            AttributeSchema(name="x", visibility="banana")

    def test_missing_required_field(self):
        with pytest.raises(ValidationError):
            AttributeSchema(visibility="private")  # missing name

    def test_valid_visibilities(self):
        for v in ("public", "private", "protected"):
            a = AttributeSchema(name="x", visibility=v)
            assert a.visibility == v


# ---------------------------------------------------------------------------
# MethodSchema
# ---------------------------------------------------------------------------

class TestMethodSchema:
    def test_minimal(self):
        m = MethodSchema(name="run", visibility="public")
        assert m.name == "run"
        assert m.parameters == []
        assert m.return_type == ""

    def test_all_fields(self):
        m = MethodSchema(
            name="calc",
            visibility="private",
            description="do math",
            parameters=["a", "b"],
            return_type="int",
        )
        assert m.parameters == ["a", "b"]
        assert m.return_type == "int"

    def test_invalid_visibility(self):
        with pytest.raises(ValidationError):
            MethodSchema(name="x", visibility="invisible")


# ---------------------------------------------------------------------------
# ClassSchema
# ---------------------------------------------------------------------------

class TestClassSchema:
    def test_minimal(self):
        c = ClassSchema(name="Widget")
        assert c.module == ""
        assert c.specialization == ""
        assert c.is_intercomponent is False
        assert c.attributes == []
        assert c.methods == []
        assert c.inherits_from == []
        assert c.realizes_interfaces == []
        assert c.requirement_ids == []

    def test_with_nested_schemas(self):
        c = ClassSchema(
            name="Engine",
            module="eng",
            specialization="class",
            attributes=[AttributeSchema(name="rpm", type_name="int", visibility="private")],
            methods=[MethodSchema(name="start", visibility="public")],
            inherits_from=["Motor"],
            realizes_interfaces=["Runnable"],
            requirement_ids=["hlr:1"],
        )
        assert len(c.attributes) == 1
        assert c.attributes[0].name == "rpm"
        assert len(c.methods) == 1
        assert "Motor" in c.inherits_from
        assert "Runnable" in c.realizes_interfaces

    def test_invalid_specialization(self):
        # specialization is str, not Literal — Pydantic will accept any string
        c = ClassSchema(name="X", specialization="trait")
        assert c.specialization == "trait"


# ---------------------------------------------------------------------------
# EnumSchema
# ---------------------------------------------------------------------------

class TestEnumSchema:
    def test_minimal(self):
        e = EnumSchema(name="Color")
        assert e.values == []
        assert e.module == ""

    def test_with_values(self):
        e = EnumSchema(name="Status", module="core", values=["OK", "FAIL"])
        assert e.values == ["OK", "FAIL"]


# ---------------------------------------------------------------------------
# InterfaceSchema
# ---------------------------------------------------------------------------

class TestInterfaceSchema:
    def test_minimal(self):
        i = InterfaceSchema(name="Serializable")
        assert i.methods == []
        assert i.is_intercomponent is False

    def test_with_methods(self):
        i = InterfaceSchema(
            name="Runnable",
            methods=[MethodSchema(name="run", visibility="public")],
        )
        assert len(i.methods) == 1


# ---------------------------------------------------------------------------
# AssociationSchema
# ---------------------------------------------------------------------------

class TestAssociationSchema:
    def test_minimal(self):
        a = AssociationSchema(from_class="A", to_class="B", kind="associates")
        assert a.description == ""
        assert a.requirement_ids == []

    def test_all_kinds(self):
        for kind in ("associates", "aggregates", "depends_on", "invokes"):
            a = AssociationSchema(from_class="A", to_class="B", kind=kind)
            assert a.kind == kind

    def test_invalid_kind(self):
        with pytest.raises(ValidationError):
            AssociationSchema(from_class="A", to_class="B", kind="invalid")


# ---------------------------------------------------------------------------
# OODesignSchema
# ---------------------------------------------------------------------------

class TestOODesignSchema:
    def test_minimal(self):
        d = OODesignSchema()
        assert d.modules == []
        assert d.classes == []
        assert d.interfaces == []
        assert d.enums == []
        assert d.associations == []

    def test_with_classes(self):
        d = OODesignSchema(
            modules=["app"],
            classes=[ClassSchema(name="Foo")],
            enums=[EnumSchema(name="Bar")],
        )
        assert len(d.classes) == 1
        assert d.modules == ["app"]

    def test_round_trip(self):
        d = OODesignSchema(
            modules=["m1"],
            classes=[
                ClassSchema(
                    name="C",
                    attributes=[AttributeSchema(name="x", visibility="public")],
                    methods=[MethodSchema(name="get", visibility="public")],
                )
            ],
        )
        restored = OODesignSchema.model_validate(d.model_dump())
        assert restored.classes[0].name == "C"
        assert len(restored.classes[0].attributes) == 1

    def test_json_round_trip(self):
        d = OODesignSchema(
            classes=[ClassSchema(name="C")],
            associations=[
                AssociationSchema(from_class="C", to_class="D", kind="depends_on")
            ],
        )
        json_str = d.model_dump_json()
        restored = OODesignSchema.model_validate_json(json_str)
        assert restored.classes[0].name == "C"
        assert restored.associations[0].kind == "depends_on"


# ---------------------------------------------------------------------------
# OntologyNodeSchema
# ---------------------------------------------------------------------------

class TestOntologyNodeSchema:
    def test_minimal(self):
        n = OntologyNodeSchema(kind="class", name="Widget", qualified_name="ns::Widget")
        assert n.specialization == ""
        assert n.visibility == ""
        assert n.is_intercomponent is False

    def test_all_fields(self):
        n = OntologyNodeSchema(
            kind="method",
            specialization="instance_method",
            visibility="public",
            name="doStuff",
            qualified_name="ns::Widget::doStuff",
            description="does stuff",
            component_id=5,
            is_intercomponent=True,
            source_type="defined_here",
            type_signature="void()",
            argsstring="(int x)",
            definition="void doStuff(int x)",
            file_path="src/widget.cpp",
            line_number=42,
            is_static=False,
            is_const=True,
            is_virtual=True,
        )
        assert n.component_id == 5
        assert n.line_number == 42
        assert n.is_const is True

    def test_invalid_kind(self):
        with pytest.raises(ValidationError):
            OntologyNodeSchema(kind="foobar", name="X", qualified_name="X")

    def test_valid_kinds(self):
        # NodeKind is derived from NODE_KINDS — test a representative sample
        for kind_name in ("class", "method", "attribute", "enum", "interface"):
            n = OntologyNodeSchema(kind=kind_name, name="X", qualified_name="X")
            assert n.kind == kind_name


# ---------------------------------------------------------------------------
# OntologyTripleSchema
# ---------------------------------------------------------------------------

class TestOntologyTripleSchema:
    def test_minimal(self):
        t = OntologyTripleSchema(
            subject_qualified_name="A::B",
            predicate="associates",
            object_qualified_name="C::D",
        )
        assert t.subject_qualified_name == "A::B"
        assert t.predicate == "associates"

    def test_missing_required_field(self):
        with pytest.raises(ValidationError):
            OntologyTripleSchema(subject_qualified_name="A::B", predicate="associates")


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
            nodes=[OntologyNodeSchema(kind="class", name="A", qualified_name="A")],
            triples=[],
        )
        assert len(d.nodes) == 1
        assert d.requirement_links == []

    def test_full_round_trip(self):
        d = DesignSchema(
            nodes=[
                OntologyNodeSchema(kind="class", name="Widget", qualified_name="app::Widget"),
                OntologyNodeSchema(kind="method", name="run", qualified_name="app::Widget::run"),
            ],
            triples=[
                OntologyTripleSchema(
                    subject_qualified_name="app::Widget",
                    predicate="has_method",
                    object_qualified_name="app::Widget::run",
                )
            ],
            requirement_links=[
                RequirementTripleLinkSchema(requirement_type="hlr", requirement_id=1),
            ],
        )
        data = d.model_dump()
        restored = DesignSchema.model_validate(data)
        assert len(restored.nodes) == 2
        assert len(restored.triples) == 1
        assert restored.requirement_links[0].requirement_type == "hlr"

    def test_json_round_trip(self):
        d = DesignSchema(
            nodes=[OntologyNodeSchema(kind="class", name="A", qualified_name="A")],
            triples=[],
        )
        json_str = d.model_dump_json()
        restored = DesignSchema.model_validate_json(json_str)
        assert restored.nodes[0].name == "A"


# ---------------------------------------------------------------------------
# Literal types
# ---------------------------------------------------------------------------

class TestNodeKindLiteral:
    def test_all_model_kinds_are_literal_members(self):
        from backend.db.models.ontology import NODE_KINDS
        for kind_name, _ in NODE_KINDS:
            assert kind_name in NodeKind.__args__, f"{kind_name} not in NodeKind Literal"


class TestVisibilityLiteral:
    def test_all_model_visibilities_are_literal_members(self):
        from backend.db.models.ontology import VISIBILITY_CHOICES
        for vis_name, _ in VISIBILITY_CHOICES:
            assert vis_name in Visibility.__args__, f"{vis_name} not in Visibility Literal"


class TestSourceTypeLiteral:
    def test_all_model_source_types_are_literal_members(self):
        from backend.db.models.ontology import SOURCE_TYPES
        for st_name, _ in SOURCE_TYPES:
            assert st_name in SourceType.__args__, f"{st_name} not in SourceType Literal"