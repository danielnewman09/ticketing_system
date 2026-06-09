"""Verification node models (:VerificationMethod / :Condition / :Action labels in Neo4j).

Verification methods, conditions, and actions form the verification
subtree beneath LLRs in the COMPOSES hierarchy:

  Component -[:COMPOSES]-> HLR -[:COMPOSES]-> LLR -[:COMPOSES]-> VerificationMethod

Conditions and Actions are further composed by their parent
VerificationMethod (also via COMPOSES), completing the requirements
verification tree.

These models extend ``CodeGraphNode`` so that verification nodes
participate in the ``LayerGraph`` system alongside code-level and
requirement nodes.  A ``LayerGraph(layer='design')`` load naturally
nests VerificationMethods under their LLR, Conditions/Actions under
their VM - all rendered by ``layer_graph_to_cytoscape()``.

Identity
~~~~~~~~
Existing :VerificationMethod/:Condition/:Action nodes use an integer
``id`` property as their primary identifier.  Neomodel does not allow
``id`` as a property name (it conflicts with an internal attribute), so
the neomodel models use ``refid`` - the ``CodeGraphNode`` unique key -
with the convention ``"vm-1"``, ``"cond-1"``, ``"act-1"`` derived from
the legacy integer ``id``.

Legacy properties retained on existing nodes but **not** managed by
neomodel include ``llr_id`` (integer FK on :VerificationMethod,
superseded by the COMPOSES edge from :LLR), ``verification_method_id``
(integer FK on :Condition/:Action, superseded by COMPOSES edge from
:VerificationMethod), and ``high_level_requirement_id`` / etc.

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
)

from codegraph.models.tags import CodeGraphNode


class VerificationMethod(StructuredNode, CodeGraphNode):
    """Verification method node - :VerificationMethod label in Neo4j.

    A VerificationMethod specifies how an LLR is verified (e.g.
    analysis, test, inspection).  It is composed by its parent LLR
    via a ``COMPOSES`` edge - the same edge type used by HLR → LLR,
    Component → HLR, and Namespace → Class throughout the codegraph.

    In a ``LayerGraph``, VerificationMethods appear as children of their
    LLR entry under ``entry.children["VerificationMethod"]``.

    Attributes:
        name: Short label for the verification method (inherited from
            CodeGraphNode).
        refid: Unique identifier with convention ``"vm-{legacy_id}"``
            (inherited from CodeGraphNode).  Serves as the primary
            lookup key, replacing the legacy auto-increment integer ``id``.
        method: Verification method type (e.g. ``"Analysis"``,
            ``"Test"``, ``"Inspection"``).
        test_name: Optional test identifier or function name.
        description: Human-readable description of the verification.
        layer: Provenance layer - ``"design"`` or ``"as-built"``.
        source: Project source, inherited from CodeGraphNode.

    Legacy properties on existing nodes (not managed by neomodel):
        id: Integer identifier (pre-neomodel).  Retained for backward
            compatibility with raw-Cypher queries.
        llr_id: Integer FK to LLR (pre-neomodel).  Superseded by the
            ``llr`` COMPOSES relationship.
    """

    # --- Identity (overrides CodeGraphNode.refid) ----------------------------
    refid = UniqueIdProperty()

    # --- Verification method properties ------------------------------------------
    method = StringProperty(required=True,
        help_text="Verification method type - 'Analysis', 'Test', 'Inspection', etc.")
    test_name = StringProperty(default="",
        help_text="Optional test identifier or function name.")
    description = StringProperty(default="",
        help_text="Human-readable description of the verification.")

    # --- Layer & provenance (same mechanism as CompoundNode/Member/Namespace) --------
    layer = StringProperty(default="design",
        help_text="Provenance layer - 'design' (speculative) or "
                  "'as-built' (implemented/verified).")

    # --- Relationships -----------------------------------------------------------
    #
    #  • COMPOSES (incoming) - LLR → VerificationMethod
    #    The parent low-level requirement.  An LLR composes its verification
    #    methods, mirroring the pattern where an HLR composes its LLRs.
    #    In a LayerGraph, VMs appear as children of their LLR entry.
    #    Example: LLR("Validate inputs")-[:COMPOSES]->VerificationMethod("Unit test")
    #
    #  • COMPOSES (outgoing) - VerificationMethod → Condition
    #    Verification methods compose their pre/post-conditions.
    #    Example: VM("Unit test")-[:COMPOSES]->Condition("Input > 0")
    #
    #  • COMPOSES (outgoing) - VerificationMethod → Action
    #    Verification methods compose their action steps.
    #    Example: VM("Unit test")-[:COMPOSES]->Action("Call function")
    # --------------------------------------------------------------------------

    llr = RelationshipFrom(
        'backend_migrated.models.requirement.LLR', 'COMPOSES')
    conditions = RelationshipTo(
        'backend_migrated.models.verification.Condition', 'COMPOSES')
    actions = RelationshipTo(
        'backend_migrated.models.verification.Action', 'COMPOSES')

    # --- Serialization contract ---
    _llm_fields: set[str] = {"name", "method", "description", "layer"}


class Condition(StructuredNode, CodeGraphNode):
    """Pre/post-condition node - :Condition label in Neo4j.

    A Condition specifies a pre-condition or post-condition for a
    VerificationMethod.  It is composed by its parent VM via a
    ``COMPOSES`` edge and may reference design-graph nodes via
    ``LEFT_OPERAND`` and ``RIGHT_OPERAND`` edges.

    Attributes:
        name: Short label (inherited from CodeGraphNode).
        refid: Unique identifier with convention ``"cond-{legacy_id}"``
            (inherited from CodeGraphNode).
        phase: ``"pre"`` or ``"post"`` - when this condition is evaluated.
        order: Sort order within the phase (0-based).
        operator: Comparison operator (e.g. ``"=="``, ``">"``, ``"<"``).
        expected_value: Expected value for the comparison.
        subject_qualified_name: Qualified name of the design-graph node
            that is the subject of the assertion (left operand).
        object_qualified_name: Qualified name of the design-graph node
            that is the reference value (right operand).
        description: Human-readable description of the condition.
        layer: Provenance layer.
        source: Project source, inherited from CodeGraphNode.

    Legacy properties on existing nodes (not managed by neomodel):
        id: Integer identifier (pre-neomodel).  Retained for backward
            compatibility with raw-Cypher queries.
        verification_method_id: Integer FK to VM (pre-neomodel).  Superseded
            by the ``verification_method`` COMPOSES relationship.
    """

    # --- Identity (overrides CodeGraphNode.refid) ----------------------------
    refid = UniqueIdProperty()

    # --- Condition properties ----------------------------------------------------
    phase = StringProperty(required=True,
        help_text="Condition phase - 'pre' or 'post'.")
    order = IntegerProperty(default=0,
        help_text="Sort order within the phase (0-based).")
    operator = StringProperty(default="==",
        help_text="Comparison operator (e.g. '==', '>', '<').")
    expected_value = StringProperty(default="",
        help_text="Expected value for the comparison.")
    subject_qualified_name = StringProperty(default="",
        help_text="Qualified name of the design-graph node that is the "
                  "subject (left operand) of the assertion.")
    object_qualified_name = StringProperty(default="",
        help_text="Qualified name of the design-graph node that is the "
                  "reference value (right operand) of the assertion.")
    description = StringProperty(default="",
        help_text="Human-readable description of the condition.")

    # --- Layer & provenance ------------------------------------------------------
    layer = StringProperty(default="design",
        help_text="Provenance layer - 'design' or 'as-built'.")

    # --- Relationships -----------------------------------------------------------
    #
    #  • COMPOSES (incoming) - VerificationMethod → Condition
    #    The parent verification method that composes this condition.
    #
    #  • LEFT_OPERAND (outgoing) - Condition → CompoundNode
    #    The design-graph compound node that is the subject of the assertion.
    #    ``CompoundNode`` covers all compound types (ClassNode, InterfaceNode,
    #    EnumNode, UnionNode, ModuleNode).  The ``subject_qualified_name``
    #    property serves as a fallback when the target node does not yet exist.
    #
    #    NOTE: Edges to NamespaceNode or MemberNode targets are also valid in
    #    Neo4j and traversable via raw Cypher, but neomodel only supports a
    #    single target class per RelationshipTo declaration.
    #
    #  • RIGHT_OPERAND (outgoing) - Condition → CompoundNode
    #    The design-graph compound node that is the reference value.
    #    The ``object_qualified_name`` property serves as a fallback.
    #    Same NamespaceNode/MemberNode caveat as LEFT_OPERAND.
    # --------------------------------------------------------------------------

    verification_method = RelationshipFrom(
        'backend_migrated.models.verification.VerificationMethod', 'COMPOSES')
    left_operand = RelationshipTo(
        'codegraph.models.compound.CompoundNode', 'LEFT_OPERAND')
    right_operand = RelationshipTo(
        'codegraph.models.compound.CompoundNode', 'RIGHT_OPERAND')

    # --- Serialization contract ---
    _llm_fields: set[str] = {
        "name", "phase", "operator", "expected_value",
        "subject_qualified_name", "object_qualified_name", "layer",
    }


class Action(StructuredNode, CodeGraphNode):
    """Action step node - :Action label in Neo4j.

    An Action specifies a step taken during verification (e.g. calling
    a function, setting up state).  It is composed by its parent VM
    via a ``COMPOSES`` edge and may reference design-graph nodes via
    ``CALLER`` and ``CALLEE`` edges.

    Attributes:
        name: Short label (inherited from CodeGraphNode).
        refid: Unique identifier with convention ``"act-{legacy_id}"``
            (inherited from CodeGraphNode).
        order: Sort order within the verification method (0-based).
        description: Human-readable description of the action step.
        caller_qualified_name: Qualified name of the design-graph node
            that performs the action (the caller).
        callee_qualified_name: Qualified name of the design-graph node
            that is invoked (the callee).
        layer: Provenance layer.
        source: Project source, inherited from CodeGraphNode.

    Legacy properties on existing nodes (not managed by neomodel):
        id: Integer identifier (pre-neomodel).  Retained for backward
            compatibility with raw-Cypher queries.
        verification_method_id: Integer FK to VM (pre-neomodel).  Superseded
            by the ``verification_method`` COMPOSES relationship.
    """

    # --- Identity (overrides CodeGraphNode.refid) ----------------------------
    refid = UniqueIdProperty()

    # --- Action properties -------------------------------------------------------
    order = IntegerProperty(default=0,
        help_text="Sort order within the verification method (0-based).")
    description = StringProperty(default="",
        help_text="Human-readable description of the action step.")
    caller_qualified_name = StringProperty(default="",
        help_text="Qualified name of the design-graph node that performs "
                  "the action (the caller).")
    callee_qualified_name = StringProperty(default="",
        help_text="Qualified name of the design-graph node that is "
                  "invoked (the callee).")

    # --- Layer & provenance ------------------------------------------------------
    layer = StringProperty(default="design",
        help_text="Provenance layer - 'design' or 'as-built'.")

    # --- Relationships -----------------------------------------------------------
    #
    #  • COMPOSES (incoming) - VerificationMethod → Action
    #    The parent verification method that composes this action step.
    #
    #  • CALLER (outgoing) — Action → CompoundNode
    #    The design-graph compound node that performs the action.
    #    The ``caller_qualified_name`` property serves as a fallback.
    #    Same NamespaceNode/MemberNode caveat as Condition's LEFT_OPERAND.
    #
    #  • CALLEE (outgoing) — Action → CompoundNode
    #    The design-graph compound node that is invoked by the action.
    #    The ``callee_qualified_name`` property serves as a fallback.
    #    Same NamespaceNode/MemberNode caveat as Condition's LEFT_OPERAND.
    # --------------------------------------------------------------------------

    verification_method = RelationshipFrom(
        'backend_migrated.models.verification.VerificationMethod', 'COMPOSES')
    caller = RelationshipTo(
        'codegraph.models.compound.CompoundNode', 'CALLER')
    callee = RelationshipTo(
        'codegraph.models.compound.CompoundNode', 'CALLEE')

    # --- Serialization contract ---
    _llm_fields: set[str] = {
        "name", "description", "caller_qualified_name",
        "callee_qualified_name", "layer",
    }