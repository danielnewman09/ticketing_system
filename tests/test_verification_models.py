"""Phase 2 ORM tests — verification models: VerificationMethod,
VerificationCondition, VerificationAction."""

import pytest
from sqlalchemy.exc import IntegrityError

from backend.db.models.verification import (
    CONDITION_OPERATORS,
    VERIFICATION_METHODS,
    VerificationAction,
    VerificationCondition,
    VerificationMethod,
)
from backend.db.models.requirements import HighLevelRequirement, LowLevelRequirement
from backend.db.models.ontology import OntologyNode


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestVerificationConstants:
    """Tests for VERIFICATION_METHODS and CONDITION_OPERATORS."""

    def test_verification_methods_values(self):
        """VERIFICATION_METHODS contains the expected methods."""
        assert set(VERIFICATION_METHODS) == {"automated", "review", "inspection"}

    def test_condition_operators_keys(self):
        """CONDITION_OPERATORS has expected operator keys."""
        keys = {op for op, _ in CONDITION_OPERATORS}
        expected = {"==", "!=", "<", ">", "<=", ">=", "is_true", "is_false", "contains", "not_null"}
        assert keys == expected


# ---------------------------------------------------------------------------
# VerificationMethod
# ---------------------------------------------------------------------------

class TestVerificationMethod:
    """Tests for VerificationMethod CRUD and relationships."""

    def _make_llr(self, session):
        """Helper: create an LLR for verification methods."""
        llr = LowLevelRequirement(description="Test LLR for verification")
        session.add(llr)
        session.flush()
        return llr

    def test_create_verification_method(self, session):
        """Create a VerificationMethod linked to an LLR."""
        llr = self._make_llr(session)

        vm = VerificationMethod(
            low_level_requirement=llr,
            method="automated",
            test_name="test_addition",
            description="Verifies addition works correctly",
        )
        session.add(vm)
        session.flush()

        assert vm.id is not None
        assert vm.method == "automated"
        assert vm.test_name == "test_addition"
        assert vm.description == "Verifies addition works correctly"
        assert vm.low_level_requirement is llr

    def test_verification_method_defaults(self, session):
        """VerificationMethod optional fields have expected defaults."""
        llr = self._make_llr(session)

        vm = VerificationMethod(
            low_level_requirement_id=llr.id,
            method="review",
        )
        session.add(vm)
        session.flush()

        assert vm.test_name == ""
        assert vm.description == ""

    def test_verification_method_repr_with_test_name(self, session):
        """VerificationMethod __repr__ includes method and test name."""
        llr = self._make_llr(session)

        vm = VerificationMethod(
            low_level_requirement_id=llr.id,
            method="automated",
            test_name="test_division",
        )
        session.add(vm)
        session.flush()

        result = repr(vm)
        assert "automated" in result
        assert "test_division" in result

    def test_verification_method_repr_without_test_name(self, session):
        """VerificationMethod __repr__ shows method only when test_name empty."""
        llr = self._make_llr(session)

        vm = VerificationMethod(
            low_level_requirement_id=llr.id,
            method="inspection",
        )
        session.add(vm)
        session.flush()

        result = repr(vm)
        assert result == "inspection"

    def test_verification_method_to_prompt_text_minimal(self, session):
        """to_prompt_text returns method only when no test_name or description."""
        llr = self._make_llr(session)

        vm = VerificationMethod(
            low_level_requirement_id=llr.id,
            method="review",
        )
        session.add(vm)
        session.flush()

        assert vm.to_prompt_text() == "review"

    def test_verification_method_to_prompt_text_full(self, session):
        """to_prompt_text returns method — test_name — description."""
        llr = self._make_llr(session)

        vm = VerificationMethod(
            low_level_requirement_id=llr.id,
            method="automated",
            test_name="test_multiply",
            description="Verifies multiplication",
        )
        session.add(vm)
        session.flush()

        text = vm.to_prompt_text()
        assert "automated" in text
        assert "test_multiply" in text
        assert "Verifies multiplication" in text

    def test_verification_method_preconditions(self, seeded_session):
        """VerificationMethod.preconditions returns conditions with phase='pre'."""
        from backend.db.models.requirements import HighLevelRequirement

        llr = LowLevelRequirement(description="LLR with conditions")
        seeded_session.add(llr)
        seeded_session.flush()

        vm = VerificationMethod(
            low_level_requirement_id=llr.id,
            method="automated",
            test_name="test_pre_post",
        )
        seeded_session.add(vm)
        seeded_session.flush()

        pre_cond = VerificationCondition(
            verification_id=vm.id,
            phase="pre",
            order=1,
            member_qualified_name="Calculator::status",
            operator="is_true",
            expected_value="true",
        )
        post_cond = VerificationCondition(
            verification_id=vm.id,
            phase="post",
            order=1,
            member_qualified_name="Calculator::result",
            operator="==",
            expected_value="0",
        )
        seeded_session.add_all([pre_cond, post_cond])
        seeded_session.flush()

        assert len(vm.preconditions) == 1
        assert pre_cond in vm.preconditions
        assert len(vm.postconditions) == 1
        assert post_cond in vm.postconditions

    def test_verification_method_cascade_delete(self, session):
        """Deleting an LLR cascades to delete its VerificationMethods."""
        llr = LowLevelRequirement(description="Will be deleted")
        session.add(llr)
        session.flush()
        llr_id = llr.id

        vm = VerificationMethod(
            low_level_requirement_id=llr.id,
            method="automated",
            test_name="test_to_delete",
        )
        session.add(vm)
        session.flush()
        vm_id = vm.id

        session.delete(llr)
        session.flush()

        assert session.query(VerificationMethod).filter_by(id=vm_id).first() is None


