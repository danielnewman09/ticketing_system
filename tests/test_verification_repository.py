"""Integration tests for VerificationRepository.

Requires a running Neo4j instance. Set RUN_NEO4J_INTEGRATION=1 to run.
"""

import os
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_NEO4J_INTEGRATION") != "1",
    reason="Set RUN_NEO4J_INTEGRATION=1 to run Neo4j integration tests",
)


@pytest.fixture
def neo4j_session():
    """Provide a Neo4j session and clean up after each test."""
    from backend.db.neo4j.connection import get_standalone_driver

    driver = get_standalone_driver()
    session = driver.session(database="neo4j")
    # Clean up before
    session.run("MATCH (n:VerificationMethod) DETACH DELETE n")
    session.run("MATCH (n:Condition) DETACH DELETE n")
    session.run("MATCH (n:Action) DETACH DELETE n")
    session.run("MATCH (n:HLR) DETACH DELETE n")
    session.run("MATCH (n:LLR) DETACH DELETE n")
    session.run("MATCH (n:Design) DETACH DELETE n")
    yield session
    # Clean up after
    session.run("MATCH (n:VerificationMethod) DETACH DELETE n")
    session.run("MATCH (n:Condition) DETACH DELETE n")
    session.run("MATCH (n:Action) DETACH DELETE n")
    session.run("MATCH (n:HLR) DETACH DELETE n")
    session.run("MATCH (n:LLR) DETACH DELETE n")
    session.run("MATCH (n:Design) DETACH DELETE n")
    session.close()
    driver.close()


def _seed_hlr_llr(neo4j_session):
    """Create an HLR + LLR for testing verifications."""
    from backend.db.neo4j.repositories.requirement import RequirementRepository

    repo = RequirementRepository(neo4j_session)
    hlr = repo.create_hlr(description="The system shall calculate")
    llr = repo.create_llr(hlr_id=hlr.id, description="The calculator shall add two numbers")
    return hlr, llr


def _seed_design_node(neo4j_session, qualified_name="calc::Calculator", kind="class"):
    """Create a :Design node for edge targets."""
    from backend.db.neo4j.repositories.design import DesignRepository
    from backend.db.neo4j.repositories.models.design import DesignNode

    repo = DesignRepository(neo4j_session)
    repo.merge_node(DesignNode(qualified_name=qualified_name, name=qualified_name.rsplit("::", 1)[-1], kind=kind))


