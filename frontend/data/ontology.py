"""Ontology data and graph queries.

Architecture (Phase 4):
- Read paths use GraphRepository → LayerGraph → layer_graph_to_cytoscape().
- Thin pass-through wrappers collapsed; pages call codegraph directly where
  no frontend-specific transform is needed.
- Requirement tags come from graph_tags.py (Cypher TRACES_TO traversal).
- HLR graph data and TRACES_TO queries in hlr.py (separate requirements pass).
"""

import logging

from codegraph.connection import get_session as get_neo4j_session

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Node property field names used for serialisation from CodeGraphNode.
# These are the fields the frontend expects in node detail views.
# ---------------------------------------------------------------------------

_NODE_DETAIL_FIELDS = (
    "qualified_name", "name", "kind", "layer", "source", "component_id",
    "protection", "description", "brief_description", "type_signature",
    "argsstring", "definition", "file_path", "line_number", "source_type",
    "is_static", "is_const", "is_virtual", "is_abstract", "is_final",
    "specialization", "visibility",
)


def _node_properties(node) -> dict:
    """Extract a flat properties dict from a CodeGraphNode neomodel instance."""
    props = {}
    for attr in _NODE_DETAIL_FIELDS:
        val = getattr(node, attr, None)
        if val is not None:
            # Map 'protection' → 'visibility' for frontend compatibility
            if attr == "protection":
                props.setdefault("visibility", val)
            elif attr == "visibility":
                # Don't override 'protection' value
                props.setdefault("visibility", val)
            else:
                props[attr] = val
    # Ensure visibility is set from protection if present
    if "visibility" not in props and "protection" not in props:
        props["visibility"] = ""
    return props


def _get_component_map() -> dict[int, str]:
    """Look up component id → name mapping from SQLite."""
    try:
        from backend.db import get_session
        from backend.db.models import Component
        with get_session() as session:
            return {c.id: c.name for c in session.query(Component).all()}
    except Exception:
        return {}


def fetch_ontology_data():
    """Fetch all data needed for the ontology overview page via LayerGraph."""
    try:
        from codegraph.repository import GraphRepository

        repo = GraphRepository()
        graph = repo.get_by_layer("design")
    except Exception:
        log.warning("GraphRepository query failed — returning empty data", exc_info=True)
        return {"nodes": [], "kind_counts": {}, "total_nodes": 0, "total_triples": 0, "total_predicates": 0}

    component_map = _get_component_map()

    nodes = []
    kind_counts: dict[str, int] = {}
    total_references = 0
    predicates: set[str] = set()

    for entry in graph._all_entries():
        node = entry.node
        total_references += len(entry.references)
        for rel_type, _tgt_key, _tgt_type in entry.references:
            predicates.add(rel_type)

        kind = getattr(node, "kind", "unknown")
        kind_counts[kind] = kind_counts.get(kind, 0) + 1

        cid = getattr(node, "component_id", None)
        nodes.append({
            "name": getattr(node, "name", ""),
            "kind": kind,
            "qualified_name": getattr(node, "qualified_name", ""),
            "component": component_map.get(cid, "-") if cid else "-",
        })

    return {
        "nodes": nodes,
        "kind_counts": kind_counts,
        "total_nodes": len(nodes),
        "total_triples": total_references,
        "total_predicates": len(predicates),
    }


