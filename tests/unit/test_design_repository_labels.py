"""Unit tests for label matching in DesignRepository."""

from backend.db.neo4j.repositories.design import _label_match


class TestLabelMatch:
    def test_default_alias(self):
        clause = _label_match()
        assert clause.startswith("(n:Compound")
        assert "OR n:Member" in clause
        assert "OR n:Namespace" in clause
        assert clause.endswith(")")

    def test_custom_alias(self):
        clause = _label_match("d")
        assert clause.startswith("(d:Compound")
        assert "OR d:Member" in clause
        assert "OR d:Namespace" in clause
        assert clause.endswith(")")

    def test_no_design_label(self):
        clause = _label_match()
        assert ":Design" not in clause
