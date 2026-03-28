"""
Stage 1 agent: derive an object-oriented class design from backend.requirements.

Produces a pure OO class diagram (classes, methods, attributes, inheritance,
associations). No ontology vocabulary — the deterministic mapper (Stage 2)
handles that translation.

Uses the more capable model via call_tool (single-model reasoning + tool call).
"""

import logging
from typing import Callable

from llm_caller import call_tool
from llm_caller import call_tool_loop
from backend.codebase.schemas import OODesignSchema
from backend.db.models.requirements import format_hlrs_for_prompt

from backend.ticketing_agent.design.design_oo_prompt import (
    SYSTEM_PROMPT,
    TOOL_DEFINITION,
    build_specializations_section,
    build_existing_classes_section,
    build_intercomponent_section,
    build_other_hlrs_section,
    build_dependency_section,
    build_namespace_section,
    build_dependency_graph_section,
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
    intercomponent_classes: list[dict] | None = None,
    other_hlr_summaries: list[dict] | None = None,
    dependency_contexts: dict[int, dict] | None = None,
    component_namespace: str = "",
    sibling_namespaces: list[str] | None = None,
    model: str = "",
    prompt_log_file: str = "",
    extra_tools: list[dict] | None = None,
    tool_dispatcher: Callable[[str, dict], str] | None = None,
    max_turns: int = 10,
) -> OODesignSchema:
    """
    Stage 1: derive an OO class design from a single HLR and its LLRs.

    Args:
        hlr: Single HLR dict with {id, description, component_name?}.
        llrs: LLR dicts for this HLR only, each {id, hlr_id, description}.
        existing_classes: Classes already designed in the same component.
        intercomponent_classes: Public API classes from other components.
        other_hlr_summaries: Other HLRs for awareness context.
        dependency_contexts: Dependency assessment keyed by HLR ID.
        component_namespace: Required C++ namespace for this component.
        sibling_namespaces: Other component namespaces (for context).
        extra_tools: Additional tool schemas (Anthropic format) for the
            multi-turn loop (e.g., dependency graph query tools).
        tool_dispatcher: Handler for non-final tool calls. Required when
            extra_tools is provided.
        max_turns: Safety limit on tool loop iterations.
    """
    requirements_text = format_hlrs_for_prompt([hlr], llrs, include_component=True)

    dep_graph_section = build_dependency_graph_section() if extra_tools else ""

    system = SYSTEM_PROMPT.format(
        specializations_section=build_specializations_section(language),
        namespace_section=build_namespace_section(component_namespace, sibling_namespaces),
        dependency_graph_section=dep_graph_section,
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

    if extra_tools and tool_dispatcher:
        all_tools = extra_tools + [TOOL_DEFINITION]
        result = call_tool_loop(
            system=system,
            messages=[user_message],
            tools=all_tools,
            final_tool_name="produce_oo_design",
            tool_dispatcher=tool_dispatcher,
            model=model,
            max_tokens=4096,
            max_turns=max_turns,
            prompt_log_file=prompt_log_file,
        )
    else:
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
