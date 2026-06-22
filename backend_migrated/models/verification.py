"""Verification node models (:VerificationMethod / :Condition / :Action labels in Neo4j).

Verification methods, conditions, and actions form the verification
subtree beneath LLRs in the COMPOSES hierarchy:

  Component -[:COMPOSES]-> HLR -[:COMPOSES]-> LLR -[:COMPOSES]-> VerificationMethod

Conditions and Actions are further composed by their parent
VerificationMethod (also via COMPOSES), completing the requirements
verification tree.

These models extend ``CodeGraphNode`` so that verification nodes
participate in the ``LayerGraph`` system alongside code-level and
requirement nodes.  Deserialization is handled by the standard
codegraph mechanisms — ``CodeGraphNode.deserialize()`` and
``LayerGraph.deserialize()`` — not by custom ``from_llm_dict()``
methods.

Edge-based references (standard codegraph pattern)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Conditions and Actions reference design-graph nodes via typed edges
(``LEFT_OPERAND``, ``RIGHT_OPERAND``, ``CALLER``, ``CALLEE``).  These
edges are created via raw Cypher ``MERGE`` (not neomodel's ``.connect()``)
because the relationship definitions target ``CompoundNode`` for
``__label__`` compatibility, but the actual targets may be
``AttributeNode`` or ``LiteralNode`` (which are NOT subclasses of
``CompoundNode``).

For traversal, use ``get_typed_edge_targets()`` which queries via raw
Cypher without label filtering.  Neomodel's relationship managers
(``.left_operand.all()``, etc.) filter by the target class's
``__label__`` and will miss cross-type targets.

Edges are expressed in the standard codegraph JSON format as an
``edges`` array on the node dict, consumed by ``LayerGraph.deserialize()``::

    {
      "type": "Condition",
      "phase": "post",
      "operator": "==",
      "edges": [
        {"relation_type": "LEFT_OPERAND", "target_uid": "Engine::result", "target_type": "AttributeNode"},
        {"relation_type": "RIGHT_OPERAND", "target_uid": "literal::30", "target_type": "LiteralNode"}
      ]
    }

NOTE: Before creating or querying nodes, neomodel's database connection
must be configured (done by importing ``codegraph.config`` or calling
``backend_migrated.connection.ensure_connection()``).
"""

from neomodel import (
    StructuredNode,
    StringProperty,
    IntegerProperty,
    UniqueIdProperty,
    RelationshipTo,
    RelationshipFrom,
    db,
)

from codegraph.models.tags import CodeGraphNode


# ══════════════════════════════════════════════════════════════════════════
# Raw Cypher edge traversal helper
# ══════════════════════════════════════════════════════════════════════════


def get_typed_edge_targets(node, edge_type: str) -> list[dict]:
    """Traverse a typed edge from a saved node via raw Cypher.

    Neomodel's relationship managers filter by the target class's
    ``__label__`` (e.g. ``CompoundNode``), which excludes nodes with
    different labels (``AttributeNode``, ``LiteralNode``).  This helper
    uses raw Cypher to find all targets of a specific edge type without
    label filtering.

    Args:
        node: A saved neomodel node instance (must have ``element_id``).
        edge_type: The Neo4j relationship type (e.g. ``"LEFT_OPERAND"``,
            ``"CALLEE"``).

    Returns:
        A list of dicts, each with ``qualified_name``, ``name``,
        ``labels``, and ``value`` keys.
    """
    try:
        results, _ = db.cypher_query(
            f"MATCH (n)-[:{edge_type}]->(t) "
            f"WHERE elementId(n) = $node_id "
            f"RETURN t.qualified_name, t.name, labels(t), t.value",
            {"node_id": db.parse_element_id(node.element_id)},
        )
        return [
            {"qualified_name": qn, "name": name, "labels": labels, "value": value}
            for qn, name, labels, value in results
        ]
    except Exception:
        return []


# ══════════════════════════════════════════════════════════════════════════
# Models
# ══════════════════════════════════════════════════════════════════════════


class VerificationMethod(StructuredNode, CodeGraphNode):
    """Verification method node - :VerificationMethod label in Neo4j.

    A VerificationMethod specifies how an LLR is verified (e.g.
    analysis, test, inspection).  It is composed by its parent LLR
    via a ``COMPOSES`` edge.

    Attributes:
        method: Verification method type (e.g. ``"automated"``).
        test_name: Optional test identifier or function name.
        description: Human-readable description of the verification.
        layer: Provenance layer - ``"design"`` or ``"as-built"``.
    """

    refid = UniqueIdProperty()

    method = StringProperty(required=True,
        help_text="Verification method type - 'automated', 'review', 'inspection', etc.")
    test_name = StringProperty(default="",
        help_text="Optional test identifier or function name.")
    description = StringProperty(default="",
        help_text="Human-readable description of the verification.")

    layer = StringProperty(default="design",
        help_text="Provenance layer - 'design' or 'as-built'.")

    llr = RelationshipFrom(
        'backend_migrated.models.requirement.LLR', 'COMPOSES')
    conditions = RelationshipTo(
        'backend_migrated.models.verification.Condition', 'COMPOSES')
    actions = RelationshipTo(
        'backend_migrated.models.verification.Action', 'COMPOSES')

    _llm_fields: set[str] = {"name", "method", "description", "layer"}
    _detail_fields: set[str] = _llm_fields | {"test_name"}

    def format(self, conditions: list | None = None,
              actions: list | None = None) -> str:
        """Format this verification method as a human-readable string.

        For saved nodes (loaded from Neo4j), pass the conditions and
        actions explicitly (usually obtained via ``vm.conditions.all()``
        and ``vm.actions.all()``).
        """
        title = f"[{self.method}]"
        if self.test_name:
            title += f" {self.test_name}"
        lines = [f"  {title}"]
        if self.description:
            lines.append(f"    {self.description}")

        pre = [c for c in (conditions or []) if c.phase == "pre"]
        post = [c for c in (conditions or []) if c.phase == "post"]
        act_list = actions or []

        if pre:
            lines.append("    Pre-conditions:")
            for c in pre:
                lines.append(f"      {c.format()}")
        else:
            lines.append("    Pre-conditions: (none)")

        if act_list:
            lines.append("    Actions:")
            for a in act_list:
                lines.append(f"      {a.format()}")
        else:
            lines.append("    Actions: (none)")

        if post:
            lines.append("    Post-conditions:")
            for c in post:
                lines.append(f"      {c.format()}")
        else:
            lines.append("    Post-conditions: (none)")

        return "\n".join(lines)


