"""
Prompt templates and formatters for the challenge_design agent.
"""

from typing import Literal

from pydantic import BaseModel


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
# Prompt
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


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

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


def format_requirements(hlrs, llrs):
    """Format requirements for the user message."""
    lines = []
    for hlr in hlrs:
        lines.append(f"HLR {hlr['id']}: {hlr['description']}")
        for llr in [l for l in llrs if l["hlr_id"] == hlr["id"]]:
            lines.append(f"  LLR {llr['id']}: {llr['description']}")
    return "\n".join(lines)


def format_ontology(nodes, triples):
    """Format ontology for the user message."""
    lines = ["Nodes:"]
    for n in nodes:
        lines.append(f"  {n['qualified_name']} ({n['kind']}): {n['description']}")
    lines.append("\nTriples:")
    for t in triples:
        lines.append(f"  {t['subject_qualified_name']} --{t['predicate']}--> {t['object_qualified_name']}")
    return "\n".join(lines)