class TestVerificationMethodCRUD:
    def test_create_verification(self, neo4j_session):
        from backend.db.neo4j.repositories.verification import VerificationRepository

        hlr, llr = _seed_hlr_llr(neo4j_session)
        repo = VerificationRepository(neo4j_session)
        vm = repo.create_verification(llr_id=llr.id, method="automated", test_name="test_add")
        assert vm.id is not None
        assert vm.llr_id == llr.id
        assert vm.method == "automated"
        assert vm.test_name == "test_add"

    def test_create_verification_with_verifies_edge(self, neo4j_session):
        from backend.db.neo4j.repositories.verification import VerificationRepository

        hlr, llr = _seed_hlr_llr(neo4j_session)
        repo = VerificationRepository(neo4j_session)
        vm = repo.create_verification(llr_id=llr.id, method="review")
        # Verify :VERIFIES edge exists
        result = neo4j_session.run(
            "MATCH (l:LLR {id: $lid})-[:VERIFIES]->(vm:VerificationMethod {id: $vid}) RETURN count(*) AS cnt",
            {"lid": llr.id, "vid": vm.id},
        )
        assert result.single()["cnt"] == 1

    def test_get_verification(self, neo4j_session):
        from backend.db.neo4j.repositories.verification import VerificationRepository

        hlr, llr = _seed_hlr_llr(neo4j_session)
        repo = VerificationRepository(neo4j_session)
        created = repo.create_verification(llr_id=llr.id, method="automated", test_name="test_get")
        fetched = repo.get_verification(created.id)
        assert fetched is not None
        assert fetched.method == "automated"
        assert fetched.test_name == "test_get"

    def test_get_verification_not_found(self, neo4j_session):
        from backend.db.neo4j.repositories.verification import VerificationRepository

        repo = VerificationRepository(neo4j_session)
        assert repo.get_verification(99999) is None

    def test_update_verification(self, neo4j_session):
        from backend.db.neo4j.repositories.verification import VerificationRepository

        hlr, llr = _seed_hlr_llr(neo4j_session)
        repo = VerificationRepository(neo4j_session)
        created = repo.create_verification(llr_id=llr.id, method="automated", test_name="original")
        updated = repo.update_verification(created.id, test_name="updated", description="New desc")
        assert updated is not None
        assert updated.test_name == "updated"
        assert updated.description == "New desc"

    def test_delete_verification(self, neo4j_session):
        from backend.db.neo4j.repositories.verification import VerificationRepository

        hlr, llr = _seed_hlr_llr(neo4j_session)
        repo = VerificationRepository(neo4j_session)
        created = repo.create_verification(llr_id=llr.id, method="automated")
        assert repo.delete_verification(created.id) is True
        assert repo.get_verification(created.id) is None

    def test_delete_verification_cascades_conditions_and_actions(self, neo4j_session):
        from backend.db.neo4j.repositories.verification import VerificationRepository

        _seed_design_node(neo4j_session, "Calc::result")
        hlr, llr = _seed_hlr_llr(neo4j_session)
        repo = VerificationRepository(neo4j_session)
        vm = repo.create_verification(llr_id=llr.id, method="automated", test_name="test_cascade")
        repo.add_condition(vm.id, phase="pre", subject_qualified_name="Calc::result", operator="==", expected_value="0")
        repo.add_action(vm.id, order=1, description="Push button", callee_qualified_name="Calc::result")
        # Verify condition and action exist
        assert len(repo.list_conditions(vm.id)) == 1
        assert len(repo.list_actions(vm.id)) == 1
        # Delete verification
        repo.delete_verification(vm.id)
        # Condition and action should be gone
        assert len(repo.list_conditions(vm.id)) == 0
        assert len(repo.list_actions(vm.id)) == 0

    def test_list_verifications(self, neo4j_session):
        from backend.db.neo4j.repositories.verification import VerificationRepository

        hlr, llr = _seed_hlr_llr(neo4j_session)
        repo = VerificationRepository(neo4j_session)
        repo.create_verification(llr_id=llr.id, method="automated", test_name="test1")
        repo.create_verification(llr_id=llr.id, method="review", test_name="test2")
        vms = repo.list_verifications(llr_id=llr.id)
        assert len(vms) == 2

    def test_list_verifications_empty(self, neo4j_session):
        from backend.db.neo4j.repositories.verification import VerificationRepository

        hlr, llr = _seed_hlr_llr(neo4j_session)
        repo = VerificationRepository(neo4j_session)
        vms = repo.list_verifications(llr_id=llr.id)
        assert vms == []


