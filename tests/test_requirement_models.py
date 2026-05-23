"""Tests for HLR/LLR Pydantic models."""

from backend.db.neo4j.repositories.models.requirement import HLRNode, LLRNode


def test_hlr_node_defaults():
    node = HLRNode(id=1, description="The system shall perform arithmetic")
    assert node.id == 1
    assert node.description == "The system shall perform arithmetic"
    assert node.component_id is None
    assert node.dependency_context is None


def test_hlr_node_with_all_fields():
    node = HLRNode(
        id=1,
        description="The system shall perform arithmetic",
        component_id=5,
        dependency_context={"recommendation": "eigen"},
    )
    assert node.component_id == 5
    assert node.dependency_context == {"recommendation": "eigen"}


def test_llr_node_defaults():
    node = LLRNode(id=10, description="The calculator shall add two numbers", high_level_requirement_id=1)
    assert node.id == 10
    assert node.description == "The calculator shall add two numbers"
    assert node.high_level_requirement_id == 1


def test_hlr_node_model_dump():
    node = HLRNode(id=1, description="test", component_id=3)
    d = node.model_dump()
    assert d["id"] == 1
    assert d["description"] == "test"
    assert d["component_id"] == 3
    assert d["dependency_context"] is None


def test_llr_node_model_dump():
    node = LLRNode(id=5, description="llr desc", high_level_requirement_id=1)
    d = node.model_dump()
    assert d["id"] == 5
    assert d["high_level_requirement_id"] == 1