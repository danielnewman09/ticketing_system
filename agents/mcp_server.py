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
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import transaction
from django.db.models import F

from mcp.server.fastmcp import FastMCP

from codebase.models import OntologyNode, OntologyTriple, Predicate
from codebase.schemas import DesignSchema
from components.models import Component, Dependency
from requirements.models import (
    HighLevelRequirement,
    LowLevelRequirement,
    VerificationMethod,
)
from requirements.schemas import LowLevelRequirementSchema, VerificationSchema
from requirements.services.persistence import (
    persist_decomposition,
    persist_design,
    persist_verification,
)

mcp = FastMCP("ticketing-system")


# ---------------------------------------------------------------------------
# Read tools — query current state
# ---------------------------------------------------------------------------

@mcp.tool()
def list_requirements() -> str:
    """List all HLRs with their LLRs and verification methods."""
    lines = []
    for hlr in HighLevelRequirement.objects.prefetch_related(
        "low_level_requirements__verifications",
    ).all():
        hlr_lines = [hlr.to_prompt_text(include_component=True)]
        for llr in hlr.low_level_requirements.all():
            hlr_lines.append(f"  {llr.to_prompt_text(include_verifications=True)}")
        lines.append("\n".join(hlr_lines))
    return "\n\n".join(lines)


@mcp.tool()
def list_ontology() -> str:
    """List all ontology nodes and triples."""
    nodes = [
        {"id": n.pk, "qualified_name": n.qualified_name, "kind": n.kind, "description": n.description}
        for n in OntologyNode.objects.all()
    ]
    triples = [
        {
            "id": t.pk,
            "subject": t.subject.qualified_name,
            "predicate": t.predicate.name,
            "object": t.object.qualified_name,
        }
        for t in OntologyTriple.objects.select_related("subject", "object", "predicate").all()
    ]
    predicates = list(Predicate.objects.values_list("name", flat=True))
    return json.dumps({"nodes": nodes, "triples": triples, "predicates": predicates}, indent=2)


@mcp.tool()
def get_graph_metrics() -> str:
    """Compute structural metrics for the requirements-ontology graph.

    Returns per-HLR cohesion data (connected components), per-node degree
    counts, predicate distribution, and orphan detection.
    """
    from agents.review.challenge_design import compute_graph_metrics, format_metrics_for_prompt

    hlrs = list(HighLevelRequirement.objects.values("id", "description"))
    llrs = list(LowLevelRequirement.objects.values(
        "id", "description",
    ).annotate(hlr_id=F("high_level_requirement_id")))
    nodes = list(OntologyNode.objects.values("id", "qualified_name", "kind", "description"))

    triples = []
    for t in OntologyTriple.objects.select_related("subject", "object", "predicate").all():
        triples.append({
            "id": t.id,
            "subject_qualified_name": t.subject.qualified_name,
            "predicate": t.predicate.name,
            "object_qualified_name": t.object.qualified_name,
        })

    hlr_triples = {}
    for hlr in HighLevelRequirement.objects.prefetch_related("triples").all():
        hlr_triples[hlr.id] = list(hlr.triples.values_list("id", flat=True))

    llr_triples = {}
    for llr in LowLevelRequirement.objects.prefetch_related("triples").all():
        llr_triples[llr.id] = list(llr.triples.values_list("id", flat=True))

    metrics = compute_graph_metrics(hlrs, llrs, nodes, triples, hlr_triples, llr_triples)
    return format_metrics_for_prompt(metrics)