class TestConditionCRUD:
    def test_add_condition(self, neo4j_session):
        from backend.db.neo4j.repositories.verification import VerificationRepository

        _seed_design_node(neo4j_session, "Calc::result")
        hlr, llr = _seed_hlr_llr(neo4j_session)
        repo = VerificationRepository(neo4j_session)
        vm = repo.create_verification(llr_id=llr.id, method="automated", test_name="test_cond")
        cond = repo.add_condition(
            vm.id, phase="pre", order=0, operator="==",
            expected_value="0", subject_qualified_name="Calc::result",
        )
        assert cond.id is not None
        assert cond.verification_method_id == vm.id
        assert cond.phase == "pre"
        assert cond.subject_qualified_name == "Calc::result"

    def test_add_condition_creates_left_operand_edge(self, neo4j_session):
        from backend.db.neo4j.repositories.verification import VerificationRepository

        _seed_design_node(neo4j_session, "Calc::result")
        hlr, llr = _seed_hlr_llr(neo4j_session)
        repo = VerificationRepository(neo4j_session)
        vm = repo.create_verification(llr_id=llr.id, method="automated")
        repo.add_condition(vm.id, phase="pre", subject_qualified_name="Calc::result", operator="==", expected_value="0")
        # Verify :LEFT_OPERAND edge
        result = neo4j_session.run(
            "MATCH (c:Condition)-[:LEFT_OPERAND]->(d:Design {qualified_name: $qn}) RETURN count(*) AS cnt",
            {"qn": "Calc::result"},
        )
        assert result.single()["cnt"] == 1

    def test_add_condition_creates_right_operand_edge(self, neo4j_session):
        from backend.db.neo4j.repositories.verification import VerificationRepository

        _seed_design_node(neo4j_session, "Calc::result")
        _seed_design_node(neo4j_session, "Calc::ZERO")
        hlr, llr = _seed_hlr_llr(neo4j_session)
        repo = VerificationRepository(neo4j_session)
        vm = repo.create_verification(llr_id=llr.id, method="automated")
        repo.add_condition(
            vm.id, phase="pre", subject_qualified_name="Calc::result",
            operator="==", expected_value="0", object_qualified_name="Calc::ZERO",
        )
        # Verify :RIGHT_OPERAND edge
        result = neo4j_session.run(
            "MATCH (c:Condition)-[:RIGHT_OPERAND]->(d:Design {qualified_name: $qn}) RETURN count(*) AS cnt",
            {"qn": "Calc::ZERO"},
        )
        assert result.single()["cnt"] == 1

    def test_add_condition_no_design_node_skips_edge(self, neo4j_session):
        """If the referenced :Design node doesn't exist, the condition is created but no edge."""
        from backend.db.neo4j.repositories.verification import VerificationRepository

        hlr, llr = _seed_hlr_llr(neo4j_session)
        repo = VerificationRepository(neo4j_session)
        vm = repo.create_verification(llr_id=llr.id, method="automated")
        cond = repo.add_condition(vm.id, phase="pre", subject_qualified_name="NonExistent::member", operator="==", expected_value="0")
        assert cond is not None
        assert cond.subject_qualified_name == "NonExistent::member"
        # No edge should exist
        result = neo4j_session.run(
            "MATCH (c:Condition)-[:LEFT_OPERAND]->(:Design) RETURN count(*) AS cnt",
        )
        assert result.single()["cnt"] == 0

    def test_list_conditions_by_phase(self, neo4j_session):
        from backend.db.neo4j.repositories.verification import VerificationRepository

        hlr, llr = _seed_hlr_llr(neo4j_session)
        repo = VerificationRepository(neo4j_session)
        vm = repo.create_verification(llr_id=llr.id, method="automated")
        repo.add_condition(vm.id, phase="pre", operator="==", expected_value="0")
        repo.add_condition(vm.id, phase="pre", operator="!=", expected_value="null")
        repo.add_condition(vm.id, phase="post", operator="==", expected_value="42")
        pre = repo.list_conditions(vm.id, phase="pre")
        post = repo.list_conditions(vm.id, phase="post")
        assert len(pre) == 2
        assert len(post) == 1
        all_conds = repo.list_conditions(vm.id)
        assert len(all_conds) == 3

    def test_add_condition_with_has_condition_edge(self, neo4j_session):
        from backend.db.neo4j.repositories.verification import VerificationRepository

        hlr, llr = _seed_hlr_llr(neo4j_session)
        repo = VerificationRepository(neo4j_session)
        vm = repo.create_verification(llr_id=llr.id, method="automated")
        repo.add_condition(vm.id, phase="pre", operator="==", expected_value="0")
        result = neo4j_session.run(
            "MATCH (vm:VerificationMethod {id: $vid})-[:HAS_CONDITION]->(c:Condition) RETURN count(*) AS cnt",
            {"vid": vm.id},
        )
        assert result.single()["cnt"] == 1


