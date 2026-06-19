"""Persistence layer for HLR decomposition results.

Creates LLR, VerificationMethod, Condition, and Action nodes in Neo4j
from a :class:`DecomposedRequirementSchema`.  Crucially, this module
also creates **scaffold CodeGraphNode objects** — real (placeholder)
``ClassNode``, ``AttributeNode``, and ``LiteralNode`` instances — from
the notional references and expected values in verification stubs.

Scaffold nodes carry the ``"scaffold"`` tag, distinguishing them from
``"design"`` (agent-produced) and ``"as-built"`` (Doxygen-parsed) nodes.
They provide a rough structural scaffold that the design agent can see
and design against.  When the real design is persisted, the
reconciliation step (future work) will rewire verification edges from
scaffold nodes to the final design nodes.

Notional reference → scaffold node mapping
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The decompose agent produces dot-separated notional references like
``Engine.result`` or ``Engine.add``.  During persistence, each
reference is parsed and converted to a real CodeGraphNode:

  ``Engine``           → ``ClassNode(qualified_name='Engine', tags=['scaffold'])``
  ``Engine.result``    → ``AttributeNode(qualified_name='Engine::result', tags=['scaffold'])``
                         + ``COMPOSES`` edge from ``Engine`` → ``Engine::result``

Per the "everything is an attribute" simplification, *all* member
references (including methods like ``Engine.add``) become
``AttributeNode`` placeholders.  The design agent will later create the
correct node type (``MethodNode`` vs ``AttributeNode``) when it
produces the real design.

Expected value → RIGHT_OPERAND edge
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The ``expected_value`` field on conditions (e.g. ``"30"``, ``"true"``,
``"InvalidOperator"``) is resolved to a target node and connected via
a ``RIGHT_OPERAND`` edge:

  - **Primitive literals** (numbers, booleans, quoted strings) →
    ``LiteralNode`` with ``value`` and ``value_type`` properties.
    Example: ``"30"`` → ``LiteralNode(value="30", value_type="int")``

  - **Enum-like identifiers** (capitalized, no dots, not numeric) →
    scaffold ``AttributeNode``.  Example: ``"InvalidOperator"`` →
    ``AttributeNode(qualified_name="InvalidOperator", tags=["scaffold"])``

  - **Notional references** (contain dots) → scaffold ``AttributeNode``.
    Example: ``"Engine.cached_result"`` →
    ``AttributeNode(qualified_name="Engine::cached_result", tags=["scaffold"])``

The ``expected_value``, ``subject_qualified_name``, ``object_qualified_name``,
``callee_qualified_name``, and ``caller_qualified_name`` fields are all
**transient** attributes on the Condition/Action instances (set by
``from_llm_dict()``).  They are NOT stored as neomodel properties — the
typed edges (``LEFT_OPERAND``, ``RIGHT_OPERAND``, ``CALLER``, ``CALLEE``)
are the references.

Edge creation via raw Cypher
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Typed edges (LEFT_OPERAND, RIGHT_OPERAND, CALLER, CALLEE) are created
using raw Cypher ``MERGE`` queries rather than neomodel's
``.connect()`` method.  This avoids neomodel's ``_check_node`` type
validation, which rejects cross-type connections (e.g. connecting an
``AttributeNode`` to a ``CompoundNode``-targeted relationship).  Raw
Cypher MERGE is idempotent and works regardless of the target node's
label.

Usage::

    from backend_migrated.connection import init_neo4j
    from backend_migrated.requirements.persistence import persist_decomposition

    init_neo4j()
    result = persist_decomposition(
        hlr_refid="2c3463b2…",
        decomposition=decomposed,
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from neomodel import db

from backend_migrated.models.requirement import HLR, LLR
from backend_migrated.models.verification import (
    VerificationMethod,
    Condition,
    Action,
)
from backend_migrated.requirements.schemas import DecomposedRequirementSchema

log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# Result dataclass
# ══════════════════════════════════════════════════════════════════════════


@dataclass
class DecompositionResult:
    """Summary of what persist_decomposition created in Neo4j."""

    llrs_created: int = 0
    verifications_created: int = 0
    conditions_created: int = 0
    actions_created: int = 0
    scaffold_classes: int = 0
    scaffold_attributes: int = 0
    scaffold_edges: int = 0
    operand_edges: int = 0
    # Map of notional_ref → scaffold qualified_name for diagnostics
    scaffold_map: dict[str, str] = field(default_factory=dict)


# ══════════════════════════════════════════════════════════════════════════
# Notional reference → scaffold node
# ══════════════════════════════════════════════════════════════════════════


def _parse_notional_reference(qname: str) -> tuple[str, str]:
    """Parse a notional reference into (class_name, member_name).

    Notional references use dot separators: ``Class.member``.
    Returns ``("Engine", "")`` for a bare class reference, or
    ``("Engine", "result")`` for ``Engine.result``.

    Args:
        qname: A notional reference string (e.g. ``"Engine.result"``).

    Returns:
        A 2-tuple of ``(class_name, member_name)``.  ``member_name`` is
        empty if *qname* is a bare class reference with no dot.
    """
    if "." in qname:
        parts = qname.split(".", 1)
        return parts[0], parts[1]
    return qname, ""


def _notional_to_scaffold_qname(qname: str) -> str:
    """Convert a notional reference to a ``::``-separated scaffold qualified name.

    ``Engine.result`` → ``Engine::result``
    ``Engine`` → ``Engine``
    """
    class_name, member_name = _parse_notional_reference(qname)
    if member_name:
        return f"{class_name}::{member_name}"
    return class_name


# ══════════════════════════════════════════════════════════════════════════
# Expected value classification
# ══════════════════════════════════════════════════════════════════════════


def _classify_expected_value(value: str) -> tuple[str, str]:
    """Classify an expected value string as a primitive literal or a reference.

    Returns a ``(kind, value_type)`` tuple:

    - ``("literal", "int")`` — integer literal (e.g. ``"30"``, ``"-5"``)
    - ``("literal", "float")`` — float literal (e.g. ``"0.0"``, ``"3.14"``)
    - ``("literal", "boolean")`` — boolean literal (``"true"`` / ``"false"``)
    - ``("literal", "string")`` — quoted string literal (e.g. ``'"hello"'``)
    - ``("reference", "enum")`` — enum-like identifier (e.g. ``"InvalidOperator"``)
    - ``("reference", "notional")`` — dot-separated notional reference (e.g. ``"Engine.result"``)

    Heuristics:
    - Tries int() first, then float().
    - ``"true"`` / ``"false"`` (case-insensitive) → boolean.
    - Values starting and ending with quotes → string literal.
    - Values containing ``.`` that aren't purely numeric → notional reference.
    - Capitalized identifiers without dots → enum value reference.
    - Everything else → string literal.

    Args:
        value: The expected_value string from LLM output.

    Returns:
        A ``(kind, value_type)`` tuple.
    """
    value = value.strip()
    if not value:
        return ("literal", "string")

    # Boolean
    if value.lower() in ("true", "false"):
        return ("literal", "boolean")

    # Quoted string
    if len(value) >= 2 and value[0] in ('"', "'") and value[-1] == value[0]:
        return ("literal", "string")

    # Integer
    try:
        int(value)
        return ("literal", "int")
    except ValueError:
        pass

    # Float
    try:
        float(value)
        # Must actually contain a decimal point or exponent to be a float
        # (otherwise int() would have succeeded)
        if "." in value or "e" in value.lower():
            return ("literal", "float")
    except ValueError:
        pass

    # Notional reference (contains dot, not purely numeric)
    if "." in value:
        return ("reference", "notional")

    # Enum-like identifier (starts with uppercase, no dots, not numeric)
    if value[0].isupper() and value.replace("_", "").isalnum():
        return ("reference", "enum")

    # Default: string literal
    return ("literal", "string")


# ══════════════════════════════════════════════════════════════════════════
# Scaffold cache
# ══════════════════════════════════════════════════════════════════════════


class _ScaffoldCache:
    """In-memory cache of scaffold nodes created during a single decomposition.

    Avoids creating duplicate ClassNode/AttributeNode/LiteralNode instances
    when the same reference appears across multiple conditions/actions.
    """

    def __init__(self) -> None:
        # class_name → ClassNode
        self.classes: dict[str, object] = {}
        # scaffold_qname → AttributeNode
        self.attributes: dict[str, object] = {}
        # literal_qname → LiteralNode
        self.literals: dict[str, object] = {}

    def get_or_create_class(self, class_name: str) -> object:
        """Get an existing scaffold ClassNode or create a new one.

        Uses neomodel's ``create_or_update`` with ``merge_by`` on
        ``qualified_name`` so that re-running decomposition on the same
        HLR reuses existing scaffold nodes rather than duplicating.
        """
        from codegraph.models.compound import ClassNode

        if class_name in self.classes:
            return self.classes[class_name]

        nodes = ClassNode.create_or_update(
            {
                "qualified_name": class_name,
                "name": class_name,
                "kind": "class",
                "tags": ["scaffold"],
            },
            merge_by={"keys": ["qualified_name"]},
        )
        node = nodes[0]
        log.debug("Scaffold ClassNode (get or create): %s", class_name)
        self.classes[class_name] = node
        return node

    def get_or_create_attribute(
        self, class_name: str, member_name: str,
    ) -> object:
        """Get an existing scaffold AttributeNode or create a new one.

        Also ensures the parent ClassNode exists and connects it via a
        ``COMPOSES`` edge.
        """
        from codegraph.models.member import AttributeNode

        scaffold_qname = f"{class_name}::{member_name}"

        if scaffold_qname in self.attributes:
            return self.attributes[scaffold_qname]

        # Ensure the parent class exists
        class_node = self.get_or_create_class(class_name)

        nodes = AttributeNode.create_or_update(
            {
                "qualified_name": scaffold_qname,
                "name": member_name,
                "kind": "attribute",
                "tags": ["scaffold"],
            },
            merge_by={"keys": ["qualified_name"]},
        )
        node = nodes[0]
        log.debug("Scaffold AttributeNode (get or create): %s", scaffold_qname)
        # Connect class → attribute via COMPOSES (idempotent — neomodel
        # uses MERGE for connect so duplicate edges are prevented)
        class_node.attributes.connect(node)

        self.attributes[scaffold_qname] = node
        return node

    def get_or_create_literal(self, value: str, value_type: str) -> object:
        """Get an existing scaffold LiteralNode or create a new one.

        LiteralNodes are deduplicated by ``qualified_name``, which is
        ``"literal::<value>"``.
        """
        from codegraph.models.literal import LiteralNode

        qualified_name = f"literal::{value}"

        if qualified_name in self.literals:
            return self.literals[qualified_name]

        nodes = LiteralNode.create_or_update(
            {
                "qualified_name": qualified_name,
                "name": value,
                "kind": "literal",
                "value": value,
                "value_type": value_type,
                "tags": ["scaffold"],
            },
            merge_by={"keys": ["qualified_name"]},
        )
        node = nodes[0]
        log.debug("Scaffold LiteralNode (get or create): %s = %s (%s)",
                  qualified_name, value, value_type)
        self.literals[qualified_name] = node
        return node

    def get_or_create_enum_value(self, name: str) -> object:
        """Get or create a scaffold AttributeNode for an enum-like value.

        Enum values (e.g. ``InvalidOperator``) are modeled as standalone
        scaffold ``AttributeNode`` instances — they don't belong to a
        class (yet).  The design agent will later determine which enum
        they belong to and wire up the proper ``EnumNode`` →
        ``EnumValueNode`` COMPOSES relationship.
        """
        from codegraph.models.member import AttributeNode

        if name in self.attributes:
            return self.attributes[name]

        nodes = AttributeNode.create_or_update(
            {
                "qualified_name": name,
                "name": name,
                "kind": "attribute",
                "tags": ["scaffold"],
            },
            merge_by={"keys": ["qualified_name"]},
        )
        node = nodes[0]
        log.debug("Scaffold enum-value AttributeNode (get or create): %s", name)
        self.attributes[name] = node
        return node

    def resolve(self, notional_qname: str) -> object | None:
        """Resolve a notional reference to a scaffold node (creating it if needed).

        Returns the ClassNode for bare references (``Engine``), or the
        AttributeNode for member references (``Engine.result``).
        Returns ``None`` if *notional_qname* is empty.
        """
        if not notional_qname or not notional_qname.strip():
            return None

        class_name, member_name = _parse_notional_reference(notional_qname)
        if not class_name:
            return None

        if member_name:
            return self.get_or_create_attribute(class_name, member_name)
        return self.get_or_create_class(class_name)

    def resolve_expected_value(self, value: str) -> object | None:
        """Resolve an expected_value string to a scaffold node (creating it if needed).

        Classifies the value as a literal or a reference, then creates
        the appropriate node type:

        - Primitive literal → ``LiteralNode``
        - Enum-like identifier → scaffold ``AttributeNode`` (standalone)
        - Notional reference → scaffold ``AttributeNode`` (with class)

        Returns ``None`` if *value* is empty.
        """
        if not value or not value.strip():
            return None

        kind, value_type = _classify_expected_value(value)

        if kind == "literal":
            return self.get_or_create_literal(value, value_type)
        elif value_type == "enum":
            return self.get_or_create_enum_value(value)
        else:  # notional reference
            return self.resolve(value)


# ══════════════════════════════════════════════════════════════════════════
# Raw Cypher edge creation
# ══════════════════════════════════════════════════════════════════════════


def _create_typed_edge(source, target, edge_type: str) -> bool:
    """Create a typed edge between two saved nodes using raw Cypher MERGE.

    Bypasses neomodel's ``.connect()`` to avoid ``_check_node`` type
    validation issues when the target node's class doesn't match the
    relationship definition's target class (e.g. connecting an
    ``AttributeNode`` to a ``CompoundNode``-targeted relationship, or a
    ``LiteralNode`` to a ``CompoundNode``-targeted relationship).

    Uses ``elementId`` for node matching and ``MERGE`` for idempotent
    edge creation.

    Args:
        source: The source neomodel node instance (must be saved).
        target: The target neomodel node instance (must be saved).
        edge_type: The relationship type (e.g. ``"LEFT_OPERAND"``).

    Returns:
        ``True`` if the edge was created or already existed, ``False``
        on failure.
    """
    try:
        query = (
            f"MATCH (s), (t) "
            f"WHERE elementId(s) = $source_id AND elementId(t) = $target_id "
            f"MERGE (s)-[:{edge_type}]->(t)"
        )
        db.cypher_query(
            query,
            {
                "source_id": db.parse_element_id(source.element_id),
                "target_id": db.parse_element_id(target.element_id),
            },
        )
        return True
    except Exception as exc:
        log.warning("Failed to create %s edge: %s", edge_type, exc)
        return False


# ══════════════════════════════════════════════════════════════════════════
# Persistence
# ══════════════════════════════════════════════════════════════════════════


def persist_decomposition(
    hlr_refid: str,
    decomposition: DecomposedRequirementSchema,
) -> DecompositionResult:
    """Persist an HLR decomposition to Neo4j — LLRs, verifications, and scaffold nodes.

    Creates:
    1. **LLR nodes** under the HLR via ``COMPOSES`` edges.
    2. **VerificationMethod nodes** under each LLR via ``COMPOSES`` edges.
    3. **Condition and Action nodes** under each VM via ``COMPOSES`` edges.
    4. **Scaffold CodeGraphNodes** (``ClassNode``, ``AttributeNode``,
       ``LiteralNode`` with ``tags=["scaffold"]``) from notional references
       and expected values in conditions/actions.
    5. **Typed edges** (``LEFT_OPERAND``, ``RIGHT_OPERAND``, ``CALLER``,
       ``CALLEE``) from Condition/Action nodes to scaffold nodes, created
       via raw Cypher ``MERGE`` for cross-type compatibility.

    The ``expected_value``, ``subject_qualified_name``,
    ``object_qualified_name``, ``callee_qualified_name``, and
    ``caller_qualified_name`` fields are all transient attributes on the
    Condition/Action instances (set by ``from_llm_dict()``).  They are
    NOT stored as neomodel properties — the typed edges are the references.

    If LLRs already exist for this HLR (re-decomposition), they are
    deleted first — including their verification subtrees.  Scaffold
    nodes are *not* deleted because they may be referenced by other HLRs'
    verifications; they are shared and deduplicated by ``qualified_name``.

    Args:
        hlr_refid: The HLR's ``refid`` (hex UUID string).
        decomposition: A validated ``DecomposedRequirementSchema`` from
            the decompose agent.

    Returns:
        A :class:`DecompositionResult` with counts of everything created.

    Raises:
        ValueError: If the HLR is not found.
    """
    result = DecompositionResult()
    scaffold = _ScaffoldCache()

    # --- Load the HLR ---
    hlr = HLR.nodes.get_or_none(refid=hlr_refid)
    if hlr is None:
        raise ValueError(f"HLR with refid '{hlr_refid}' not found")

    # --- Delete existing LLRs (and their verification subtrees) ---
    for old_llr in hlr.llrs.all():
        _delete_llr_subtree(old_llr)

    # --- Persist each LLR ---
    for llr_data in decomposition.low_level_requirements:
        llr = LLR.from_llm_dict({"description": llr_data.description})
        llr.save()
        hlr.llrs.connect(llr)
        result.llrs_created += 1

        # --- Persist verification methods ---
        for v in llr_data.verifications:
            vm, conditions, actions = VerificationMethod.from_llm_dict(v)
            vm.save()
            llr.verification_methods.connect(vm)
            result.verifications_created += 1

            # --- Conditions (pre + post) ---
            for cond in conditions:
                _persist_condition(cond, vm, scaffold, result)

            # --- Actions ---
            for action in actions:
                _persist_action(action, vm, scaffold, result)

    # --- Aggregate scaffold counts ---
    result.scaffold_classes = len(scaffold.classes)
    result.scaffold_attributes = len(scaffold.attributes)
    # Build notional_ref → scaffold_qname map for diagnostics.
    scaffold_map: dict[str, str] = {}
    for class_name in scaffold.classes:
        scaffold_map[class_name] = class_name
    for attr_qname in scaffold.attributes:
        notional = attr_qname.replace("::", ".", 1) if "::" in attr_qname else attr_qname
        scaffold_map[notional] = attr_qname
    for lit_qname in scaffold.literals:
        scaffold_map[lit_qname] = lit_qname
    result.scaffold_map = scaffold_map

    log.info(
        "persist_decomposition: HLR %s — %d LLRs, %d VMs, %d conditions, "
        "%d actions, %d scaffold classes, %d scaffold attributes, %d literals",
        hlr_refid[:8], result.llrs_created, result.verifications_created,
        result.conditions_created, result.actions_created,
        result.scaffold_classes, result.scaffold_attributes,
        len(scaffold.literals),
    )

    return result


# ══════════════════════════════════════════════════════════════════════════
# Internal helpers
# ══════════════════════════════════════════════════════════════════════════


def _delete_llr_subtree(llr: LLR) -> None:
    """Delete an LLR and its entire verification subtree (VMs, conditions, actions).

    Scaffold nodes referenced by conditions/actions are NOT deleted —
    they are shared across HLRs and deduplicated by ``qualified_name``.
    Only the typed edges (LEFT_OPERAND, CALLEE, etc.) are removed when
    the Condition/Action nodes are deleted (via neomodel's DETACH DELETE).
    """
    for vm in llr.verification_methods.all():
        for cond in vm.conditions.all():
            cond.delete()
        for action in vm.actions.all():
            action.delete()
        vm.delete()
    llr.delete()


def _persist_condition(
    cond: Condition,
    vm: VerificationMethod,
    scaffold: _ScaffoldCache,
    result: DecompositionResult,
) -> None:
    """Save a Condition node, create scaffold nodes, and wire typed edges.

    Uses transient attributes (set by from_llm_dict()) to create scaffold
    nodes and typed edges:

    - ``subject_qualified_name`` → ``LEFT_OPERAND`` edge to scaffold node
    - ``object_qualified_name`` → ``RIGHT_OPERAND`` edge to scaffold node
      (takes priority over ``expected_value`` if both are set)
    - ``expected_value`` → ``RIGHT_OPERAND`` edge to LiteralNode or
      scaffold node (only if ``object_qualified_name`` is not set)

    All edges are created via raw Cypher MERGE for cross-type compatibility.
    """
    # --- Resolve subject (left operand) via notional reference ---
    subject_node = None
    if getattr(cond, "subject_qualified_name", ""):
        subject_node = scaffold.resolve(cond.subject_qualified_name)

    # --- Resolve right operand ---
    # object_qualified_name takes priority (explicit notional reference).
    # Otherwise, use expected_value (literal or enum/notional reference).
    right_node = None
    object_qn = getattr(cond, "object_qualified_name", "")
    expected_val = getattr(cond, "expected_value", "")
    if object_qn:
        right_node = scaffold.resolve(object_qn)
    elif expected_val:
        right_node = scaffold.resolve_expected_value(expected_val)

    # --- Save the Condition and connect to VM ---
    cond.save()
    vm.conditions.connect(cond)
    result.conditions_created += 1

    # --- Wire LEFT_OPERAND edge ---
    if subject_node is not None:
        if _create_typed_edge(cond, subject_node, "LEFT_OPERAND"):
            result.operand_edges += 1

    # --- Wire RIGHT_OPERAND edge ---
    if right_node is not None:
        if _create_typed_edge(cond, right_node, "RIGHT_OPERAND"):
            result.operand_edges += 1


def _persist_action(
    action: Action,
    vm: VerificationMethod,
    scaffold: _ScaffoldCache,
    result: DecompositionResult,
) -> None:
    """Save an Action node, create scaffold nodes, and wire typed edges.

    Uses transient ``callee_qualified_name`` and ``caller_qualified_name``
    attributes (set by from_llm_dict()) to create scaffold nodes and
    ``CALLEE`` / ``CALLER`` edges via raw Cypher MERGE.
    """
    # --- Resolve callee via notional reference ---
    callee_node = None
    if getattr(action, "callee_qualified_name", ""):
        callee_node = scaffold.resolve(action.callee_qualified_name)

    # --- Resolve caller via notional reference ---
    caller_node = None
    if getattr(action, "caller_qualified_name", ""):
        caller_node = scaffold.resolve(action.caller_qualified_name)

    # --- Save the Action and connect to VM ---
    action.save()
    vm.actions.connect(action)
    result.actions_created += 1

    # --- Wire CALLEE edge ---
    if callee_node is not None:
        if _create_typed_edge(action, callee_node, "CALLEE"):
            result.operand_edges += 1

    # --- Wire CALLER edge ---
    if caller_node is not None:
        if _create_typed_edge(action, caller_node, "CALLER"):
            result.operand_edges += 1