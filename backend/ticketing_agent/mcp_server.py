"""
MCP server exposing the ticketing system's persistence layer as tools.

Claude Code acts as the LLM (the reasoning engine). These tools provide:
- Read tools: query current state (requirements, ontology, graph metrics)
- Write tools: persist structured results (decompositions, designs, verifications, remediations)

No Anthropic API calls are made here — Claude Code IS the model.

Phase 3: All verification data lives in Neo4j via VerificationRepository.
"""

import json

from mcp.server.fastmcp import FastMCP

from backend.db import init_db, get_session, get_or_create
from backend.db.models import (
    Component,
    Dependency,
    OntologyNode,
    OntologyTriple,
    Predicate,
)
from backend.codebase.schemas import DesignSchema
from backend.db.neo4j.repositories.requirement import RequirementRepository
from backend.db.neo4j.repositories.verification import VerificationRepository
from backend.requirements.schemas import LowLevelRequirementSchema, VerificationSchema
from backend.requirements.services.persistence import (
    persist_decomposition,
    persist_design,
    persist_verification,
)
from services.dependencies import get_neo4j

init_db()
mcp = FastMCP("ticketing-system")


def _get_component_name(component_id: int | None) -> str | None:
    """Look up a component name by ID from SQLite."""
    if component_id is None:
        return None
    try:
        from backend.db.models import Component
        with get_session() as session:
            comp = session.query(Component).filter_by(id=component_id).first()
            return comp.name if comp else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Read tools — query current state
# ---------------------------------------------------------------------------


@mcp.tool()
def list_requirements() -> str:
    """List all HLRs with their LLRs and verification methods."""
    with get_neo4j().session() as ns:
        repo = RequirementRepository(ns)
        ver_repo = VerificationRepository(ns)
        hlrs_neo4j = repo.list_hlrs()
        all_llrs = repo.list_llrs()

        ver_by_llr: dict[int, list[str]] = {}
        for llr in all_llrs:
            vms = ver_repo.list_verifications(llr.id)
            ver_by_llr[llr.id] = [vm.method for vm in vms]

    lines = []
    for hlr in hlrs_neo4j:
        comp_name = _get_component_name(hlr.component_id) if hlr.component_id else None
        hlr_line = f"HLR {hlr.id}: {hlr.description}"
        if comp_name:
            hlr_line += f" [Component: {comp_name}]"
        hlr_lines = [hlr_line]
        for llr in all_llrs:
            if llr.high_level_requirement_id == hlr.id:
                methods = ver_by_llr.get(llr.id, [])
                methods_str = f" (methods: {', '.join(methods)})" if methods else ""
                hlr_lines.append(f"  LLR {llr.id}: {llr.description}{methods_str}")
        lines.append("\n".join(hlr_lines))
    return "\n\n".join(lines)


@mcp.tool()
def list_ontology() -> str:
    """List all ontology nodes and triples."""
    with get_session() as session:
        nodes = [
            {
                "id": n.id,
                "qualified_name": n.qualified_name,
                "kind": n.kind,
                "description": n.description,
            }
            for n in session.query(OntologyNode).all()
        ]
        triples = [
            {
                "id": t.id,
                "subject": t.subject.qualified_name,
                "predicate": t.predicate.name,
                "object": t.object.qualified_name,
            }
            for t in session.query(OntologyTriple).all()
        ]
        predicates = [name for (name,) in session.query(Predicate.name).all()]
        return json.dumps({"nodes": nodes, "triples": triples, "predicates": predicates}, indent=2)


@mcp.tool()
def list_component_dependencies(component_id: int) -> str:
    """List all dependencies available for a component's language."""
    with get_session() as session:
        component = session.query(Component).filter_by(id=component_id).first()
        if not component:
            return json.dumps({"error": f"Component {component_id} not found"})
        if not component.language:
            return json.dumps({"error": f"Component '{component.name}' has no language assigned"})

        language = component.language
        deps = (
            session.query(Dependency)
            .filter(Dependency.manager.has(language_id=language.id))
            .order_by(Dependency.name)
            .all()
        )

        return json.dumps(
            {
                "component_id": component.id,
                "component_name": component.name,
                "language": repr(language),
                "language_id": language.id,
                "dependencies": [
                    {
                        "name": d.name,
                        "version": d.version,
                        "is_dev": d.is_dev,
                        "manager_name": d.manager.name,
                    }
                    for d in deps
                ],
            },
            indent=2,
        )


