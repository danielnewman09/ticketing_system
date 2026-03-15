"""
Agent that assesses dependencies for HLRs before decomposition.

Reviews each HLR against the available dependencies for its component's
language and advises whether existing or new dependencies cover the need.

This runs as stage 0.5 between assign_components (stage 0) and
decompose_hlr (stage 1), so that decomposition and OO design are
dependency-aware.
"""

from agents.llm_client import call_tool


SYSTEM_PROMPT = """\
You are a software architect reviewing high-level requirements (HLRs) against
the available third-party dependencies for a project.

For each HLR, determine whether an existing dependency already provides the
needed functionality, whether a new dependency should be added, or whether
no dependency is relevant.

Rules:
- "use_existing": An installed dependency already covers the HLR's need.
  Cite the specific structures/APIs from that dependency.
- "add_new": No installed dependency covers the need, but a well-known
  third-party package would. Name the specific package.
- "none": The HLR requires custom implementation with no relevant dependency.

When recommending "use_existing", be specific about which structures and APIs
from the dependency are relevant (e.g., "pydantic.BaseModel", "pydantic.Field").

When recommending "add_new", name a specific, well-maintained package that is
appropriate for the language and ecosystem.

You MUST use the assess_dependencies tool to return your result.
"""

TOOL_DEFINITION = {
    "name": "assess_dependencies",
    "description": "Assess dependency relevance for each HLR",
    "input_schema": {
        "type": "object",
        "properties": {
            "assessments": {
                "type": "array",
                "description": "One assessment per HLR",
                "items": {
                    "type": "object",
                    "properties": {
                        "hlr_id": {
                            "type": "integer",
                            "description": "The HLR ID",
                        },
                        "recommendation": {
                            "type": "string",
                            "enum": ["use_existing", "add_new", "none"],
                            "description": "Whether to use an existing dep, add a new one, or none",
                        },
                        "dependency_name": {
                            "type": "string",
                            "description": "Name of existing or proposed package (empty for 'none')",
                        },
                        "relevant_structures": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Specific structures/APIs from the dependency (e.g., 'pydantic.BaseModel')",
                        },
                        "rationale": {
                            "type": "string",
                            "description": "Why this recommendation was made",
                        },
                    },
                    "required": ["hlr_id", "recommendation", "rationale"],
                },
            },
        },
        "required": ["assessments"],
    },
}


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
    hlr_text = "\n".join(
        f"HLR {h['id']}: {h['description']}" for h in hlrs
    )

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