# ---------------------------------------------------------------------------
# VerificationCondition
# ---------------------------------------------------------------------------

class TestVerificationCondition:
    """Tests for VerificationCondition CRUD and relationships."""

    def _make_vm(self, session):
        """Helper: create an LLR and VerificationMethod."""
        llr = LowLevelRequirement(description="LLR for condition test")
        session.add(llr)
        session.flush()

        vm = VerificationMethod(
            low_level_requirement_id=llr.id,
            method="automated",
            test_name="test_conditions",
        )
        session.add(vm)
        session.flush()
        return vm

    def test_create_condition_minimal(self, session):
        """Create a VerificationCondition with required fields."""
        vm = self._make_vm(session)

        cond = VerificationCondition(
            verification_id=vm.id,
            phase="pre",
            member_qualified_name="Foo::bar",
            operator="==",
            expected_value="42",
        )
        session.add(cond)
        session.flush()

        assert cond.id is not None
        assert cond.phase == "pre"
        assert cond.member_qualified_name == "Foo::bar"
        assert cond.operator == "=="
        assert cond.expected_value == "42"

    def test_condition_defaults(self, session):
        """VerificationCondition defaults: order=0, operator='=='."""
        vm = self._make_vm(session)

        cond = VerificationCondition(
            verification_id=vm.id,
            phase="post",
            member_qualified_name="Baz::qux",
            expected_value="hello",
        )
        session.add(cond)
        session.flush()

        assert cond.order == 0
        assert cond.operator == "=="

    def test_condition_with_ontology_node(self, session):
        """VerificationCondition can reference an OntologyNode."""
        vm = self._make_vm(session)

        node = OntologyNode(kind="method", name="calculate", qualified_name="Calculator::calculate")
        session.add(node)
        session.flush()

        cond = VerificationCondition(
            verification_id=vm.id,
            phase="pre",
            member_qualified_name="Calculator::calculate",
            ontology_node_id=node.id,
            operator="not_null",
            expected_value="true",
        )
        session.add(cond)
        session.flush()

        assert cond.ontology_node is node

    def test_condition_null_ontology_node(self, session):
        """VerificationCondition.ontology_node_id can be None."""
        vm = self._make_vm(session)

        cond = VerificationCondition(
            verification_id=vm.id,
            phase="pre",
            member_qualified_name="Free::func",
            operator="is_true",
            expected_value="true",
        )
        session.add(cond)
        session.flush()

        assert cond.ontology_node_id is None

    def test_condition_repr(self, session):
        """VerificationCondition __repr__ shows qualified_name op expected_value."""
        vm = self._make_vm(session)

        cond = VerificationCondition(
            verification_id=vm.id,
            phase="pre",
            member_qualified_name="Foo::bar",
            operator="!=",
            expected_value="null",
        )
        session.add(cond)
        session.flush()

        assert repr(cond) == "Foo::bar != null"

    def test_condition_cascade_from_verification(self, session):
        """Deleting a VerificationMethod cascades to delete its conditions."""
        vm = self._make_vm(session)

        cond = VerificationCondition(
            verification_id=vm.id,
            phase="pre",
            member_qualified_name="Foo::bar",
            operator="==",
            expected_value="5",
        )
        session.add(cond)
        session.flush()
        cond_id = cond.id

        session.delete(vm)
        session.flush()

        assert session.query(VerificationCondition).filter_by(id=cond_id).first() is None


