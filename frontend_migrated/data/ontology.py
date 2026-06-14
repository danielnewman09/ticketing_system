"""Ontology data and graph queries — migrated to codegraph backend.

All functions use ``codegraph.GraphRepository`` and ``LayerGraph`` as
the single data backend.  No imports from ``backend/`` — only from
``codegraph``, ``backend_migrated``, and ``frontend_migrated``.

Architecture (Phase 5 — codegraph migration):
- Read paths use GraphRepository → LayerGraph → layer_graph_to_cytoscape().
- Requirement tag enrichment uses neomodel TRACES_TO relationships on
  HLR/LLR nodes instead of raw Cypher queries.
- The Cytoscape dict format is the single graph format for visualisation.
"""

from __future__ import annotations

import hashlib
import logging
from typing import TypedDict

from codegraph.models import (
    ClassNode,
    ConceptNode,
    EnumNode,
    InterfaceNode,
    ModuleNode,
    NamespaceNode,
    UnionNode,
    MethodNode,
    AttributeNode,
    EnumValueNode,
    FunctionNode,
    DefineNode,
)
from codegraph.repository import GraphRepository
from neomodel.properties import Property

from frontend_migrated.graph.format import (
    layer_graph_to_cytoscape,
    _filter_by_kind,
    _filter_by_search,
    _filter_by_component,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Node property fields — derived from codegraph model properties
# ---------------------------------------------------------------------------
#
# _NODE_DETAIL_FIELDS is the union of all neomodel properties across
# every codegraph node model (CompoundNode subclasses + MemberNode
# subclasses + NamespaceNode), minus fields that are too large or
# too internal for the ontology detail panel, plus a handful of
# computed/derived fields that don't correspond to neomodel properties.
#
# This replaces a hardcoded tuple and stays in sync automatically
# when new properties are added to the model classes.

# Neomodel properties we exclude from the detail view because they are
# too large (embeddings), internal (refids), or handled separately
# (tags → layer).
_EXCLUDED_DETAIL_PROPS: frozenset[str] = frozenset({
    "doc_embedding",       # large vector — not for UI
    "impl_embedding",     # large vector — not for UI
    "refid",               # internal ID
    "tags",                # handled separately as 'layer'
    "detailed_description", # too verbose for detail panel
    "body_start",           # implementation detail
    "body_end",             # implementation detail
    "compound_refid",       # internal reference
})

# Computed/derived fields that aren't neomodel properties but should
# appear in the detail dict (populated at runtime from tags, aliases, etc.).
_COMPUTED_DETAIL_FIELDS: frozenset[str] = frozenset({
    "layer",          # derived from tags[0]
    "protection",     # legacy alias for visibility
    "specialization", # template specialization (not a direct property)
})

# Collect all property names from all ontology-relevant model classes.
_ALL_MODEL_CLASSES = [
    ClassNode, InterfaceNode, EnumNode, UnionNode, ModuleNode, ConceptNode,
    MethodNode, AttributeNode, EnumValueNode, FunctionNode, DefineNode,
    NamespaceNode,
]

_all_props: set[str] = set()
for _cls in _ALL_MODEL_CLASSES:
    for _klass in reversed(_cls.__mro__):
        for _name, _val in vars(_klass).items():
            if isinstance(_val, Property):
                _all_props.add(_name)

_NODE_DETAIL_FIELDS: frozenset[str] = frozenset(
    (_all_props - _EXCLUDED_DETAIL_PROPS) | _COMPUTED_DETAIL_FIELDS
)


# ---------------------------------------------------------------------------
# TypedDict contracts — documented return types
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
    """Build a mapping from legacy integer id → Component name.

    Code-level nodes (Compound, Member, Namespace) carry a
    ``component_id`` integer that references the legacy SQLite
    Component id.  In the migrated neomodel system, Components
    use ``refid`` as their unique key.  We iterate all Components
    and try to match by checking the ``id`` property (preserved
    on pre-existing nodes) and fall back to the ``name``.
    """
    try:
        from backend_migrated.models import Component
        result: dict[int, str] = {}
        for comp in Component.nodes.all():
            # Legacy integer id may be preserved on pre-existing nodes
            legacy_id = getattr(comp, "id", None)
            if legacy_id is not None:
                try:
                    result[int(legacy_id)] = comp.name
                except (ValueError, TypeError):
                    pass
            # Also add a mapping by name hash for fallback
            result[hash(comp.name) & 0xFFFFFFFF] = comp.name
        return result
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Requirement tag enrichment (replaces raw-Cypher graph_tags.py)
# ---------------------------------------------------------------------------


def _enrich_with_requirement_tags(
    nodes: list[dict],
    mode: str = "none",
) -> list[dict]:
    """Tag design nodes with HLR/LLR badges using neomodel TRACES_TO.

    Walks HLR and LLR neomodel nodes, follows their traces_to_*
    relationship managers to find linked design nodes, and adds a
    ``requirements`` key to matching Cytoscape node dicts.

    Args:
        nodes: Cytoscape-format node dicts (modified in-place).
        mode: "none" for bare topology, "hlr" for HLR badges.

    Returns:
        The same list (modified in-place).
    """
    if mode == "none":
        return nodes

    # Build a lookup: qualified_name → node data dict
    qn_to_node: dict[str, dict] = {}
    for n in nodes:
        d = n.get("data", n)
        qn = d.get("qualified_name", "")
        if qn and d.get("source_type") != "dependency":
            qn_to_node[qn] = d

    if not qn_to_node:
        return nodes

    # Walk HLR TRACES_TO targets
    try:
        from backend_migrated.models.requirement import HLR, LLR

        for hlr in HLR.nodes.all():
            hlr_id = getattr(hlr, "id", None) or getattr(hlr, "refid", "")
            hlr_desc = (getattr(hlr, "description", "") or "")[:80]
            badge = {"id": hlr_id, "type": "HLR", "description": hlr_desc}

            for manager in (hlr.traces_to_compounds, hlr.traces_to_members, hlr.traces_to_namespaces):
                try:
                    for target in manager.all():
                        qn = getattr(target, "qualified_name", "")
                        if qn in qn_to_node:
                            qn_to_node[qn].setdefault("requirements", []).append(badge)
                            qn_to_node[qn]["has_requirements"] = "true"
                except Exception:
                    pass  # best-effort — manager may not be initialised

        # Walk LLR TRACES_TO targets
        for llr in LLR.nodes.all():
            llr_id = getattr(llr, "id", None) or getattr(llr, "refid", "")
            llr_desc = (getattr(llr, "description", "") or "")[:80]
            badge = {"id": llr_id, "type": "LLR", "description": llr_desc}

            for manager in (llr.traces_to_compounds, llr.traces_to_members, llr.traces_to_namespaces):
                try:
                    for target in manager.all():
                        qn = getattr(target, "qualified_name", "")
                        if qn in qn_to_node:
                            qn_to_node[qn].setdefault("requirements", []).append(badge)
                            qn_to_node[qn]["has_requirements"] = "true"
                except Exception:
                    pass  # best-effort

    except Exception:
        log.warning("Requirement tag enrichment failed — continuing without tags", exc_info=True)

    return nodes


def _tag_direct_nodes_only(nodes: list[dict], hlr_id: str | int) -> None:
    """Mark seed nodes directly linked to an HLR via TRACES_TO.

    Uses neomodel TRACES_TO relationship managers instead of raw Cypher.
    Modifies nodes in-place.

    Args:
        nodes: Cytoscape-format node dicts.
        hlr_id: The HLR's refid (string) or legacy integer id.
    """
    try:
        from backend_migrated.models.requirement import HLR

        # Try lookup by refid (primary key)
        hlr = HLR.nodes.get_or_none(refid=str(hlr_id))
        if hlr is None:
            # Fallback: try legacy integer id property
            for candidate in HLR.nodes.all():
                if getattr(candidate, "id", None) == hlr_id:
                    hlr = candidate
                    break
        if hlr is None:
            return

        hlr_desc = (getattr(hlr, "description", "") or "")[:80]
        badge = {"id": hlr_id, "type": "HLR", "description": hlr_desc}

        # Collect traced qualified names
        seed_qns: set[str] = set()
        for manager in (hlr.traces_to_compounds, hlr.traces_to_members, hlr.traces_to_namespaces):
            try:
                for target in manager.all():
                    qn = getattr(target, "qualified_name", "")
                    if qn:
                        seed_qns.add(qn)
            except Exception:
                pass

        # Tag matching Cytoscape nodes
        for node in nodes:
            d = node.get("data", node)
            qn = d.get("qualified_name", "")
            if qn in seed_qns:
                d["is_hlr_highlight"] = "true"
                d.setdefault("requirements", []).append(badge)
                d["has_requirements"] = "true"

    except Exception:
        log.warning("HLR direct-tag enrichment failed", exc_info=True)


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


# ---------------------------------------------------------------------------
# Public API — data fetching functions
# ---------------------------------------------------------------------------


def fetch_ontology_data() -> OntologyData:
    """Fetch all data needed for the ontology overview page via LayerGraph."""
    try:
        repo = GraphRepository()
        graph = repo.get_by_tag("design")
    except Exception:
        log.warning("GraphRepository query failed — returning empty data", exc_info=True)
        return {"nodes": [], "kind_counts": {}, "total_nodes": 0, "total_triples": 0, "total_predicates": 0}

    component_map = _get_component_map()

    nodes: list[OntologyNodeRow] = []
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
            "qualified_name": getattr(node, "qualified_name", "") or getattr(node, "name", ""),
            "component": component_map.get(cid, "-") if cid else "-",
        })

    return {
        "nodes": nodes,
        "kind_counts": kind_counts,
        "total_nodes": len(nodes),
        "total_triples": total_references,
        "total_predicates": len(predicates),
    }


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
        kind_filter: Optional kind to filter by (e.g. "class", "method").
        search: Optional text to search in name/qualified_name.
        component_id: Optional component ID to filter by.
        source_filter: Optional source project name to filter by (unused
            in the migrated path; kept for API compatibility).
        requirement_tags: "none" for bare topology, "hlr" for HLR badges.
        include_dependencies: If False, remove dependency/as-built nodes
            and cross-layer edges from the result (design-only graph).
    """
    try:
        repo = GraphRepository()
        graph = repo.get_by_tag(layer)

        if kind_filter:
            _filter_by_kind(graph, kind_filter)
        if search:
            _filter_by_search(graph, search)
        if component_id:
            _filter_by_component(graph, component_id)

        formatted = layer_graph_to_cytoscape(graph)

        # Enrich with requirement tags (design layer only)
        if layer == "design" and requirement_tags != "none":
            _enrich_with_requirement_tags(formatted["nodes"], mode=requirement_tags)

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
    hlr_id: str | int,
    component_id: str | None = None,
    requirement_tags: str = "hlr",
) -> dict:
    """Fetch the ontology subgraph around an HLR for Cytoscape.js.

    Finds the HLR by refid (or legacy integer id), walks its TRACES_TO
    relationships to find seed design nodes, builds a LayerGraph from
    those seeds using GraphRepository, and converts to Cytoscape format.

    Args:
        hlr_id: The HLR's refid (string) or legacy integer id.
        component_id: Optional component ID to filter by (unused in
            migrated path; kept for API compatibility).
        requirement_tags: "none" for bare topology, "hlr" for HLR
            highlight + badges.
    """
    try:
        from backend_migrated.models.requirement import HLR

        # Find the HLR node
        hlr = HLR.nodes.get_or_none(refid=str(hlr_id))
        if hlr is None:
            # Fallback: try legacy integer id
            for candidate in HLR.nodes.all():
                if getattr(candidate, "id", None) == hlr_id:
                    hlr = candidate
                    break
        if hlr is None:
            log.warning("HLR %s not found", hlr_id)
            return {"nodes": [], "edges": []}

        # Collect seed qualified names from TRACES_TO relationships
        seed_qns: list[str] = []
        for manager in (hlr.traces_to_compounds, hlr.traces_to_members, hlr.traces_to_namespaces):
            try:
                for target in manager.all():
                    qn = getattr(target, "qualified_name", "")
                    if qn:
                        seed_qns.append(qn)
            except Exception:
                pass

        if not seed_qns:
            log.warning("HLR %s has no TRACES_TO targets", hlr_id)
            return {"nodes": [], "edges": []}

        # Build a LayerGraph from the seed nodes using GraphRepository
        repo = GraphRepository()
        # Use get_by_neighbourhood for the first seed, which pulls 1-hop
        # neighbours. Then merge in the rest of the seeds.
        graph = repo.get_by_neighbourhood(seed_qns[0])

        # For additional seeds, merge their neighbourhoods
        for qn in seed_qns[1:]:
            try:
                extra = repo.get_by_neighbourhood(qn)
                # Merge entries and references
                for key, entry in extra.entries.items():
                    if key not in graph.entries:
                        graph.entries[key] = entry
                # Also merge flat references from extra entries
                for entry in extra._all_entries():
                    for ref in entry.references:
                        existing = graph._flat_index()
                        if graph._node_key(entry.node) in existing:
                            existing_entry = existing[graph._node_key(entry.node)]
                            existing_refs = {(r[0], r[1]) for r in existing_entry.references}
                            if (ref[0], ref[1]) not in existing_refs:
                                existing_entry.references.append(ref)
            except Exception:
                log.debug("Failed to merge neighbourhood for seed %s", qn, exc_info=True)

        # Include the HLR itself in the graph (it's a CompositeEntry root)
        hlr_entry_found = False
        for entry in graph._all_entries():
            if getattr(entry.node, "refid", None) == str(hlr_id) or getattr(entry.node, "name", "") == getattr(hlr, "name", ""):
                hlr_entry_found = True
                break

        formatted = layer_graph_to_cytoscape(graph)

        if requirement_tags != "none":
            _tag_direct_nodes_only(formatted["nodes"], hlr_id)

        return formatted
    except Exception:
        log.warning("HLR graph data fetch failed — returning empty graph", exc_info=True)
        return {"nodes": [], "edges": []}


def fetch_graph_node_detail(qualified_name: str) -> NodeDetail | None:
    """Fetch node detail from LayerGraph (properties + relationships + members).

    Uses GraphRepository.get_by_neighbourhood() to get the node and its
    1-hop context, then builds a detail dict.
    """
    try:
        repo = GraphRepository()
        graph = repo.get_by_neighbourhood(qualified_name)
        flat = graph._flat_index()
        entry = flat.get(qualified_name)
        if entry is None:
            return None

        node = entry.node
        props = _node_properties(node)

        # Build outgoing references
        outgoing: list[OutgoingRef] = [
            {
                "rel": rel_type,
                "target_qn": target_key,
                "target_name": "",
                "target_labels": [target_type],
            }
            for rel_type, target_key, target_type in entry.references
        ]

        # Build incoming references by scanning other entries
        incoming: list[IncomingRef] = []
        for other_key, other_entry in flat.items():
            if other_key == qualified_name:
                continue
            for rel_type, target_key, target_type in other_entry.references:
                if target_key == qualified_name:
                    incoming.append({
                        "rel": rel_type,
                        "source_qn": other_key,
                        "source_name": getattr(other_entry.node, "name", ""),
                        "source_labels": [target_type],
                    })

        # Build members from entry children (flatten all type groups)
        members: list[dict] = []
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


def fetch_node_detail_full(qualified_name: str) -> NodeDetailFull | None:
    """Fetch ontology node by qualified_name with all properties + Neo4j relationships.

    Composes fetch_graph_node_detail() with component name lookup.
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
    # component_id is an integer reference to a Component node;
    # find the Component by matching the integer id or by name.
    component_name = ""
    if node_data["component_id"]:
        try:
            from backend_migrated.models import Component
            # Try to find Component by name (components are identified by name
            # in the migrated system, not by integer id)
            # component_id may refer to the legacy SQLAlchemy id
            comp = Component.nodes.get_or_none(refid=str(node_data["component_id"]))
            if comp is None:
                # Fallback: try matching by integer id property
                for candidate in Component.nodes.all():
                    if getattr(candidate, "id", None) == node_data["component_id"]:
                        comp = candidate
                        break
            if comp:
                component_name = comp.name
        except Exception:
            pass
    node_data["component"] = component_name

    # Requirement tags: walk TRACES_TO on HLR/LLR nodes pointing at this qn
    requirements: list[dict] = []
    try:
        from backend_migrated.models.requirement import HLR, LLR

        for hlr in HLR.nodes.all():
            for manager in (hlr.traces_to_compounds, hlr.traces_to_members, hlr.traces_to_namespaces):
                try:
                    for target in manager.all():
                        if getattr(target, "qualified_name", "") == qualified_name:
                            requirements.append({
                                "id": getattr(hlr, "id", None) or getattr(hlr, "refid", ""),
                                "type": "HLR",
                                "description": (getattr(hlr, "description", "") or "")[:80],
                            })
                            break  # found this HLR for this qn, no need to check other managers
                except Exception:
                    pass

        for llr in LLR.nodes.all():
            for manager in (llr.traces_to_compounds, llr.traces_to_members, llr.traces_to_namespaces):
                try:
                    for target in manager.all():
                        if getattr(target, "qualified_name", "") == qualified_name:
                            requirements.append({
                                "id": getattr(llr, "id", None) or getattr(llr, "refid", ""),
                                "type": "LLR",
                                "description": (getattr(llr, "description", "") or "")[:80],
                            })
                            break
                except Exception:
                    pass
    except Exception:
        log.debug("Requirement tag lookup failed for %s", qualified_name, exc_info=True)

    return {
        "node": node_data,
        "neo4j": neo4j_data,
        "requirements": requirements,
    }


