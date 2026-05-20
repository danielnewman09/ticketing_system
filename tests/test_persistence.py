"""Tests for persist_design with dependency stub nodes."""
import pytest
from backend.codebase.schemas import (
    AssociationSchema,
    ClassSchema,
    DesignSchema,
    OntologyNodeSchema,
    OntologyTripleSchema,
)
from backend.requirements.services.persistence import persist_design


@pytest.fixture
def db_session():
    from backend.db import init_db, get_session
    from backend.db.models import OntologyNode, OntologyTriple, Predicate, HighLevelRequirement, LowLevelRequirement

    # Flush existing data for clean test
    init_db()
    with get_session() as session:
        # Delete in dependency order
        session.query(OntologyTriple).delete()
        session.query(OntologyNode).delete()
        session.query(Predicate).filter(Predicate.name != "composes").delete()
        Predicate.ensure_defaults(session)
        session.flush()
        yield session


class TestPersistDependencyStubs:
    def test_dependency_stub_persisted_with_triple(self, db_session):
        """When a dependency stub node and a triple targeting it are in the
        DesignSchema, both should be persisted correctly."""
        from backend.db.models import OntologyNode, OntologyTriple

        nodes = [
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
        ]
        triples = [
            OntologyTripleSchema(
                subject_qualified_name="calc::Calculator",
                predicate="depends_on",
                object_qualified_name="Fl_Button",
            ),
        ]
        design = DesignSchema(nodes=nodes, triples=triples)

        result = persist_design(db_session, design)

        assert result.triples_created == 1
        assert result.triples_skipped == 0

        # The dependency stub should exist in the DB with correct attributes
        dep_node = db_session.query(OntologyNode).filter_by(
            qualified_name="Fl_Button"
        ).first()
        assert dep_node is not None
        assert dep_node.source_type == "dependency"
        assert dep_node.is_intercomponent is True

        # The triple should reference the stub node
        from backend.db.models import Predicate
        dep_pred = db_session.query(Predicate).filter_by(name="depends_on").first()
        assert dep_pred is not None, "depends_on predicate not found in DB"
        triple = db_session.query(OntologyTriple).filter_by(
            predicate_id=dep_pred.id
        ).first()
        assert triple is not None
        assert triple.object_id == dep_node.id

    def test_dependency_stub_deduplication(self, db_session):
        """If multiple triples target the same dependency, only one stub
        node should exist in the DB."""
        from backend.db.models import OntologyNode

        nodes = [
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
        ]
        triples = [
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
        ]
        design = DesignSchema(nodes=nodes, triples=triples)

        result = persist_design(db_session, design)

        assert result.triples_created == 2
        assert result.triples_skipped == 0

        # Only one Fl_Button node in the DB
        count = db_session.query(OntologyNode).filter_by(
            qualified_name="Fl_Button"
        ).count()
        assert count == 1
        fl_button = db_session.query(OntologyNode).filter_by(
            qualified_name="Fl_Button"
        ).first()
        assert fl_button.source_type == "dependency"