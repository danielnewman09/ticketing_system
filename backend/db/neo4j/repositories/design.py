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
from backend.db.neo4j.models.graph import (
    CompoundGraph,
    GraphEdge,
    NamespaceGraph,
    OntologyGraph,
)
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


def _hydrate_graph_edge(rel_type: str, source_qn: str, target_qn: str,
                        mechanism: str = "", position: int | None = None,
                        name: str = "", display_name: str = "") -> GraphEdge:
    """Create a GraphEdge from raw Neo4j relationship fields."""
    return GraphEdge(
        source_qualified_name=source_qn,
        target_qualified_name=target_qn,
        predicate=rel_type,
        mechanism=mechanism or "",
        position=position,
        name=name or "",
        display_name=display_name or "",
    )


_DESIGN_NODE_LABELS: list[str] = ["Compound", "Member", "Namespace"]


def _label_match(alias: str = "n") -> str:
    """Build a Neo4j label-matching clause for codebase graph nodes.

    Example: ``_label_match("d")`` returns
    ``"(d:Compound OR d:Member OR d:Namespace)"``
    """
    return f"({' OR '.join(f'{alias}:{l}' for l in _DESIGN_NODE_LABELS)})"


class DesignRepository:
    """CRUD operations for codebase graph nodes and their relationships.

    Uses the :Compound, :Member, :Namespace labels with ``layer``
    property for filtering design-intent vs. as-built vs. dependency.

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

        Searches across :Compound, :Member, :Namespace
        (legacy) labels.
        """
        label_clause = _label_match("n")
        result = self._session.run(
            f"""
            MATCH (n)
            WHERE n.qualified_name = $qn
              AND {label_clause}
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

        Searches across :Compound, :Member, :Namespace
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
        conditions = [_label_match("n")]
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

    def get_compound_graph(
        self, qualified_name: str, *, layer: str | None = None
    ) -> CompoundGraph | None:
        """Fetch a single compound with members, edges, and nested classes.

        One Cypher query fills the entire CompoundGraph. Returns None
        if the compound is not found.
        """
        layer_condition = "AND c.layer = $layer" if layer is not None else ""
        params: dict = {"qn": qualified_name}
        if layer is not None:
            params["layer"] = layer

        result = self._session.run(
            f"""
            MATCH (c:Compound {{qualified_name: $qn}})
            {layer_condition}
            OPTIONAL MATCH (c)-[:COMPOSES]->(m:Member)
            OPTIONAL MATCH (c)-[r_out]->(tgt)
              WHERE type(r_out) <> 'COMPOSES'
                AND (tgt:Compound OR tgt:Namespace)
                AND tgt.layer = $layer
            OPTIONAL MATCH (src)-[r_in]->(c)
              WHERE NOT src:Member
            OPTIONAL MATCH (c)-[:COMPOSES]->(nested:Compound)
            RETURN c,
                   collect(DISTINCT m) AS members,
                   collect(DISTINCT {{rel: type(r_out),
                       source_qn: c.qualified_name,
                       target_qn: tgt.qualified_name}}) AS outs,
                   collect(DISTINCT {{rel: type(r_in),
                       source_qn: src.qualified_name,
                       target_qn: c.qualified_name}}) AS ins,
                   collect(DISTINCT nested) AS nested_compounds
            """,
            params,
        )
        record = result.single()
        if record is None or record["c"] is None:
            return None

        c_props = dict(record["c"])
        compound = CompoundNode(**c_props)

        members: list[MemberNode] = []
        for m in (record["members"] or []):
            if m is None:
                continue
            try:
                members.append(MemberNode(**dict(m)))
            except Exception:
                log.debug("Skipping invalid member: %s",
                          m.get("qualified_name", "?"))

        edges_out: list[GraphEdge] = []
        for e in (record["outs"] or []):
            if e is None or e.get("rel") is None:
                continue
            edges_out.append(_hydrate_graph_edge(
                e["rel"], e.get("source_qn", ""), e.get("target_qn", ""),
            ))

        edges_in: list[GraphEdge] = []
        for e in (record["ins"] or []):
            if e is None or e.get("rel") is None:
                continue
            edges_in.append(_hydrate_graph_edge(
                e["rel"], e.get("source_qn", ""), e.get("target_qn", ""),
            ))

        nested: list[CompoundGraph] = []
        for nc in (record["nested_compounds"] or []):
            if nc is None:
                continue
            nc_qn = nc.get("qualified_name", "")
            if nc_qn:
                nested_cg = self.get_compound_graph(nc_qn, layer=layer)
                if nested_cg:
                    nested.append(nested_cg)

        return CompoundGraph(
            node=compound,
            members=members,
            nested=nested,
            edges_out=edges_out,
            edges_in=edges_in,
        )

    def get_namespace_graph(
        self, qualified_name: str, *, layer: str | None = None
    ) -> NamespaceGraph | None:
        """Fetch a namespace with all contained compounds and child namespaces.

        One Cypher query fills the NamespaceGraph. Returns None if
        the namespace is not found.
        """
        layer_condition = "AND n.layer = $layer" if layer is not None else ""
        params: dict = {"qn": qualified_name}
        if layer is not None:
            params["layer"] = layer

        result = self._session.run(
            f"""
            MATCH (n:Namespace {{qualified_name: $qn}})
            {layer_condition}
            OPTIONAL MATCH (n)-[:COMPOSES]->(c:Compound)
            RETURN n, collect(DISTINCT c) AS compounds
            """,
            params,
        )
        record = result.single()
        if record is None or record["n"] is None:
            return None

        ns_props = dict(record["n"])
        ns_node = NamespaceNode(**ns_props)

        compounds: list[CompoundGraph] = []
        for c in (record["compounds"] or []):
            if c is None:
                continue
            c_qn = c.get("qualified_name", "")
            if c_qn:
                cg = self.get_compound_graph(c_qn, layer=layer)
                if cg:
                    compounds.append(cg)

        return NamespaceGraph(
            node=ns_node,
            compounds=compounds,
            namespaces=[],
        )

    def get_ontology_graph(
        self,
        *,
        layer: str = "design",
        kind_filter: str | None = None,
        search: str | None = None,
        component_id: int | None = None,
    ) -> OntologyGraph:
        """Fetch the full ontology graph for the given layer.

        Returns an OntologyGraph with all namespaces, their compounds,
        unparented compounds, and cross-cutting edges.
        """
        # Build filter conditions for compounds
        conditions = ["c.layer = $layer"]
        params: dict = {"layer": layer}

        if kind_filter:
            conditions.append("c.kind = $kind")
            params["kind"] = kind_filter
        if component_id is not None:
            conditions.append("c.component_id = $comp_id")
            params["comp_id"] = component_id
        if search:
            conditions.append(
                "(c.name CONTAINS $search OR c.qualified_name CONTAINS $search)"
            )
            params["search"] = search

        where = " AND ".join(conditions)

        result = self._session.run(
            f"""
            MATCH (c:Compound)
            WHERE {where}
            OPTIONAL MATCH (c)-[:COMPOSES]->(m:Member)
            OPTIONAL MATCH (c)-[r_out]->(tgt)
              WHERE type(r_out) <> 'COMPOSES'
                AND (tgt:Compound OR tgt:Namespace)
                AND tgt.layer = $layer
            OPTIONAL MATCH (src)-[r_in]->(c)
              WHERE NOT src:Member
            RETURN c,
                   collect(DISTINCT m) AS members,
                   collect(DISTINCT {{rel: type(r_out),
                       source_qn: c.qualified_name,
                       target_qn: tgt.qualified_name}}) AS outs,
                   collect(DISTINCT {{rel: type(r_in),
                       source_qn: src.qualified_name,
                       target_qn: c.qualified_name}}) AS ins
            ORDER BY c.qualified_name
            """,
            params,
        )

        compound_graphs: dict[str, CompoundGraph] = {}
        for record in result:
            c = record["c"]
            if c is None:
                continue
            c_props = dict(c)
            c_qn = c_props.get("qualified_name", "")

            members: list[MemberNode] = []
            for m in (record["members"] or []):
                if m is None:
                    continue
                try:
                    members.append(MemberNode(**dict(m)))
                except Exception:
                    pass

            edges_out: list[GraphEdge] = []
            for e in (record["outs"] or []):
                if e is None or e.get("rel") is None:
                    continue
                edges_out.append(_hydrate_graph_edge(
                    e["rel"], e.get("source_qn", ""), e.get("target_qn", ""),
                ))

            edges_in: list[GraphEdge] = []
            for e in (record["ins"] or []):
                if e is None or e.get("rel") is None:
                    continue
                edges_in.append(_hydrate_graph_edge(
                    e["rel"], e.get("source_qn", ""), e.get("target_qn", ""),
                ))

            compound = CompoundNode(**c_props)
            cg = CompoundGraph(
                node=compound,
                members=members,
                edges_out=edges_out,
                edges_in=edges_in,
            )
            compound_graphs[c_qn] = cg

        # Fetch namespaces with layer filter
        ns_result = self._session.run(
            """
            MATCH (n:Namespace)
            WHERE n.layer = $layer
            OPTIONAL MATCH (n)-[:COMPOSES]->(c:Compound)
            RETURN n, collect(DISTINCT c) AS compounds
            ORDER BY n.qualified_name
            """,
            {"layer": layer},
        )

        ns_graphs: dict[str, NamespaceGraph] = {}
        ns_owned_compound_qns: set[str] = set()
        for record in ns_result:
            n = record["n"]
            if n is None:
                continue
            ns_props = dict(n)
            ns_qn = ns_props.get("qualified_name", "")
            ns_node = NamespaceNode(**ns_props)

            ns_compounds: list[CompoundGraph] = []
            for c in (record["compounds"] or []):
                if c is None:
                    continue
                c_qn = c.get("qualified_name", "")
                ns_owned_compound_qns.add(c_qn)
                if c_qn in compound_graphs:
                    ns_compounds.append(compound_graphs[c_qn])

            ns_graphs[ns_qn] = NamespaceGraph(
                node=ns_node,
                compounds=ns_compounds,
                namespaces=[],
            )

        unparented: list[CompoundGraph] = [
            cg for qn, cg in compound_graphs.items()
            if qn not in ns_owned_compound_qns
        ]

        cross_edges: list[GraphEdge] = []
        edge_seen: set[tuple[str, str, str]] = set()
        for cg in compound_graphs.values():
            for ge in cg.edges_out:
                key = (ge.source_qualified_name, ge.target_qualified_name, ge.predicate)
                if key not in edge_seen:
                    edge_seen.add(key)
                    cross_edges.append(ge)

        return OntologyGraph(
            namespaces=list(ns_graphs.values()),
            compounds=unparented,
            edges=cross_edges,
        )

    def get_hlr_subgraph(
        self, hlr_id: int, component_id: int | None = None
    ) -> OntologyGraph:
        """Fetch the design subgraph around an HLR.

        Finds seed design nodes via TRACES_TO from the HLR, then fetches
        a 1-hop neighbourhood of compounds and their members.
        """
        seed_result = self._session.run(
            f"""
            MATCH (hlr:HLR {{id: $hid}})-[:TRACES_TO]->(d)
            WHERE {_label_match("d")}
            RETURN d.qualified_name AS qn
            """,
            {"hid": hlr_id},
        )
        seed_qns = [r["qn"] for r in seed_result if r["qn"]]
        if not seed_qns:
            log.warning("HLR %d has no linked nodes via TRACES_TO", hlr_id)
            return OntologyGraph()

        return self._get_neighbourhood_from_seeds(seed_qns, component_id)

    def get_neighbourhood_graph(self, qualified_name: str) -> OntologyGraph:
        """Fetch the 1-hop neighbourhood of a node as an OntologyGraph."""
        return self._get_neighbourhood_from_seeds([qualified_name])

    def _get_neighbourhood_from_seeds(
        self, seed_qns: list[str], component_id: int | None = None
    ) -> OntologyGraph:
        """Build an OntologyGraph from seed qualified names."""
        label_clause = _label_match("d")

        result = self._session.run(
            f"UNWIND $qns AS qn MATCH (d) WHERE d.qualified_name = qn AND {label_clause} RETURN d",
            {"qns": seed_qns},
        )
        compound_graphs: dict[str, CompoundGraph] = {}
        for record in result:
            d = record["d"]
            if d is None:
                continue
            qn = d.get("qualified_name", "")
            cg = self.get_compound_graph(qn)
            if cg:
                compound_graphs[qn] = cg

        edge_out = self._session.run(
            """
            UNWIND $qns AS qn
            MATCH (s {qualified_name: qn})-[r]->(t)
            WHERE type(r) <> 'COMPOSES'
              AND (t:Compound OR t:Namespace)
            RETURN s.qualified_name AS src, t.qualified_name AS tgt,
                   type(r) AS rel_type
            """,
            {"qns": seed_qns},
        )
        for record in edge_out:
            src, tgt, rel = record["src"], record["tgt"], record["rel_type"]
            if tgt and tgt not in compound_graphs:
                cg = self.get_compound_graph(tgt)
                if cg:
                    compound_graphs[tgt] = cg
            if src in compound_graphs:
                compound_graphs[src].edges_out.append(
                    _hydrate_graph_edge(rel, src, tgt or "")
                )

        edge_in = self._session.run(
            """
            UNWIND $qns AS qn
            MATCH (s)-[r]->(t {qualified_name: qn})
            WHERE type(r) <> 'COMPOSES'
              AND NOT s:Member
              AND s.qualified_name <> t.qualified_name
            RETURN s.qualified_name AS src, t.qualified_name AS tgt,
                   type(r) AS rel_type
            """,
            {"qns": seed_qns},
        )
        for record in edge_in:
            src, tgt, rel = record["src"], record["tgt"], record["rel_type"]
            if src and src not in compound_graphs:
                cg = self.get_compound_graph(src)
                if cg:
                    compound_graphs[src] = cg
            if tgt in compound_graphs:
                compound_graphs[tgt].edges_in.append(
                    _hydrate_graph_edge(rel, src or "", tgt)
                )

        if component_id is not None:
            comp_result = self._session.run(
                """
                MATCH (c:Compound {component_id: $cid})
                RETURN c.qualified_name AS qn
                """,
                {"cid": component_id},
            )
            for record in comp_result:
                qn = record["qn"]
                if qn and qn not in compound_graphs:
                    cg = self.get_compound_graph(qn)
                    if cg:
                        compound_graphs[qn] = cg

        return OntologyGraph(compounds=list(compound_graphs.values()))

    def get_graph_stats(self) -> dict:
        """Return node counts by kind, edge counts by predicate."""
        label_clause = _label_match("d")

        kind_result = self._session.run(
            f"MATCH (d) WHERE {label_clause} RETURN d.kind AS kind, count(d) AS cnt"
        )
        kind_counts: dict[str, int] = {}
        total_nodes = 0
        for record in kind_result:
            k = record["kind"] or "unknown"
            cnt = record["cnt"]
            kind_counts[k] = cnt
            total_nodes += cnt

        nodes_result = self._session.run(
            f"""
            MATCH (d) WHERE {label_clause}
            RETURN d.qualified_name AS qn, d.name AS name,
                   d.kind AS kind, d.component_id AS cid
            ORDER BY d.qualified_name LIMIT 200
            """
        )
        nodes = []
        for record in nodes_result:
            nodes.append({
                "name": record["name"],
                "kind": record["kind"],
                "qualified_name": record["qn"],
                "component_id": record["cid"],
            })

        edge_result = self._session.run(
            f"""
            MATCH (s)-[r]->(t)
            WHERE {_label_match('s')} AND {_label_match('t')}
            RETURN count(r) AS cnt
            """
        )
        total_edges = edge_result.single()["cnt"]

        pred_result = self._session.run(
            f"""
            MATCH (s)-[r]->(t)
            WHERE {_label_match('s')} AND {_label_match('t')}
            RETURN count(DISTINCT type(r)) AS cnt
            """
        )
        total_predicates = pred_result.single()["cnt"]

        return {
            "nodes": nodes,
            "kind_counts": kind_counts,
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "total_predicates": total_predicates,
        }

    def get_dependency_links(self, design_qnames: list[str]) -> OntologyGraph:
        """Find dependency Compounds linked to given design qualified names."""
        if not design_qnames:
            return OntologyGraph()

        label_clause = _label_match("d")

        result = self._session.run(
            f"""
            UNWIND $qnames AS qn
            MATCH (d) WHERE d.qualified_name = qn AND {label_clause}
            OPTIONAL MATCH (d)-[r]->(dep:Compound)
            WHERE dep.layer = 'dependency'
            RETURN d, collect(DISTINCT {{dep: dep, rel: type(r)}}) AS dep_links
            """,
            {"qnames": design_qnames},
        )

        compounds: list[CompoundGraph] = []
        seen_qns: set[str] = set()
        edges: list[GraphEdge] = []

        for record in result:
            d = record["d"]
            if d is None:
                continue
            d_qn = d.get("qualified_name", "")
            if d_qn not in seen_qns:
                seen_qns.add(d_qn)
                d_props = dict(d)
                compounds.append(CompoundGraph(
                    node=CompoundNode(**d_props),
                ))

            for item in (record["dep_links"] or []):
                if item is None or item.get("dep") is None:
                    continue
                dep = item["dep"]
                dep_qn = dep.get("qualified_name", "")
                dep_props = dict(dep)
                if dep_qn not in seen_qns:
                    seen_qns.add(dep_qn)
                    try:
                        compounds.append(CompoundGraph(
                            node=CompoundNode(**dep_props),
                        ))
                    except Exception:
                        pass
                edges.append(_hydrate_graph_edge(
                    item["rel"], d_qn, dep_qn,
                ))

        return OntologyGraph(compounds=compounds, edges=edges)

    def delete_node(self, qualified_name: str) -> bool:
        """Delete a node and all its relationships. Returns True if deleted.

        Matches across :Compound, :Member, :Namespace labels.
        """
        label_clause = _label_match("n")
        result = self._session.run(
            f"""
            MATCH (n)
            WHERE n.qualified_name = $qn
              AND {label_clause}
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

        Matches subject and object across :Compound, :Member, :Namespace.

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

        subj_clause = _label_match("s")
        obj_clause = _label_match("target")
        cypher = f"""
        MATCH (s)
        WHERE s.qualified_name = $subj AND {subj_clause}
        MATCH (target)
        WHERE target.qualified_name = $obj AND {obj_clause}
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

        Removes :Compound, :Member, :Namespace nodes.
        """
        try:
            label_clause = _label_match("n")
            self._session.run(f"MATCH (n) WHERE {label_clause} DETACH DELETE n")
            log.info("Cleared design graph from Neo4j")
            return True
        except Exception:
            log.warning("Neo4j clear failed", exc_info=True)
            return False

    def sync_implementation_status(self, qualified_name: str, status: str, source_file: str = "", test_file: str = "") -> None:
        """Update implementation_status on a node.

        Matches across :Compound, :Member, :Namespace labels.
        """
        label_clause = _label_match("n")
        self._session.run(
            f"""
            MATCH (n)
            WHERE n.qualified_name = $qn
              AND {label_clause}
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