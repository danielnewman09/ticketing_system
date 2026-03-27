"""
Agent that assesses dependencies for HLRs before decomposition.

Reviews each HLR against the available dependencies for its component's
language and advises whether existing or new dependencies cover the need.

This runs as stage 0.5 between assign_components (stage 0) and
decompose_hlr (stage 1), so that decomposition and OO design are
dependency-aware.
"""

from agents.llm_client import call_tool
from db.models.requirements import format_hlrs_for_prompt

from agents.design.assess_dependencies_prompt import SYSTEM_PROMPT, TOOL_DEFINITION


def assess_dependencies(
    hlrs: list[dict],
    dependencies: list[dict],
    language: str,
    model: str = "",
    prompt_log_file: str = "",
) -> list[dict]:
    """Assess dependency relevance for each HLR.

    Args:
        hlrs: List of dicts with 'id', 'description', and optionally
            'component_name' keys.
        dependencies: List of dicts with 'name', 'version', 'is_dev',
            and 'manager_name' keys.
        language: The target language (e.g., "Python 3.13").
        model: LLM model override.
        prompt_log_file: Optional path to log the prompt.

    Returns:
        List of assessment dicts with 'hlr_id', 'recommendation',
        'dependency_name', 'relevant_structures', and 'rationale'.
    """
    hlr_text = format_hlrs_for_prompt(hlrs)

    if dependencies:
        dep_lines = []
        for d in dependencies:
            version = f"=={d['version']}" if d.get("version") else ""
            dev_tag = " (dev)" if d.get("is_dev") else ""
            manager = f" [{d['manager_name']}]" if d.get("manager_name") else ""
            dep_lines.append(f"- {d['name']}{version}{dev_tag}{manager}")
        deps_text = "\n".join(dep_lines)
    else:
        deps_text = "(no dependencies installed)"

    result = call_tool(
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Language: {language}\n\n"
                    f"## Installed Dependencies\n\n{deps_text}\n\n"
                    f"## High-Level Requirements\n\n{hlr_text}\n\n"
                    f"Assess each HLR against the available dependencies."
                ),
            }
        ],
        tools=[TOOL_DEFINITION],
        tool_name="assess_dependencies",
        model=model,
        prompt_log_file=prompt_log_file,
    )

    assessments = result.get("assessments", [])

    # Validate: every HLR should have an assessment
    all_ids = {h["id"] for h in hlrs}
    assessed_ids = {a["hlr_id"] for a in assessments}
    for missing_id in all_ids - assessed_ids:
        assessments.append({
            "hlr_id": missing_id,
            "recommendation": "none",
            "dependency_name": "",
            "relevant_structures": [],
            "rationale": "not assessed",
        })

    return assessments
