"""Smoke test: verify that the exported SQLite fixtures load correctly.

Phase 2 note: HLR/LLR data is now in Neo4j, not SQLite. These tests
verify only the SQLite-backed data (ontology, components, verifications).
HLR/LLR queries should be tested against Neo4j in integration tests.
"""

from backend.db.models import (
    Component,
    OntologyNode,
    OntologyTriple,
    Predicate,
)


class TestLoadedFixtures:
    """Validate that the exported fixture data loads into a fresh database."""

    def test_predicates_loaded(self, loaded_session):
        predicates = loaded_session.query(Predicate).all()
        names = {p.name for p in predicates}
        assert "composes" in names
        assert "depends_on" in names
        assert "generalizes" in names
        assert "aggregates" in names

    def test_components_loaded(self, loaded_session):
        comps = loaded_session.query(Component).order_by(Component.id).all()
        assert len(comps) == 2
        assert comps[0].name == "User Interface"
        assert comps[1].name == "Calculation Engine"

    def test_ontology_nodes_loaded(self, loaded_session):
        nodes = loaded_session.query(OntologyNode).order_by(OntologyNode.id).all()
        assert len(nodes) == 47

        # Check dependency stubs
        dep_nodes = [n for n in nodes if n.source_type == "dependency"]
        assert len(dep_nodes) == 4
        dep_qnames = {n.qualified_name for n in dep_nodes}
        assert "Fl_Double_Window" in dep_qnames
        assert "Fl_Output" in dep_qnames
        assert "Fl_Button" in dep_qnames
        assert "Fl_Return_Button" in dep_qnames

    def test_ontology_triples_loaded(self, loaded_session):
        triples = loaded_session.query(OntologyTriple).count()
        assert triples == 47

    def test_dependency_triples(self, loaded_session):
        """Verify dependency cross-layer relationships exist."""
        triples = loaded_session.query(OntologyTriple).all()

        # CalculatorWindow generalizes Fl_Double_Window
        gen = [t for t in triples
               if t.object.qualified_name == "Fl_Double_Window"
               and t.predicate.name == "generalizes"]
        assert len(gen) == 1

        # CalculatorWindow depends_on Fl_Output
        dep = [t for t in triples
               if t.object.qualified_name == "Fl_Output"
               and t.predicate.name == "depends_on"]
        assert len(dep) == 1

        # CalculatorWindow depends_on Fl_Button
        dep2 = [t for t in triples
                 if t.object.qualified_name == "Fl_Button"
                 and t.predicate.name == "depends_on"]
        assert len(dep2) == 1

    def test_verifications_loaded(self, loaded_session):
        """Phase 3: verification data lives in Neo4j, not SQLite.
        Verification tables will be dropped by Alembic migration.
        Verification data is tested against Neo4j in test_verification_repository.py."""
        pass

    def test_intercomponent_flags(self, loaded_session):
        """Dependency stubs should be marked as intercomponent."""
        deps = loaded_session.query(OntologyNode).filter_by(
            source_type="dependency"
        ).all()
        for d in deps:
            assert d.is_intercomponent is True

    def test_calculation_engine_design(self, loaded_session):
        """Verify the calculation engine's design structure."""
        engine = loaded_session.query(OntologyNode).filter_by(
            qualified_name="calculation_engine::CalculatorEngine"
        ).first()
        assert engine is not None
        assert engine.kind == "class"
        assert engine.source_type == "compound"
        assert engine.is_intercomponent is True

        # It should have members
        members = loaded_session.query(OntologyTriple).filter_by(
            subject_id=engine.id, predicate_id=3  # composes
        ).all()
        member_names = {t.object.qualified_name for t in members}
        assert "calculation_engine::CalculatorEngine::add" in member_names
        assert "calculation_engine::CalculatorEngine::precision" in member_names