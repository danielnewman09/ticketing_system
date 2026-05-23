"""Tests for VerificationMethod/Condition/Action Pydantic models for Neo4j.

Phase 3: These models replace the SQLAlchemy VerificationMethod,
VerificationCondition, and VerificationAction models.
"""

from backend.db.neo4j.repositories.models.verification import (
    ActionNode,
    ConditionNode,
    VerificationMethodNode,
)


class TestVerificationMethodNode:
    def test_defaults(self):
        vm = VerificationMethodNode(id=1, llr_id=10, method="automated")
        assert vm.id == 1
        assert vm.llr_id == 10
        assert vm.method == "automated"
        assert vm.test_name == ""
        assert vm.description == ""

    def test_full_fields(self):
        vm = VerificationMethodNode(
            id=1,
            llr_id=10,
            method="review",
            test_name="test_addition",
            description="Verifies addition works correctly",
        )
        assert vm.test_name == "test_addition"
        assert vm.description == "Verifies addition works correctly"

    def test_model_dump(self):
        vm = VerificationMethodNode(id=5, llr_id=20, method="inspection", test_name="check_ui")
        d = vm.model_dump()
        assert d["id"] == 5
        assert d["llr_id"] == 20
        assert d["method"] == "inspection"
        assert d["test_name"] == "check_ui"
        assert d["description"] == ""


class TestConditionNode:
    def test_defaults(self):
        c = ConditionNode(
            id=1,
            verification_method_id=5,
            phase="pre",
            order=0,
            operator="==",
            expected_value="0",
        )
        assert c.id == 1
        assert c.phase == "pre"
        assert c.order == 0
        assert c.operator == "=="
        assert c.subject_qualified_name == ""

    def test_with_design_references(self):
        c = ConditionNode(
            id=1,
            verification_method_id=5,
            phase="pre",
            order=0,
            operator="==",
            expected_value="0",
            subject_qualified_name="Calculator::result",
            object_qualified_name="Calculator::ZERO",
        )
        assert c.subject_qualified_name == "Calculator::result"
        assert c.object_qualified_name == "Calculator::ZERO"

    def test_model_dump(self):
        c = ConditionNode(
            id=1,
            verification_method_id=5,
            phase="post",
            order=2,
            operator="!=",
            expected_value="null",
            subject_qualified_name="Foo::bar",
        )
        d = c.model_dump()
        assert d["phase"] == "post"
        assert d["subject_qualified_name"] == "Foo::bar"
        assert d["object_qualified_name"] == ""


class TestActionNode:
    def test_defaults(self):
        a = ActionNode(
            id=1,
            verification_method_id=5,
            order=1,
            description="Press + button",
        )
        assert a.id == 1
        assert a.order == 1
        assert a.description == "Press + button"
        assert a.caller_qualified_name == ""
        assert a.callee_qualified_name == ""

    def test_with_design_references(self):
        a = ActionNode(
            id=1,
            verification_method_id=5,
            order=1,
            description="Call add()",
            caller_qualified_name="Calculator",
            callee_qualified_name="Calculator::add",
        )
        assert a.caller_qualified_name == "Calculator"
        assert a.callee_qualified_name == "Calculator::add"

    def test_model_dump(self):
        a = ActionNode(
            id=10,
            verification_method_id=3,
            order=0,
            description="Invoke calculate",
            callee_qualified_name="Calc::calculate",
        )
        d = a.model_dump()
        assert d["callee_qualified_name"] == "Calc::calculate"
        assert d["caller_qualified_name"] == ""
