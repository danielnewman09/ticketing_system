"""
Discover dependency and as-built classes relevant to requirements.

Uses an LLM agent with doxygen_index graph query tools to search indexed
codebases — both external dependencies and the project's own code — and
produce a curated, categorized list for the design agent.
"""

import json
import logging

from llm_caller import call_tool_loop
from backend.db.models.requirements import format_hlrs_for_prompt

from backend.ticketing_agent.design.discover_classes_prompt import (
    SYSTEM_PROMPT,
    TOOL_DEFINITION,
)

log = logging.getLogger("agents.design")


def _slim_compound(records: list[dict]) -> list[dict]:
    """Strip heavyweight fields from get_compound results.

    The discovery agent only needs signatures and brief descriptions to
    decide relevance — detailed docs and internal IDs waste context.
    """
    drop = {"detailed", "member_refid", "member_brief"}
    return [{k: v for k, v in r.items() if k not in drop} for r in records]


def _slim_member(records: list[dict]) -> list[dict]:
    """Strip detailed_description from get_member results."""
    return [{k: v for k, v in r.items() if k != "detailed"} for r in records]


_SLIM = {
    "get_compound": _slim_compound,
    "get_member": _slim_member,
}


def _make_tool_dispatcher(toolset):
    """Create a dispatcher routing calls to DependencyGraphTools methods."""
    method_map = {
        "list_sources": toolset.list_sources,
        "search_symbols": toolset.search_symbols,
        "get_compound": toolset.get_compound,
        "get_member": toolset.get_member,
        "browse_namespace": toolset.browse_namespace,
        "find_inheritance": toolset.find_inheritance,
        "find_callers_and_callees": toolset.find_callers_and_callees,
        "get_include_chain": toolset.get_include_chain,
    }

    def dispatch(tool_name: str, tool_input: dict) -> str:
        method = method_map.get(tool_name)
        if not method:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
        try:
            result = method(**tool_input)
            slim = _SLIM.get(tool_name)
            if slim:
                result = slim(result)
            return json.dumps(result, default=str)
        except Exception as e:
            log.warning("Codebase graph tool %s failed: %s", tool_name, e)
            return json.dumps({"error": str(e)})

    return dispatch


def _build_user_message(
    hlr: dict,
    llrs: list[dict],
    dependency_contexts: dict[int, dict] | None,
    component_namespace: str,
) -> str:
    """Format the user message with requirements, dependency names, and namespace."""
    requirements_text = format_hlrs_for_prompt([hlr], llrs, include_component=True)

    # Dependency names from assessments
    dep_lines = []
    if dependency_contexts:
        for hlr_id, ctx in sorted(dependency_contexts.items()):
            rec = ctx.get("recommendation", "none")
            if rec == "none":
                continue
            dep_name = ctx.get("dependency_name", "")
            structures = ctx.get("relevant_structures", [])
            structs_text = (
                f" (suggested structures: {', '.join(structures)})"
                if structures else ""
            )
            dep_lines.append(f"- {dep_name}{structs_text}")

    deps_text = "\n".join(dep_lines) if dep_lines else "(no dependencies identified)"

    ns_text = ""
    if component_namespace:
        ns_text = (
            f"\n## Project namespace\n\n"
            f"The component's namespace is `{component_namespace}`. "
            f"Search for existing project classes in or near this namespace.\n"
        )

    return (
        "Find classes relevant to these requirements:\n\n"
        f"{requirements_text}\n\n"
        f"## Dependencies to search\n\n{deps_text}\n"
        f"{ns_text}\n"
        "Search the indexed documentation for dependency API classes AND "
        "existing project code that the design should be aware of."
    )


def discover_classes(
    hlr: dict,
    llrs: list[dict],
    dependency_contexts: dict[int, dict] | None,
    component_namespace: str,
    toolset,
    model: str = "",
    prompt_log_file: str = "",
    max_turns: int = 15,
) -> list[dict]:
    """Discover dependency and as-built classes relevant to requirements.

    Args:
        hlr: Single HLR dict with ``{id, description, component_name?}``.
        llrs: LLR dicts for this HLR.
        dependency_contexts: Dependency assessment keyed by HLR ID
            (from ``assess_dependencies``). May be ``None``.
        component_namespace: The component's C++ namespace. When non-empty,
            triggers search for as-built project code.
        toolset: A ``DependencyGraphTools`` instance.
        model: LLM model override.
        prompt_log_file: Optional path to log the prompt exchange.
        max_turns: Safety limit on tool loop iterations.

    Returns:
        List of class dicts, each with a ``category`` field
        (``"dependency"`` or ``"as-built"``).
    """
    has_deps = dependency_contexts and any(
        ctx.get("recommendation", "none") != "none"
        for ctx in dependency_contexts.values()
    )
    if not has_deps and not component_namespace:
        log.info(
            "No dependencies and no namespace for HLR %s, skipping discovery",
            hlr.get("id"),
        )
        return []

    user_message = _build_user_message(
        hlr, llrs, dependency_contexts, component_namespace,
    )
    all_tools = toolset.schemas() + [TOOL_DEFINITION]
    dispatcher = _make_tool_dispatcher(toolset)

    result = call_tool_loop(
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
        tools=all_tools,
        final_tool_name="produce_discovered_classes",
        tool_dispatcher=dispatcher,
        model=model,
        max_tokens=4096,
        max_turns=max_turns,
        prompt_log_file=prompt_log_file,
    )

    classes = result.get("classes", [])

    dep_count = sum(1 for c in classes if c.get("category") == "dependency")
    built_count = sum(1 for c in classes if c.get("category") == "as-built")
    log.info(
        "Discovered %d dependency + %d as-built classes for HLR %s",
        dep_count, built_count, hlr.get("id"),
    )
    return classes
