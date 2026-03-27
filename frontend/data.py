"""Data-fetching functions for UI pages. Run in threads via asyncio.to_thread."""

import logging

from db import get_session
from db.models import (
    Component,
    Dependency,
    DependencyManager,
    DependencyRecommendation,
    HighLevelRequirement,
    Language,
    LowLevelRequirement,
    OntologyNode,
    OntologyTriple,
    Predicate,
    ProjectMeta,
    VerificationMethod,
)

log = logging.getLogger(__name__)


def fetch_project_meta() -> dict:
    """Fetch project metadata (single row), creating defaults if missing."""
    with get_session() as session:
        meta = session.query(ProjectMeta).filter_by(id=1).first()
        if not meta:
            meta = ProjectMeta(id=1, name="", description="", working_directory="")
            session.add(meta)
            session.flush()
        return {
            "name": meta.name,
            "description": meta.description,
            "working_directory": meta.working_directory,
        }


def update_project_meta(name: str, description: str, working_directory: str) -> bool:
    """Update project metadata. Returns True on success."""
    with get_session() as session:
        meta = session.query(ProjectMeta).filter_by(id=1).first()
        if not meta:
            meta = ProjectMeta(id=1)
            session.add(meta)
        meta.name = name
        meta.description = description
        meta.working_directory = working_directory
        return True


def fetch_requirements_data():
    """Fetch all data needed for the requirements dashboard."""
    with get_session() as session:
        hlrs = []
        for hlr in session.query(HighLevelRequirement).all():
            llrs = []
            for llr in hlr.low_level_requirements:
                methods = [v.method for v in llr.verifications]
                llrs.append({
                    "id": llr.id,
                    "description": llr.description,
                    "methods": methods,
                })
            hlrs.append({
                "id": hlr.id,
                "description": hlr.description,
                "component": hlr.component.name if hlr.component else None,
                "llrs": llrs,
            })

        unlinked = []
        for llr in session.query(LowLevelRequirement).filter(
            LowLevelRequirement.high_level_requirement_id.is_(None),
        ).all():
            methods = [v.method for v in llr.verifications]
            unlinked.append({
                "id": llr.id,
                "description": llr.description,
                "methods": methods,
            })

        return {
            "hlrs": hlrs,
            "unlinked_llrs": unlinked,
            "total_hlrs": session.query(HighLevelRequirement).count(),
            "total_llrs": session.query(LowLevelRequirement).count(),
            "total_verifications": session.query(VerificationMethod).count(),
            "total_nodes": session.query(OntologyNode).count(),
            "total_triples": session.query(OntologyTriple).count(),
        }


def fetch_hlr_detail(hlr_id):
    """Fetch all data needed for HLR detail page."""
    with get_session() as session:
        hlr = session.query(HighLevelRequirement).filter_by(id=hlr_id).first()
        if not hlr:
            return None

        llrs = []
        for llr in hlr.low_level_requirements:
            methods = [v.method for v in llr.verifications]
            llrs.append({
                "id": llr.id,
                "description": llr.description,
                "methods": methods,
            })

        all_triples = set(hlr.triples)
        for llr_obj in hlr.low_level_requirements:
            all_triples.update(llr_obj.triples)
        triples = [
            {
                "subject": t.subject.name,
                "predicate": t.predicate.name,
                "object": t.object.name,
            }
            for t in sorted(all_triples, key=lambda t: t.id)
        ]

        return {
            "id": hlr.id,
            "description": hlr.description,
            "component": hlr.component.name if hlr.component else None,
            "component_id": hlr.component_id,
            "llrs": llrs,
            "triples": triples,
        }


def fetch_llr_detail(llr_id):
    """Fetch all data needed for LLR detail page."""
    with get_session() as session:
        llr = session.query(LowLevelRequirement).filter_by(id=llr_id).first()
        if not llr:
            return None

        hlr = llr.high_level_requirement
        hlr_data = None
        if hlr:
            hlr_data = {
                "id": hlr.id,
                "description": hlr.description,
                "component": hlr.component.name if hlr.component else None,
            }

        verifications = []
        for v in llr.verifications:
            preconditions = [
                {
                    "member_qualified_name": c.member_qualified_name,
                    "operator": c.operator,
                    "expected_value": c.expected_value,
                }
                for c in sorted(
                    [c for c in v.conditions if c.phase == "pre"],
                    key=lambda c: c.order,
                )
            ]
            postconditions = [
                {
                    "member_qualified_name": c.member_qualified_name,
                    "operator": c.operator,
                    "expected_value": c.expected_value,
                }
                for c in sorted(
                    [c for c in v.conditions if c.phase == "post"],
                    key=lambda c: c.order,
                )
            ]
            actions = [
                {
                    "order": a.order,
                    "description": a.description,
                    "member_qualified_name": a.member_qualified_name,
                }
                for a in sorted(v.actions, key=lambda a: a.order)
            ]
            verifications.append({
                "id": v.id,
                "method": v.method,
                "test_name": v.test_name,
                "description": v.description,
                "preconditions": preconditions,
                "actions": actions,
                "postconditions": postconditions,
            })

        components = [c.name for c in llr.components]

        triples = [
            {
                "subject": t.subject.name,
                "predicate": t.predicate.name,
                "object": t.object.name,
            }
            for t in llr.triples
        ]

        return {
            "id": llr.id,
            "description": llr.description,
            "hlr": hlr_data,
            "verifications": verifications,
            "components": components,
            "triples": triples,
        }