def filter_cross_layer_elements(
    nodes: list[dict], edges: list[dict]
) -> tuple[list[dict], list[dict]]:
    """Remove cross-layer nodes and edges (dependency and as-built).

    Used when include_dependencies=False to return a design-only graph.
    """
    cross_layer_ids = {
        n["data"]["id"]
        for n in nodes
        if n["data"].get("layer") in ("dependency", "as-built")
    }
    filtered_nodes = [n for n in nodes if n["data"]["id"] not in cross_layer_ids]
    filtered_edges = [
        e for e in edges
        if e["data"].get("source") not in cross_layer_ids
        and e["data"].get("target") not in cross_layer_ids
    ]
    return filtered_nodes, filtered_edges


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

    Args:
        layer: "design", "codebase", or "dependency".
        requirement_tags: "none" for bare topology, "hlr" for HLR badges.
        include_dependencies: If False, remove dependency/as-built nodes and
            cross-layer edges from the result (design-only graph).
    """
    try:
        from codegraph.repository import GraphRepository
        from frontend.graph.format import (
            layer_graph_to_cytoscape,
            _filter_by_kind,
            _filter_by_search,
            _filter_by_component,
        )
        from backend.requirements.services.graph_tags import enrich_with_requirement_tags

        repo = GraphRepository()
        graph = repo.get_by_layer(layer)

        if kind_filter:
            _filter_by_kind(graph, kind_filter)
        if search:
            _filter_by_search(graph, search)
        if component_id:
            _filter_by_component(graph, component_id)

        formatted = layer_graph_to_cytoscape(graph)

        # Enrich with requirement tags (design layer only)
        if layer == "design" and requirement_tags != "none":
            enrich_with_requirement_tags(formatted["nodes"], mode=requirement_tags)

        # Filter out cross-layer nodes when toggle is off
        if not include_dependencies:
            formatted["nodes"], formatted["edges"] = filter_cross_layer_elements(
                formatted["nodes"], formatted["edges"]
            )

        return formatted
    except Exception:
        log.warning("Neo4j/LayerGraph query failed — returning empty graph", exc_info=True)
        return {"nodes": [], "edges": []}


def fetch_hlr_graph_data(
    hlr_id: int,
    component_id: int | None = None,
    requirement_tags: str = "hlr",
) -> dict:
    """Fetch the ontology subgraph around an HLR for Cytoscape.js.

    Uses DesignRepository (TRACES_TO edges are not in the codegraph model).

    Args:
        requirement_tags: "none" for bare topology, "hlr" for HLR highlight + badges.
    """
    try:
        from backend.db.neo4j.repositories.design import DesignRepository
        from backend.graph import format_ontology_graph
        from backend.requirements.services.graph_tags import tag_direct_nodes_only

        with get_neo4j_session() as session:
            repo = DesignRepository(session)
            graph = repo.get_hlr_subgraph(hlr_id, component_id)

        formatted = format_ontology_graph(graph)

        if requirement_tags != "none":
            tag_direct_nodes_only(formatted["nodes"], hlr_id)

        return formatted
    except Exception:
        log.warning("Neo4j HLR subgraph query failed — returning empty graph", exc_info=True)
        return {"nodes": [], "edges": []}


def fetch_graph_node_detail(qualified_name: str) -> dict | None:
    """Fetch node detail from LayerGraph (properties + relationships + members)."""
    try:
        from codegraph.repository import GraphRepository

        repo = GraphRepository()
        graph = repo.get_by_compound(qualified_name)
        flat = graph._flat_index()
        entry = flat.get(qualified_name)
        if entry is None:
            return None

        node = entry.node
        props = _node_properties(node)

        # Build outgoing references
        outgoing = [
            {
                "rel": rel_type,
                "target_qn": target_key,
                "target_name": "",
                "target_labels": [target_type],
            }
            for rel_type, target_key, target_type in entry.references
        ]

        # Build incoming references by scanning other entries
        incoming = []
        for other_key, other_entry in flat.items():
            if other_key == qualified_name:
                continue
            for rel_type, target_key, target_type in other_entry.references:
                if target_key == qualified_name:
                    incoming.append({
                        "rel": rel_type,
                        "source_qn": other_key,
                        "source_name": "",
                        "source_labels": [target_type],
                    })

        # Build members from entry children (flatten all type groups)
        members = []
        for _type_key, children in entry.children.items():
            for _child_key, child_entry in children.items():
                child_props = _node_properties(child_entry.node)
                members.append(child_props)

        return {
            "properties": props,
            "outgoing": outgoing,
            "incoming": incoming,
            "implemented_by": [],
            "members": members,
            "codebase_members": [],
            "available_types": [],
        }
    except Exception:
        log.warning("GraphRepository node detail query failed", exc_info=True)
        return None


def fetch_node_detail_full(qualified_name: str) -> dict | None:
    """Fetch ontology node by qualified_name with all properties + Neo4j relationships.

    In Phase 2, requirement tags come from TRACES_TO edges on :HLR/:LLR nodes
    with native id properties (no more sqlite_id bridge).
    """
    neo4j_data = fetch_graph_node_detail(qualified_name)
    if not neo4j_data:
        return None

    props = neo4j_data.get("properties", {})
    node_data = {
        "name": props.get("name", ""),
        "qualified_name": props.get("qualified_name", ""),
        "kind": props.get("kind", ""),
        "specialization": props.get("specialization", ""),
        "visibility": props.get("visibility", ""),
        "description": props.get("description", ""),
        "component_id": props.get("component_id"),
        "type_signature": props.get("type_signature", ""),
        "argsstring": props.get("argsstring", ""),
        "definition": props.get("definition", ""),
        "file_path": props.get("file_path", ""),
        "line_number": props.get("line_number"),
        "source_type": props.get("source_type", ""),
        "is_static": props.get("is_static", False),
        "is_const": props.get("is_const", False),
        "is_virtual": props.get("is_virtual", False),
        "is_abstract": props.get("is_abstract", False),
        "is_final": props.get("is_final", False),
    }

    # Look up component name if component_id exists
    component_name = ""
    if node_data["component_id"]:
        try:
            from backend.db import get_session
            from backend.db.models import Component
            with get_session() as session:
                comp = session.query(Component).filter_by(id=node_data["component_id"]).first()
                if comp:
                    component_name = comp.name
        except Exception:
            pass
    node_data["component"] = component_name

    # Requirement tags deferred to requirements pass (hlr.py).
    # The page handler already handles an empty requirements list gracefully.
    return {"node": node_data, "neo4j": neo4j_data, "requirements": []}


def resolve_node_id_by_qualified_name(qualified_name: str) -> int | None:
    """Look up an identifier for an ontology node by qualified_name.

    Returns a stable hash of the qualified_name since design nodes are
    identified by qualified_name in Neo4j, not by SQLAlchemy id.
    """
    import hashlib
    return int(hashlib.md5(qualified_name.encode()).hexdigest()[:8], 16)


def update_member_type(qualified_name: str, type_signature: str) -> bool:
    """Update type_signature on a design member node in Neo4j (primary store)."""
    try:
        with get_neo4j_session() as ns:
            ns.run(
                "MATCH (n:Member {qualified_name: $qn}) SET n.type_signature = $ts",
                {"qn": qualified_name, "ts": type_signature},
            )
        return True
    except Exception:
        log.warning("Neo4j type_signature update failed", exc_info=True)
        return False