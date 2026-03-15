"""
MCP server exposing the ticketing system's persistence layer as tools.

Claude Code acts as the LLM (the reasoning engine). These tools provide:
- Read tools: query current state (requirements, ontology, graph metrics)
- Write tools: persist structured results (decompositions, designs, verifications, remediations)

No Anthropic API calls are made here — Claude Code IS the model.

Run with:
    python -m agents.mcp_server
"""

import json

from mcp.server.fastmcp import FastMCP

from db import init_db, get_session, get_or_create
from db.models import (
    Component,
    Dependency,
    HighLevelRequirement,
    LowLevelRequirement,
    OntologyNode,
    OntologyTriple,
    Predicate,
    VerificationMethod,
)
from codebase.schemas import DesignSchema
from requirements.schemas import LowLevelRequirementSchema, VerificationSchema
from requirements.services.persistence import (
    persist_decomposition,
    persist_design,
    persist_verification,
)

init_db()
mcp = FastMCP("ticketing-system")


# ---------------------------------------------------------------------------
# Read tools — query current state
# ---------------------------------------------------------------------------

@mcp.tool()
def list_requirements() -> str:
    """List all HLRs with their LLRs and verification methods."""
    with get_session() as session:
        lines = []
        for hlr in session.query(HighLevelRequirement).all():
            hlr_lines = [hlr.to_prompt_text(include_component=True)]
            for llr in hlr.low_level_requirements:
                hlr_lines.append(f"  {llr.to_prompt_text(include_verifications=True)}")
            lines.append("\n".join(hlr_lines))
        return "\n\n".join(lines)