class Condition(StructuredNode, CodeGraphNode):
    """Pre/post-condition node - :Condition label in Neo4j.

    A Condition specifies a pre-condition or post-condition for a
    VerificationMethod.  It is composed by its parent VM via a
    ``COMPOSES`` edge and references design-graph nodes via
    ``LEFT_OPERAND`` and ``RIGHT_OPERAND`` edges.

    The relationship definitions target ``CompoundNode`` for
    ``__label__`` compatibility with neomodel's traversal, but the
    actual edge targets may be any ``CodeGraphNode`` subclass
    (``AttributeNode``, ``LiteralNode``, ``ClassNode``).  Edges are
    created via raw Cypher and traversed via ``get_typed_edge_targets()``.

    Attributes:
        phase: ``"pre"`` or ``"post"``.
        order: Sort order within the phase (0-based).
        operator: Comparison operator (e.g. ``"=="``, ``">"``).
        description: Human-readable description.
        layer: Provenance layer.
    """

    refid = UniqueIdProperty()

    phase = StringProperty(required=True,
        help_text="Condition phase - 'pre' or 'post'.")
    order = IntegerProperty(default=0,
        help_text="Sort order within the phase (0-based).")
    operator = StringProperty(default="==",
        help_text="Comparison operator (e.g. '==', '>', '<').")
    description = StringProperty(default="",
        help_text="Human-readable description of the condition.")

    layer = StringProperty(default="design",
        help_text="Provenance layer - 'design' or 'as-built'.")

    verification_method = RelationshipFrom(
        'backend_migrated.models.verification.VerificationMethod', 'COMPOSES')
    left_operand = RelationshipTo(
        'codegraph.models.compound.CompoundNode', 'LEFT_OPERAND')
    right_operand = RelationshipTo(
        'codegraph.models.compound.CompoundNode', 'RIGHT_OPERAND')

    _llm_fields: set[str] = {"name", "phase", "operator", "layer"}
    _detail_fields: set[str] = _llm_fields | {"description", "order"}

    def format(self) -> str:
        """Format this condition as a human-readable string.

        Uses ``get_typed_edge_targets()`` to traverse ``LEFT_OPERAND``
        and ``RIGHT_OPERAND`` edges via raw Cypher, bypassing neomodel's
        label-filtered relationship managers.
        """
        left_targets = get_typed_edge_targets(self, "LEFT_OPERAND")
        right_targets = get_typed_edge_targets(self, "RIGHT_OPERAND")
        left = (left_targets[0]["qualified_name"] or left_targets[0]["name"]) if left_targets else ""
        right = (right_targets[0]["qualified_name"] or right_targets[0]["name"]) if right_targets else ""
        parts = [left, self.operator]
        if right:
            parts.append(right)
        return " ".join(parts)


class Action(StructuredNode, CodeGraphNode):
    """Action step node - :Action label in Neo4j.

    An Action specifies a step taken during verification (e.g. calling
    a function, setting up state).  It is composed by its parent VM
    via a ``COMPOSES`` edge and references design-graph nodes via
    ``CALLER`` and ``CALLEE`` edges.

    Edges are created via raw Cypher and traversed via
    ``get_typed_edge_targets()``.

    Attributes:
        order: Sort order within the verification method (0-based).
        description: Human-readable description of the action step.
        layer: Provenance layer.
    """

    refid = UniqueIdProperty()

    order = IntegerProperty(default=0,
        help_text="Sort order within the verification method (0-based).")
    description = StringProperty(default="",
        help_text="Human-readable description of the action step.")

    layer = StringProperty(default="design",
        help_text="Provenance layer - 'design' or 'as-built'.")

    verification_method = RelationshipFrom(
        'backend_migrated.models.verification.VerificationMethod', 'COMPOSES')
    caller = RelationshipTo(
        'codegraph.models.compound.CompoundNode', 'CALLER')
    callee = RelationshipTo(
        'codegraph.models.compound.CompoundNode', 'CALLEE')

    _llm_fields: set[str] = {"name", "description", "layer"}
    _detail_fields: set[str] = _llm_fields | {"order"}

    def format(self) -> str:
        """Format this action as a human-readable string.

        Uses ``get_typed_edge_targets()`` to traverse ``CALLEE`` and
        ``CALLER`` edges via raw Cypher.
        """
        callee_targets = get_typed_edge_targets(self, "CALLEE")
        caller_targets = get_typed_edge_targets(self, "CALLER")
        callee = (callee_targets[0]["qualified_name"] or callee_targets[0]["name"]) if callee_targets else ""
        caller = (caller_targets[0]["qualified_name"] or caller_targets[0]["name"]) if caller_targets else ""

        if caller and callee:
            core = f"{caller} → {callee}"
        elif callee:
            core = callee
        else:
            core = ""
        if self.description and core:
            return f"{core}: {self.description}"
        if self.description:
            return self.description
        return core or "(no action)"