@mcp.tool()
def list_component_dependencies(component_id: int) -> str:
    """List all dependencies available for a component's language.

    Follows the path: Component → Language → DependencyManager(s) → Dependency(ies).

    Args:
        component_id: The Component ID to look up.

    Returns:
        JSON with language info and flat list of dependencies.
    """
    component = Component.objects.select_related("language").filter(pk=component_id).first()
    if not component:
        return json.dumps({"error": f"Component {component_id} not found"})
    if not component.language:
        return json.dumps({"error": f"Component '{component.name}' has no language assigned"})

    language = component.language
    deps = Dependency.objects.filter(
        manager__language=language,
    ).select_related("manager").order_by("name")

    return json.dumps({
        "component_id": component.pk,
        "component_name": component.name,
        "language": str(language),
        "language_id": language.pk,
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
    """Save a dependency assessment to an HLR's dependency_context field.

    Args:
        hlr_id: The HighLevelRequirement ID.
        assessment: Dict with keys: recommendation ("use_existing", "add_new",
            or "none"), dependency_name, relevant_structures, rationale.
    """
    hlr = HighLevelRequirement.objects.filter(pk=hlr_id).first()
    if not hlr:
        return json.dumps({"error": f"HLR {hlr_id} not found"})

    hlr.dependency_context = assessment
    hlr.save(update_fields=["dependency_context"])

    return json.dumps({
        "hlr_id": hlr_id,
        "message": f"Saved dependency assessment for HLR {hlr_id}",
        "recommendation": assessment.get("recommendation", ""),
    })


@mcp.tool()
def list_predicates() -> str:
    """List all available predicates for ontology triples."""
    predicates = list(Predicate.objects.values("name", "description"))
    return json.dumps(predicates, indent=2)


# ---------------------------------------------------------------------------
# Write tools — persist structured results
# ---------------------------------------------------------------------------

@mcp.tool()
def save_decomposed_requirement(
    hlr_description: str,
    low_level_requirements: list[dict],
) -> str:
    """Save a decomposed high-level requirement with its LLRs and verifications.

    Args:
        hlr_description: The high-level requirement description.
        low_level_requirements: List of LLRs, each with:
            - description: str
            - verifications: list of {method, test_name, description}
              where method is one of "automated", "review", "inspection"
    """
    with transaction.atomic():
        hlr = HighLevelRequirement.objects.create(description=hlr_description)
        llrs = [LowLevelRequirementSchema.model_validate(d) for d in low_level_requirements]
        result = persist_decomposition(hlr, llrs)

    return json.dumps({
        "hlr_id": hlr.pk,
        "llr_count": result.llrs_created,
        "message": f"Created HLR {hlr.pk} with {result.llrs_created} LLRs",
    })


@mcp.tool()
def save_ontology_design(
    nodes: list[dict],
    triples: list[dict],
    requirement_links: list[dict] | None = None,
) -> str:
    """Save ontology nodes, triples, and requirement-to-triple links.

    Args:
        nodes: List of ontology nodes, each with:
            - kind: one of the NODE_KINDS defined in codebase.models.ontology
            - name: short name (e.g., "Calculator")
            - qualified_name: fully qualified (e.g., "calc::Calculator")
            - description: what this entity is responsible for
        triples: List of triples, each with:
            - subject_qualified_name: str
            - predicate: must match a Predicate name in the database
            - object_qualified_name: str
        requirement_links: Optional list linking requirements to triples, each with:
            - requirement_type: "hlr" or "llr"
            - requirement_id: int
            - triple_index: 0-based index into the triples array
    """
    design = DesignSchema.model_validate({
        "nodes": nodes,
        "triples": triples,
        "requirement_links": requirement_links or [],
    })
    result = persist_design(design)

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
    """Save fleshed-out verification procedures for an LLR, replacing any existing ones.

    Args:
        llr_id: The LowLevelRequirement ID to update.
        verifications: List of verification methods, each with:
            - method: one of "automated", "review", "inspection"
            - test_name: snake_case test function name
            - description: what this verification does
            - preconditions: list of {member_qualified_name, operator, expected_value}
            - actions: list of {description, member_qualified_name}
            - postconditions: list of {member_qualified_name, operator, expected_value}
    """
    llr = LowLevelRequirement.objects.get(pk=llr_id)
    schemas = [VerificationSchema.model_validate(v) for v in verifications]
    result = persist_verification(llr, schemas)

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
    """Apply a remediation plan to fix design suitability issues.

    Args:
        split_hlrs: List of HLR splits, each with:
            - original_hlr_id: int
            - new_hlrs: list of {description, reassign_llr_ids, new_llrs}
        new_hlrs: List of new HLRs to create, each with:
            - description: str
            - new_llrs: list of {description, verifications: [{method, test_name, description}]}
        new_llrs: List of new LLRs under existing HLRs, each with:
            - hlr_id: int
            - description: str
            - verifications: list of {method, test_name, description}
        remove_llr_ids: List of LLR IDs to delete.
        new_nodes: List of ontology nodes to add (kind, name, qualified_name, description).
        remove_node_qualified_names: Qualified names of nodes to remove.
        new_triples: Triples to add (subject_qualified_name, predicate, object_qualified_name).
        remove_triples: Triples to remove (subject_qualified_name, predicate, object_qualified_name).
    """
    changes = []

    with transaction.atomic():
        # Remove LLRs
        if remove_llr_ids:
            count = LowLevelRequirement.objects.filter(pk__in=remove_llr_ids).delete()[0]
            changes.append(f"Removed {count} LLR(s)")

        # Remove triples
        for rt in (remove_triples or []):
            count = OntologyTriple.objects.filter(
                subject__qualified_name=rt["subject_qualified_name"],
                predicate__name=rt["predicate"],
                object__qualified_name=rt["object_qualified_name"],
            ).delete()[0]
            if count:
                changes.append(f"Removed triple: {rt['subject_qualified_name']} --{rt['predicate']}--> {rt['object_qualified_name']}")

        # Remove nodes
        if remove_node_qualified_names:
            count = OntologyNode.objects.filter(
                qualified_name__in=remove_node_qualified_names,
            ).delete()[0]
            changes.append(f"Removed {count} node(s)")

        # Split HLRs
        for split in (split_hlrs or []):
            old_hlr = HighLevelRequirement.objects.filter(pk=split["original_hlr_id"]).first()
            if not old_hlr:
                changes.append(f"Split skipped: HLR {split['original_hlr_id']} not found")
                continue
            for new_hlr_data in split["new_hlrs"]:
                hlr = HighLevelRequirement.objects.create(description=new_hlr_data["description"])
                if new_hlr_data.get("reassign_llr_ids"):
                    LowLevelRequirement.objects.filter(
                        pk__in=new_hlr_data["reassign_llr_ids"],
                    ).update(high_level_requirement=hlr)
                for llr_data in new_hlr_data.get("new_llrs", []):
                    llr = LowLevelRequirement.objects.create(
                        high_level_requirement=hlr, description=llr_data["description"],
                    )
                    for v in llr_data.get("verifications", []):
                        VerificationMethod.objects.create(
                            low_level_requirement=llr, method=v["method"],
                            test_name=v.get("test_name", ""), description=v.get("description", ""),
                        )
                changes.append(f"Created HLR {hlr.pk}: {hlr.description[:60]}")
            old_hlr.delete()
            changes.append(f"Removed original HLR {split['original_hlr_id']}")

        # New HLRs
        for new_hlr_data in (new_hlrs or []):
            hlr = HighLevelRequirement.objects.create(description=new_hlr_data["description"])
            for llr_data in new_hlr_data.get("new_llrs", []):
                llr = LowLevelRequirement.objects.create(
                    high_level_requirement=hlr, description=llr_data["description"],
                )
                for v in llr_data.get("verifications", []):
                    VerificationMethod.objects.create(
                        low_level_requirement=llr, method=v["method"],
                        test_name=v.get("test_name", ""), description=v.get("description", ""),
                    )
            changes.append(f"Created HLR {hlr.pk} with {hlr.low_level_requirements.count()} LLRs")

        # New LLRs under existing HLRs
        for new_llr in (new_llrs or []):
            hlr = HighLevelRequirement.objects.filter(pk=new_llr["hlr_id"]).first()
            if not hlr:
                changes.append(f"New LLR skipped: HLR {new_llr['hlr_id']} not found")
                continue
            llr = LowLevelRequirement.objects.create(
                high_level_requirement=hlr, description=new_llr["description"],
            )
            for v in new_llr.get("verifications", []):
                VerificationMethod.objects.create(
                    low_level_requirement=llr, method=v["method"],
                    test_name=v.get("test_name", ""), description=v.get("description", ""),
                )
            changes.append(f"Created LLR {llr.pk} under HLR {hlr.pk}")

        # New nodes
        for node_data in (new_nodes or []):
            node, created = OntologyNode.objects.get_or_create(
                qualified_name=node_data["qualified_name"],
                defaults={
                    "kind": node_data["kind"], "name": node_data["name"],
                    "description": node_data.get("description", ""),
                },
            )
            if created:
                changes.append(f"Created node: {node.qualified_name}")

        # New triples
        for t in (new_triples or []):
            subj = OntologyNode.objects.filter(qualified_name=t["subject_qualified_name"]).first()
            obj = OntologyNode.objects.filter(qualified_name=t["object_qualified_name"]).first()
            pred = Predicate.objects.filter(name=t["predicate"]).first()
            if subj and obj and pred:
                _, created = OntologyTriple.objects.get_or_create(
                    subject=subj, predicate=pred, object=obj,
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
    Predicate.ensure_defaults()
    predicates = list(Predicate.objects.values("name", "description"))
    return json.dumps(predicates, indent=2)


if __name__ == "__main__":
    mcp.run()