class TestActionCRUD:
    def test_add_action(self, neo4j_session):
        from backend.db.neo4j.repositories.verification import VerificationRepository

        _seed_design_node(neo4j_session, "Calc::add")
        hlr, llr = _seed_hlr_llr(neo4j_session)
        repo = VerificationRepository(neo4j_session)
        vm = repo.create_verification(llr_id=llr.id, method="automated")
        action = repo.add_action(vm.id, order=1, description="Call add()", callee_qualified_name="Calc::add")
        assert action.id is not None
        assert action.verification_method_id == vm.id
        assert action.description == "Call add()"
        assert action.callee_qualified_name == "Calc::add"

    def test_add_action_creates_callee_edge(self, neo4j_session):
        from backend.db.neo4j.repositories.verification import VerificationRepository

        _seed_design_node(neo4j_session, "Calc::add")
        hlr, llr = _seed_hlr_llr(neo4j_session)
        repo = VerificationRepository(neo4j_session)
        vm = repo.create_verification(llr_id=llr.id, method="automated")
        repo.add_action(vm.id, order=1, description="Invoke", callee_qualified_name="Calc::add")
        result = neo4j_session.run(
            "MATCH (a:Action)-[:CALLEE]->(d:Design {qualified_name: $qn}) RETURN count(*) AS cnt",
            {"qn": "Calc::add"},
        )
        assert result.single()["cnt"] == 1

    def test_add_action_creates_caller_edge(self, neo4j_session):
        from backend.db.neo4j.repositories.verification import VerificationRepository

        _seed_design_node(neo4j_session, "Calc")
        _seed_design_node(neo4j_session, "Calc::add")
        hlr, llr = _seed_hlr_llr(neo4j_session)
        repo = VerificationRepository(neo4j_session)
        vm = repo.create_verification(llr_id=llr.id, method="automated")
        repo.add_action(vm.id, order=1, description="Calc calls add()", caller_qualified_name="Calc", callee_qualified_name="Calc::add")
        result = neo4j_session.run(
            "MATCH (a:Action)-[:CALLER]->(d:Design {qualified_name: $qn}) RETURN count(*) AS cnt",
            {"qn": "Calc"},
        )
        assert result.single()["cnt"] == 1

    def test_list_actions(self, neo4j_session):
        from backend.db.neo4j.repositories.verification import VerificationRepository

        hlr, llr = _seed_hlr_llr(neo4j_session)
        repo = VerificationRepository(neo4j_session)
        vm = repo.create_verification(llr_id=llr.id, method="automated")
        repo.add_action(vm.id, order=1, description="Step 1")
        repo.add_action(vm.id, order=2, description="Step 2")
        actions = repo.list_actions(vm.id)
        assert len(actions) == 2
        # Should be ordered
        assert actions[0].order <= actions[1].order


