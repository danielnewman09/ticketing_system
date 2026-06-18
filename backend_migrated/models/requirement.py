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
HLR and LLR override ``CodeGraphNode.refid`` as ``UniqueIdProperty()``,
matching the pattern used by ``FileNode`` in the codegraph.  This makes
``refid`` the canonical unique identifier enforced by Neo4j, and
neomodel auto-generates a UUID on ``.save()``.  The legacy integer
``id`` property on pre-existing nodes is no longer set on newly created
nodes — ``refid`` replaces it for all lookups and serialisation.

A data migration in ``backend_migrated.constraints`` back-fills
``refid`` on existing nodes that were created before the neomodel
switch.

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
    ArrayProperty,
    StructuredNode,
    StringProperty,
    UniqueIdProperty,
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
        refid: Auto-generated unique identifier.  Overrides
            ``CodeGraphNode.refid`` as ``UniqueIdProperty``, matching
            the pattern used by ``FileNode`` in the codegraph.  Serves
            as the primary lookup key.
        name: Short label for the requirement (inherited from CodeGraphNode).
        description: Full requirement text.
        layer: Provenance layer — ``"design"`` (speculative/abstracted)
            or ``"as-built"`` (implemented/verified).  Mirrors the same
            ``layer`` property on Compound/Member/Namespace nodes.
        source: Project source, inherited from CodeGraphNode.
    """

    # --- Identity (overrides CodeGraphNode.refid) ----------------------------
    refid = UniqueIdProperty()

    # --- Requirement text -------------------------------------------------------
    description = StringProperty(required=True,
        help_text="Full requirement text.")

    # --- Layer & provenance (same mechanism as Compound/Member/Namespace) ------
    layer = StringProperty(default="design",
        help_text="Provenance layer — 'design' (speculative) or "
                  "'as-built' (implemented).  Mirrors the same layer "
                  "property on code-level nodes so that requirements "
                  "participate in LayerGraph queries and rendering.")

    # --- Tags & provenance ------------------------------------------------------
    tags = ArrayProperty(StringProperty(), default=list,
        help_text="Provenance tags: 'design', 'as-built'. "
                  "Mirrors the same tags property on code-level nodes "
                  "so that HLRs participate in LayerGraph queries.")

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
    #
    #  • COMPOSES (outgoing) — HLR → CompoundNode
    #    The design-graph nodes (classes, interfaces, enums) that this
    #    requirement composes.  Uses the same COMPOSES edge type as
    #    HLR → LLR and Component → HLR so that the entire
    #    requirement-to-design traceability lives in one composition
    #    hierarchy.
    #    Example: HLR("Handle errors")-[:COMPOSES]->ClassNode("calc::Calculator")
    # --------------------------------------------------------------------------

    llrs = RelationshipTo(
        'backend_migrated.models.requirement.LLR', 'COMPOSES')
    component = RelationshipFrom(
        'backend_migrated.models.component.Component', 'COMPOSES')

    # Design nodes composed by this requirement (COMPOSES, same edge
    # type as HLR → LLR)
    design_compounds = RelationshipTo(
        'codegraph.models.compound.CompoundNode', 'COMPOSES')

    # --- Serialization contract ---
    _llm_fields: set[str] = {"name", "description", "layer", "tags"}

    # Fields included in detail views and agent tool schemas.
    _detail_fields: set[str] = _llm_fields | {"component_id"}

    @classmethod
    def from_llm_dict(cls, data: dict) -> "HLR":
        """Construct an HLR from an LLM tool-call dict.

        The LLM returns HLR data without ``layer``, ``name``, or
        ``tags`` — those are filled with design-time defaults.
        ``refid`` is auto-generated by neomodel on save.

        Args:
            data: Raw HLR dict from the LLM.  Typically just
                ``{"description": "..."}``.

        Returns:
            An HLR instance ready for persistence.
        """
        normalised = dict(data)
        normalised.setdefault("layer", "design")
        normalised.setdefault("name", "")
        normalised.setdefault("tags", ["design"])
        normalised.pop("refid", None)
        normalised.pop("source", None)
        normalised.pop("type", None)
        normalised.pop("edges", None)
        return cls(**normalised)

    def format(self, include_component: bool = False, component_name: str = "") -> str:
        """Format this HLR as a human-readable line for agent prompts.

        Args:
            include_component: Whether to include component name.
            component_name: Component name to include (if provided).

        Returns:
            Formatted string like ``"HLR The system shall..."``.
        """
        comp = f" [Component: {component_name}]" if include_component and component_name else ""
        return f"HLR{comp}: {self.description}"


class LLR(StructuredNode, CodeGraphNode):
    """Low-level requirement node — :LLR label in Neo4j.

    An LLR is a concrete, testable requirement derived from an HLR.
    Connected to its parent HLR via an incoming ``COMPOSES`` edge (the
    same edge type used for Namespace → Class in the codegraph layer).

    Component membership is inferred transitively through the parent
    HLR's ``BELONGS_TO`` relationship — LLR does not carry its own
    ``BELONGS_TO`` edge.

    Attributes:
        refid: Auto-generated unique identifier.  Overrides
            ``CodeGraphNode.refid`` as ``UniqueIdProperty``, matching
            the pattern used by ``FileNode`` in the codegraph.  Serves
            as the primary lookup key.
        name: Short label for the requirement (inherited from CodeGraphNode).
        description: Full requirement text.
        layer: Provenance layer — ``"design"`` or ``"as-built"``.
        source: Project source, inherited from CodeGraphNode.
    """

    # --- Identity (overrides CodeGraphNode.refid) ----------------------------
    refid = UniqueIdProperty()

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
    #
    #  • COMPOSES (outgoing) — LLR → VerificationMethod
    #    An LLR composes its verification methods.  In a LayerGraph,
    #    VerificationMethods appear as children of their LLR entry
    #    under ``entry.children["VerificationMethod"]``.
    #    Example: LLR("Validate inputs")-[:COMPOSES]->VerificationMethod("Unit test")
    # --------------------------------------------------------------------------

    # --- Tags & provenance ------------------------------------------------------
    tags = ArrayProperty(StringProperty(), default=list,
        help_text="Provenance tags: 'design', 'as-built'. "
                  "Mirrors the same tags property on code-level nodes "
                  "so that LLRs participate in LayerGraph queries.")

    hlr = RelationshipFrom(
        'backend_migrated.models.requirement.HLR', 'COMPOSES')
    verification_methods = RelationshipTo(
        'backend_migrated.models.verification.VerificationMethod', 'COMPOSES')

    # Design nodes composed by this LLR (COMPOSES, same edge type)
    design_compounds = RelationshipTo(
        'codegraph.models.compound.CompoundNode', 'COMPOSES')

    # --- Serialization contract ---
    _llm_fields: set[str] = {"name", "description", "layer", "tags"}
    # Fields included in detail views and agent tool schemas.
    _detail_fields: set[str] = _llm_fields | {"hlr_id"}

    @classmethod
    def from_llm_dict(cls, data: dict) -> "LLR":
        """Construct an LLR from an LLM tool-call dict.

        The LLM returns LLR data without ``layer``, ``name``, or
        ``tags`` — those are filled with design-time defaults.
        ``refid`` is auto-generated by neomodel on save.

        Args:
            data: Raw LLR dict from the LLM.  Typically
                ``{"description": "..."}``.

        Returns:
            An LLR instance ready for persistence.
        """
        normalised = dict(data)
        normalised.setdefault("layer", "design")
        normalised.setdefault("name", "")
        normalised.setdefault("tags", ["design"])
        normalised.pop("refid", None)
        normalised.pop("source", None)
        normalised.pop("type", None)
        normalised.pop("edges", None)
        normalised.pop("component_id", None)  # not a neomodel property on LLR
        return cls(**normalised)

    def format(self, hlr_id: str | int = "", verifications: list | None = None) -> str:
        """Format this LLR (and optional verifications) for agent prompts.

        Args:
            hlr_id: Optional HLR identifier for the prefix line.
            verifications: List of ``(VerificationMethod, conditions, actions)``
                tuples as returned by
                :meth:`VerificationMethod.from_llm_dict`.

        Returns:
            Multi-line formatted string.
        """
        prefix = f"LLR {hlr_id}: " if hlr_id else "LLR: "
        lines = [f"{prefix}{self.description}"]
        from backend_migrated.models.verification import VerificationMethod
        if verifications:
            lines.append("  Verifications:")
            for vm, conditions, actions in verifications:
                lines.append(vm.format(conditions=conditions, actions=actions))
        else:
            lines.append("  (No verification stubs)")
        lines.append("")
        return "\n".join(lines)
