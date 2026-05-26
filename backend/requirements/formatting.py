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


def _format_condition(cond: dict) -> str:
    """Format a single condition (pre or post) as a readable string."""
    subject = cond.get("subject_qualified_name", "")
    operator = cond.get("operator", "==")
    expected = cond.get("expected_value", "")
    obj = cond.get("object_qualified_name", "")
    parts = [subject, operator]
    if expected:
        parts.append(expected)
    if obj:
        parts.append(f"(ref: {obj})")
    return " ".join(parts)


def _format_action(action: dict) -> str:
    """Format a single action as a readable string."""
    desc = action.get("description", "")
    callee = action.get("callee_qualified_name", "")
    caller = action.get("caller_qualified_name", "")
    if caller and callee:
        return f"{caller} → {callee}" + (f": {desc}" if desc else "")
    elif callee:
        return callee + (f": {desc}" if desc else "")
    return desc


def _format_verification(v: dict) -> list[str]:
    """Format a single verification stub as indented lines."""
    lines = []
    method = v.get("method", "")
    test_name = v.get("test_name", "")
    desc = v.get("description", "")
    title = f"[{method}]"
    if test_name:
        title += f" {test_name}"
    lines.append(f"    {title}")
    if desc:
        lines.append(f"      {desc}")

    preconditions = v.get("preconditions", [])
    if preconditions:
        lines.append("      Pre-conditions:")
        for cond in preconditions:
            lines.append(f"        {_format_condition(cond)}")
    else:
        lines.append("      Pre-conditions: (none)")

    actions = v.get("actions", [])
    if actions:
        lines.append("      Actions:")
        for action in actions:
            lines.append(f"        {_format_action(action)}")
    else:
        lines.append("      Actions: (none)")

    postconditions = v.get("postconditions", [])
    if postconditions:
        lines.append("      Post-conditions:")
        for cond in postconditions:
            lines.append(f"        {_format_condition(cond)}")
    else:
        lines.append("      Post-conditions: (none)")

    return lines


def format_llrs_with_verifications_for_prompt(
    llrs: list[dict],
    llr_verifications: dict[int, list[dict]],
) -> str:
    """Format LLRs with their full verification stubs for the design_verify prompt.

    Args:
        llrs: List of LLR dicts with at least id, description, hlr_id.
        llr_verifications: Dict mapping LLR ID to list of verification dicts.
            Each verification dict has: method, test_name, description,
            preconditions, actions, postconditions. Each condition dict has:
            subject_qualified_name, operator, expected_value, object_qualified_name.
            Each action dict has: description, callee_qualified_name, caller_qualified_name.

    Returns:
        Formatted text suitable for inclusion in an agent prompt.
    """
    lines = []
    for llr in llrs:
        lines.append(f"LLR {llr['id']}: {llr['description']}")
        verifs = llr_verifications.get(llr["id"], [])
        if verifs:
            lines.append("  Verifications:")
            for v in verifs:
                lines.extend(_format_verification(v))
        else:
            lines.append("  (No verification stubs)")
        lines.append("")
    return "\n".join(lines)