def fetch_components_data():
    """Fetch all data needed for components page."""
    with get_session() as session:
        result = []
        for comp in session.query(Component).all():
            result.append({
                "id": comp.id,
                "name": comp.name,
                "namespace": comp.namespace or "",
                "language": repr(comp.language) if comp.language else None,
                "parent": comp.parent.name if comp.parent else None,
                "hlr_count": len(comp.high_level_requirements),
                "node_count": len(comp.ontology_nodes),
            })
        return result


def fetch_component_detail(component_id: int) -> dict | None:
    """Fetch full component detail including children, environment, requirements, and nodes."""
    with get_session() as session:
        comp = session.query(Component).filter_by(id=component_id).first()
        if not comp:
            return None

        # Children
        children = [
            {"id": c.id, "name": c.name, "namespace": c.namespace,
             "hlr_count": len(c.high_level_requirements),
             "node_count": len(c.ontology_nodes)}
            for c in comp.children
        ]

        # Environment (language, build systems, test frameworks, dep managers)
        env = None
        if comp.language:
            lang = comp.language
            env = {
                "language_id": lang.id,
                "language": repr(lang),
                "build_systems": [
                    {"name": bs.name, "config_file": bs.config_file, "version": bs.version}
                    for bs in lang.build_systems
                ],
                "test_frameworks": [
                    {"name": tf.name, "config_file": tf.config_file,
                     "discovery_path": tf.test_discovery_path}
                    for tf in lang.test_frameworks
                ],
                "dependency_managers": [
                    {
                        "id": dm.id,
                        "name": dm.name,
                        "manifest_file": dm.manifest_file,
                        "lock_file": dm.lock_file,
                        "dependencies": [
                            {"id": d.id, "name": d.name, "version": d.version, "is_dev": d.is_dev}
                            for d in dm.dependencies
                        ],
                    }
                    for dm in lang.dependency_managers
                ],
            }

        # HLRs in this component
        hlrs = [
            {"id": h.id, "description": h.description,
             "llr_count": len(h.low_level_requirements)}
            for h in comp.high_level_requirements
        ]

        # Ontology nodes (group by kind)
        node_kinds: dict[str, int] = {}
        nodes_sample = []
        for n in comp.ontology_nodes:
            node_kinds[n.kind] = node_kinds.get(n.kind, 0) + 1
            if len(nodes_sample) < 20:
                nodes_sample.append({
                    "id": n.id, "name": n.name,
                    "qualified_name": n.qualified_name,
                    "kind": n.kind,
                })

        return {
            "id": comp.id,
            "name": comp.name,
            "description": comp.description or "",
            "namespace": comp.namespace or "",
            "parent": {"id": comp.parent.id, "name": comp.parent.name} if comp.parent else None,
            "children": children,
            "environment": env,
            "hlrs": hlrs,
            "node_kinds": node_kinds,
            "nodes_sample": nodes_sample,
            "node_count": len(comp.ontology_nodes),
        }


def fetch_ontology_data():
    """Fetch all data needed for ontology page."""
    with get_session() as session:
        nodes = []
        kind_counts = {}
        for n in session.query(OntologyNode).all():
            kind_counts[n.kind] = kind_counts.get(n.kind, 0) + 1
            nodes.append({
                "name": n.name,
                "kind": n.kind,
                "qualified_name": n.qualified_name,
                "component": n.component.name if n.component else "-",
            })

        return {
            "nodes": nodes[:200],
            "kind_counts": kind_counts,
            "total_nodes": len(nodes),
            "total_triples": session.query(OntologyTriple).count(),
            "total_predicates": session.query(Predicate).count(),
        }


# ---------------------------------------------------------------------------
# Mutations — requirements
# ---------------------------------------------------------------------------

