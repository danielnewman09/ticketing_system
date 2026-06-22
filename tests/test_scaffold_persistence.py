"""Integration tests for scaffold node creation during decomposition persistence.

Requires a running Neo4j instance. Set RUN_NEO4J_INTEGRATION=1 to run.

These tests verify that ``persist_decomposition`` creates real placeholder
CodeGraphNode objects (ClassNode + AttributeNode with ``tags=["scaffold"]``)
from notional references in verification stubs, and wires typed edges
(LEFT_OPERAND, RIGHT_OPERAND, CALLER, CALLEE) from Condition/Action nodes
to those scaffold nodes.

Run::

    RUN_NEO4J_INTEGRATION=1 pytest tests/test_scaffold_persistence.py -v -s
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from backend_migrated.models.verification import get_typed_edge_targets
from backend_migrated.requirements.persistence import persist_decomposition

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_NEO4J_INTEGRATION") != "1",
    reason="Set RUN_NEO4J_INTEGRATION=1 to run Neo4j integration tests",
)

# Directory for artifact output (gitignored)
DATA_DIR = Path(__file__).resolve().parent / "agents" / "__data__" / "scaffold_persistence"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def artifact_path():
    """Return a function that builds an output path under __data__/scaffold_persistence/.

    Mirrors the ``artifact_path`` fixture in ``tests/agents/conftest.py``.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    def _artifact_path(filename: str) -> Path:
        dest = DATA_DIR / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        return dest

    return _artifact_path


@pytest.fixture(autouse=True, scope="module")
def setup_neo4j():
    """Ensure neomodel is connected before tests run."""
    from backend_migrated.connection import ensure_connection
    ensure_connection()
    yield


@pytest.fixture()
def clean_neo4j():
    """Clean up all relevant nodes before and after each test."""
    from neomodel import db

    # Clean up before
    with db.driver.session() as session:
        # Delete verification subtrees
        session.run("MATCH (n:VerificationMethod) DETACH DELETE n")
        session.run("MATCH (n:Condition) DETACH DELETE n")
        session.run("MATCH (n:Action) DETACH DELETE n")
        session.run("MATCH (n:LLR) DETACH DELETE n")
        session.run("MATCH (n:HLR) DETACH DELETE n")
        # Delete scaffold nodes (ClassNode/AttributeNode with tags containing 'scaffold')
        session.run("MATCH (n) WHERE 'scaffold' IN n.tags DETACH DELETE n")

    yield

    # Clean up after
    with db.driver.session() as session:
        session.run("MATCH (n:VerificationMethod) DETACH DELETE n")
        session.run("MATCH (n:Condition) DETACH DELETE n")
        session.run("MATCH (n:Action) DETACH DELETE n")
        session.run("MATCH (n:LLR) DETACH DELETE n")
        session.run("MATCH (n:HLR) DETACH DELETE n")
        session.run("MATCH (n) WHERE 'scaffold' IN n.tags DETACH DELETE n")


def _seed_hlr(description: str = "Test HLR"):
    """Create a minimal HLR node and return its refid."""
    from backend_migrated.models.requirement import HLR

    hlr = HLR(description=description, layer="design", tags=["design"])
    hlr.save()
    return hlr


