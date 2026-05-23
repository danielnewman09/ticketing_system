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

import json
import logging
import os

from llm_caller import call_tool
from backend.codebase.schemas import OODesignSchema
from backend.requirements.formatting import format_hlrs_for_prompt

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

MAX_TOOL_RETRIES = 2


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_oo_design(
    oo: OODesignSchema,
    prior_class_lookup: dict[str, str],
    dependency_lookup: dict[str, str] | None,
    intercomponent_classes: list[dict] | None,
) -> list[str]:
    """Validate an OO design for association target resolution and intercomponent coverage.

    Returns a list of error strings. Empty list means valid.
    """
    errors = []

    # Build set of known names
    design_class_names = {cls.name for cls in oo.classes}
    design_iface_names = {iface.name for iface in oo.interfaces}
    design_enum_names = {enum.name for enum in oo.enums}
    all_design_names = design_class_names | design_iface_names | design_enum_names

    # Set of intercomponent qualified names for lookup
    intercomp_qnames: set[str] = set()
    intercomp_bare: set[str] = set()
    if intercomponent_classes:
        intercomp_qnames = {c["qualified_name"] for c in intercomponent_classes}
        intercomp_bare = {qname.rsplit("::", 1)[-1] for qname in intercomp_qnames}

    # Build dependency lookup
    dep_lookup = dict(dependency_lookup or {})

    # Check 1: Unknown association targets
    for assoc in oo.associations:
        for ref in [assoc.from_class, assoc.to_class]:
            if ref in all_design_names:
                continue
            if ref in prior_class_lookup.values():
                continue
            if ref in prior_class_lookup:
                continue
            if ref in dep_lookup:
                continue
            if ref in intercomp_qnames or ref in intercomp_bare:
                continue
            errors.append(
                f'Unknown class reference: "{ref}" in association '
                f'({assoc.from_class} -[{assoc.kind}]-> {assoc.to_class}). '
                f'"{ref}" is not defined in this design or the provided context.'
            )

    # Check 2: Missing intercomponent associations
    if intercomponent_classes:
        for cls in oo.classes:
            referenced_intercomp: set[str] = set()
            for attr in cls.attributes:
                for ic in intercomponent_classes:
                    ic_bare = ic["qualified_name"].rsplit("::", 1)[-1]
                    if attr.type_name and (ic_bare in attr.type_name or ic["qualified_name"] in attr.type_name):
                        referenced_intercomp.add(ic["qualified_name"])
            for method in cls.methods:
                if method.return_type:
                    for ic in intercomponent_classes:
                        ic_bare = ic["qualified_name"].rsplit("::", 1)[-1]
                        if ic_bare in method.return_type or ic["qualified_name"] in method.return_type:
                            referenced_intercomp.add(ic["qualified_name"])

            if referenced_intercomp:
                assoc_targets = {assoc.to_class for assoc in oo.associations} | {assoc.from_class for assoc in oo.associations}
                for ic_qname in referenced_intercomp:
                    if ic_qname not in assoc_targets:
                        ic_bare = ic_qname.rsplit("::", 1)[-1]
                        if ic_bare not in assoc_targets:
                            errors.append(
                                f"Missing intercomponent association: {cls.name} references "
                                f"{ic_qname} in attributes/methods but has no association to it."
                            )

    return errors


def _format_design_validation_errors(errors: list[str]) -> str:
    """Format design validation errors into a retry message."""
    issue_lines = "\n".join(f"{i+1}. {e}" for i, e in enumerate(errors))
    return (
        "Your previous output had the following issues:\n\n"
        f"<issues>\n{issue_lines}\n</issues>\n\n"
        "Please correct these issues and respond again with the fixed output."
    )


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
    prior_class_lookup: dict[str, str] | None = None,
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
            f"\n\nThis requirement belongs to the architectural " f"component: **{component_name}**"
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

    messages = [user_message]

    # Build dependency lookup from dependency classes for validation
    dep_lookup: dict[str, str] = {}
    if dependency_classes:
        for cls in dependency_classes:
            qname = cls.get("qualified_name", "")
            if qname:
                bare = qname.rsplit("::", 1)[-1]
                dep_lookup[bare] = qname

    for attempt in range(MAX_TOOL_RETRIES + 1):
        try:
            result = call_tool(
                system=system,
                messages=messages,
                tools=[TOOL_DEFINITION],
                tool_name="produce_oo_design",
                model=model,
                prompt_log_file=prompt_log_file if attempt == 0 else "",
            )
        except Exception as e:
            # LLM returned an error — log it and retry if possible
            log.error(
                "design_oo: LLM call failed on attempt %d/%d for HLR %s: %s: %s",
                attempt + 1, MAX_TOOL_RETRIES + 1, hlr.get('id', '?'), type(e).__name__, e,
            )
            # Write failure info to prompt log for debugging
            if prompt_log_file:
                try:
                    base, ext = os.path.splitext(prompt_log_file)
                    fail_path = f"{base}_attempt{attempt + 1}_failed.txt"
                    os.makedirs(os.path.dirname(fail_path), exist_ok=True)
                    with open(fail_path, "w") as f:
                        f.write(f"design_oo attempt {attempt + 1}/{MAX_TOOL_RETRIES + 1} FAILED\n")
                        f.write(f"Error: {type(e).__name__}: {e}\n\n")
                        f.write(f"Messages so far ({len(messages)} turns):\n")
                        for i, msg in enumerate(messages):
                            f.write(f"\n--- Message {i + 1} ({msg.get('role', 'unknown')}) ---\n")
                            f.write(str(msg.get('content', ''))[:5000])
                            f.write("\n")
                        f.write("\n")
                        f.write(f"Retrying with recovery message...\n")
                except Exception:
                    pass  # Best-effort logging
            if attempt < MAX_TOOL_RETRIES:
                messages.append({
                    "role": "user",
                    "content": (
                        "Your previous response could not be processed. "
                        "Please respond again with a valid produce_oo_design tool call. "
                        "Make sure the tool call contains properly formatted JSON "
                        "with all required fields (modules, classes, interfaces, enums, associations)."
                    ),
                })
                continue
            # Final attempt failed — re-raise
            raise

        schema = OODesignSchema.model_validate(result)
        # Validate associations and intercomponent coverage
        errors = _validate_oo_design(
            schema,
            prior_class_lookup=prior_class_lookup or {},
            dependency_lookup=dep_lookup,
            intercomponent_classes=intercomponent_classes or [],
        )

        if not errors:
            break  # Valid output, proceed

        if attempt < MAX_TOOL_RETRIES:
            log.warning(
                "design_oo: validation errors on attempt %d/%d: %s",
                attempt + 1, MAX_TOOL_RETRIES + 1, errors,
            )
            error_msg = _format_design_validation_errors(errors)
            messages.append({"role": "assistant", "content": json.dumps(result)})
            messages.append({"role": "user", "content": error_msg})
            continue

        # Final attempt still has errors — log and proceed
        log.warning(
            "design_oo: %d validation errors after %d attempts: %s",
            len(errors), MAX_TOOL_RETRIES + 1, errors,
        )

    for cls in schema.classes:
        if not cls.methods and not cls.attributes:
            log.warning(
                "design_oo: class %s has no methods or attributes — "
                "the model may have dropped nested arrays",
                cls.name,
            )

    return schema