def fetch_components_options():
    """Return list of {id, name} for component dropdowns."""
    with get_session() as session:
        return [
            {"id": c.id, "name": c.name}
            for c in session.query(Component).order_by(Component.name).all()
        ]


def create_hlr(description: str, component_id: int | None = None) -> int:
    """Create a new HLR. Returns the new HLR id."""
    with get_session() as session:
        hlr = HighLevelRequirement(
            description=description,
            component_id=component_id or None,
        )
        session.add(hlr)
        session.flush()
        return hlr.id


def update_hlr(hlr_id: int, description: str, component_id: int | None = None) -> bool:
    """Update an HLR's description and component. Returns True on success."""
    with get_session() as session:
        hlr = session.query(HighLevelRequirement).filter_by(id=hlr_id).first()
        if not hlr:
            return False
        hlr.description = description
        hlr.component_id = component_id or None
        return True


def delete_hlr(hlr_id: int) -> bool:
    """Delete an HLR and its child LLRs. Returns True on success."""
    with get_session() as session:
        hlr = session.query(HighLevelRequirement).filter_by(id=hlr_id).first()
        if not hlr:
            return False
        # Delete child LLRs first (cascade handles verifications)
        for llr in hlr.low_level_requirements:
            session.delete(llr)
        session.delete(hlr)
        return True


def create_llr(hlr_id: int, description: str) -> int:
    """Create a new LLR under an HLR. Returns the new LLR id."""
    with get_session() as session:
        llr = LowLevelRequirement(
            high_level_requirement_id=hlr_id,
            description=description,
        )
        session.add(llr)
        session.flush()
        return llr.id


def decompose_hlr(hlr_id: int) -> dict:
    """Run the decomposition agent on an HLR and persist results.

    Returns dict with llrs_created and verifications_created.
    """
    from requirements.agents.decompose_hlr import decompose
    from requirements.services.persistence import persist_decomposition

    with get_session() as session:
        hlr = session.query(HighLevelRequirement).filter_by(id=hlr_id).first()
        if not hlr:
            raise ValueError(f"HLR {hlr_id} not found")

        siblings = session.query(HighLevelRequirement).filter(
            HighLevelRequirement.id != hlr_id,
        ).all()
        other_hlrs = [
            {
                "id": s.id,
                "description": s.description,
                "component__name": s.component.name if s.component else None,
            }
            for s in siblings
        ]

        decomposed = decompose(
            description=hlr.description,
            other_hlrs=other_hlrs,
            component=hlr.component.name if hlr.component else "",
            dependency_context=hlr.dependency_context,
        )

        result = persist_decomposition(session, hlr, decomposed.low_level_requirements)
        return {
            "llrs_created": result.llrs_created,
            "verifications_created": result.verifications_created,
        }


def update_llr(llr_id: int, description: str) -> bool:
    """Update an LLR's description. Returns True on success."""
    with get_session() as session:
        llr = session.query(LowLevelRequirement).filter_by(id=llr_id).first()
        if not llr:
            return False
        llr.description = description
        return True


def delete_llr(llr_id: int) -> bool:
    """Delete an LLR. Returns True on success."""
    with get_session() as session:
        llr = session.query(LowLevelRequirement).filter_by(id=llr_id).first()
        if not llr:
            return False
        session.delete(llr)
        return True


# ---------------------------------------------------------------------------
# Neo4j-backed graph data
# ---------------------------------------------------------------------------

def fetch_ontology_graph_data(
    kind_filter: str | None = None,
    search: str | None = None,
    component_id: int | None = None,
) -> dict:
    """Fetch design graph from Neo4j for Cytoscape.js rendering."""
    try:
        from db.neo4j_queries import fetch_design_graph
        return fetch_design_graph(kind_filter, search, component_id)
    except Exception:
        log.warning("Neo4j query failed — returning empty graph", exc_info=True)
        return {"nodes": [], "edges": []}


def fetch_codebase_graph_data(
    search: str | None = None,
    namespace_filter: str | None = None,
) -> dict:
    """Fetch the as-built codebase graph from Neo4j for Cytoscape.js rendering."""
    try:
        from db.neo4j_queries import fetch_codebase_graph
        return fetch_codebase_graph(search, namespace_filter)
    except Exception:
        log.warning("Neo4j codebase query failed — returning empty graph", exc_info=True)
        return {"nodes": [], "edges": []}


def fetch_hlr_graph_data(hlr_id: int, component_id: int | None = None) -> dict:
    """Fetch the ontology subgraph around an HLR for Cytoscape.js."""
    try:
        from db.neo4j_queries import fetch_hlr_subgraph
        return fetch_hlr_subgraph(hlr_id, component_id)
    except Exception:
        log.warning("Neo4j HLR subgraph query failed — returning empty graph", exc_info=True)
        return {"nodes": [], "edges": []}


