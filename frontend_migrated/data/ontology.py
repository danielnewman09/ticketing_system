"""Ontology data and graph queries — stubs.

Return types are documented via TypedDicts. All functions raise
NotImplementedError until reimplemented against the migrated backend.
No imports from backend/ anywhere in this module.
"""

from __future__ import annotations

from typing import TypedDict


class OntologyNodeRow(TypedDict):
    name: str
    kind: str
    qualified_name: str
    component: str


class OntologyData(TypedDict):
    nodes: list[OntologyNodeRow]
    kind_counts: dict[str, int]
    total_nodes: int
    total_triples: int
    total_predicates: int


class OutgoingRef(TypedDict):
    rel: str
    target_qn: str
    target_name: str
    target_labels: list[str]


class IncomingRef(TypedDict):
    rel: str
    source_qn: str
    source_name: str
    source_labels: list[str]


class NodeDetail(TypedDict):
    properties: dict
    outgoing: list[OutgoingRef]
    incoming: list[IncomingRef]
    implemented_by: list
    members: list[dict]
    codebase_members: list
    available_types: list


class NodeDetailFull(TypedDict):
    node: dict
    neo4j: NodeDetail
    requirements: list


def fetch_ontology_data() -> OntologyData:
    """Fetch all data needed for the ontology overview page via LayerGraph."""
    raise NotImplementedError("fetch_ontology_data — requires backend_migrated data layer")


def fetch_ontology_graph_data(
    layer: str = "design",
    kind_filter: str | None = None,
    search: str | None = None,
    component_id: int | None = None,
    source_filter: str | None = None,
    requirement_tags: str = "hlr",
    include_dependencies: bool = True,
) -> dict:
    """Fetch graph data for Cytoscape.js rendering via LayerGraph.

    Returns Cytoscape-format dict with 'nodes' and 'edges' keys.
    """
    raise NotImplementedError("fetch_ontology_graph_data — requires backend_migrated data layer")


def fetch_hlr_graph_data(
    hlr_id: int,
    component_id: int | None = None,
    requirement_tags: str = "hlr",
) -> dict:
    """Fetch the ontology subgraph around an HLR for Cytoscape.js.

    Returns Cytoscape-format dict with 'nodes' and 'edges' keys.
    """
    raise NotImplementedError("fetch_hlr_graph_data — requires backend_migrated data layer")


def fetch_graph_node_detail(qualified_name: str) -> NodeDetail | None:
    """Fetch node detail from LayerGraph (properties + relationships + members)."""
    raise NotImplementedError("fetch_graph_node_detail — requires backend_migrated data layer")


def fetch_node_detail_full(qualified_name: str) -> NodeDetailFull | None:
    """Fetch ontology node by qualified_name with all properties + Neo4j relationships."""
    raise NotImplementedError("fetch_node_detail_full — requires backend_migrated data layer")


def resolve_node_id_by_qualified_name(qualified_name: str) -> int | None:
    """Look up an identifier for an ontology node by qualified_name.

    Returns a stable hash of the qualified_name since design nodes are
    identified by qualified_name in Neo4j, not by SQLAlchemy id.
    """
    raise NotImplementedError("resolve_node_id_by_qualified_name — requires backend_migrated data layer")


def update_member_type(qualified_name: str, type_signature: str) -> bool:
    """Update type_signature on a design member node in Neo4j."""
    raise NotImplementedError("update_member_type — requires backend_migrated data layer")


def filter_cross_layer_elements(
    nodes: list[dict], edges: list[dict]
) -> tuple[list[dict], list[dict]]:
    """Remove cross-layer nodes and edges (dependency and as-built).

    Used when include_dependencies=False to return a design-only graph.
    """
    raise NotImplementedError("filter_cross_layer_elements — requires backend_migrated data layer")