@mcp.tool()
def save_dependency_assessment(hlr_id: int, assessment: dict) -> str:
    """Save a dependency assessment to an HLR's dependency_context field."""
    with get_neo4j().session() as ns:
        repo = RequirementRepository(ns)
        hlr = repo.update_hlr(hlr_id, dependency_context=assessment)
        if not hlr:
            return json.dumps({"error": f"HLR {hlr_id} not found"})

    return json.dumps(
        {
            "hlr_id": hlr_id,
            "message": f"Saved dependency assessment for HLR {hlr_id}",
            "recommendation": assessment.get("recommendation", ""),
        }
    )


@mcp.tool()
def list_predicates() -> str:
    """List all available predicates for ontology triples."""
    with get_session() as session:
        predicates = [
            {"name": p.name, "description": p.description} for p in session.query(Predicate).all()
        ]
        return json.dumps(predicates, indent=2)


# ---------------------------------------------------------------------------
# Write tools — persist structured results
# ---------------------------------------------------------------------------


@mcp.tool()
def save_decomposed_requirement(
    hlr_description: str,
    low_level_requirements: list[dict],
) -> str:
    """Save a decomposed high-level requirement with its LLRs and verifications."""
    from codegraph.neo4j import Neo4jConnection
    from backend.db.neo4j.constraints import ensure_ticketing_constraints
    neo4j_conn = Neo4jConnection()
    ensure_ticketing_constraints(neo4j_conn)

    with get_neo4j().session() as ns:
        repo = RequirementRepository(ns)
        hlr = repo.create_hlr(description=hlr_description)
        llrs = [LowLevelRequirementSchema.model_validate(d) for d in low_level_requirements]
        result = persist_decomposition(ns, hlr.id, llrs)

    return json.dumps(
        {
            "hlr_id": hlr.id,
            "llr_count": result.llrs_created,
            "message": f"Created HLR {hlr.id} with {result.llrs_created} LLRs",
        }
    )


@mcp.tool()
def save_ontology_design(
    nodes: list[dict],
    triples: list[dict],
    requirement_links: list[dict] | None = None,
) -> str:
    """Save ontology nodes, triples, and requirement links to Neo4j."""
    with get_neo4j().session() as neo4j_session:
        design = DesignSchema.model_validate(
            {
                "nodes": nodes,
                "triples": triples,
                "requirement_links": requirement_links or [],
            }
        )
        result = persist_design(design, neo4j_session)

        return json.dumps(
            {
                "nodes_created": result.nodes_created,
                "triples_created": result.triples_created,
                "triples_skipped": result.triples_skipped,
                "requirement_links_applied": result.links_applied,
            }
        )


@mcp.tool()
def save_verification(
    llr_id: int,
    verifications: list[dict],
) -> str:
    """Save fleshed-out verification procedures for an LLR, replacing any existing ones."""
    with get_neo4j().session() as ns:
        schemas = [VerificationSchema.model_validate(v) for v in verifications]
        result = persist_verification(ns, llr_id, schemas)

        return json.dumps(
            {
                "llr_id": llr_id,
                "verifications_saved": result.verifications_saved,
                "conditions_created": result.conditions_created,
                "actions_created": result.actions_created,
            }
        )


@mcp.tool()
def ensure_predicates() -> str:
    """Ensure default UML-aligned predicates exist in the database."""
    with get_session() as session:
        Predicate.ensure_defaults(session)
        predicates = [
            {"name": p.name, "description": p.description} for p in session.query(Predicate).all()
        ]
        return json.dumps(predicates, indent=2)


# ---------------------------------------------------------------------------
# Codebase dependency query tools (delegated to doxygen_index)
# ---------------------------------------------------------------------------