def fetch_neighbourhood_graph_data(qualified_name: str) -> dict:
    """Fetch the 1-hop neighbourhood graph with collapsed members."""
    try:
        from db.neo4j_queries import fetch_neighbourhood_graph
        return fetch_neighbourhood_graph(qualified_name)
    except Exception:
        log.warning("Neo4j neighbourhood query failed", exc_info=True)
        return {"nodes": [], "edges": []}


def fetch_graph_node_detail(qualified_name: str) -> dict | None:
    """Fetch node detail from Neo4j (properties + relationships + requirements)."""
    try:
        from db.neo4j_queries import fetch_node_detail
        return fetch_node_detail(qualified_name)
    except Exception:
        log.warning("Neo4j node detail query failed", exc_info=True)
        return None


def fetch_node_detail_full(node_id: int) -> dict | None:
    """Fetch ontology node by SQLite id with all properties + Neo4j relationships."""
    with get_session() as session:
        node = session.query(OntologyNode).filter_by(id=node_id).first()
        if not node:
            return None

        node_data = {
            "id": node.id,
            "name": node.name,
            "qualified_name": node.qualified_name,
            "kind": node.kind,
            "specialization": node.specialization or "",
            "visibility": node.visibility or "",
            "description": node.description or "",
            "component": node.component.name if node.component else "",
            "component_id": node.component_id,
            "type_signature": node.type_signature or "",
            "argsstring": node.argsstring or "",
            "definition": node.definition or "",
            "file_path": node.file_path or "",
            "line_number": node.line_number,
            "refid": node.refid or "",
            "source_type": node.source_type or "",
            "is_static": node.is_static,
            "is_const": node.is_const,
            "is_virtual": node.is_virtual,
            "is_abstract": node.is_abstract,
            "is_final": node.is_final,
        }

    # Fetch Neo4j relationships if available
    neo4j_data = None
    if node_data["qualified_name"]:
        neo4j_data = fetch_graph_node_detail(node_data["qualified_name"])

    return {"node": node_data, "neo4j": neo4j_data}


def resolve_node_id_by_qualified_name(qualified_name: str) -> int | None:
    """Look up the SQLite id for an ontology node by qualified_name."""
    with get_session() as session:
        node = session.query(OntologyNode).filter_by(
            qualified_name=qualified_name
        ).first()
        return node.id if node else None


def update_member_type(qualified_name: str, type_signature: str) -> bool:
    """Update type_signature on an ontology node (and sync to Neo4j)."""
    with get_session() as session:
        node = session.query(OntologyNode).filter_by(
            qualified_name=qualified_name
        ).first()
        if not node:
            return False
        node.type_signature = type_signature
    # Also update Neo4j
    try:
        from db.neo4j import get_neo4j_session
        with get_neo4j_session() as ns:
            ns.run(
                "MATCH (n:Design {qualified_name: $qn}) SET n.type_signature = $ts",
                {"qn": qualified_name, "ts": type_signature},
            )
    except Exception:
        log.warning("Neo4j type_signature sync failed", exc_info=True)
    return True


# ---------------------------------------------------------------------------
# Component environment CRUD
# ---------------------------------------------------------------------------

def ensure_component_language(component_id: int, language_name: str, version: str = "") -> int:
    """Ensure a component has a language set, creating it if needed. Returns language id."""
    from db import get_or_create
    with get_session() as session:
        lang, _ = get_or_create(session, Language, defaults={"version": version}, name=language_name)
        comp = session.query(Component).filter_by(id=component_id).first()
        if comp and comp.language_id != lang.id:
            comp.language_id = lang.id
        return lang.id


def create_dependency_manager(
    language_id: int, name: str, manifest_file: str, lock_file: str = "",
) -> int:
    """Create a dependency manager. Returns the new id."""
    with get_session() as session:
        dm = DependencyManager(
            language_id=language_id,
            name=name,
            manifest_file=manifest_file,
            lock_file=lock_file,
        )
        session.add(dm)
        session.flush()
        return dm.id


def add_dependency(manager_id: int, name: str, version: str = "", is_dev: bool = False) -> int:
    """Add a dependency to a manager. Returns the new id."""
    with get_session() as session:
        dep = Dependency(
            manager_id=manager_id,
            name=name,
            version=version,
            is_dev=is_dev,
        )
        session.add(dep)
        session.flush()
        return dep.id


