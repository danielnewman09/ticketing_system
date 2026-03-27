"""
Design suitability challenger agent.

Analyzes the structural quality of the requirements-to-ontology mapping
and identifies design issues: poor cohesion, excessive coupling, orphaned
nodes, granularity problems, and testability concerns.

Runs after design_ontology but before verify_llr, so that design issues
can be remediated before investing in detailed verification procedures.

The agent receives deterministically-computed graph metrics alongside the
raw requirements and ontology, letting it focus on interpretation rather
than counting.
"""

import json
from collections import defaultdict

from agents.llm_client import call_tool

from agents.review.challenge_design_prompt import (
    SYSTEM_PROMPT,
    TOOL_DEFINITION,
    DesignChallenge,
    DesignChallengeResult,
    RemedyType,
    format_metrics_for_prompt,
    format_requirements,
    format_ontology,
)

# Re-export for backward compatibility
__all__ = [
    "DesignChallenge",
    "DesignChallengeResult",
    "RemedyType",
    "compute_graph_metrics",
    "format_metrics_for_prompt",
    "challenge",
]


# ---------------------------------------------------------------------------
# Graph metrics (computed deterministically, fed to the LLM as context)
# ---------------------------------------------------------------------------

def compute_graph_metrics(hlrs, llrs, nodes, triples, hlr_triples, llr_triples):
    """Compute structural metrics about the requirements-ontology graph.

    Args:
        hlrs: [{id, description}, ...]
        llrs: [{id, description, hlr_id}, ...]
        nodes: [{id, qualified_name, kind, description}, ...]
        triples: [{id, subject_qualified_name, predicate, object_qualified_name}, ...]
        hlr_triples: {hlr_id: [triple_id, ...]}
        llr_triples: {llr_id: [triple_id, ...]}

    Returns:
        dict with metrics for prompt injection.
    """
    # Build adjacency from triples
    node_set = {n["qualified_name"] for n in nodes}
    triple_by_id = {t["id"]: t for t in triples}

    # Node degree counts
    in_degree = defaultdict(int)
    out_degree = defaultdict(int)
    predicate_dist = defaultdict(int)
    for t in triples:
        out_degree[t["subject_qualified_name"]] += 1
        in_degree[t["object_qualified_name"]] += 1
        predicate_dist[t["predicate"]] += 1

    # Nodes referenced by at least one triple
    referenced_nodes = set()
    for t in triples:
        referenced_nodes.add(t["subject_qualified_name"])
        referenced_nodes.add(t["object_qualified_name"])
    orphaned_nodes = node_set - referenced_nodes

    # Per-HLR: connected components in the triple subgraph
    hlr_metrics = []
    for hlr in hlrs:
        triple_ids = hlr_triples.get(hlr["id"], [])
        llr_ids = [l["id"] for l in llrs if l["hlr_id"] == hlr["id"]]
        # Collect all triple IDs from this HLR and its LLRs
        all_triple_ids = set(triple_ids)
        for lid in llr_ids:
            all_triple_ids.update(llr_triples.get(lid, []))

        # Build adjacency for connected component analysis
        adj = defaultdict(set)
        hlr_nodes = set()
        for tid in all_triple_ids:
            t = triple_by_id.get(tid)
            if t:
                s, o = t["subject_qualified_name"], t["object_qualified_name"]
                adj[s].add(o)
                adj[o].add(s)
                hlr_nodes.update([s, o])

        # Count connected components via BFS
        visited = set()
        components = 0
        for node in hlr_nodes:
            if node not in visited:
                components += 1
                queue = [node]
                while queue:
                    current = queue.pop()
                    if current in visited:
                        continue
                    visited.add(current)
                    queue.extend(adj[current] - visited)

        hlr_metrics.append({
            "hlr_id": hlr["id"],
            "description": hlr["description"][:80],
            "llr_count": len(llr_ids),
            "triple_count": len(all_triple_ids),
            "node_count": len(hlr_nodes),
            "connected_components": components,
        })

    # Per-node metrics
    node_metrics = []
    for n in nodes:
        qn = n["qualified_name"]
        node_metrics.append({
            "qualified_name": qn,
            "kind": n["kind"],
            "in_degree": in_degree.get(qn, 0),
            "out_degree": out_degree.get(qn, 0),
            "total_degree": in_degree.get(qn, 0) + out_degree.get(qn, 0),
            "is_orphan": qn in orphaned_nodes,
        })

    # Sort by total degree descending for readability
    node_metrics.sort(key=lambda x: x["total_degree"], reverse=True)

    return {
        "hlr_metrics": hlr_metrics,
        "node_metrics": node_metrics,
        "predicate_distribution": dict(predicate_dist),
        "orphaned_nodes": sorted(orphaned_nodes),
        "total_nodes": len(nodes),
        "total_triples": len(triples),
    }


# ---------------------------------------------------------------------------
# Agent invocation
# ---------------------------------------------------------------------------

def challenge(
    hlrs: list[dict],
    llrs: list[dict],
    nodes: list[dict],
    triples: list[dict],
    hlr_triples: dict[int, list[int]],
    llr_triples: dict[int, list[int]],
    all_hlrs: list[dict] | None = None,
    all_llrs: list[dict] | None = None,
    model: str = "",
    prompt_log_file: str = "",
) -> DesignChallengeResult:
    """
    Analyze the requirements-ontology mapping for design suitability issues.

    Args:
        hlrs: [{id, description}, ...] — the HLR(s) under review
        llrs: [{id, description, hlr_id}, ...] — LLRs for the HLR(s) under review
        nodes: [{id, qualified_name, kind, description}, ...]
        triples: [{id, subject_qualified_name, predicate, object_qualified_name}, ...]
        hlr_triples: {hlr_id: [triple_id, ...]}
        llr_triples: {llr_id: [triple_id, ...]}
        all_hlrs: full requirements hierarchy (all HLRs) for context
        all_llrs: full requirements hierarchy (all LLRs) for context
    """
    metrics = compute_graph_metrics(hlrs, llrs, nodes, triples, hlr_triples, llr_triples)
    metrics_text = format_metrics_for_prompt(metrics)

    requirements_text = format_requirements(hlrs, llrs)
    ontology_text = format_ontology(nodes, triples)

    # Build context section showing the full requirements hierarchy so the
    # agent can avoid duplicating coverage that other HLRs already provide.
    context_section = ""
    if all_hlrs and all_llrs:
        reviewed_ids = {h["id"] for h in hlrs}
        other_hlrs = [h for h in all_hlrs if h["id"] not in reviewed_ids]
        if other_hlrs:
            context_section = (
                f"## Other HLRs (for context — do NOT challenge these, "
                f"but avoid duplicating their coverage)\n\n"
                f"{format_requirements(other_hlrs, all_llrs)}\n\n"
            )

    user_message = (
        f"## Requirements Under Review\n\n{requirements_text}\n\n"
        f"{context_section}"
        f"## Ontology\n\n{ontology_text}\n\n"
        f"## Computed Metrics\n\n{metrics_text}"
    )

    result = call_tool(
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
        tools=[TOOL_DEFINITION],
        tool_name="report_challenges",
        model=model,
        max_tokens=8192,
        prompt_log_file=prompt_log_file,
    )

    return DesignChallengeResult.model_validate(result)


if __name__ == "__main__":
    import os
    import sys

    from db import init_db, get_session
    from db.models import OntologyNode, OntologyTriple, HighLevelRequirement, LowLevelRequirement

    init_db()

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

    result = challenge(hlrs, llrs, nodes, triples, hlr_triples, llr_triples)
    print(json.dumps(result.model_dump(), indent=2))