# ---------------------------------------------------------------------------
# VerificationAction
# ---------------------------------------------------------------------------

class TestVerificationAction:
    """Tests for VerificationAction CRUD and relationships."""

    def _make_vm(self, session):
        """Helper: create an LLR and VerificationMethod."""
        llr = LowLevelRequirement(description="LLR for action test")
        session.add(llr)
        session.flush()

        vm = VerificationMethod(
            low_level_requirement_id=llr.id,
            method="automated",
            test_name="test_actions",
        )
        session.add(vm)
        session.flush()
        return vm

    def test_create_action(self, session):
        """Create a VerificationAction linked to a VerificationMethod."""
        vm = self._make_vm(session)

        action = VerificationAction(
            verification_id=vm.id,
            order=1,
            description="Call Calculator::add(2, 3)",
        )
        session.add(action)
        session.flush()

        assert action.id is not None
        assert action.description == "Call Calculator::add(2, 3)"
        assert action.order == 1
        assert action.verification is vm

    def test_action_defaults(self, session):
        """VerificationAction defaults: order=0, member_qualified_name=''."""
        vm = self._make_vm(session)

        action = VerificationAction(
            verification_id=vm.id,
            description="Check result",
        )
        session.add(action)
        session.flush()

        assert action.order == 0
        assert action.member_qualified_name == ""

    def test_action_with_ontology_node(self, session):
        """VerificationAction can reference an OntologyNode."""
        vm = self._make_vm(session)

        node = OntologyNode(kind="method", name="add", qualified_name="Calc::add")
        session.add(node)
        session.flush()

        action = VerificationAction(
            verification_id=vm.id,
            order=1,
            description="Invoke add method",
            ontology_node_id=node.id,
            member_qualified_name="Calc::add",
        )
        session.add(action)
        session.flush()

        assert action.ontology_node is node

    def test_action_repr(self, session):
        """VerificationAction __repr__ returns first 80 chars of description."""
        vm = self._make_vm(session)

        action = VerificationAction(
            verification_id=vm.id,
            description="Short action desc",
        )
        session.add(action)
        session.flush()

        assert repr(action) == "Short action desc"

    def test_action_repr_truncates(self, session):
        """VerificationAction __repr__ truncates descriptions >80 chars."""
        vm = self._make_vm(session)

        long_desc = "A" * 100
        action = VerificationAction(
            verification_id=vm.id,
            description=long_desc,
        )
        session.add(action)
        session.flush()

        assert repr(action) == long_desc[:80]

    def test_action_cascade_from_verification(self, session):
        """Deleting a VerificationMethod cascades to delete its actions."""
        vm = self._make_vm(session)

        action = VerificationAction(
            verification_id=vm.id,
            description="Will be deleted",
        )
        session.add(action)
        session.flush()
        action_id = action.id

        session.delete(vm)
        session.flush()

        assert session.query(VerificationAction).filter_by(id=action_id).first() is None