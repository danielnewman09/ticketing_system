"""Formatting helpers for requirement data.

Thin wrappers around the ``format()`` methods on the neomodel models.
The heavy lifting is done by:

- :meth:`HLR.format` — formats an HLR as a prompt line
- :meth:`LLR.format` — formats an LLR with optional verifications
- :meth:`VerificationMethod.format` — formats a VM with conditions/actions
- :meth:`Condition.format` — formats a condition assertion
- :meth:`Action.format` — formats an action step

For new code, prefer calling ``node.format()`` directly on the neomodel
instance instead of these dict-based wrappers.
"""

from __future__ import annotations

from backend_migrated.models.verification import VerificationMethod


def format_hlr_dict(hlr_dict: dict, include_component: bool = False) -> str:
    """Format a single HLR dict as a prompt line."""
    comp = ""
    if include_component:
        comp_name = hlr_dict.get("component_name") or hlr_dict.get("component__name")
        if comp_name:
            comp = f" [Component: {comp_name}]"
    hlr_id = hlr_dict.get("id", hlr_dict.get("refid", ""))
    return f"HLR {hlr_id}{comp}: {hlr_dict['description']}"


def format_llr_dict(llr_dict: dict) -> str:
    """Format a single LLR dict as a prompt line."""
    llr_id = llr_dict.get("id", llr_dict.get("refid", ""))
    return f"LLR {llr_id}: {llr_dict['description']}"


def format_hlrs_for_prompt(
    hlrs: list[dict],
    llrs: list[dict] | None = None,
    include_component: bool = False,
) -> str:
    """Format HLR/LLR dicts into a text block for agent prompts."""
    lines = []
    for hlr in hlrs:
        lines.append(format_hlr_dict(hlr, include_component))
        if llrs:
            for llr in [l for l in llrs if l.get("hlr_id") == hlr["id"]]:
                lines.append(f"  {format_llr_dict(llr)}")
    if llrs:
        unlinked = [l for l in llrs if l.get("hlr_id") is None]
        if unlinked:
            lines.append("\nUnlinked LLRs:")
            for llr in unlinked:
                lines.append(f"  {format_llr_dict(llr)}")
    return "\n".join(lines)


def format_llrs_with_verifications_for_prompt(
    llrs: list[dict],
    llr_verifications: dict[int, list[dict]],
) -> str:
    """Format LLRs with their full verification stubs for agent prompts.

    Each verification dict is parsed via
    :meth:`VerificationMethod.from_llm_dict` to produce neomodel
    instances, then formatted with :meth:`VerificationMethod.format`.

    Args:
        llrs: List of LLR dicts with at least id, description, hlr_id.
        llr_verifications: Dict mapping LLR ID to list of verification
            dicts (the raw LLM format with
            preconditions/actions/postconditions).

    Returns:
        Formatted text suitable for inclusion in an agent prompt.
    """
    lines = []
    for llr in llrs:
        llr_id = llr.get("id", llr.get("refid", ""))
        lines.append(f"LLR {llr_id}: {llr['description']}")
        verifs = llr_verifications.get(llr_id, [])
        if verifs:
            lines.append("  Verifications:")
            for v in verifs:
                vm, conditions, actions = VerificationMethod.from_llm_dict(v)
                lines.append(vm.format(conditions=conditions, actions=actions))
        else:
            lines.append("  (No verification stubs)")
        lines.append("")
    return "\n".join(lines)