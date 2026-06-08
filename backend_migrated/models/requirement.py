"""HLR and LLR requirement node models (:HLR / :LLR labels in Neo4j).

High-level requirements (HLRs) and low-level requirements (LLRs) are the
two primary requirement types in the ticketing system.  Both participate
in the ``COMPOSES`` composition hierarchy used by ``LayerGraph``:

  Component -[:COMPOSES]-> HLR -[:COMPOSES]-> LLR

This mirrors the codegraph pattern where Namespace -[:COMPOSES]->
Class -[:COMPOSES]-> Method, so requirements and code occupy the same
``LayerGraph`` tree.  A ``LayerGraph(layer='design')`` load naturally
includes Components as root entries whose HLR children nest their LLR
children — all rendered by ``layer_graph_to_cytoscape()``.

These models extend ``CodeGraphNode`` to share serialization, registry,
and relationship-introspection infrastructure with the other
project-management node types (Component, Language, Dependency, ProjectMeta).

Identity
~~~~~~~~
Existing HLR/LLR nodes use an integer ``id`` property as their primary
identifier.  Neomodel does not allow ``id`` as a property name (it
conflicts with an internal attribute), so the neomodel models use
``refid`` — the ``CodeGraphNode`` unique key — with the convention
``"hlr-1"`` / ``"llr-5"`` derived from the legacy integer ``id``.
A data migration in ``backend_migrated.constraints`` back-fills ``refid``
on existing nodes.

Legacy properties retained on existing nodes but **not** managed by
neomodel include ``component_id`` (integer FK, superseded by the
``COMPOSES`` relationship from Component), ``dependency_context`` (Neo4j
map, accessed via raw Cypher by the decomposition agent), and
``high_level_requirement_id`` / ``component_ids`` (replaced by
relationship edges).

LayerGraph integration
~~~~~~~~~~~~~~~~~~~~~~
Because HLR/LLR extend ``CodeGraphNode`` and define a ``layer`` property,
they are automatically included when ``LayerGraph.from_neo4j(layer)``
or ``GraphRepository.get_by_layer(layer)`` is called.  In a "design"
layer graph, an HLR whose Component is also in the graph appears as a
child of that Component's ``CompositeEntry``; otherwise the HLR is a
root entry.  The ``COMPOSES`` edges between HLR and LLR create the
nested structure that ``layer_graph_to_cytoscape()`` renders.

NOTE: Before creating or querying nodes, neomodel's database connection
must be configured (done by importing ``codegraph.config`` or calling
``backend_migrated.connection.ensure_connection()``).
"""

from neomodel import (
    StructuredNode,
    StringProperty,
    RelationshipTo,
    RelationshipFrom,
)

from codegraph.models.tags import CodeGraphNode


