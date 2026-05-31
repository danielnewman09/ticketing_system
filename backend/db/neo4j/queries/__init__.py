"""Read-side Neo4j queries — backward-compat shim delegating to DesignRepository.

New code should use ``DesignRepository`` methods directly:
``repo.get_ontology_graph()`` instead of ``fetch_design_graph()``.
"""

from __future__ import annotations

from backend.db.neo4j.repositories.design import DesignRepository


def _get_neo4j():
    """Lazy import to avoid circular dependency with services.dependencies."""
    from services.dependencies import get_neo4j
    return get_neo4j()


def fetch_design_graph(
    kind_filter=None, search=None, component_id=None
):
    conn = _get_neo4j()
    with conn.session() as session:
        repo = DesignRepository(session)
        graph = repo.get_ontology_graph(
            layer="design",
            kind_filter=kind_filter,
            search=search,
            component_id=component_id,
        )
        return graph.to_raw()


def fetch_hlr_subgraph(hlr_id, component_id=None):
    conn = _get_neo4j()
    with conn.session() as session:
        repo = DesignRepository(session)
        graph = repo.get_hlr_subgraph(hlr_id, component_id)
        return graph.to_raw()


def fetch_neighbourhood_graph(qualified_name):
    conn = _get_neo4j()
    with conn.session() as session:
        repo = DesignRepository(session)
        graph = repo.get_neighbourhood_graph(qualified_name)
        return graph.to_raw()


def fetch_node_detail(qualified_name):
    conn = _get_neo4j()
    with conn.session() as session:
        repo = DesignRepository(session)
        cg = repo.get_compound_graph(qualified_name)
        if cg is None:
            return None
        return {
            "properties": cg.node.model_dump(),
            "outgoing": [
                {"rel": e.predicate, "target_qn": e.target_qualified_name,
                 "target_name": "", "target_labels": ["Compound"]}
                for e in cg.edges_out
            ],
            "incoming": [
                {"rel": e.predicate, "source_qn": e.source_qualified_name,
                 "source_name": "", "source_labels": ["Compound"]}
                for e in cg.edges_in
            ],
            "implemented_by": [],
            "members": [m.model_dump() for m in cg.members],
            "codebase_members": [],
            "available_types": [],
        }


def fetch_codebase_compounds(search=None):
    conn = _get_neo4j()
    with conn.session() as session:
        repo = DesignRepository(session)
        graph = repo.get_ontology_graph(
            layer="as-built", search=search,
        )
        return graph.to_raw()


def fetch_dependency_compounds(search=None, source_filter=None, limit=100):
    conn = _get_neo4j()
    with conn.session() as session:
        repo = DesignRepository(session)
        graph = repo.get_ontology_graph(
            layer="dependency", search=search,
        )
        raw = graph.to_raw()
        return raw


def fetch_design_dependency_links(design_qnames):
    conn = _get_neo4j()
    with conn.session() as session:
        repo = DesignRepository(session)
        graph = repo.get_dependency_links(design_qnames)
        return graph.to_raw()


__all__ = [
    "fetch_design_graph",
    "fetch_hlr_subgraph",
    "fetch_neighbourhood_graph",
    "fetch_node_detail",
    "fetch_codebase_compounds",
    "fetch_dependency_compounds",
    "fetch_design_dependency_links",
]
