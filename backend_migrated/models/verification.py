"""Verification node models — re-exported from codegraph's test models.

Provides TestNode, AssertionNode, TestStepNode, and TestFixtureNode
from :mod:`codegraph.models.test`.  These replace the legacy
VerificationMethod / Condition / Action custom models.

Usage::

    from backend_migrated.models.verification import (
        TestNode, AssertionNode, TestStepNode, TestFixtureNode,
    )

Composition hierarchy::

    LLR -[:COMPOSES]-> TestNode -[:COMPOSES]-> AssertionNode / TestStepNode / TestFixtureNode

Edge traversal
~~~~~~~~~~~~~~
Codegraph test models use properly typed neomodel relationship
descriptors (separate per target type).  Instead of raw Cypher, use:

    # AssertionNode operands
    node.left_operand_compound.all()
    node.left_operand_attribute.all()
    node.left_operand_method.all()
    node.left_operand_function.all()
    node.left_operand_literal.all()

    node.right_operand_compound.all()
    node.right_operand_attribute.all()
    node.right_operand_method.all()
    node.right_operand_function.all()
    node.right_operand_literal.all()

    # TestStepNode call edges
    node.callee_method.all()
    node.callee_function.all()
    node.callee_class.all()

    node.caller_method.all()
    node.caller_function.all()
    node.caller_class.all()
    node.caller_test.all()

For convenience when all target types are wanted, use
:func:`get_typed_edge_targets`.

NOTE: Before creating or querying nodes, neomodel's database connection
must be configured (done by importing ``codegraph.config`` or calling
``backend_migrated.connection.ensure_connection()``).
"""

from codegraph.models.test import (
    AssertionNode,
    TestFixtureNode,
    TestNode,
    TestStepNode,
)

from neomodel import RelationshipTo, RelationshipFrom


def get_typed_edge_targets(node, edge_type: str) -> list[dict]:
    """Return all targets of *edge_type* from *node* across all relationship managers.

    Because codegraph test models declare separate RelationshipTo /
    RelationshipFrom descriptors per target type (e.g.
    ``left_operand_compound``, ``left_operand_literal``), a single edge
    type has multiple managers.  This helper iterates all of them and
    returns a combined list of dicts with ``qualified_name``, ``name``,
    ``labels``, and ``value`` keys.

    Args:
        node: A saved neomodel node instance.
        edge_type: Neo4j relationship label (e.g. ``"LEFT_OPERAND"``,
            ``"CALLEE"``).

    Returns:
        A list of dicts, each with ``qualified_name``, ``name``,
        ``labels``, and ``value`` keys.
    """
    targets: list[dict] = []
    seen: set[str] = set()

    for klass in type(node).__mro__:
        for name, val in vars(klass).items():
            if not isinstance(val, (RelationshipTo, RelationshipFrom)):
                continue
            if val.definition["relation_type"] != edge_type:
                continue
            if name in seen:
                continue
            seen.add(name)

            manager = getattr(node, name)
            for connected in manager.all():
                qn = getattr(connected, "qualified_name", "") or ""
                name_val = getattr(connected, "name", "") or ""

                # Labels
                labels: list[str] = []
                if hasattr(connected, "element_id_property"):
                    try:
                        from neomodel import db as _db
                        _, results = _db.cypher_query(
                            "MATCH (n) WHERE elementId(n) = $eid RETURN labels(n)",
                            {"eid": _db.parse_element_id(connected.element_id)},
                        )
                        if results:
                            labels = results[0][0]
                    except Exception:
                        pass

                # LiteralNode value
                value = ""
                if hasattr(connected, "value"):
                    value = connected.value or ""

                targets.append({
                    "qualified_name": qn,
                    "name": name_val,
                    "labels": labels,
                    "value": value,
                })

    return targets


__all__ = [
    "AssertionNode",
    "TestFixtureNode",
    "TestNode",
    "TestStepNode",
    "get_typed_edge_targets",
]