class HLR(StructuredNode, CodeGraphNode):
    """High-level requirement node — :HLR label in Neo4j.

    An HLR captures a top-level system requirement.  It composes into
    one or more :LLR nodes via ``COMPOSES`` edges and may belong to a
    :Component via ``BELONGS_TO``.

    The ``COMPOSES`` edge is the same relationship type used by
    NamespaceNode → ClassNode → MethodNode in the codegraph layer.
    This means HLRs and LLRs participate in the ``LayerGraph`` nesting
    structure: an HLR is a ``CompositeEntry`` root, and its LLRs are
    nested children — rendered identically to namespace/class/member
    trees by ``layer_graph_to_cytoscape()``.

    Attributes:
        name: Short label for the requirement (inherited from CodeGraphNode).
        refid: Unique identifier with convention ``"hlr-{legacy_id}"``
            (inherited from CodeGraphNode).  Serves as the primary
            lookup key, replacing the legacy auto-increment integer ``id``.
        description: Full requirement text.
        layer: Provenance layer — ``"design"`` (speculative/abstracted)
            or ``"as-built"`` (implemented/verified).  Mirrors the same
            ``layer`` property on Compound/Member/Namespace nodes.
        source: Project source, inherited from CodeGraphNode.

    Legacy properties on existing nodes (not managed by neomodel):
        id: Integer identifier (pre-neomodel).  Retained for backward
            compatibility with raw-Cypher queries in RequirementRepository.
        component_id: Integer FK to Component (pre-neomodel).  Superseded
            by the incoming ``component`` COMPOSES relationship from Component.
        dependency_context: Neo4j map stored by the decomposition agent.
            Accessed via raw Cypher, not modelled as a neomodel property.
    """

    # --- Requirement text -------------------------------------------------------
    description = StringProperty(required=True,
        help_text="Full requirement text.")

    # --- Layer & provenance (same mechanism as Compound/Member/Namespace) ------
    layer = StringProperty(default="design",
        help_text="Provenance layer — 'design' (speculative) or "
                  "'as-built' (implemented).  Mirrors the same layer "
                  "property on code-level nodes so that requirements "
                  "participate in LayerGraph queries and rendering.")

    # --- Relationships -----------------------------------------------------------
    #
    #  • COMPOSES (outgoing) — HLR → LLR
    #    Each HLR composes into one or more low-level requirements.
    #    This is the same COMPOSES edge type used by NamespaceNode →
    #    ClassNode → MethodNode in the codegraph.  In a LayerGraph,
    #    the HLR appears as a CompositeEntry and its LLRs are nested
    #    children under entry.children["LLR"].
    #    Example: HLR("System shall handle errors")-[:COMPOSES]->LLR("Validate input")
    #
    #  • COMPOSES (incoming) — Component → HLR
    #    The project component this requirement belongs to.
    #    A Component composes its HLRs, mirroring the pattern where a
    #    NamespaceNode composes its ClassNodes.  In a LayerGraph, an
    #    HLR that is composed by a Component is not a root entry — it
    #    appears as a child of the Component entry.
    #    Example: Component("calculation_engine")-[:COMPOSES]->HLR("Handle errors")
    # --------------------------------------------------------------------------

    llrs = RelationshipTo(
        'backend_migrated.models.requirement.LLR', 'COMPOSES')
    component = RelationshipFrom(
        'backend_migrated.models.component.Component', 'COMPOSES')

    # --- Serialization contract ---
    _llm_fields: set[str] = {"name", "description", "layer"}


class LLR(StructuredNode, CodeGraphNode):
    """Low-level requirement node — :LLR label in Neo4j.

    An LLR is a concrete, testable requirement derived from an HLR.
    Connected to its parent HLR via an incoming ``COMPOSES`` edge (the
    same edge type used for Namespace → Class in the codegraph layer).

    Component membership is inferred transitively through the parent
    HLR's ``BELONGS_TO`` relationship — LLR does not carry its own
    ``BELONGS_TO`` edge.

    Attributes:
        name: Short label for the requirement (inherited from CodeGraphNode).
        refid: Unique identifier with convention ``"llr-{legacy_id}"``
            (inherited from CodeGraphNode).  Serves as the primary
            lookup key, replacing the legacy auto-increment integer ``id``.
        description: Full requirement text.
        layer: Provenance layer — ``"design"`` or ``"as-built"``.
        source: Project source, inherited from CodeGraphNode.

    Legacy properties on existing nodes (not managed by neomodel):
        id: Integer identifier (pre-neomodel).  Retained for backward
            compatibility with raw-Cypher queries.
        high_level_requirement_id: Integer FK to HLR (pre-neomodel).
            Superseded by the ``hlr`` relationship (COMPOSES edge).
    """

    # --- Requirement text -------------------------------------------------------
    description = StringProperty(required=True,
        help_text="Full requirement text.")

    # --- Layer & provenance (same mechanism as Compound/Member/Namespace) ------
    layer = StringProperty(default="design",
        help_text="Provenance layer — 'design' (speculative) or "
                  "'as-built' (implemented).  Mirrors the same layer "
                  "property on code-level nodes so that requirements "
                  "participate in LayerGraph queries and rendering.")

    # --- Relationships -----------------------------------------------------------
    #
    #  • COMPOSES (incoming) — HLR → LLR
    #    The parent high-level requirement.  Traversed via ``hlr``.
    #    In a LayerGraph, this creates the nested CompositeEntry
    #    structure where LLRs appear as children of their HLR.
    #
    #    This is the same COMPOSES pattern used by Namespace → Class →
    #    Method in the codegraph — the parent "composes" its parts.
    # --------------------------------------------------------------------------

    hlr = RelationshipFrom(
        'backend_migrated.models.requirement.HLR', 'COMPOSES')

    # --- Serialization contract ---
    _llm_fields: set[str] = {"name", "description", "layer"}