@mcp.tool()
def list_ontology() -> str:
    """List all ontology nodes and triples."""
    with get_session() as session:
        nodes = [
            {"id": n.id, "qualified_name": n.qualified_name, "kind": n.kind, "description": n.description}
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
def get_graph_metrics() -> str:
    """Compute structural metrics for the requirements-ontology graph."""
    from agents.review.challenge_design import compute_graph_metrics, format_metrics_for_prompt

    with get_session() as session:
        hlrs = [{"id": h.id, "description": h.description} for h in session.query(HighLevelRequirement).all()]
        llrs = [
            {"id": l.id, "description": l.description, "hlr_id": l.high_level_requirement_id}
            for l in session.query(LowLevelRequirement).all()
        ]
        nodes = [
            {"id": n.id, "qualified_name": n.qualified_name, "kind": n.kind, "description": n.description}
            for n in session.query(OntologyNode).all()
        ]

        triples = []
        for t in session.query(OntologyTriple).all():
            triples.append({
                "id": t.id,
                "subject_qualified_name": t.subject.qualified_name,
                "predicate": t.predicate.name,
                "object_qualified_name": t.object.qualified_name,
            })

        hlr_triples = {}
        for hlr in session.query(HighLevelRequirement).all():
            hlr_triples[hlr.id] = [t.id for t in hlr.triples]

        llr_triples = {}
        for llr in session.query(LowLevelRequirement).all():
            llr_triples[llr.id] = [t.id for t in llr.triples]

    metrics = compute_graph_metrics(hlrs, llrs, nodes, triples, hlr_triples, llr_triples)
    return format_metrics_for_prompt(metrics)


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

        return json.dumps({
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
        }, indent=2)


@mcp.tool()
def save_dependency_assessment(hlr_id: int, assessment: dict) -> str:
    """Save a dependency assessment to an HLR's dependency_context field."""
    with get_session() as session:
        hlr = session.query(HighLevelRequirement).filter_by(id=hlr_id).first()
        if not hlr:
            return json.dumps({"error": f"HLR {hlr_id} not found"})

        hlr.dependency_context = assessment

        return json.dumps({
            "hlr_id": hlr_id,
            "message": f"Saved dependency assessment for HLR {hlr_id}",
            "recommendation": assessment.get("recommendation", ""),
        })


@mcp.tool()
def list_predicates() -> str:
    """List all available predicates for ontology triples."""
    with get_session() as session:
        predicates = [
            {"name": p.name, "description": p.description}
            for p in session.query(Predicate).all()
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
    with get_session() as session:
        hlr = HighLevelRequirement(description=hlr_description)
        session.add(hlr)
        session.flush()
        llrs = [LowLevelRequirementSchema.model_validate(d) for d in low_level_requirements]
        result = persist_decomposition(session, hlr, llrs)

        return json.dumps({
            "hlr_id": hlr.id,
            "llr_count": result.llrs_created,
            "message": f"Created HLR {hlr.id} with {result.llrs_created} LLRs",
        })


@mcp.tool()
def save_ontology_design(
    nodes: list[dict],
    triples: list[dict],
    requirement_links: list[dict] | None = None,
) -> str:
    """Save ontology nodes, triples, and requirement-to-triple links."""
    with get_session() as session:
        design = DesignSchema.model_validate({
            "nodes": nodes,
            "triples": triples,
            "requirement_links": requirement_links or [],
        })
        result = persist_design(session, design)

        return json.dumps({
            "nodes_created": result.nodes_created,
            "triples_created": result.triples_created,
            "triples_skipped": result.triples_skipped,
            "requirement_links_applied": result.links_applied,
        })


@mcp.tool()
def save_verification(
    llr_id: int,
    verifications: list[dict],
) -> str:
    """Save fleshed-out verification procedures for an LLR, replacing any existing ones."""
    with get_session() as session:
        llr = session.query(LowLevelRequirement).filter_by(id=llr_id).first()
        if not llr:
            return json.dumps({"error": f"LLR {llr_id} not found"})
        schemas = [VerificationSchema.model_validate(v) for v in verifications]
        result = persist_verification(session, llr, schemas)

        return json.dumps({
            "llr_id": llr_id,
            "verifications_saved": result.verifications_saved,
            "conditions_created": result.conditions_created,
            "actions_created": result.actions_created,
        })


@mcp.tool()
def apply_remediation(
    split_hlrs: list[dict] | None = None,
    new_hlrs: list[dict] | None = None,
    new_llrs: list[dict] | None = None,
    remove_llr_ids: list[int] | None = None,
    new_nodes: list[dict] | None = None,
    remove_node_qualified_names: list[str] | None = None,
    new_triples: list[dict] | None = None,
    remove_triples: list[dict] | None = None,
) -> str:
    """Apply a remediation plan to fix design suitability issues."""
    changes = []

    with get_session() as session:
        # Remove LLRs
        if remove_llr_ids:
            count = session.query(LowLevelRequirement).filter(
                LowLevelRequirement.id.in_(remove_llr_ids)
            ).delete(synchronize_session="fetch")
            changes.append(f"Removed {count} LLR(s)")

        # Remove triples
        for rt in (remove_triples or []):
            triples = (
                session.query(OntologyTriple)
                .join(OntologyNode, OntologyTriple.subject_id == OntologyNode.id)
                .filter(OntologyNode.qualified_name == rt["subject_qualified_name"])
                .join(Predicate, OntologyTriple.predicate_id == Predicate.id)
                .filter(Predicate.name == rt["predicate"])
            ).all()
            for t in triples:
                if t.object.qualified_name == rt["object_qualified_name"]:
                    session.delete(t)
                    changes.append(f"Removed triple: {rt['subject_qualified_name']} --{rt['predicate']}--> {rt['object_qualified_name']}")

        # Remove nodes
        if remove_node_qualified_names:
            count = session.query(OntologyNode).filter(
                OntologyNode.qualified_name.in_(remove_node_qualified_names)
            ).delete(synchronize_session="fetch")
            changes.append(f"Removed {count} node(s)")

        # Split HLRs
        for split in (split_hlrs or []):
            old_hlr = session.query(HighLevelRequirement).filter_by(id=split["original_hlr_id"]).first()
            if not old_hlr:
                changes.append(f"Split skipped: HLR {split['original_hlr_id']} not found")
                continue
            for new_hlr_data in split["new_hlrs"]:
                hlr = HighLevelRequirement(description=new_hlr_data["description"])
                session.add(hlr)
                session.flush()
                if new_hlr_data.get("reassign_llr_ids"):
                    session.query(LowLevelRequirement).filter(
                        LowLevelRequirement.id.in_(new_hlr_data["reassign_llr_ids"])
                    ).update({"high_level_requirement_id": hlr.id}, synchronize_session="fetch")
                for llr_data in new_hlr_data.get("new_llrs", []):
                    llr = LowLevelRequirement(
                        high_level_requirement=hlr, description=llr_data["description"],
                    )
                    session.add(llr)
                    session.flush()
                    for v in llr_data.get("verifications", []):
                        vm = VerificationMethod(
                            low_level_requirement=llr, method=v["method"],
                            test_name=v.get("test_name", ""), description=v.get("description", ""),
                        )
                        session.add(vm)
                changes.append(f"Created HLR {hlr.id}: {hlr.description[:60]}")
            session.delete(old_hlr)
            changes.append(f"Removed original HLR {split['original_hlr_id']}")

        # New HLRs
        for new_hlr_data in (new_hlrs or []):
            hlr = HighLevelRequirement(description=new_hlr_data["description"])
            session.add(hlr)
            session.flush()
            for llr_data in new_hlr_data.get("new_llrs", []):
                llr = LowLevelRequirement(
                    high_level_requirement=hlr, description=llr_data["description"],
                )
                session.add(llr)
                session.flush()
                for v in llr_data.get("verifications", []):
                    vm = VerificationMethod(
                        low_level_requirement=llr, method=v["method"],
                        test_name=v.get("test_name", ""), description=v.get("description", ""),
                    )
                    session.add(vm)
            changes.append(f"Created HLR {hlr.id} with LLRs")

        # New LLRs under existing HLRs
        for new_llr in (new_llrs or []):
            hlr = session.query(HighLevelRequirement).filter_by(id=new_llr["hlr_id"]).first()
            if not hlr:
                changes.append(f"New LLR skipped: HLR {new_llr['hlr_id']} not found")
                continue
            llr = LowLevelRequirement(
                high_level_requirement=hlr, description=new_llr["description"],
            )
            session.add(llr)
            session.flush()
            for v in new_llr.get("verifications", []):
                vm = VerificationMethod(
                    low_level_requirement=llr, method=v["method"],
                    test_name=v.get("test_name", ""), description=v.get("description", ""),
                )
                session.add(vm)
            changes.append(f"Created LLR {llr.id} under HLR {hlr.id}")

        # New nodes
        for node_data in (new_nodes or []):
            node, created = get_or_create(
                session, OntologyNode,
                defaults={
                    "kind": node_data["kind"], "name": node_data["name"],
                    "description": node_data.get("description", ""),
                },
                qualified_name=node_data["qualified_name"],
            )
            if created:
                changes.append(f"Created node: {node.qualified_name}")

        # New triples
        for t in (new_triples or []):
            subj = session.query(OntologyNode).filter_by(qualified_name=t["subject_qualified_name"]).first()
            obj = session.query(OntologyNode).filter_by(qualified_name=t["object_qualified_name"]).first()
            pred = session.query(Predicate).filter_by(name=t["predicate"]).first()
            if subj and obj and pred:
                _, created = get_or_create(
                    session, OntologyTriple,
                    subject_id=subj.id, predicate_id=pred.id, object_id=obj.id,
                )
                if created:
                    changes.append(f"Created triple: {subj.name} --{pred.name}--> {obj.name}")
            else:
                missing = []
                if not subj:
                    missing.append(f"subject '{t['subject_qualified_name']}'")
                if not pred:
                    missing.append(f"predicate '{t['predicate']}'")
                if not obj:
                    missing.append(f"object '{t['object_qualified_name']}'")
                changes.append(f"Triple skipped — could not resolve {', '.join(missing)}")

    return json.dumps({"changes": changes, "total": len(changes)})


@mcp.tool()
def ensure_predicates() -> str:
    """Ensure default UML-aligned predicates exist in the database."""
    with get_session() as session:
        Predicate.ensure_defaults(session)
        predicates = [
            {"name": p.name, "description": p.description}
            for p in session.query(Predicate).all()
        ]
        return json.dumps(predicates, indent=2)


if __name__ == "__main__":
    mcp.run()
