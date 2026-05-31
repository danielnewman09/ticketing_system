"""Tests for persist_design with dependency stub nodes.

Phase 2: persist_design uses RequirementRepository for TRACES_TO edges
(replacing the sqlite_id-based stub approach). These tests are Neo4j
integration tests marked with skipif.
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
    from neomodel import db

    session = db.driver.session()
    yield session
    from backend.db.neo4j.repositories.design import DesignRepository
    DesignRepository(session).clear_design_graph()
    session.run("MATCH (n:HLR) DETACH DELETE n")
    session.run("MATCH (n:LLR) DETACH DELETE n")
    session.close()


class TestPersistDesignNeo4j:
    """Integration tests for persist_design against live Neo4j."""

    def test_persist_design_creates_nodes(self, neo4j_session):
        from backend.codebase.schemas import DesignSchema
        from codegraph.models import ClassNode
        from backend.requirements.services.persistence import persist_design

        design = DesignSchema(
            nodes=[
                ClassNode(
                    kind="class",
                    name="Calculator",
                    qualified_name="calc::Calculator",
                    layer="design",
                ),
                ClassNode(
                    kind="class",
                    name="Fl_Button",
                    qualified_name="Fl_Button",
                    layer="dependency",
                ),
            ],
            associations=[
                {"subject": "calc::Calculator", "predicate": "depends_on", "object": "Fl_Button"},
            ],
        )

        result = persist_design(design, neo4j_session)

        assert result.triples_created == 1

        # Verify the design node exists in Neo4j
        record = neo4j_session.run(
            "MATCH (d:Design {qualified_name: $qn}) RETURN d.kind AS kind",
            {"qn": "calc::Calculator"},
        ).single()
        assert record is not None
        assert record["kind"] == "class"

        # Dependency stub should NOT be created as a Design node
        record = neo4j_session.run(
            "MATCH (d:Design {qualified_name: $qn}) RETURN d",
            {"qn": "Fl_Button"},
        ).single()
        assert record is None, "Dependency stub should not be created as Design node"

    def test_persist_design_deduplication(self, neo4j_session):
        from backend.codebase.schemas import DesignSchema
        from codegraph.models import ClassNode
        from backend.requirements.services.persistence import persist_design

        design = DesignSchema(
            nodes=[
                ClassNode(
                    kind="class",
                    name="Calculator",
                    qualified_name="calc::Calculator",
                    layer="design",
                ),
                ClassNode(
                    kind="class",
                    name="Fl_Button",
                    qualified_name="Fl_Button",
                    layer="dependency",
                ),
            ],
            associations=[
                {"subject": "calc::Calculator", "predicate": "depends_on", "object": "Fl_Button"},
                {"subject": "calc::Calculator", "predicate": "aggregates", "object": "Fl_Button"},
            ],
        )

        result = persist_design(design, neo4j_session)

        assert result.triples_created == 2

        # Only one Fl_Button node in Neo4j (should be none, since it's a dep stub)
        count_result = neo4j_session.run(
            "MATCH (d:Design {qualified_name: 'Fl_Button'}) RETURN count(d) AS cnt"
        ).single()
        assert count_result["cnt"] == 0

    def test_persist_design_with_hlr_links(self, neo4j_session):
        """Verify that HLR links create TRACES_TO edges in Neo4j."""
        from backend.codebase.schemas import (
            DesignSchema,
            RequirementTripleLinkSchema,
        )
        from codegraph.models import ClassNode
        from backend.requirements.services.persistence import persist_design
        from backend.db.neo4j.repositories.requirement import RequirementRepository

        # Create HLR node in Neo4j
        req_repo = RequirementRepository(neo4j_session)
        hlr = req_repo.create_hlr(description="The system shall calculate")

        design = DesignSchema(
            nodes=[
                ClassNode(
                    kind="class",
                    name="Calculator",
                    qualified_name="calc::Calculator",
                ),
            ],
            triples=[],
            requirement_links=[
                RequirementTripleLinkSchema(
                    requirement_type="hlr",
                    requirement_id=hlr.id,
                    triple_index=-1,  # No triple to link, just node link
                ),
            ],
        )

        result = persist_design(design, neo4j_session)
        assert result.nodes_created == 1

        # Verify TRACES_TO edge exists
        record = neo4j_session.run(
            "MATCH (h:HLR {id: $hid})-[r:TRACES_TO]->(d:Design {qualified_name: 'calc::Calculator'}) RETURN type(r) AS rel_type",
            {"hid": hlr.id},
        ).single()
        assert record is not None
        assert record["rel_type"] == "TRACES_TO"


class TestPersistDecompositionNeo4j:
    """Integration tests for persist_decomposition with conditions and actions."""

    def test_persist_decomposition_stores_conditions_and_actions(self, neo4j_session):
        """persist_decomposition stores verification method stubs with full
        conditions and actions, not just method/test_name/description."""
        from backend.requirements.schemas import (
            VerificationConditionSchema,
            VerificationActionSchema,
            VerificationSchema,
            LowLevelRequirementSchema,
        )
        from backend.requirements.services.persistence import persist_decomposition
        from backend.db.neo4j.repositories.verification import VerificationRepository
        from backend.db.neo4j.repositories.requirement import RequirementRepository

        llr_data = LowLevelRequirementSchema(
            description="The engine computes addition.",
            verifications=[
                VerificationSchema(
                    method="automated",
                    test_name="test_compute_returns_sum",
                    description="Verify that 2 + 3 returns 5.",
                    preconditions=[
                        VerificationConditionSchema(
                            subject_qualified_name="calc::Engine::state",
                            operator="==",
                            expected_value="initialized",
                            object_qualified_name="",
                        ),
                    ],
                    actions=[
                        VerificationActionSchema(
                            description="Call compute(2, 3, '+')",
                            callee_qualified_name="calc::Engine::compute",
                            caller_qualified_name="TestSuite",
                        ),
                    ],
                    postconditions=[
                        VerificationConditionSchema(
                            subject_qualified_name="calc::Engine::result",
                            operator="==",
                            expected_value="5",
                            object_qualified_name="",
                        ),
                    ],
                ),
            ],
        )

        req_repo = RequirementRepository(neo4j_session)
        hlr = req_repo.create_hlr(description="The system shall compute.")

        result = persist_decomposition(neo4j_session, hlr.id, [llr_data])

        assert result.llrs_created == 1
        assert result.verifications_created == 1
        assert result.conditions_created == 2  # 1 pre + 1 post
        assert result.actions_created == 1

        # Verify data in Neo4j via VerificationRepository
        ver_repo = VerificationRepository(neo4j_session)
        llrs = req_repo.list_llrs(hlr_id=hlr.id)
        assert len(llrs) == 1

        hydrated = ver_repo.get_verifications_for_llr(llrs[0].id)
        assert len(hydrated) == 1
        v = hydrated[0]
        assert v["method"] == "automated"
        assert v["test_name"] == "test_compute_returns_sum"
        assert len(v["preconditions"]) == 1
        assert v["preconditions"][0]["subject_qualified_name"] == "calc::Engine::state"
        assert v["preconditions"][0]["operator"] == "=="
        assert v["preconditions"][0]["expected_value"] == "initialized"
        assert len(v["actions"]) == 1
        assert v["actions"][0]["description"] == "Call compute(2, 3, '+')"
        assert v["actions"][0]["callee_qualified_name"] == "calc::Engine::compute"
        assert len(v["postconditions"]) == 1
        assert v["postconditions"][0]["subject_qualified_name"] == "calc::Engine::result"
        assert v["postconditions"][0]["expected_value"] == "5"

    def test_persist_decomposition_with_no_conditions_or_actions(self, neo4j_session):
        """persist_decomposition handles verification stubs with empty
        conditions and actions gracefully."""
        from backend.requirements.schemas import (
            VerificationSchema,
            LowLevelRequirementSchema,
        )
        from backend.requirements.services.persistence import persist_decomposition
        from backend.db.neo4j.repositories.verification import VerificationRepository
        from backend.db.neo4j.repositories.requirement import RequirementRepository

        llr_data = LowLevelRequirementSchema(
            description="The engine returns immediately.",
            verifications=[
                VerificationSchema(
                    method="inspection",
                    test_name="test_immediate_response",
                    description="Verify synchronous response.",
                ),
            ],
        )

        req_repo = RequirementRepository(neo4j_session)
        hlr = req_repo.create_hlr(description="The system shall respond fast.")

        result = persist_decomposition(neo4j_session, hlr.id, [llr_data])

        assert result.llrs_created == 1
        assert result.verifications_created == 1
        assert result.conditions_created == 0
        assert result.actions_created == 0

        ver_repo = VerificationRepository(neo4j_session)
        llrs = req_repo.list_llrs(hlr_id=hlr.id)
        hydrated = ver_repo.get_verifications_for_llr(llrs[0].id)
        assert len(hydrated) == 1
        assert hydrated[0]["preconditions"] == []
        assert hydrated[0]["actions"] == []
        assert hydrated[0]["postconditions"] == []