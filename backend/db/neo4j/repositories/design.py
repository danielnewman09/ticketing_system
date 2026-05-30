"""Design node and triple repository — Neo4j-primary data access.

All design graph CRUD goes through this class. No SQLAlchemy models
are used for design data.

Graph primitives (CompoundNode, MemberNode, NamespaceNode, CodebaseEdge)
are the typed Pydantic models for Neo4j nodes and edges. The repository
dispatches to the correct Neo4j label (:Compound, :Member, :Namespace)
based on the node model type.
"""

from __future__ import annotations

import logging
from typing import Union

from neo4j import Session as Neo4jSession

from backend.db.neo4j.models.constants import COMPOUND_KINDS, MEMBER_KINDS, NAMESPACE_KINDS
from backend.db.neo4j.models.edges import CodebaseEdge
from backend.db.neo4j.models.nodes import CompoundNode, MemberNode, NamespaceNode
from backend.db.neo4j.repositories.constants import PREDICATE_TO_REL_TYPE

# Type alias for any codebase graph node
NodeModel = Union[CompoundNode, MemberNode, NamespaceNode]

log = logging.getLogger(__name__)


def _determine_node_type(kind: str) -> type[CompoundNode | MemberNode | NamespaceNode]:
    """Return the correct model class for a given kind value."""
    if kind in COMPOUND_KINDS:
        return CompoundNode
    elif kind in MEMBER_KINDS:
        return MemberNode
    elif kind in NAMESPACE_KINDS:
        return NamespaceNode
    else:
        # Default to Compound for unknown kinds
        log.debug("Unknown kind %r — defaulting to CompoundNode", kind)
        return CompoundNode


def _determine_label(kind: str) -> str:
    """Return the Neo4j label for a given kind value."""
    if kind in COMPOUND_KINDS:
        return "Compound"
    elif kind in MEMBER_KINDS:
        return "Member"
    elif kind in NAMESPACE_KINDS:
        return "Namespace"
    else:
        return "Compound"


def _props_to_node(props: dict) -> NodeModel | None:
    """Hydrate a node model from a Neo4j property dict.

    Determines the correct model type from the `kind` property.
    Returns None if the props dict cannot be hydrated.
    """
    kind = props.get("kind", "")
    model_cls = _determine_node_type(kind)
    # Filter props to only those the model accepts
    try:
        return model_cls(**props)
    except Exception:
        log.warning("Skipping node %r with invalid props for %s", props.get("qualified_name", "?"), model_cls.__name__)
        return None