def resolve_node_id_by_qualified_name(qualified_name: str) -> int | None:
    """Look up an identifier for an ontology node by qualified_name.

    Returns a stable hash of the qualified_name since design nodes are
    identified by qualified_name in Neo4j, not by SQLAlchemy id.
    """
    return int(hashlib.md5(qualified_name.encode()).hexdigest()[:8], 16)


def update_member_type(qualified_name: str, type_signature: str) -> bool:
    """Update type_signature on a design member node via neomodel.

    Finds the MethodNode (or other member) by qualified_name and calls
    .update() to persist the change.
    """
    try:
        from codegraph.models.member import MethodNode, AttributeNode

        for NodeClass in (MethodNode, AttributeNode):
            node = NodeClass.nodes.get_or_none(qualified_name=qualified_name)
            if node is not None:
                node.update(type_signature=type_signature)
                return True

        # Fallback: try GraphRepository for other member types
        repo = GraphRepository()
        graph = repo.get_by_neighbourhood(qualified_name)
        flat = graph._flat_index()
        entry = flat.get(qualified_name)
        if entry is not None:
            node = entry.node
            if hasattr(node, "type_signature"):
                node.type_signature = type_signature
                node.save()
                return True

        return False
    except Exception:
        log.warning("Member type update failed for %s", qualified_name, exc_info=True)
        return False