_codebase_tools = None


def _get_codebase_tools():
    """Lazy singleton for DependencyGraphTools from doxygen_index."""
    global _codebase_tools
    if _codebase_tools is None:
        from doxygen_index.tools import create_toolset
        from codegraph.neo4j import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

        _codebase_tools = create_toolset(
            uri=NEO4J_URI,
            user=NEO4J_USER,
            password=NEO4J_PASSWORD,
        )
    return _codebase_tools


@mcp.tool()
def codebase_list_sources() -> str:
    """List all indexed dependency sources and their symbol counts."""
    try:
        results = _get_codebase_tools().list_sources()
        return json.dumps(results, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": f"Codebase query failed: {e}"})


@mcp.tool()
def codebase_search_symbols(query: str, source: str | None = None, limit: int = 20) -> str:
    """Full-text search across all codebase symbols (classes, functions, variables).

    Args:
        query: Search term (supports Lucene syntax: AND, OR, quotes, ~fuzzy)
        source: Optional dependency filter (e.g. "eigen", "sdl")
        limit: Maximum results (default 20)
    """
    try:
        results = _get_codebase_tools().search_symbols(query, source=source, limit=limit)
        return json.dumps(results, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": f"Codebase search failed: {e}"})


@mcp.tool()
def codebase_get_compound(name: str, source: str | None = None) -> str:
    """Get full details of a class/struct and all its members.

    Args:
        name: Exact or qualified name (e.g. "Matrix3d", "Eigen::Matrix3d")
        source: Optional dependency filter
    """
    try:
        results = _get_codebase_tools().get_compound(name, source=source)
        return json.dumps(results, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": f"Codebase compound query failed: {e}"})


@mcp.tool()
def codebase_get_member(name: str, source: str | None = None, fuzzy: bool = False) -> str:
    """Get detailed info on a specific function, variable, or enum.

    Args:
        name: Exact or qualified name (e.g. "CreateContext", "ImGui::Begin")
        source: Optional dependency filter
        fuzzy: If true, match names containing the term
    """
    try:
        results = _get_codebase_tools().get_member(name, source=source, fuzzy=fuzzy)
        return json.dumps(results, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": f"Codebase member query failed: {e}"})


@mcp.tool()
def codebase_browse_namespace(name: str, source: str | None = None, limit: int = 50) -> str:
    """List classes and free functions in a namespace.

    Args:
        name: Namespace name (e.g. "Eigen", "ImGui")
        source: Optional dependency filter
        limit: Maximum results per category
    """
    try:
        results = _get_codebase_tools().browse_namespace(name, source=source, limit=limit)
        return json.dumps(results, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": f"Codebase namespace query failed: {e}"})


@mcp.tool()
def codebase_find_inheritance(name: str, direction: str = "both", max_depth: int = 5) -> str:
    """Explore class inheritance hierarchy.

    Args:
        name: Exact or qualified class name
        direction: "up" (base classes), "down" (derived), or "both"
        max_depth: Maximum traversal depth
    """
    try:
        results = _get_codebase_tools().find_inheritance(
            name, direction=direction, max_depth=max_depth
        )
        return json.dumps(results, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": f"Codebase inheritance query failed: {e}"})


@mcp.tool()
def codebase_find_callers_and_callees(name: str, direction: str = "both", limit: int = 30) -> str:
    """Explore call graph around a function.

    Args:
        name: Exact or qualified function name
        direction: "callers", "callees", or "both"
        limit: Maximum results per direction
    """
    try:
        results = _get_codebase_tools().find_callers_and_callees(
            name, direction=direction, limit=limit
        )
        return json.dumps(results, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": f"Codebase call graph query failed: {e}"})


@mcp.tool()
def codebase_get_include_chain(header: str) -> str:
    """Find which header files are needed for a given header.

    Args:
        header: Header file name (e.g. "imgui.h", "Eigen/Dense")
    """
    try:
        results = _get_codebase_tools().get_include_chain(header)
        return json.dumps(results, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": f"Codebase include chain query failed: {e}"})


if __name__ == "__main__":
    mcp.run()
