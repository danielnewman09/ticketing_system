"""Integration test: design pipeline with dependency linkages."""
import pytest
from backend.codebase.schemas import (
    AssociationSchema,
    AttributeSchema,
    ClassSchema,
    MethodSchema,
    OODesignSchema,
)
from backend.ticketing_agent.design.map_to_ontology import map_oo_to_ontology
from backend.requirements.services.persistence import persist_design


@pytest.fixture
def db_session():
    from backend.db import init_db, get_session
    from backend.db.models import OntologyNode, OntologyTriple, Predicate

    init_db()
    with get_session() as session:
        # Clean up for isolation
        session.query(OntologyTriple).delete()
        session.query(OntologyNode).delete()
        Predicate.ensure_defaults(session)
        session.flush()
        yield session


class TestDependencyPipeline:
    def test_full_pipeline_with_dependency(self, db_session):
        """End-to-end: OO design references dependency class →
        triples created → stubs persisted → graph shows linkage."""
        # Step 1: Map OO design with dependency references
        oo = OODesignSchema(
            modules=["ui"],
            classes=[
                ClassSchema(
                    name="CalculatorWindow",
                    module="ui",
                    inherits_from=["Fl_Window"],
                    attributes=[
                        AttributeSchema(
                            name="display",
                            type_name="Fl_Output*",
                            visibility="private",
                            description="The display widget",
                        ),
                        AttributeSchema(
                            name="clearButton",
                            type_name="Fl_Button*",
                            visibility="private",
                            description="The clear button",
                        ),
                    ],
                    methods=[],
                ),
            ],
            associations=[
                AssociationSchema(
                    from_class="CalculatorWindow",
                    to_class="Fl_Button",
                    kind="aggregates",
                    description="Button widgets",
                    requirement_ids=["hlr:1"],
                ),
            ],
        )
        dep_lookup = {
            "Fl_Window": "Fl_Window",
            "Fl_Output": "Fl_Output",
            "Fl_Button": "Fl_Button",
        }

        design = map_oo_to_ontology(
            oo, dependency_lookup=dep_lookup, component_id=1
        )

        # Verify mapper output
        dep_nodes = [n for n in design.nodes if n.source_type == "dependency"]
        dep_qnames = {n.qualified_name for n in dep_nodes}
        assert "Fl_Window" in dep_qnames, f"Fl_Window missing from deps: {dep_qnames}"
        assert "Fl_Button" in dep_qnames, f"Fl_Button missing from deps: {dep_qnames}"

        # Verify triples targeting dependency nodes
        dep_triple_obj_qnames = {t.object_qualified_name for t in design.triples}
        assert "Fl_Window" in dep_triple_obj_qnames  # generalizes
        assert "Fl_Button" in dep_triple_obj_qnames  # aggregates
        assert "Fl_Output" in dep_triple_obj_qnames  # depends_on from type

        # Step 2: Persist
        qname_to_node = {}
        result = persist_design(db_session, design, qname_to_node=qname_to_node)

        assert result.triples_skipped == 0, f"Some triples were skipped: {result}"

        # Verify stubs in DB
        from backend.db.models import OntologyNode as ON
        fl_button = db_session.query(ON).filter_by(
            qualified_name="Fl_Button"
        ).first()
        assert fl_button is not None
        assert fl_button.source_type == "dependency"
        assert fl_button.is_intercomponent is True

        # Verify triple edges exist
        from backend.db.models import OntologyTriple as OT
        all_triples = db_session.query(OT).all()

        # CalculatorWindow generalizes Fl_Window
        gen_triples = [
            t for t in all_triples
            if t.object.qualified_name == "Fl_Window" and t.predicate.name == "generalizes"
        ]
        assert len(gen_triples) == 1

        # CalculatorWindow depends_on Fl_Output
        dep_triples = [
            t for t in all_triples
            if t.object.qualified_name == "Fl_Output" and t.predicate.name == "depends_on"
        ]
        assert len(dep_triples) == 1

        # CalculatorWindow aggregates Fl_Button
        agg_triples = [
            t for t in all_triples
            if t.object.qualified_name == "Fl_Button" and t.predicate.name == "aggregates"
        ]
        assert len(agg_triples) == 1