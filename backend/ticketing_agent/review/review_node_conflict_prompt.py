"""
Prompt templates and formatters for the review_node_conflict agent.
"""

from typing import Literal

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Output schemas
# ---------------------------------------------------------------------------

class NodeResolution(BaseModel):
    """Resolution for a single proposed-vs-existing node conflict."""

    proposed_qualified_name: str
    existing_qualified_name: str
    action: Literal["keep_proposed", "keep_existing", "keep_both"]
    winning_qualified_name: str
    rationale: str


class ConflictReviewResult(BaseModel):
    """The complete set of conflict resolutions."""
    resolutions: list[NodeResolution]


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an Object-Oriented design reviewer specializing in ontology naming
and class hierarchy correctness.

You are given a set of naming conflicts where a remediation step proposed new
ontology nodes whose names match existing nodes. Your job is to decide the
correct resolution for each conflict.

## Context

The ontology uses C++-style qualified names (e.g., `gui::CalculatorWindow::NumericButton`).
The `::` separator denotes namespace/class nesting — a node `A::B::C` means C is
a member/inner class of B, which is in namespace A.

## Decision criteria

For each conflict, decide:

1. **keep_proposed** — The proposed qualified_name is more correct from an OO
   hierarchy perspective. The existing node should be replaced by the proposed
   one. All triples referencing the existing node will be rewritten to use the
   proposed node's qualified_name.

   Choose this when the proposed name better reflects composition/ownership
   (e.g., `gui::CalculatorWindow::NumericButton` is better than `gui::NumericButton`
   because NumericButton is composed by CalculatorWindow).

2. **keep_existing** — The existing node's qualified_name is correct. The proposed
   node is a duplicate and should be dropped. Triples referencing the proposed
   node will be rewritten to use the existing node.

   Choose this when the existing name already has the correct hierarchy placement,
   or when the proposed name adds unnecessary nesting.

3. **keep_both** — These are genuinely distinct entities that happen to share a
   short name. Both should be kept as-is.

   Choose this rarely — only when the nodes truly represent different concepts.

## Enum and enum_value rules

Enum values (kind=enum_value) MUST remain nested under their parent enum type.
For example, `core::ErrorType::DivisionByZero` is an enum_value under the enum
`core::ErrorType`. This hierarchy is ALWAYS correct and must never be disrupted:

- NEVER choose keep_proposed if the existing node is an enum_value properly
  nested under an enum (e.g., `ParentEnum::Value`) and the proposed node is a
  different kind (class, struct, etc.).
- An enum_value like `core::ErrorType::DivisionByZero` must NOT be renamed to
  `core::DivisionByZeroError` — that would break the enum hierarchy.
- If the proposed node represents a distinct concept (e.g., an error class vs
  an enum value), choose keep_both.

## Important

- Prefer deeper nesting when a `composes` relationship exists or is being created
  between the parent and child (e.g., if CalculatorWindow composes NumericButton,
  then `gui::CalculatorWindow::NumericButton` is correct).
- When considering kind differences, respect the semantic distinction: an enum_value
  is a constant defined by an enum, a class is an instantiable type. These are
  fundamentally different and a name match between them does not imply they are
  the same entity.
- Set `winning_qualified_name` to the qualified_name that should be used going
  forward. For keep_proposed, this is the proposed name. For keep_existing,
  this is the existing name. For keep_both, set it to the proposed name (no
  rewriting needed).

You MUST use the resolve_conflicts tool to return your result.
"""

TOOL_DEFINITION = {
    "name": "resolve_conflicts",
    "description": "Return resolutions for node naming conflicts",
    "input_schema": ConflictReviewResult.model_json_schema(),
}


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def format_conflicts(conflicts):
    """Format conflicts for the user message.

    Args:
        conflicts: list of dicts with keys:
            proposed_qualified_name, proposed_kind, proposed_description,
            existing_qualified_name, existing_kind, existing_description,
            existing_triples (list of triple summary strings),
            proposed_triples (list of triple summary strings from plan.new_triples),
            hlr_context (list of HLR summary strings),
            llr_context (list of LLR summary strings),
    """
    lines = []
    for i, c in enumerate(conflicts, 1):
        lines.append(f"### Conflict {i}")
        lines.append(f"Proposed: {c['proposed_qualified_name']} ({c['proposed_kind']})")
        lines.append(f"  Description: {c['proposed_description']}")
        lines.append(f"Existing: {c['existing_qualified_name']} ({c['existing_kind']})")
        lines.append(f"  Description: {c['existing_description']}")
        if c["existing_triples"]:
            lines.append("Existing triples:")
            for t in c["existing_triples"]:
                lines.append(f"  {t}")
        if c["proposed_triples"]:
            lines.append("Proposed new triples referencing this node:")
            for t in c["proposed_triples"]:
                lines.append(f"  {t}")
        if c["hlr_context"]:
            lines.append("Related HLRs:")
            for h in c["hlr_context"]:
                lines.append(f"  {h}")
        if c["llr_context"]:
            lines.append("Related LLRs:")
            for l in c["llr_context"]:
                lines.append(f"  {l}")
        lines.append("")
    return "\n".join(lines)
