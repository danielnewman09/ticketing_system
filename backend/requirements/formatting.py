"""Formatting helpers for requirement data.

Replaces the SQLAlchemy-model-based formatters from requirements.py module.
These operate on plain dicts (from RequirementRepository) instead of ORM objects.
"""


def format_hlr_dict(hlr_dict: dict, include_component: bool = False) -> str:
    """Format a single HLR dict as a prompt line."""
    comp = ""
    if include_component:
        comp_name = hlr_dict.get("component_name") or hlr_dict.get("component__name")
        if comp_name:
            comp = f" [Component: {comp_name}]"
    return f"HLR {hlr_dict['id']}{comp}: {hlr_dict['description']}"


def format_llr_dict(llr_dict: dict) -> str:
    """Format a single LLR dict as a prompt line."""
    return f"LLR {llr_dict['id']}: {llr_dict['description']}"


def format_hlrs_for_prompt(hlrs: list[dict], llrs: list[dict] | None = None, include_component: bool = False) -> str:
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