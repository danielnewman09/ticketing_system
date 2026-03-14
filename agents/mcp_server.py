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
from requirements.models import (
    HighLevelRequirement,
    LowLevelRequirement,
    VerificationAction,
    VerificationCondition,
    VerificationMethod,
)

mcp = FastMCP("ticketing-system")


# ---------------------------------------------------------------------------
# Read tools — query current state
# ---------------------------------------------------------------------------

@mcp.tool()
def list_requirements() -> str:
    """List all HLRs with their LLRs and verification methods."""
    output = []
    for hlr in HighLevelRequirement.objects.prefetch_related(
        "low_level_requirements__verifications",
    ).all():
        hlr_data = {"id": hlr.pk, "description": hlr.description, "llrs": []}
        for llr in hlr.low_level_requirements.all():
            llr_data = {
                "id": llr.pk,
                "description": llr.description,
                "verifications": [
                    {"method": v.method, "test_name": v.test_name, "description": v.description}
                    for v in llr.verifications.all()
                ],
            }
            hlr_data["llrs"].append(llr_data)
        output.append(hlr_data)
    return json.dumps(output, indent=2)


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

        for llr_data in low_level_requirements:
            llr = LowLevelRequirement.objects.create(
                high_level_requirement=hlr,
                description=llr_data["description"],
            )
            for v in llr_data.get("verifications", []):
                VerificationMethod.objects.create(
                    low_level_requirement=llr,
                    method=v["method"],
                    test_name=v.get("test_name", ""),
                    description=v.get("description", ""),
                )

    llr_count = hlr.low_level_requirements.count()
    return json.dumps({
        "hlr_id": hlr.pk,
        "llr_count": llr_count,
        "message": f"Created HLR {hlr.pk} with {llr_count} LLRs",
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
            - kind: one of "class", "struct", "enum", "enum_value", "union",
              "namespace", "interface", "typedef", "function", "variable", "primitive"
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
    qname_to_node = {}
    saved_triples = []
    skipped_nodes = 0
    skipped_triples = 0

    with transaction.atomic():
        for node_data in nodes:
            node, _ = OntologyNode.objects.get_or_create(
                qualified_name=node_data["qualified_name"],
                defaults={
                    "kind": node_data["kind"],
                    "name": node_data["name"],
                    "description": node_data.get("description", ""),
                    "compound_refid": node_data["qualified_name"],
                },
            )
            qname_to_node[node_data["qualified_name"]] = node

        for triple_data in triples:
            subj = qname_to_node.get(triple_data["subject_qualified_name"])
            obj = qname_to_node.get(triple_data["object_qualified_name"])
            pred = Predicate.objects.filter(name=triple_data["predicate"]).first()
            if subj and obj and pred:
                triple, _ = OntologyTriple.objects.get_or_create(
                    subject=subj, predicate=pred, object=obj,
                )
                saved_triples.append(triple)
            else:
                saved_triples.append(None)
                skipped_triples += 1

        linked = 0
        if requirement_links:
            for link in requirement_links:
                idx = link.get("triple_index", -1)
                if 0 <= idx < len(saved_triples) and saved_triples[idx]:
                    if link["requirement_type"] == "hlr":
                        req = HighLevelRequirement.objects.filter(pk=link["requirement_id"]).first()
                    else:
                        req = LowLevelRequirement.objects.filter(pk=link["requirement_id"]).first()
                    if req:
                        req.triples.add(saved_triples[idx])
                        linked += 1

    return json.dumps({
        "nodes_created": len(qname_to_node),
        "triples_created": len([t for t in saved_triples if t]),
        "triples_skipped": skipped_triples,
        "requirement_links_applied": linked,
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

    # Build a lookup of ontology nodes for resolving member references
    all_nodes = list(OntologyNode.objects.values_list("qualified_name", "pk"))
    # Sort longest first for prefix matching
    all_nodes.sort(key=lambda x: len(x[0]), reverse=True)

    def resolve_node(member_qname):
        if not member_qname:
            return None
        for qname, pk in all_nodes:
            if member_qname.startswith(qname):
                return OntologyNode.objects.get(pk=pk)
        return None

    total_conditions = 0
    total_actions = 0

    with transaction.atomic():
        llr.verifications.all().delete()

        for v in verifications:
            vm = VerificationMethod.objects.create(
                low_level_requirement=llr,
                method=v["method"],
                test_name=v.get("test_name", ""),
                description=v.get("description", ""),
            )

            for i, cond in enumerate(v.get("preconditions", [])):
                VerificationCondition.objects.create(
                    verification=vm,
                    phase="pre",
                    order=i,
                    ontology_node=resolve_node(cond["member_qualified_name"]),
                    member_qualified_name=cond["member_qualified_name"],
                    operator=cond.get("operator", "=="),
                    expected_value=cond["expected_value"],
                )
                total_conditions += 1

            for i, action in enumerate(v.get("actions", [])):
                VerificationAction.objects.create(
                    verification=vm,
                    order=i,
                    description=action["description"],
                    ontology_node=resolve_node(action.get("member_qualified_name", "")),
                    member_qualified_name=action.get("member_qualified_name", ""),
                )
                total_actions += 1

            for i, cond in enumerate(v.get("postconditions", [])):
                VerificationCondition.objects.create(
                    verification=vm,
                    phase="post",
                    order=i,
                    ontology_node=resolve_node(cond["member_qualified_name"]),
                    member_qualified_name=cond["member_qualified_name"],
                    operator=cond.get("operator", "=="),
                    expected_value=cond["expected_value"],
                )
                total_conditions += 1

    return json.dumps({
        "llr_id": llr_id,
        "verifications_saved": len(verifications),
        "conditions_created": total_conditions,
        "actions_created": total_actions,
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
