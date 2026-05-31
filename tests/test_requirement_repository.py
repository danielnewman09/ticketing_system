"""Integration tests for RequirementRepository.

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
    """Provide a Neo4j session and clean up HLR/LLR nodes after each test."""
    from neomodel import db

    session = db.driver.session()
    yield session
    # Cleanup: remove all test data
    session.run("MATCH (n:HLR) DETACH DELETE n")
    session.run("MATCH (n:LLR) DETACH DELETE n")
    session.close()


class TestHLRCRUD:
    def test_create_hlr(self, neo4j_session):
        from backend.db.neo4j.repositories.requirement import RequirementRepository

        repo = RequirementRepository(neo4j_session)
        hlr = repo.create_hlr(description="The system shall perform arithmetic")
        assert hlr.id is not None
        assert hlr.description == "The system shall perform arithmetic"
        assert hlr.component_id is None

    def test_get_hlr(self, neo4j_session):
        from backend.db.neo4j.repositories.requirement import RequirementRepository

        repo = RequirementRepository(neo4j_session)
        created = repo.create_hlr(description="The system shall calculate")
        fetched = repo.get_hlr(created.id)
        assert fetched is not None
        assert fetched.description == "The system shall calculate"

    def test_update_hlr(self, neo4j_session):
        from backend.db.neo4j.repositories.requirement import RequirementRepository

        repo = RequirementRepository(neo4j_session)
        created = repo.create_hlr(description="Original description", component_id=1)
        updated = repo.update_hlr(created.id, description="Updated description", component_id=2)
        assert updated is not None
        assert updated.description == "Updated description"
        assert updated.component_id == 2

    def test_delete_hlr(self, neo4j_session):
        from backend.db.neo4j.repositories.requirement import RequirementRepository

        repo = RequirementRepository(neo4j_session)
        created = repo.create_hlr(description="To be deleted")
        assert repo.delete_hlr(created.id) is True
        assert repo.get_hlr(created.id) is None

    def test_list_hlrs(self, neo4j_session):
        from backend.db.neo4j.repositories.requirement import RequirementRepository

        repo = RequirementRepository(neo4j_session)
        repo.create_hlr(description="HLR A", component_id=1)
        repo.create_hlr(description="HLR B", component_id=1)
        repo.create_hlr(description="HLR C", component_id=2)
        all_hlrs = repo.list_hlrs()
        assert len(all_hlrs) == 3
        filtered = repo.list_hlrs(component_id=1)
        assert len(filtered) == 2


class TestLLRCRUD:
    def test_create_llr(self, neo4j_session):
        from backend.db.neo4j.repositories.requirement import RequirementRepository

        repo = RequirementRepository(neo4j_session)
        hlr = repo.create_hlr(description="Parent HLR")
        llr = repo.create_llr(hlr_id=hlr.id, description="The calculator shall add")
        assert llr.id is not None
        assert llr.description == "The calculator shall add"
        assert llr.high_level_requirement_id == hlr.id

    def test_get_llr(self, neo4j_session):
        from backend.db.neo4j.repositories.requirement import RequirementRepository

        repo = RequirementRepository(neo4j_session)
        hlr = repo.create_hlr(description="HLR")
        created = repo.create_llr(hlr_id=hlr.id, description="LLR desc")
        fetched = repo.get_llr(created.id)
        assert fetched is not None
        assert fetched.description == "LLR desc"

    def test_update_llr(self, neo4j_session):
        from backend.db.neo4j.repositories.requirement import RequirementRepository

        repo = RequirementRepository(neo4j_session)
        hlr = repo.create_hlr(description="HLR")
        created = repo.create_llr(hlr_id=hlr.id, description="Original LLR")
        updated = repo.update_llr(created.id, description="Updated LLR")
        assert updated is not None
        assert updated.description == "Updated LLR"

    def test_delete_llr(self, neo4j_session):
        from backend.db.neo4j.repositories.requirement import RequirementRepository

        repo = RequirementRepository(neo4j_session)
        hlr = repo.create_hlr(description="HLR")
        created = repo.create_llr(hlr_id=hlr.id, description="To delete")
        assert repo.delete_llr(created.id) is True
        assert repo.get_llr(created.id) is None

    def test_list_llrs(self, neo4j_session):
        from backend.db.neo4j.repositories.requirement import RequirementRepository

        repo = RequirementRepository(neo4j_session)
        hlr1 = repo.create_hlr(description="HLR 1")
        hlr2 = repo.create_hlr(description="HLR 2")
        repo.create_llr(hlr_id=hlr1.id, description="LLR 1A")
        repo.create_llr(hlr_id=hlr1.id, description="LLR 1B")
        repo.create_llr(hlr_id=hlr2.id, description="LLR 2A")
        all_llrs = repo.list_llrs()
        assert len(all_llrs) == 3
        filtered = repo.list_llrs(hlr_id=hlr1.id)
        assert len(filtered) == 2

    def test_delete_hlr_cascades_to_llrs(self, neo4j_session):
        """Deleting an HLR should also delete its LLRs and edges."""
        from backend.db.neo4j.repositories.requirement import RequirementRepository

        repo = RequirementRepository(neo4j_session)
        hlr = repo.create_hlr(description="HLR")
        llr = repo.create_llr(hlr_id=hlr.id, description="LLR")
        repo.delete_hlr(hlr.id)
        assert repo.get_llr(llr.id) is None


class TestComponentLinks:
    def test_link_unlink_component(self, neo4j_session):
        from backend.db.neo4j.repositories.requirement import RequirementRepository

        repo = RequirementRepository(neo4j_session)
        hlr = repo.create_hlr(description="HLR")
        llr = repo.create_llr(hlr_id=hlr.id, description="LLR")
        repo.link_component(llr_id=llr.id, component_id=5)
        cids = repo.get_llr_components(llr.id)
        assert 5 in cids

        repo.link_component(llr_id=llr.id, component_id=7)
        cids = repo.get_llr_components(llr.id)
        assert 5 in cids
        assert 7 in cids

        repo.unlink_component(llr_id=llr.id, component_id=5)
        cids = repo.get_llr_components(llr.id)
        assert 5 not in cids
        assert 7 in cids


class TestTracesToDesign:
    def test_trace_and_untrace_design(self, neo4j_session):
        from backend.db.neo4j.repositories.requirement import RequirementRepository
        from backend.db.neo4j.models.nodes import CompoundNode
        from backend.db.neo4j.repositories.design import DesignRepository

        design_repo = DesignRepository(neo4j_session)
        design_repo.merge_node(CompoundNode(qualified_name="calc::Foo", name="Foo", kind="class"))

        req_repo = RequirementRepository(neo4j_session)
        hlr = req_repo.create_hlr(description="The system shall calculate")
        req_repo.trace_to_design(hlr_id=hlr.id, design_qualified_name="calc::Foo")

        # Verify edge exists
        result = neo4j_session.run(
            "MATCH (h:HLR {id: $hid})-[:TRACES_TO]->(d:Design {qualified_name: $qn}) RETURN count(*) AS cnt",
            {"hid": hlr.id, "qn": "calc::Foo"},
        )
        assert result.single()["cnt"] == 1

        # Untrace
        req_repo.untrace_from_design(hlr_id=hlr.id, design_qualified_name="calc::Foo")
        result2 = neo4j_session.run(
            "MATCH (h:HLR {id: $hid})-[:TRACES_TO]->(d:Design {qualified_name: $qn}) RETURN count(*) AS cnt",
            {"hid": hlr.id, "qn": "calc::Foo"},
        )
        assert result2.single()["cnt"] == 0

    def test_llr_trace_to_design(self, neo4j_session):
        from backend.db.neo4j.repositories.requirement import RequirementRepository
        from backend.db.neo4j.models.nodes import CompoundNode
        from backend.db.neo4j.repositories.design import DesignRepository

        design_repo = DesignRepository(neo4j_session)
        design_repo.merge_node(CompoundNode(qualified_name="calc::Bar", name="Bar", kind="class"))

        req_repo = RequirementRepository(neo4j_session)
        hlr = req_repo.create_hlr(description="HLR")
        llr = req_repo.create_llr(hlr_id=hlr.id, description="LLR")
        req_repo.trace_to_design(llr_id=llr.id, design_qualified_name="calc::Bar")

        result = neo4j_session.run(
            "MATCH (l:LLR {id: $lid})-[:TRACES_TO]->(d:Design {qualified_name: $qn}) RETURN count(*) AS cnt",
            {"lid": llr.id, "qn": "calc::Bar"},
        )
        assert result.single()["cnt"] == 1