class TestDesignNodeAugmentation:
    def test_augment_missing_design_nodes(self, neo4j_session):
        from backend.db.neo4j.repositories.verification import VerificationRepository

        repo = VerificationRepository(neo4j_session)
        created = repo.augment_missing_design_nodes(["Calc::missing_method", "Calc::missing_attr"])
        assert len(created) == 2
        assert "Calc::missing_method" in created
        assert "Calc::missing_attr" in created
        # Verify the stubs exist in Neo4j
        result = neo4j_session.run(
            "MATCH (d:Design) WHERE d.qualified_name IN $qns AND d.source_type = 'verification' RETURN count(*) AS cnt",
            {"qns": ["Calc::missing_method", "Calc::missing_attr"]},
        )
        assert result.single()["cnt"] == 2

    def test_augment_skips_existing_design_nodes(self, neo4j_session):
        from backend.db.neo4j.repositories.verification import VerificationRepository

        _seed_design_node(neo4j_session, "Calc::existing")
        repo = VerificationRepository(neo4j_session)
        created = repo.augment_missing_design_nodes(["Calc::existing", "Calc::new_one"])
        assert len(created) == 1
        assert "Calc::new_one" in created

    def test_validate_references(self, neo4j_session):
        from backend.db.neo4j.repositories.verification import VerificationRepository

        _seed_design_node(neo4j_session, "Calc::result")
        repo = VerificationRepository(neo4j_session)
        resolved, unresolved = repo.validate_references(["Calc::result", "Calc::nonexistent"])
        assert "Calc::result" in resolved
        assert "Calc::nonexistent" in unresolved

    def test_augment_skips_invalid_test_artifact_names(self, neo4j_session):
        """Invalid qnames like test_*, result_of_* should be skipped."""
        from backend.db.neo4j.repositories.verification import VerificationRepository

        repo = VerificationRepository(neo4j_session)
        # These should all be skipped, so created list should be empty
        created = repo.augment_missing_design_nodes(["test_perform_addition", "result_of_first_call", "verify_display"])
        assert len(created) == 0

    def test_augment_auto_corrects_dot_separator(self, neo4j_session):
        """Dot separators should be auto-corrected to ::"""
        from backend.db.neo4j.repositories.verification import VerificationRepository

        repo = VerificationRepository(neo4j_session)
        created = repo.augment_missing_design_nodes(["Calc::Engine.last_result"])
        # Should have been corrected to Calc::Engine::last_result
        assert len(created) == 1
        assert created[0] == "Calc::Engine::last_result"
        # Verify the stub exists with corrected name
        result = neo4j_session.run(
            "MATCH (d:Design {qualified_name: $qn}) RETURN d.qualified_name AS qn",
            {"qn": "Calc::Engine::last_result"},
        )
        assert result.single() is not None

    def test_augment_skips_bare_lowercase(self, neo4j_session):
        """Bare lowercase words like 'value' should be skipped."""
        from backend.db.neo4j.repositories.verification import VerificationRepository

        repo = VerificationRepository(neo4j_session)
        created = repo.augment_missing_design_nodes(["value", "5.0"])
        assert len(created) == 0
    def test_augment_missing_design_nodes(self, neo4j_session):
        from backend.db.neo4j.repositories.verification import VerificationRepository

        repo = VerificationRepository(neo4j_session)
        created = repo.augment_missing_design_nodes(["Calc::missing_method", "Calc::missing_attr"])
        assert len(created) == 2
        assert "Calc::missing_method" in created
        assert "Calc::missing_attr" in created
        # Verify the stubs exist in Neo4j
        result = neo4j_session.run(
            "MATCH (d:Design) WHERE d.qualified_name IN $qns AND d.source_type = 'verification' RETURN count(*) AS cnt",
            {"qns": ["Calc::missing_method", "Calc::missing_attr"]},
        )
        assert result.single()["cnt"] == 2

    def test_augment_skips_existing_design_nodes(self, neo4j_session):
        from backend.db.neo4j.repositories.verification import VerificationRepository

        _seed_design_node(neo4j_session, "Calc::existing")
        repo = VerificationRepository(neo4j_session)
        created = repo.augment_missing_design_nodes(["Calc::existing", "Calc::new_one"])
        assert len(created) == 1
        assert "Calc::new_one" in created

    def test_validate_references(self, neo4j_session):
        from backend.db.neo4j.repositories.verification import VerificationRepository

        _seed_design_node(neo4j_session, "Calc::result")
        repo = VerificationRepository(neo4j_session)
        resolved, unresolved = repo.validate_references(["Calc::result", "Calc::nonexistent"])
        assert "Calc::result" in resolved
        assert "Calc::nonexistent" in unresolved

    def test_augment_skips_invalid_test_artifact_names(self, neo4j_session):
        """Invalid qnames like test_*, result_of_* should be skipped."""
        from backend.db.neo4j.repositories.verification import VerificationRepository

        repo = VerificationRepository(neo4j_session)
        # These should all be skipped, so created list should be empty
        created = repo.augment_missing_design_nodes(["test_perform_addition", "result_of_first_call", "verify_display"])
        assert len(created) == 0

    def test_augment_auto_corrects_dot_separator(self, neo4j_session):
        """Dot separators should be auto-corrected to ::"""
        from backend.db.neo4j.repositories.verification import VerificationRepository

        repo = VerificationRepository(neo4j_session)
        created = repo.augment_missing_design_nodes(["Calc::Engine.last_result"])
        # Should have been corrected to Calc::Engine::last_result
        assert len(created) == 1
        assert created[0] == "Calc::Engine::last_result"
        # Verify the stub exists with corrected name
        result = neo4j_session.run(
            "MATCH (d:Design {qualified_name: $qn}) RETURN d.qualified_name AS qn",
            {"qn": "Calc::Engine::last_result"},
        )
        assert result.single() is not None

    def test_augment_skips_bare_lowercase(self, neo4j_session):
        """Bare lowercase words like 'value' should be skipped."""
        from backend.db.neo4j.repositories.verification import VerificationRepository

        repo = VerificationRepository(neo4j_session)
        created = repo.augment_missing_design_nodes(["value", "5.0"])
        assert len(created) == 0