def _make_decomposition():
    """Create a mock DecomposedRequirementSchema with notional references."""
    from backend_migrated.requirements.schemas import DecomposedRequirementSchema

    return DecomposedRequirementSchema(
        description="The Calculation Engine shall expose arithmetic operations",
        nodes=[
            # LLR
            {"type": "LLR", "refid": "llr-1", "description": (
                "The Calculation Engine shall expose an addition "
                "operation that accepts two numeric operands and returns "
                "their sum. The operation rejects non-numeric inputs "
                "with an error signal."
            ), "edges": [
                {"relation_type": "COMPOSES", "target_uid": "vm-1", "target_type": "VerificationMethod"},
                {"relation_type": "COMPOSES", "target_uid": "vm-2", "target_type": "VerificationMethod"},
            ]},
            # VM 1 — happy path
            {"type": "VerificationMethod", "refid": "vm-1", "method": "automated",
             "test_name": "test_add_returns_sum_of_two_valid_operands",
             "description": "Invoke the addition operation with numeric operands and verify the returned result is their sum.",
             "edges": [
                {"relation_type": "COMPOSES", "target_uid": "cond-1", "target_type": "Condition"},
                {"relation_type": "COMPOSES", "target_uid": "act-1", "target_type": "Action"},
                {"relation_type": "COMPOSES", "target_uid": "cond-2", "target_type": "Condition"},
                {"relation_type": "COMPOSES", "target_uid": "cond-3", "target_type": "Condition"},
            ]},
            {"type": "Condition", "refid": "cond-1", "phase": "pre", "operator": "is_true",
             "edges": [
                {"relation_type": "LEFT_OPERAND", "target_uid": "Engine::is_initialized", "target_type": "AttributeNode"},
                {"relation_type": "RIGHT_OPERAND", "target_uid": "literal::true", "target_type": "LiteralNode"},
            ]},
            {"type": "Action", "refid": "act-1",
             "description": "Invoke the add operation with operands 10 and 20",
             "edges": [
                {"relation_type": "CALLEE", "target_uid": "Engine::add", "target_type": "AttributeNode"},
            ]},
            {"type": "Condition", "refid": "cond-2", "phase": "post", "operator": "==",
             "edges": [
                {"relation_type": "LEFT_OPERAND", "target_uid": "Engine::result", "target_type": "AttributeNode"},
                {"relation_type": "RIGHT_OPERAND", "target_uid": "literal::30", "target_type": "LiteralNode"},
            ]},
            {"type": "Condition", "refid": "cond-3", "phase": "post", "operator": "is_true",
             "edges": [
                {"relation_type": "LEFT_OPERAND", "target_uid": "Engine::is_success", "target_type": "AttributeNode"},
                {"relation_type": "RIGHT_OPERAND", "target_uid": "literal::true", "target_type": "LiteralNode"},
            ]},
            # VM 2 — error path
            {"type": "VerificationMethod", "refid": "vm-2", "method": "automated",
             "test_name": "test_add_rejects_non_numeric_operand",
             "description": "Invoke the addition operation with a non-numeric operand and verify the error signal indicates invalid input.",
             "edges": [
                {"relation_type": "COMPOSES", "target_uid": "cond-4", "target_type": "Condition"},
                {"relation_type": "COMPOSES", "target_uid": "act-2", "target_type": "Action"},
                {"relation_type": "COMPOSES", "target_uid": "cond-5", "target_type": "Condition"},
                {"relation_type": "COMPOSES", "target_uid": "cond-6", "target_type": "Condition"},
            ]},
            {"type": "Condition", "refid": "cond-4", "phase": "pre", "operator": "is_true",
             "edges": [
                {"relation_type": "LEFT_OPERAND", "target_uid": "Engine::is_initialized", "target_type": "AttributeNode"},
                {"relation_type": "RIGHT_OPERAND", "target_uid": "literal::true", "target_type": "LiteralNode"},
            ]},
            {"type": "Action", "refid": "act-2",
             "description": "Invoke the add operation with a non-numeric string operand",
             "edges": [
                {"relation_type": "CALLEE", "target_uid": "Engine::add", "target_type": "AttributeNode"},
            ]},
            {"type": "Condition", "refid": "cond-5", "phase": "post", "operator": "==",
             "edges": [
                {"relation_type": "LEFT_OPERAND", "target_uid": "Engine::error_signal", "target_type": "AttributeNode"},
                {"relation_type": "RIGHT_OPERAND", "target_uid": "InvalidInput", "target_type": "AttributeNode"},
            ]},
            {"type": "Condition", "refid": "cond-6", "phase": "post", "operator": "is_false",
             "edges": [
                {"relation_type": "LEFT_OPERAND", "target_uid": "Engine::is_success", "target_type": "AttributeNode"},
                {"relation_type": "RIGHT_OPERAND", "target_uid": "literal::false", "target_type": "LiteralNode"},
            ]},
        ],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestScaffoldNodeCreation:
    """Verify that persist_decomposition creates scaffold CodeGraphNodes."""

    def test_creates_scaffold_class_nodes(self, clean_neo4j):
        """ClassNode scaffold nodes should be created for each bare class reference."""
        from codegraph.models.compound import ClassNode

        hlr = _seed_hlr()
        decomp = _make_decomposition()

        result = persist_decomposition(hlr.refid, decomp)

        # Engine is the only class referenced
        assert result.scaffold_classes >= 1
        engine_node = ClassNode.nodes.get_or_none(qualified_name="Engine")
        assert engine_node is not None
        assert engine_node.kind == "class"
        assert "scaffold" in (engine_node.tags or [])

    def test_creates_scaffold_attribute_nodes(self, clean_neo4j):
        """AttributeNode scaffold nodes should be created for each member reference."""
        from codegraph.models.member import AttributeNode

        hlr = _seed_hlr()
        decomp = _make_decomposition()

        result = persist_decomposition(hlr.refid, decomp)

        # Engine::result, Engine::add, Engine::is_initialized, Engine::is_success,
        # Engine::error_signal — all become AttributeNode
        expected_members = [
            "Engine::result",
            "Engine::add",
            "Engine::is_initialized",
            "Engine::is_success",
            "Engine::error_signal",
        ]
        for qname in expected_members:
            node = AttributeNode.nodes.get_or_none(qualified_name=qname)
            assert node is not None, f"Missing scaffold attribute: {qname}"
            assert node.kind == "attribute"
            assert "scaffold" in (node.tags or [])

    def test_scaffold_attributes_are_composed_by_class(self, clean_neo4j):
        """COMPOSES edges should connect scaffold ClassNode → AttributeNode."""
        from codegraph.models.compound import ClassNode

        hlr = _seed_hlr()
        decomp = _make_decomposition()

        persist_decomposition(hlr.refid, decomp)

        engine = ClassNode.nodes.get_or_none(qualified_name="Engine")
        assert engine is not None

        # Engine should compose its attributes
        composed_attrs = engine.attributes.all()
        attr_qnames = {a.qualified_name for a in composed_attrs}
        assert "Engine::result" in attr_qnames
        assert "Engine::add" in attr_qnames
        assert "Engine::is_initialized" in attr_qnames

    def test_all_members_are_attribute_kind(self, clean_neo4j):
        """Per the 'everything is an attribute' simplification, all members
        (including methods like Engine::add) should be AttributeNode, not MethodNode.
        """
        from codegraph.models.member import MethodNode, AttributeNode

        hlr = _seed_hlr()
        decomp = _make_decomposition()

        persist_decomposition(hlr.refid, decomp)

        # Engine::add is a callee (a method call), but should still be
        # an AttributeNode scaffold, not a MethodNode
        add_as_attr = AttributeNode.nodes.get_or_none(qualified_name="Engine::add")
        assert add_as_attr is not None
        assert add_as_attr.kind == "attribute"

        # No MethodNode scaffolds should be created
        add_as_method = MethodNode.nodes.get_or_none(qualified_name="Engine::add")
        assert add_as_method is None


class TestTypedEdges:
    """Verify that typed edges (LEFT_OPERAND, CALLEE, etc.) are created."""

    def test_left_operand_edges_to_scaffold(self, clean_neo4j):
        """LEFT_OPERAND edges should connect Condition nodes to scaffold nodes."""
        from neomodel import db

        hlr = _seed_hlr()
        decomp = _make_decomposition()

        result = persist_decomposition(hlr.refid, decomp)

        # At least one LEFT_OPERAND edge should exist pointing to a scaffold node
        with db.driver.session() as session:
            records = session.run(
                """
                MATCH (c:Condition)-[:LEFT_OPERAND]->(s)
                WHERE 'scaffold' IN s.tags
                RETURN s.qualified_name AS scaffold_qn
                """
            )
            scaffold_qns = {r["scaffold_qn"] for r in records}

        assert len(scaffold_qns) > 0, "No LEFT_OPERAND edges to scaffold nodes found"
        # Check that Engine::result (postcondition subject) is wired
        assert "Engine::result" in scaffold_qns or "Engine::is_initialized" in scaffold_qns

    def test_callee_edges_to_scaffold(self, clean_neo4j):
        """CALLEE edges should connect Action nodes to scaffold nodes."""
        from neomodel import db

        hlr = _seed_hlr()
        decomp = _make_decomposition()

        persist_decomposition(hlr.refid, decomp)

        with db.driver.session() as session:
            records = session.run(
                """
                MATCH (a:Action)-[:CALLEE]->(s)
                WHERE 'scaffold' IN s.tags
                RETURN s.qualified_name AS scaffold_qn
                """
            )
            scaffold_qns = {r["scaffold_qn"] for r in records}

        assert len(scaffold_qns) > 0, "No CALLEE edges to scaffold nodes found"
        # Engine::add is the callee in both verification stubs
        assert "Engine::add" in scaffold_qns


class TestEdgeReferences:
    """Verify that typed edges (not string properties) carry the references."""

    def test_condition_subject_via_left_operand_edge(self, clean_neo4j):
        """LEFT_OPERAND edges should point to scaffold nodes with ::-separated qnames."""
        from backend_migrated.models.verification import Condition

        hlr = _seed_hlr()
        decomp = _make_decomposition()

        persist_decomposition(hlr.refid, decomp)

        # Load saved conditions and traverse LEFT_OPERAND edges
        conditions = Condition.nodes.all()
        for cond in conditions:
            left_targets = get_typed_edge_targets(cond, "LEFT_OPERAND")
            if left_targets:
                qn = left_targets[0]["qualified_name"]
                # Should use :: separator (scaffold format), not dot
                assert "." not in qn, (
                    f"Scaffold qname should not contain dots: '{qn}'"
                )

    def test_action_callee_via_callee_edge(self, clean_neo4j):
        """CALLEE edges should point to scaffold nodes with ::-separated qnames."""
        from backend_migrated.models.verification import Action

        hlr = _seed_hlr()
        decomp = _make_decomposition()

        persist_decomposition(hlr.refid, decomp)

        actions = Action.nodes.all()
        for action in actions:
            callee_targets = get_typed_edge_targets(action, "CALLEE")
            if callee_targets:
                qn = callee_targets[0]["qualified_name"]
                assert "." not in qn, (
                    f"Scaffold qname should not contain dots: '{qn}'"
                )

    def test_no_qname_string_properties_persisted(self, clean_neo4j):
        """Condition/Action nodes should NOT have subject_qualified_name,
        callee_qualified_name, or expected_value as stored properties —
        the edges are the references.
        """
        from neomodel import db

        hlr = _seed_hlr()
        decomp = _make_decomposition()

        persist_decomposition(hlr.refid, decomp)

        with db.driver.session() as session:
            # Check that saved Condition nodes don't have the property
            records = session.run(
                """
                MATCH (c:Condition)
                WHERE c.subject_qualified_name IS NOT NULL
                   OR c.expected_value IS NOT NULL
                RETURN count(c) AS cnt
                """
            )
            assert records.single()["cnt"] == 0, (
                "Condition nodes should not have subject_qualified_name or expected_value as stored properties"
            )

            # Check that saved Action nodes don't have the property
            records = session.run(
                """
                MATCH (a:Action)
                WHERE a.callee_qualified_name IS NOT NULL
                RETURN count(a) AS cnt
                """
            )
            assert records.single()["cnt"] == 0, (
                "Action nodes should not have callee_qualified_name as a stored property"
            )


class TestExpectedValueEdges:
    """Verify that expected_value is modeled as RIGHT_OPERAND edges to LiteralNodes and scaffold nodes."""

    def test_literal_nodes_created_for_primitive_values(self, clean_neo4j):
        """Primitive expected values (numbers, booleans) should create LiteralNode scaffolds."""
        from neomodel import db

        hlr = _seed_hlr()
        decomp = _make_decomposition()
        persist_decomposition(hlr.refid, decomp)

        with db.driver.session() as session:
            # Should have LiteralNode for "30" (int), "true" (boolean), "false" (boolean)
            records = session.run(
                """
                MATCH (l:LiteralNode)
                WHERE 'scaffold' IN l.tags
                RETURN l.value AS value, l.value_type AS value_type
                ORDER BY l.value
                """
            )
            literals = {r["value"]: r["value_type"] for r in records}

        assert "30" in literals, f"Expected LiteralNode for '30', found: {literals}"
        assert literals["30"] == "int", f"Expected int type for '30', got {literals['30']}"
        assert "true" in literals, f"Expected LiteralNode for 'true'"
        assert literals["true"] == "boolean"
        assert "false" in literals, f"Expected LiteralNode for 'false'"
        assert literals["false"] == "boolean"

    def test_right_operand_edges_to_literals(self, clean_neo4j):
        """RIGHT_OPERAND edges should connect Conditions to LiteralNodes for primitive values."""
        from neomodel import db

        hlr = _seed_hlr()
        decomp = _make_decomposition()
        persist_decomposition(hlr.refid, decomp)

        with db.driver.session() as session:
            records = session.run(
                """
                MATCH (c:Condition)-[:RIGHT_OPERAND]->(l:LiteralNode)
                WHERE 'scaffold' IN l.tags
                RETURN l.value AS value, l.value_type AS value_type
                ORDER BY l.value
                """
            )
            edges = [(r["value"], r["value_type"]) for r in records]

        assert len(edges) > 0, "No RIGHT_OPERAND edges to LiteralNodes found"
        values = {e[0] for e in edges}
        assert "30" in values, f"Expected RIGHT_OPERAND to literal '30', found: {values}"

    def test_enum_value_creates_scaffold_not_literal(self, clean_neo4j):
        """Enum-like expected values (e.g. 'InvalidInput') should create scaffold AttributeNodes, not LiteralNodes."""
        from neomodel import db

        hlr = _seed_hlr()
        decomp = _make_decomposition()
        persist_decomposition(hlr.refid, decomp)

        with db.driver.session() as session:
            # Should have a scaffold AttributeNode for InvalidInput
            records = session.run(
                """
                MATCH (a:AttributeNode)
                WHERE a.qualified_name = 'InvalidInput' AND 'scaffold' IN a.tags
                RETURN count(a) AS cnt
                """
            )
            assert records.single()["cnt"] == 1, (
                "Expected scaffold AttributeNode for 'InvalidInput'"
            )

            # Should have a RIGHT_OPERAND edge from a Condition to this scaffold
            records = session.run(
                """
                MATCH (c:Condition)-[:RIGHT_OPERAND]->(a:AttributeNode)
                WHERE a.qualified_name = 'InvalidInput'
                RETURN count(c) AS cnt
                """
            )
            assert records.single()["cnt"] >= 1, (
                "Expected RIGHT_OPERAND edge to 'InvalidInput' scaffold"
            )

    def test_no_expected_value_string_property_persisted(self, clean_neo4j):
        """Condition nodes should NOT have expected_value as a stored property."""
        from neomodel import db

        hlr = _seed_hlr()
        decomp = _make_decomposition()
        persist_decomposition(hlr.refid, decomp)

        with db.driver.session() as session:
            records = session.run(
                """
                MATCH (c:Condition)
                WHERE c.expected_value IS NOT NULL
                RETURN count(c) AS cnt
                """
            )
            assert records.single()["cnt"] == 0, (
                "Condition nodes should not have expected_value as a stored property"
            )

    def test_literal_nodes_deduplicated(self, clean_neo4j):
        """Re-running decomposition should not duplicate LiteralNodes."""
        from neomodel import db

        hlr = _seed_hlr()
        decomp = _make_decomposition()

        persist_decomposition(hlr.refid, decomp)
        persist_decomposition(hlr.refid, decomp)

        with db.driver.session() as session:
            records = session.run(
                """
                MATCH (l:LiteralNode {value: '30'})
                WHERE 'scaffold' IN l.tags
                RETURN count(l) AS cnt
                """
            )
            assert records.single()["cnt"] == 1, (
                "LiteralNode for '30' should be deduplicated across re-decomposition"
            )


class TestDeduplication:
    """Verify that scaffold nodes are deduplicated across verifications."""

    def test_scaffold_nodes_deduplicated(self, clean_neo4j):
        """Running decomposition twice should not duplicate scaffold nodes."""
        from codegraph.models.compound import ClassNode

        hlr = _seed_hlr()
        decomp = _make_decomposition()

        # First run
        persist_decomposition(hlr.refid, decomp)

        # Second run (re-decomposition — deletes old LLRs but reuses scaffolds)
        persist_decomposition(hlr.refid, decomp)

        # Should still only have one Engine class node
        engine_nodes = ClassNode.nodes.filter(qualified_name="Engine")
        assert len(engine_nodes) == 1, (
            f"Expected 1 Engine ClassNode, found {len(engine_nodes)}"
        )

    def test_scaffold_shared_across_hlrs(self, clean_neo4j):
        """Two HLRs referencing the same notional class should share the scaffold."""
        from codegraph.models.compound import ClassNode

        hlr1 = _seed_hlr("HLR 1")
        hlr2 = _seed_hlr("HLR 2")
        decomp = _make_decomposition()

        persist_decomposition(hlr1.refid, decomp)
        persist_decomposition(hlr2.refid, decomp)

        # Only one Engine class node — shared across both HLRs
        engine_nodes = ClassNode.nodes.filter(qualified_name="Engine")
        assert len(engine_nodes) == 1


# ---------------------------------------------------------------------------
# Artifact snapshot — saves persisted nodes as JSON + MD for sanity checking
# ---------------------------------------------------------------------------


def _query_full_graph(hlr_refid: str) -> dict:
    """Query Neo4j for the full persisted graph rooted at an HLR.

    Returns a dict with:
      - hlr: the HLR node properties
      - llrs: list of LLR dicts with nested verifications
      - scaffold_classes: list of scaffold ClassNode dicts
      - scaffold_attributes: list of scaffold AttributeNode dicts
      - composes_edges: list of {source, target} for scaffold COMPOSES
      - typed_edges: list of {source, edge_type, target} for verification→scaffold
    """
    from neomodel import db

    with db.driver.session() as session:
        # --- HLR ---
        hlr_rec = session.run(
            "MATCH (h:HLR {refid: $refid}) RETURN h",
            {"refid": hlr_refid},
        ).single()
        hlr = dict(hlr_rec["h"]) if hlr_rec else {}

        # --- LLRs with nested verifications, conditions, actions ---
        llr_records = session.run(
            """
            MATCH (h:HLR {refid: $refid})-[:COMPOSES]->(l:LLR)
            RETURN l ORDER BY l.refid
            """,
            {"refid": hlr_refid},
        )
        llrs = []
        for rec in llr_records:
            llr = dict(rec["l"])
            llr_refid = llr.get("refid", "")

            # Verifications for this LLR
            vm_records = session.run(
                """
                MATCH (l:LLR {refid: $refid})-[:COMPOSES]->(vm:VerificationMethod)
                RETURN vm ORDER BY vm.refid
                """,
                {"refid": llr_refid},
            )
            verifications = []
            for vm_rec in vm_records:
                vm = dict(vm_rec["vm"])
                vm_refid = vm.get("refid", "")

                # Conditions
                cond_records = session.run(
                    """
                    MATCH (vm:VerificationMethod {refid: $refid})-[:COMPOSES]->(c:Condition)
                    RETURN c ORDER BY c.phase, c.`order`
                    """,
                    {"refid": vm_refid},
                )
                conditions = []
                for cond_rec in cond_records:
                    cond = dict(cond_rec["c"])
                    # Fetch LEFT_OPERAND / RIGHT_OPERAND targets
                    operand_recs = session.run(
                        """
                        MATCH (c:Condition {refid: $refid})-[r]->(target)
                        WHERE type(r) IN ['LEFT_OPERAND', 'RIGHT_OPERAND']
                        RETURN type(r) AS edge, target.qualified_name AS qname,
                               target.tags AS tags
                        """,
                        {"refid": cond.get("refid", "")},
                    )
                    operands = [
                        {"edge": r["edge"], "target": r["qname"], "tags": list(r["tags"] or [])}
                        for r in operand_recs
                    ]
                    cond["_operand_edges"] = operands
                    # Populate subject/object from edge targets
                    left_targets = [o["target"] for o in operands if o["edge"] == "LEFT_OPERAND"]
                    right_targets = [o["target"] for o in operands if o["edge"] == "RIGHT_OPERAND"]
                    cond["subject_qualified_name"] = left_targets[0] if left_targets else ""
                    cond["object_qualified_name"] = right_targets[0] if right_targets else ""
                    # Populate expected_value from RIGHT_OPERAND target.
                    # For LiteralNode targets, use the value property;
                    # for scaffold nodes, use the qualified_name.
                    if right_targets:
                        # Fetch the actual node to check if it's a LiteralNode
                        right_node_recs = session.run(
                            """
                            MATCH (c:Condition {refid: $refid})-[:RIGHT_OPERAND]->(t)
                            RETURN t.value AS value, t.qualified_name AS qname,
                                   labels(t) AS labels
                            """,
                            {"refid": cond.get("refid", "")},
                        )
                        for r in right_node_recs:
                            if r["value"] is not None:
                                cond["expected_value"] = r["value"]
                            else:
                                cond["expected_value"] = r["qname"]
                            break
                    else:
                        cond["expected_value"] = ""
                    conditions.append(cond)

                # Actions
                act_records = session.run(
                    """
                    MATCH (vm:VerificationMethod {refid: $refid})-[:COMPOSES]->(a:Action)
                    RETURN a ORDER BY a.`order`
                    """,
                    {"refid": vm_refid},
                )
                actions = []
                for act_rec in act_records:
                    act = dict(act_rec["a"])
                    caller_callee_recs = session.run(
                        """
                        MATCH (a:Action {refid: $refid})-[r]->(target)
                        WHERE type(r) IN ['CALLER', 'CALLEE']
                        RETURN type(r) AS edge, target.qualified_name AS qname,
                               target.tags AS tags
                        """,
                        {"refid": act.get("refid", "")},
                    )
                    call_edges = [
                        {"edge": r["edge"], "target": r["qname"], "tags": list(r["tags"] or [])}
                        for r in caller_callee_recs
                    ]
                    act["_call_edges"] = call_edges
                    # Populate callee/caller from edge targets
                    callee_targets = [e["target"] for e in call_edges if e["edge"] == "CALLEE"]
                    caller_targets = [e["target"] for e in call_edges if e["edge"] == "CALLER"]
                    act["callee_qualified_name"] = callee_targets[0] if callee_targets else ""
                    act["caller_qualified_name"] = caller_targets[0] if caller_targets else ""
                    actions.append(act)

                vm["_conditions"] = conditions
                vm["_actions"] = actions
                verifications.append(vm)

            llr["_verifications"] = verifications
            llrs.append(llr)

        # --- Scaffold classes ---
        class_records = session.run(
            """
            MATCH (c:ClassNode) WHERE 'scaffold' IN c.tags
            RETURN c.qualified_name AS qname, c.name AS name, c.kind AS kind,
                   c.tags AS tags
            ORDER BY c.qualified_name
            """
        )
        scaffold_classes = [
            {"qualified_name": r["qname"], "name": r["name"], "kind": r["kind"],
             "tags": list(r["tags"] or [])}
            for r in class_records
        ]

        # --- Scaffold attributes ---
        attr_records = session.run(
            """
            MATCH (a:AttributeNode) WHERE 'scaffold' IN a.tags
            RETURN a.qualified_name AS qname, a.name AS name, a.kind AS kind,
                   a.tags AS tags
            ORDER BY a.qualified_name
            """
        )
        scaffold_attributes = [
            {"qualified_name": r["qname"], "name": r["name"], "kind": r["kind"],
             "tags": list(r["tags"] or [])}
            for r in attr_records
        ]

        # --- Scaffold literal nodes ---
        literal_records = session.run(
            """
            MATCH (l:LiteralNode) WHERE 'scaffold' IN l.tags
            RETURN l.qualified_name AS qname, l.name AS name, l.kind AS kind,
                   l.value AS value, l.value_type AS value_type,
                   l.tags AS tags
            ORDER BY l.qualified_name
            """
        )
        scaffold_literals = [
            {"qualified_name": r["qname"], "name": r["name"], "kind": r["kind"],
             "value": r["value"], "value_type": r["value_type"],
             "tags": list(r["tags"] or [])}
            for r in literal_records
        ]

        # --- Scaffold COMPOSES edges ---
        composes_records = session.run(
            """
            MATCH (c:ClassNode)-[:COMPOSES]->(a:AttributeNode)
            WHERE 'scaffold' IN c.tags AND 'scaffold' IN a.tags
            RETURN c.qualified_name AS source, a.qualified_name AS target
            ORDER BY source, target
            """
        )
        composes_edges = [
            {"source": r["source"], "target": r["target"]}
            for r in composes_records
        ]

        # --- Typed edges (verification → scaffold) ---
        # The source qualified_name is now on the edge TARGET node (via
        # LEFT_OPERAND/CALLEE etc.), not on the Condition/Action node itself.
        typed_records = session.run(
            """
            MATCH (v)-[r]->(s)
            WHERE 'scaffold' IN s.tags
              AND (v:Condition OR v:Action)
              AND type(r) IN ['LEFT_OPERAND', 'RIGHT_OPERAND', 'CALLER', 'CALLEE']
            RETURN type(r) AS edge_type,
                   s.qualified_name AS source,
                   s.qualified_name AS target,
                   labels(s) AS target_labels
            ORDER BY edge_type, target
            """
        )
        typed_edges = [
            {"edge_type": r["edge_type"],
             "source": r["source"] or "",
             "target": r["target"],
             "target_labels": list(r["target_labels"] or [])}
            for r in typed_records
        ]

    return {
        "hlr": hlr,
        "llrs": llrs,
        "scaffold_classes": scaffold_classes,
        "scaffold_attributes": scaffold_attributes,
        "scaffold_literals": scaffold_literals,
        "composes_edges": composes_edges,
        "typed_edges": typed_edges,
    }


def _format_snapshot_md(snapshot: dict, result: dict) -> str:
    """Format the graph snapshot as a human-readable Markdown report."""
    lines = []
    lines.append("# Scaffold Persistence Snapshot")
    lines.append("")
    lines.append(f"HLR: {snapshot["hlr"].get("description", "")}")
    lines.append(f"HLR refid: {snapshot["hlr"].get("refid", "")}")
    lines.append("")
    lines.append("## Persistence Summary")
    lines.append("")
    lines.append(f"| Metric | Count |")
    lines.append(f"|---|---|")
    lines.append(f"| LLRs created | {result["llrs_created"]} |")
    lines.append(f"| Verification methods | {result["verifications_created"]} |")
    lines.append(f"| Conditions | {result["conditions_created"]} |")
    lines.append(f"| Actions | {result["actions_created"]} |")
    lines.append(f"| Scaffold classes | {result["scaffold_classes"]} |")
    lines.append(f"| Scaffold attributes | {result["scaffold_attributes"]} |")
    lines.append(f"| Scaffold literals | {result.get("scaffold_literals", 0)} |")
    lines.append(f"| Typed edges | {result["operand_edges"]} |")
    lines.append("")

    lines.append("## Scaffold Nodes")
    lines.append("")
    lines.append("### ClassNodes")
    lines.append("")
    if snapshot["scaffold_classes"]:
        lines.append("| Qualified Name | Name | Kind | Tags |")
        lines.append("|---|---|---|---|")
        for c in snapshot["scaffold_classes"]:
            lines.append(f"| `{c["qualified_name"]}` | {c["name"]} | {c["kind"]} | {", ".join(c["tags"])} |")
    else:
        lines.append("(none)")
    lines.append("")
    lines.append("### AttributeNodes")
    lines.append("")
    if snapshot.get("scaffold_literals"):
        lines.append("")
        lines.append("### LiteralNodes")
        lines.append("")
        lines.append("| Qualified Name | Value | Type | Tags |")
        lines.append("|---|---|---|---|")
        for l in snapshot["scaffold_literals"]:
            lines.append(f"| `{l["qualified_name"]}` | {l["value"]} | {l["value_type"]} | {", ".join(l["tags"])} |")

    if snapshot["scaffold_attributes"]:
        lines.append("| Qualified Name | Name | Kind | Tags |")
        lines.append("|---|---|---|---|")
        for a in snapshot["scaffold_attributes"]:
            lines.append(f"| `{a["qualified_name"]}` | {a["name"]} | {a["kind"]} | {", ".join(a["tags"])} |")
    else:
        lines.append("(none)")
    lines.append("")

    lines.append("## Scaffold COMPOSES Edges (Class → Attribute)")
    lines.append("")
    if snapshot["composes_edges"]:
        for e in snapshot["composes_edges"]:
            lines.append(f"- `{e["source"]}` → `{e["target"]}`")
    else:
        lines.append("(none)")
    lines.append("")

    lines.append("## Typed Edges (Verification → Scaffold)")
    lines.append("")
    if snapshot["typed_edges"]:
        lines.append("| Edge Type | Source | Target | Target Type |")
        lines.append("|---|---|---|---|")
        for e in snapshot["typed_edges"]:
            target_type = ", ".join(e.get("target_labels", []))
            lines.append(f"| {e["edge_type"]} | `{e["source"]}` | `{e["target"]}` | {target_type} |")
    else:
        lines.append("(none)")
    lines.append("")

    lines.append("## Requirements Tree")
    lines.append("")
    for llr in snapshot["llrs"]:
        lines.append(f"### LLR: {llr.get("description", "")[:80]}")
        lines.append("")
        for vm in llr.get("_verifications", []):
            lines.append(f"**[{vm.get("method", "")}] {vm.get("test_name", "")}**")
            lines.append("")
            lines.append(f"{vm.get("description", "")}")
            lines.append("")

            pre = [c for c in vm.get("_conditions", []) if c.get("phase") == "pre"]
            post = [c for c in vm.get("_conditions", []) if c.get("phase") == "post"]
            acts = vm.get("_actions", [])

            if pre:
                lines.append("**Pre-conditions:**")
                lines.append("")
                for c in pre:
                    sqn = c.get("subject_qualified_name", "")
                    op = c.get("operator", "==")
                    ev = c.get("expected_value", "")
                    edges = c.get("_operand_edges", [])
                    edge_str = ""
                    if edges:
                        edge_str = "  " + ", ".join(
                            f"-{e["edge"]}->`{e["target"]}`" for e in edges if e["edge"] == "LEFT_OPERAND"
                        )
                    lines.append(f"- `{sqn}` {op} `{ev}`{edge_str}")
                lines.append("")

            if acts:
                lines.append("**Actions:**")
                lines.append("")
                for a in acts:
                    desc = a.get("description", "")
                    cqn = a.get("callee_qualified_name", "")
                    edges = a.get("_call_edges", [])
                    edge_str = ""
                    if edges:
                        edge_str = "  " + ", ".join(
                            f"-{e["edge"]}->`{e["target"]}`" for e in edges
                        )
                    lines.append(f"- {desc} → `{cqn}`{edge_str}")
                lines.append("")

            if post:
                lines.append("**Post-conditions:**")
                lines.append("")
                for c in post:
                    sqn = c.get("subject_qualified_name", "")
                    op = c.get("operator", "==")
                    ev = c.get("expected_value", "")
                    edges = c.get("_operand_edges", [])
                    edge_str = ""
                    if edges:
                        edge_str = "  " + ", ".join(
                            f"-{e["edge"]}->`{e["target"]}`" for e in edges if e["edge"] == "LEFT_OPERAND"
                        )
                    lines.append(f"- `{sqn}` {op} `{ev}`{edge_str}")
                lines.append("")

    return "\n".join(lines)


class TestArtifactSnapshot:
    """Persist a decomposition and save the full graph as JSON + MD artifacts.

    Artifacts are written to ``tests/agents/__data__/scaffold_persistence/``
    for manual inspection and sanity checking.
    """

    def test_save_persisted_graph_snapshot(self, clean_neo4j, artifact_path):
        """Persist a mock decomposition and save all Neo4j nodes as artifacts."""

        hlr = _seed_hlr()
        decomp = _make_decomposition()

        result = persist_decomposition(hlr.refid, decomp)

        # Query the full persisted graph
        snapshot = _query_full_graph(hlr.refid)

        # --- Save JSON snapshot ---
        json_path = artifact_path("persisted_graph.json")
        # Convert result dataclass to dict for JSON serialization
        result_dict = {
            "llrs_created": result.llrs_created,
            "verifications_created": result.verifications_created,
            "conditions_created": result.conditions_created,
            "actions_created": result.actions_created,
            "scaffold_classes": result.scaffold_classes,
            "scaffold_attributes": result.scaffold_attributes,
            "operand_edges": result.operand_edges,
        }
        json_payload = {
            "result": result_dict,
            "graph": snapshot,
        }
        json_path.write_text(json.dumps(json_payload, indent=2, default=str))

        # --- Save Markdown report ---
        md_path = artifact_path("persisted_graph.md")
        md_path.write_text(_format_snapshot_md(snapshot, result_dict))

        # --- Sanity assertions (verify the snapshot is non-trivial) ---
        assert len(snapshot["scaffold_classes"]) >= 1, "No scaffold classes in snapshot"
        assert len(snapshot["scaffold_attributes"]) >= 3, "Too few scaffold attributes"
        assert len(snapshot.get("scaffold_literals", [])) >= 2, "Too few scaffold literals"
        assert len(snapshot["composes_edges"]) >= 1, "No COMPOSES edges in snapshot"
        assert len(snapshot["typed_edges"]) >= 1, "No typed edges in snapshot"
        assert len(snapshot["llrs"]) == 1, "Expected exactly 1 LLR"
        assert len(snapshot["llrs"][0]["_verifications"]) == 2, "Expected 2 verification methods"

        print(f"\n  Artifacts saved to: {DATA_DIR}")
        print(f"  - {json_path.name}")
        print(f"  - {md_path.name}")