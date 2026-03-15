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
from typing import Literal

from pydantic import BaseModel

from agents.llm_client import call_tool


# ---------------------------------------------------------------------------
# Output schemas
# ---------------------------------------------------------------------------

RemedyType = Literal[
    "split_hlr",
    "merge_llrs",
    "add_llr",
    "remove_llr",
    "restructure_ontology",
    "no_action",
]


class DesignChallenge(BaseModel):
    """A single design issue identified by the challenger."""

    category: Literal[
        "cohesion",
        "coupling",
        "orphan",
        "testability",
        "granularity",
        "class_design",
    ]
    severity: Literal["critical", "major", "minor"]
    description: str
    affected_hlr_ids: list[int] = []
    affected_llr_ids: list[int] = []
    affected_node_qualified_names: list[str] = []
    remedy_type: RemedyType
    suggested_remedy: str


class DesignChallengeResult(BaseModel):
    challenges: list[DesignChallenge]


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


def format_metrics_for_prompt(metrics):
    """Format computed metrics into a readable text block."""
    lines = []

    lines.append("## HLR Analysis")
    for h in metrics["hlr_metrics"]:
        lines.append(
            f"- HLR {h['hlr_id']}: \"{h['description']}\" — "
            f"{h['llr_count']} LLRs, {h['triple_count']} triples, "
            f"{h['node_count']} nodes, {h['connected_components']} connected component(s)"
        )

    lines.append("\n## Predicate Distribution")
    for pred, count in sorted(metrics["predicate_distribution"].items()):
        lines.append(f"- {pred}: {count}")

    lines.append(f"\n## Node Metrics ({metrics['total_nodes']} total, "
                 f"{len(metrics['orphaned_nodes'])} orphaned)")
    for n in metrics["node_metrics"]:
        orphan_tag = " [ORPHAN]" if n["is_orphan"] else ""
        lines.append(
            f"- {n['qualified_name']} ({n['kind']}): "
            f"in={n['in_degree']} out={n['out_degree']}{orphan_tag}"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Agent prompt and invocation
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a design suitability reviewer. You analyze the structural quality
of a requirements-to-ontology mapping and identify design issues.

You will receive:
1. The HLRs and their LLRs
2. The ontology nodes and triples
3. Pre-computed graph metrics

## Challenge categories

**cohesion** — An HLR's triples should form a connected subgraph. If an HLR
produces disconnected components, it is trying to specify unrelated behaviors
and should be split. Similarly, LLRs under the same HLR should reference
overlapping ontology regions.

**coupling** — A node with very high in-degree or out-degree relative to others
may indicate a god class or a design bottleneck. Excessive `depends_on` edges
without `composes`/`aggregates` suggest loose structure.

**orphan** — Nodes not referenced by any triple serve no purpose in the design.
They should either be connected via triples or removed.

**testability** — An LLR that maps to zero triples cannot be verified against
the ontology. An LLR whose triples span too many nodes may be too broad to
test atomically.

**granularity** — An HLR with too many LLRs may be too broad. An HLR with
only one LLR may be too narrow to justify as a high-level requirement.
Similarly, the ontology should have appropriate granularity — too many fine-grained
nodes or too few coarse nodes are both problematic.

## Valid structural patterns

**Inheritance hierarchies** are expected and valid. A base class with multiple
derived classes connected via `generalizes` triples is good design — do NOT
flag base classes as granularity or coupling issues. A container class that
aggregates or composes a base class implicitly covers all derived types; it
does NOT need separate relationships to each subclass.

**Enum hierarchies** — An enum node with enum_value children connected via
`composes` triples is the correct pattern. Enum values MUST be nested under
their parent enum (e.g., `core::ErrorType::DivisionByZero` under
`core::ErrorType`). Do NOT suggest converting enum_values to classes or
restructuring them outside their parent enum. Do NOT flag enum nodes as
granularity issues for having many enum_values — that is expected behavior.

**Attributes and methods** — Attribute and method nodes are members of a
class, connected via `composes` triples (e.g., `gui::Window --composes-->
gui::Window::title`). Attributes must NEVER appear as the subject of any
triple. Methods may appear as subjects of `invokes` triples. If a node is
modeled as a class but has no behavior or outgoing relationships, it should
likely be an attribute instead — flag this as a granularity issue. Do NOT
flag attribute or method nodes as orphans when they are correctly composed
by their parent class.

## Output

For each issue found, produce a challenge with:
- category: one of the above
- severity: "critical" (blocks design), "major" (significant concern), "minor" (improvement)
- description: clear explanation of the problem
- affected IDs and node names
- remedy_type: "split_hlr", "merge_llrs", "add_llr", "remove_llr",
  "restructure_ontology", or "no_action"
- suggested_remedy: what specifically to change

If the design is sound, return an empty challenges list.
Focus on actionable structural issues, not stylistic preferences.

## Reasoning guidelines

Be decisive. Analyze the metrics, identify issues, and commit to your
assessment. Do NOT revisit or second-guess conclusions you have already
reached. State each issue once, then move on to the next. If you are
uncertain whether something is an issue, it is not — skip it.

You MUST use the report_challenges tool to return your result.
"""

TOOL_DEFINITION = {
    "name": "report_challenges",
    "description": "Report design suitability challenges found in the requirements-ontology mapping",
    "input_schema": DesignChallengeResult.model_json_schema(),
}

def _format_requirements(hlrs, llrs):
    """Format requirements for the user message."""
    lines = []
    for hlr in hlrs:
        lines.append(f"HLR {hlr['id']}: {hlr['description']}")
        for llr in [l for l in llrs if l["hlr_id"] == hlr["id"]]:
            lines.append(f"  LLR {llr['id']}: {llr['description']}")
    return "\n".join(lines)


def _format_ontology(nodes, triples):
    """Format ontology for the user message."""
    lines = ["Nodes:"]
    for n in nodes:
        lines.append(f"  {n['qualified_name']} ({n['kind']}): {n['description']}")
    lines.append("\nTriples:")
    for t in triples:
        lines.append(f"  {t['subject_qualified_name']} --{t['predicate']}--> {t['object_qualified_name']}")
    return "\n".join(lines)


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

    requirements_text = _format_requirements(hlrs, llrs)
    ontology_text = _format_ontology(nodes, triples)

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
                f"{_format_requirements(other_hlrs, all_llrs)}\n\n"
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