def delete_dependency(dep_id: int) -> bool:
    """Delete a dependency. Returns True on success."""
    with get_session() as session:
        dep = session.query(Dependency).filter_by(id=dep_id).first()
        if not dep:
            return False
        session.delete(dep)
        return True


def delete_dependency_manager(manager_id: int) -> bool:
    """Delete a dependency manager and its dependencies. Returns True on success."""
    with get_session() as session:
        dm = session.query(DependencyManager).filter_by(id=manager_id).first()
        if not dm:
            return False
        session.delete(dm)
        return True


# ---------------------------------------------------------------------------
# Dependency recommendations
# ---------------------------------------------------------------------------

def fetch_recommendations(component_id: int) -> list[dict]:
    """Fetch all dependency recommendations for a component."""
    with get_session() as session:
        recs = session.query(DependencyRecommendation).filter_by(
            component_id=component_id,
        ).order_by(DependencyRecommendation.status, DependencyRecommendation.name).all()
        return [
            {
                "id": r.id,
                "name": r.name,
                "github_url": r.github_url,
                "description": r.description,
                "version": r.version,
                "stars": r.stars,
                "license": r.license,
                "last_updated": r.last_updated,
                "pros": r.pros or [],
                "cons": r.cons or [],
                "relevant_hlrs": r.relevant_hlrs or [],
                "relevant_structures": r.relevant_structures or [],
                "summary": r.summary,
                "status": r.status,
            }
            for r in recs
        ]


def save_recommendations(component_id: int, summary: str, recommendations: list[dict]):
    """Save research results as pending recommendations, clearing previous pending ones."""
    with get_session() as session:
        # Remove old pending recommendations
        session.query(DependencyRecommendation).filter_by(
            component_id=component_id, status="pending",
        ).delete()
        session.flush()

        for rec in recommendations:
            session.add(DependencyRecommendation(
                component_id=component_id,
                name=rec.get("name", ""),
                github_url=rec.get("github_url", ""),
                description=rec.get("description", ""),
                version=rec.get("version", ""),
                stars=rec.get("stars", 0),
                license=rec.get("license", ""),
                last_updated=rec.get("last_updated", ""),
                pros=rec.get("pros"),
                cons=rec.get("cons"),
                relevant_hlrs=rec.get("relevant_hlrs"),
                relevant_structures=rec.get("relevant_structures"),
                summary=summary,
                status="pending",
            ))


def update_recommendation_status(rec_id: int, status: str) -> bool:
    """Update a recommendation's status (accepted/rejected). Returns True on success."""
    with get_session() as session:
        rec = session.query(DependencyRecommendation).filter_by(id=rec_id).first()
        if not rec:
            return False
        rec.status = status
        return True


def accept_recommendation(rec_id: int) -> bool:
    """Accept a recommendation: mark as accepted and add to dependency manager.

    If no dependency manager exists, creates one automatically.
    """
    from db import get_or_create

    with get_session() as session:
        rec = session.query(DependencyRecommendation).filter_by(id=rec_id).first()
        if not rec:
            return False
        rec.status = "accepted"

        # Find the component and ensure it has a dependency manager
        comp = session.query(Component).filter_by(id=rec.component_id).first()
        if not comp:
            return True  # status updated, but can't add dep

        # Ensure language exists
        if not comp.language:
            lang, _ = get_or_create(session, Language, name="C++")
            comp.language_id = lang.id
            session.flush()
            session.refresh(comp)

        lang = comp.language

        # Ensure dependency manager exists
        managers = lang.dependency_managers
        if not managers:
            dm = DependencyManager(
                language_id=lang.id,
                name="dependencies",
                manifest_file="dependencies.txt",
            )
            session.add(dm)
            session.flush()
        else:
            dm = managers[0]

        # Add the dependency
        existing = session.query(Dependency).filter_by(
            manager_id=dm.id, name=rec.name,
        ).first()
        if not existing:
            session.add(Dependency(
                manager_id=dm.id,
                name=rec.name,
                version=rec.version,
            ))
        return True


def fetch_pending_recommendations_summary() -> list[dict]:
    """Fetch components that have pending dependency recommendations.

    Returns list of {component_id, component_name, pending_count}.
    """
    with get_session() as session:
        pending = session.query(DependencyRecommendation).filter_by(status="pending").all()
        by_comp: dict[int, dict] = {}
        for r in pending:
            if r.component_id not in by_comp:
                comp = session.query(Component).filter_by(id=r.component_id).first()
                by_comp[r.component_id] = {
                    "component_id": r.component_id,
                    "component_name": comp.name if comp else "Unknown",
                    "pending_count": 0,
                }
            by_comp[r.component_id]["pending_count"] += 1
        return list(by_comp.values())
