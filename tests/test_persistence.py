"""Tests for persist_design with dependency stub nodes.

Phase 1 note: persist_design now writes to Neo4j via DesignRepository.
These tests are Neo4j integration tests marked with skipif.
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
    yield session
    session.run("MATCH (n:Design) DETACH DELETE n")
    session.run("MATCH (n:HLR) DETACH DELETE n")
    session.run("MATCH (n:LLR) DETACH DELETE n")
    session.close()
    driver.close()


class TestPersistDesignNeo4j:
    """Integration tests for persist_design against live Neo4j."""

    def test_persist_design_creates_nodes(self, neo4j_session):
        from backend.codebase.schemas import (
            AssociationSchema,
            ClassSchema,
            DesignSchema,
            OntologyNodeSchema,
            OntologyTripleSchema,
        )
        from backend.requirements.services.persistence import persist_design

        design = DesignSchema(
            nodes=[
                OntologyNodeSchema(
                    kind="class",
                    name="Calculator",
                    qualified_name="calc::Calculator",
                    source_type="compound",
                ),
                OntologyNodeSchema(
                    kind="class",
                    name="Fl_Button",
                    qualified_name="Fl_Button",
                    source_type="dependency",
                    is_intercomponent=True,
                    description="External dependency: Fl_Button",
                ),
            ],
            triples=[
                OntologyTripleSchema(
                    subject_qualified_name="calc::Calculator",
                    predicate="depends_on",
                    object_qualified_name="Fl_Button",
                ),
            ],
        )

        result = persist_design(design, neo4j_session)

        assert result.triples_created == 1
        assert result.triples_skipped == 0

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
        from backend.codebase.schemas import (
            DesignSchema,
            OntologyNodeSchema,
            OntologyTripleSchema,
        )
        from backend.requirements.services.persistence import persist_design

        design = DesignSchema(
            nodes=[
                OntologyNodeSchema(
                    kind="class",
                    name="Calculator",
                    qualified_name="calc::Calculator",
                    source_type="compound",
                ),
                OntologyNodeSchema(
                    kind="class",
                    name="Fl_Button",
                    qualified_name="Fl_Button",
                    source_type="dependency",
                    is_intercomponent=True,
                    description="External dependency: Fl_Button",
                ),
            ],
            triples=[
                OntologyTripleSchema(
                    subject_qualified_name="calc::Calculator",
                    predicate="depends_on",
                    object_qualified_name="Fl_Button",
                ),
                OntologyTripleSchema(
                    subject_qualified_name="calc::Calculator",
                    predicate="aggregates",
                    object_qualified_name="Fl_Button",
                ),
            ],
        )

        result = persist_design(design, neo4j_session)

        assert result.triples_created == 2
        assert result.triples_skipped == 0

        # Only one Fl_Button node in Neo4j (should be none, since it's a dep stub)
        count_result = neo4j_session.run(
            "MATCH (d:Design {qualified_name: 'Fl_Button'}) RETURN count(d) AS cnt"
        ).single()
        assert count_result["cnt"] == 0

    def test_persist_design_with_hlr_links(self, neo4j_session):
        """Verify that HLR links create TRACES_TO edges in Neo4j."""
        from backend.codebase.schemas import (
            DesignSchema,
            OntologyNodeSchema,
            RequirementLinkSchema,
        )
        from backend.requirements.services.persistence import persist_design
        from backend.db.neo4j.repositories.design import DesignRepository

        # Create HLR stub in Neo4j first
        repo = DesignRepository(neo4j_session)
        repo.merge_hlr_stub(sqlite_id=1, description="The system shall calculate")

        design = DesignSchema(
            nodes=[
                OntologyNodeSchema(
                    kind="class",
                    name="Calculator",
                    qualified_name="calc::Calculator",
                ),
            ],
            triples=[],
            requirement_links=[
                RequirementLinkSchema(
                    requirement_type="hlr",
                    requirement_id=1,
                    triple_index=-1,  # No triple to link, just node link
                ),
            ],
        )

        result = persist_design(design, neo4j_session)
        assert result.nodes_created == 1

        # Verify TRACES_TO edge exists
        record = neo4j_session.run(
            "MATCH (h:HLR {sqlite_id: 1})-[r:TRACES_TO]->(d:Design {qualified_name: 'calc::Calculator'}) RETURN type(r) AS rel_type"
        ).single()
        assert record is not None
        assert record["rel_type"] == "TRACES_TO"