class DesignRepository:
    """CRUD operations for codebase graph nodes and their relationships.

    Supports both the new label scheme (:Compound, :Member, :Namespace
    with `layer` property) and the legacy :Design label for backward
    compatibility during migration.

    Each method accepts a Neo4j session and performs Cypher queries
    directly. The caller is responsible for transaction management.
    """

    def __init__(self, session: Neo4jSession) -> None:
        self._session = session

    # -----------------------------------------------------------------------
    # Node operations
    # -----------------------------------------------------------------------

    def merge_node(self, node: NodeModel) -> NodeModel:
        """Create or update a node by qualified_name.

        Dispatches to the appropriate Neo4j label (:Compound, :Member,
        :Namespace) based on the node model type.

        Dependency-layer compounds are written normally with
        layer='dependency'.
        """
        if isinstance(node, CompoundNode):
            label = "Compound"
        elif isinstance(node, MemberNode):
            label = "Member"
        elif isinstance(node, NamespaceNode):
            label = "Namespace"
        else:
            raise ValueError(f"Unknown node type: {type(node)}")

        props = node.model_dump(exclude_none=True)
        # Strip empty-string values that may conflict with Neo4j constraints
        # (e.g. cppreference data creates unique constraints on refid)
        props = {k: v for k, v in props.items() if v != ""}
        # Ensure layer is set explicitly (not buried in $props dict)
        layer = props.pop("layer", "design")

        cypher = f"""
        MERGE (n:{label} {{qualified_name: $qualified_name}})
        SET n += $props, n.layer = $layer
        """
        self._session.run(cypher, {
            "qualified_name": node.qualified_name,
            "props": props,
            "layer": layer,
        })
        return node

    def get_by_qualified_name(self, qualified_name: str) -> NodeModel | None:
        """Fetch a node by qualified_name. Returns None if not found.

        Searches across :Compound, :Member, :Namespace, and :Design
        (legacy) labels.
        """
        result = self._session.run(
            """
            MATCH (n)
            WHERE n.qualified_name = $qn
              AND (n:Compound OR n:Member OR n:Namespace OR n:Design)
            RETURN n
            """,
            {"qn": qualified_name},
        )
        record = result.single()
        if record is None:
            return None
        props = dict(record["n"])
        return _props_to_node(props)

    def find_nodes(
        self,
        kind: str | None = None,
        search: str | None = None,
        component_id: int | None = None,
        layer: str | None = None,
        exclude_layers: list[str] | None = None,
        exclude_source_types: list[str] | None = None,
    ) -> list[NodeModel]:
        """Find nodes matching optional filters.

        Searches across :Compound, :Member, :Namespace, and :Design
        (legacy) labels.

        Args:
            kind: Filter by node kind (e.g. "class", "method").
            search: Text search on name and qualified_name.
            component_id: Filter by component FK.
            layer: Filter by layer (design, as-built, dependency).
            exclude_layers: Exclude nodes with these layer values.
            exclude_source_types: Legacy — maps to exclude_layers
                for backward compatibility.
        """
        conditions = ["(n:Compound OR n:Member OR n:Namespace OR n:Design)"]
        params: dict = {}

        if kind:
            conditions.append("n.kind = $kind")
            params["kind"] = kind
        if component_id is not None:
            conditions.append("n.component_id = $comp_id")
            params["comp_id"] = component_id
        if search:
            conditions.append("(n.name CONTAINS $search OR n.qualified_name CONTAINS $search)")
            params["search"] = search
        if layer is not None:
            conditions.append("n.layer = $layer")
            params["layer"] = layer
        if exclude_layers:
            conditions.append("NOT n.layer IN $exclude_layers")
            params["exclude_layers"] = exclude_layers
        # Legacy: exclude_source_types maps to layer filtering
        if exclude_source_types and not exclude_layers:
            # "dependency" source_type → layer="dependency"
            mapped = [s for s in exclude_source_types if s != "verification"]
            if mapped:
                conditions.append("NOT n.layer IN $exclude_layers_legacy")
                params["exclude_layers_legacy"] = mapped

        where = " AND ".join(conditions)
        cypher = f"MATCH (n) WHERE {where} RETURN n"

        result = self._session.run(cypher, params)
        nodes = []
        for record in result:
            props = dict(record["n"])
            node = _props_to_node(props)
            if node is not None:
                nodes.append(node)
        return nodes

    def delete_node(self, qualified_name: str) -> bool:
        """Delete a node and all its relationships. Returns True if deleted.

        Matches across :Compound, :Member, :Namespace, and :Design labels.
        """
        result = self._session.run(
            """
            MATCH (n)
            WHERE n.qualified_name = $qn
              AND (n:Compound OR n:Member OR n:Namespace OR n:Design)
            DETACH DELETE n
            RETURN count(n) AS cnt
            """,
            {"qn": qualified_name},
        )
        record = result.single()
        return record is not None and record["cnt"] > 0

    # -----------------------------------------------------------------------
    # Triple / relationship operations
    # -----------------------------------------------------------------------

    def merge_triple(
        self,
        subject_qualified_name: str,
        predicate: str,
        object_qualified_name: str,
        mechanism: str = "",
        position: int | None = None,
        name: str = "",
        display_name: str = "",
    ) -> None:
        """MERGE a typed relationship between two codebase nodes.

        Matches subject and object across :Compound, :Member, :Namespace,
        and :Design (legacy) labels.

        Args:
            subject_qualified_name: Qualified name of the source node.
            predicate: Relationship predicate (lowercase, e.g. "aggregates").
            object_qualified_name: Qualified name of the target node.
            mechanism: Optional mechanism property (e.g. "std::vector",
                "std::unique_ptr") for aggregates/references relationships.
            position: For TYPE_ARGUMENT: parameter position (0-based).
            name: For TEMPLATE_PARAM: parameter name (e.g. "T").
            display_name: Alias display name (e.g. "std::string" for
                std::basic_string edge).
        """
        rel_type = PREDICATE_TO_REL_TYPE.get(predicate)
        if not rel_type:
            log.warning("Unknown predicate %r — skipping triple", predicate)
            return

        # Build SET clause for extra properties
        set_props = []
        if mechanism:
            set_props.append("r.mechanism = $mechanism")
        if position is not None:
            set_props.append("r.position = $position")
        if name:
            set_props.append("r.name = $name")
        if display_name:
            set_props.append("r.display_name = $display_name")
        set_clause = "\n            " + "\n            ".join(set_props) if set_props else ""

        cypher = """
        MATCH (s)
        WHERE s.qualified_name = $subj AND (s:Compound OR s:Member OR s:Namespace OR s:Design)
        OPTIONAL MATCH (o_new)
        WHERE o_new.qualified_name = $obj AND (o_new:Compound OR o_new:Member OR o_new:Namespace)
        OPTIONAL MATCH (o_legacy:Design {qualified_name: $obj})
        WITH s, coalesce(o_new, o_legacy) AS target
        WHERE target IS NOT NULL
        MERGE (s)-[r:REL_TYPE]->(target)
        """
        if set_clause:
            cypher += "\n        SET" + set_clause
        cypher = cypher.replace("REL_TYPE", rel_type)

        params = {"subj": subject_qualified_name, "obj": object_qualified_name}
        if mechanism:
            params["mechanism"] = mechanism
        if position is not None:
            params["position"] = position
        if name:
            params["name"] = name
        if display_name:
            params["display_name"] = display_name

        self._session.run(cypher, params)

    # -----------------------------------------------------------------------
    # Bulk operations
    # -----------------------------------------------------------------------

    def clear_design_graph(self) -> bool:
        """Delete all codebase graph nodes and their relationships.

        Removes :Compound, :Member, :Namespace, and legacy :Design nodes.
        """
        try:
            self._session.run("MATCH (n) WHERE n:Compound OR n:Member OR n:Namespace OR n:Design DETACH DELETE n")
            log.info("Cleared design graph from Neo4j")
            return True
        except Exception:
            log.warning("Neo4j clear failed", exc_info=True)
            return False

    def sync_implementation_status(self, qualified_name: str, status: str, source_file: str = "", test_file: str = "") -> None:
        """Update implementation_status on a node.

        Matches across :Compound, :Member, :Namespace, and :Design labels.
        """
        self._session.run(
            """
            MATCH (n)
            WHERE n.qualified_name = $qn
              AND (n:Compound OR n:Member OR n:Namespace OR n:Design)
            SET n.implementation_status = $status,
                n.source_file = $source_file,
                n.test_file = $test_file
            """,
            {
                "qn": qualified_name,
                "status": status,
                "source_file": source_file,
                "test_file": test_file,
            },
        )