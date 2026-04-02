"""
Stage 1 agent: derive an object-oriented class design from backend.requirements.

Produces a pure OO class diagram (classes, methods, attributes, inheritance,
associations). No ontology vocabulary — the deterministic mapper (Stage 2)
handles that translation.

Uses the more capable model via call_tool (single-model reasoning + tool call).
Dependency API exploration is handled upstream by the
discover_classes skill, whose output is partitioned into
dependency_classes and as_built_classes.
"""

import logging

from llm_caller import call_tool
from backend.codebase.schemas import OODesignSchema
from backend.db.models.requirements import format_hlrs_for_prompt

from backend.ticketing_agent.design.design_oo_prompt import (
    SYSTEM_PROMPT,
    TOOL_DEFINITION,
    build_specializations_section,
    build_dependency_api_section,
    build_as_built_section,
    build_existing_classes_section,
    build_intercomponent_section,
    build_other_hlrs_section,
    build_dependency_section,
    build_namespace_section,
)

log = logging.getLogger("agents.design")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def design_oo(
    hlr: dict,
    llrs: list[dict],
    language: str = "",
    existing_classes: list[dict] | None = None,
    dependency_classes: list[dict] | None = None,
    as_built_classes: list[dict] | None = None,
    intercomponent_classes: list[dict] | None = None,
    other_hlr_summaries: list[dict] | None = None,
    dependency_contexts: dict[int, dict] | None = None,
    component_namespace: str = "",
    sibling_namespaces: list[str] | None = None,
    model: str = "",
    prompt_log_file: str = "",
) -> OODesignSchema:
    """
    Stage 1: derive an OO class design from a single HLR and its LLRs.

    Args:
        hlr: Single HLR dict with {id, description, component_name?}.
        llrs: LLR dicts for this HLR only, each {id, hlr_id, description}.
        existing_classes: Classes already designed in the same component.
        dependency_classes: External dependency API classes (read-only).
        as_built_classes: Existing project codebase classes that may be
            reused, extended, or redesigned.
        intercomponent_classes: Public API classes from other components.
        other_hlr_summaries: Other HLRs for awareness context.
        dependency_contexts: Dependency assessment keyed by HLR ID.
        component_namespace: Required C++ namespace for this component.
        sibling_namespaces: Other component namespaces (for context).
    """
    requirements_text = format_hlrs_for_prompt([hlr], llrs, include_component=True)

    system = SYSTEM_PROMPT.format(
        specializations_section=build_specializations_section(language),
        namespace_section=build_namespace_section(component_namespace, sibling_namespaces),
        dependency_api_section=build_dependency_api_section(dependency_classes or []),
        as_built_section=build_as_built_section(as_built_classes or []),
        existing_classes_section=build_existing_classes_section(existing_classes or []),
        intercomponent_section=build_intercomponent_section(intercomponent_classes or []),
        other_hlrs_section=build_other_hlrs_section(other_hlr_summaries or []),
    )
    dep_section = build_dependency_section(dependency_contexts or {})
    if dep_section:
        system += dep_section

    # Build component context for the user prompt
    component_name = hlr.get("component_name")
    component_hint = ""
    if component_name:
        component_desc = hlr.get("component_description", "")
        component_hint = (
            f"\n\nThis requirement belongs to the architectural "
            f"component: **{component_name}**"
        )
        if component_namespace:
            component_hint += f" (namespace: `{component_namespace}`)"
        component_hint += (
            ". Your class design should be scoped to "
            "and appropriate for this component context.\n"
        )
        if component_desc:
            component_hint += f"\n### Component Description\n\n{component_desc}\n"

    user_message = {
        "role": "user",
        "content": (
            "Derive an object-oriented class design from these requirements:\n\n"
            f"{requirements_text}"
            f"{component_hint}"
        ),
    }

    result = call_tool(
        system=system,
        messages=[user_message],
        tools=[TOOL_DEFINITION],
        tool_name="produce_oo_design",
        model=model,
        prompt_log_file=prompt_log_file,
    )

    schema = OODesignSchema.model_validate(result)

    for cls in schema.classes:
        if not cls.methods and not cls.attributes:
            log.warning(
                "design_oo: class %s has no methods or attributes — "
                "the model may have dropped nested arrays",
                cls.name,
            )

    return schema
