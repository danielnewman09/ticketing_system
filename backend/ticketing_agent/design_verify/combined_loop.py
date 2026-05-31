"""Combined design+verify agent: per-HLR loop that designs and verifies.

Uses call_tool_loop with draft-state tools so the agent can design,
verify, discover gaps, and revise before committing.
"""

import json
import logging
import os

from llm_caller import call_tool_loop
from codegraph.designs import ClassDiagram
from backend.requirements.schemas import VerificationSchema
from backend.requirements.schemas import VerificationSchema
from backend.requirements.formatting import format_hlr_dict, format_llrs_with_verifications_for_prompt
from backend.db.neo4j.repositories.verification import VerificationRepository

from backend.ticketing_agent.design_verify.combined_prompt import SYSTEM_PROMPT
from backend.ticketing_agent.tools.design_verify import CombinedDispatcher
from backend.ticketing_agent.design.container_lookup import seed_container_lookup
from backend.ticketing_agent.tools.helpers.design_validation import validate_oo_design

log = logging.getLogger("agents.design_verify")


def _collect_verification_warnings(
    verifications: dict[int, list[VerificationSchema]],
) -> list[str]:
    """Collect quality warnings from verification data.

    Checks for common issues:
    - Conditions with no operator (will default to ==)
    - Empty preconditions (may indicate missing setup)
    - Unqualified caller_qualified_name values
    """
    warnings = []
    for llr_id, verifs in verifications.items():
        for v in verifs:
            test_label = v.test_name or v.method
            # Check for empty preconditions
            if not v.preconditions:
                warnings.append(
                    f"LLR {llr_id} '{test_label}': no preconditions specified"
                )
            # Check for conditions without operators
            for cond in v.preconditions + v.postconditions:
                if not cond.operator:
                    warnings.append(
                        f"LLR {llr_id} '{test_label}': condition on "
                        f"'{cond.subject_qualified_name}' has no operator \u2014 "
                        f"defaulting to '=='"
                    )
            # Check for unqualified caller references
            for action in v.actions:
                if action.caller_qualified_name and "::" not in action.caller_qualified_name:
                    warnings.append(
                        f"LLR {llr_id} '{test_label}': action caller "
                        f"'{action.caller_qualified_name}' is not a valid "
                        f"qualified name \u2014 leave empty if the caller is "
                        f"the test harness"
                    )
    return warnings


class DesignVerifyResult:
    """Result from the combined design+verify loop."""

    def __init__(
        self,
        oo_design: ClassDiagram,
        verifications: dict[int, list[VerificationSchema]],
        design_warnings: list[str] | None = None,
        verification_warnings: list[str] | None = None,
    ):
        self.oo_design = oo_design
        self.verifications = verifications
        self.design_warnings = design_warnings or []
        self.verification_warnings = verification_warnings or []


def design_and_verify(
    hlr: dict,
    llrs: list[dict],
    existing_classes: list[dict] | None = None,
    intercomponent_classes: list[dict] | None = None,
    component_namespace: str = "",
    sibling_namespaces: list[str] | None = None,
    prior_class_lookup: dict[str, str] | None = None,
    dependency_lookup: dict[str, str] | None = None,
    neo4j_session=None,
    toolset=None,
    model: str = "",
    prompt_log_file: str = "",
    discovery_failed: bool = False,
) -> DesignVerifyResult:
    """Run the combined design+verify loop for a single HLR.

    Uses call_tool_loop with design and verification tools so the LLM
    can design, verify against LLRs, discover gaps, and revise.

    Args:
        hlr: HLR dict with {id, description, component_name?}.
        llrs: LLR dicts for this HLR.
        existing_classes: Classes already designed in the same component.
        intercomponent_classes: Public API classes from other components.
        component_namespace: Required namespace for this component.
        sibling_namespaces: Other component namespaces.
        prior_class_lookup: bare_name -> qualified_name for previously designed classes.
        dependency_lookup: bare_name -> qualified_name for dependency API classes.
        neo4j_session: Optional Neo4j session for persistent lookups.
        model: LLM model override.
        prompt_log_file: File path for prompt logging.
        discovery_failed: If True, the dependency discover step failed
            and no dependency classes are available. The design agent
            will be warned about this gap.

    Returns:
        DesignVerifyResult with oo_design, verifications, and any warnings.
    """
    from backend.ticketing_agent.design.design_oo_prompt import (
        build_as_built_section,
        build_existing_classes_section,
        build_intercomponent_section,
        build_namespace_section,
    )

    # Format requirements with full verification stubs from decompose
    llr_verifications: dict[int, list[dict]] = {}
    if neo4j_session is not None and llrs:
        ver_repo = VerificationRepository(neo4j_session)
        for llr in llrs:
            verifs = ver_repo.get_verifications_for_llr(llr["id"])
            if verifs:
                llr_verifications[llr["id"]] = verifs

    requirements_text = format_llrs_with_verifications_for_prompt(llrs, llr_verifications)

    # Prepend the HLR description
    hlr_line = format_hlr_dict(hlr, include_component=True)
    requirements_text = f"{hlr_line}\n\n{requirements_text}"

    # Build dependency lookup dict, seeded with standard containers from Neo4j
    # Container names are seeded into dep_lookup for runtime resolution,
    # but they are NOT listed in the prompt's dependency API section.
    dep_lookup = dict(dependency_lookup or {})
    if neo4j_session is not None:
        container_lookup = seed_container_lookup(neo4j_session)
        if container_lookup:
            before = len(dep_lookup)
            dep_lookup.update(container_lookup)
            log.info(
                "Seeded %d container entries into dep_lookup (was %d, now %d)",
                len(container_lookup),
                before,
                len(dep_lookup),
            )

    # Build prompt sections from context
    specializations_section = ""
    # TODO: build from language/specialization info when available

    namespace_section = build_namespace_section(component_namespace, sibling_namespaces or []) if component_namespace else ""

    as_built_section = ""
    if existing_classes:
        as_built_section = build_as_built_section(existing_classes)

    existing_section = ""
    if existing_classes:
        existing_section = build_existing_classes_section(existing_classes)

    intercomp_section = ""
    if intercomponent_classes:
        intercomp_section = build_intercomponent_section(intercomponent_classes)

    system = SYSTEM_PROMPT.format(
        specializations_section=specializations_section,
        namespace_section=namespace_section,
        as_built_section=as_built_section,
        existing_classes_section=existing_section,
        intercomponent_section=intercomp_section,
    )

    if discovery_failed:
        system += (
            "\n\n## WARNING: Dependency discovery failed\n\n"
            "The dependency discovery step encountered an error and could not"
            " complete. No dependency API classes or as-built classes are"
            " available in the design context. You should design classes that"
            " are self-contained and note in your design that dependency"
            " integration (e.g., inheriting from framework base classes like"
            " Fl_Window or Fl_Button for GUI components) will need to be"
            " added once discovery is re-run successfully. If you are aware"
            " of relevant dependency classes from general knowledge, you may"
            " reference them using inherits_from but acknowledge the gap."
        )

    # Build component context for the user prompt
    component_name = hlr.get("component_name")
    component_hint = ""
    if component_name:
        component_desc = hlr.get("component_description", "")
        component_hint = f"\n\nThis requirement belongs to the architectural component: **{component_name}**"
        if component_namespace:
            component_hint += f" (namespace: `{component_namespace}`)"
        component_hint += ". Your class design should be scoped to this component context.\n"
        if component_desc:
            component_hint += f"\n### Component Description\n\n{component_desc}\n"

    user_content = (
        f"Design the object-oriented class structure and write verification procedures "
        f"for the following requirements:\n\n{requirements_text}{component_hint}"
    )

    messages = [{"role": "user", "content": user_content}]

    # Build tool dispatcher with draft state + Neo4j
    dispatcher = CombinedDispatcher(
        prior_class_lookup=prior_class_lookup or {},
        dependency_lookup=dep_lookup,
        intercomponent_classes=intercomponent_classes or [],
        neo4j_session=neo4j_session,
        toolset=toolset,
    )

    # Run the tool loop
    result = call_tool_loop(
        system=system,
        messages=messages,
        tools=dispatcher.all_tool_schemas,
        final_tool_name="commit_design_and_verifications",
        tool_dispatcher=dispatcher.dispatch,
        model=model,
        max_tokens=65536,
        max_turns=75,
        prompt_log_file=prompt_log_file,
    )

    # Warn if the agent spent too many turns on discovery without designing
    if prompt_log_file and os.path.exists(prompt_log_file):
        try:
            with open(prompt_log_file) as f:
                log_content = f.read()
            discovery_calls = log_content.count("dispatching search_symbols") + \
                              log_content.count("dispatching get_compound") + \
                              log_content.count("dispatching browse_namespace") + \
                              log_content.count("dispatching find_inheritance")
            if discovery_calls > 20:
                log.warning(
                    "design_and_verify: HLR %s used %d discovery tool calls — "
                    "consider tightening the discovery prompt",
                    hlr.get("id", "?"), discovery_calls,
                )
        except Exception:
            pass

    # Parse the final result
    oo_design = ClassDiagram.model_validate(result["oo_design"])

    # Safety check: detect truncated responses where classes/enums/interfaces are missing
    # This happens when the LLM's output is cut off mid-JSON, leaving only associations.
    total_design_elements = len(oo_design.classes) + len(oo_design.enums) + len(oo_design.interfaces)
    if total_design_elements == 0 and oo_design.associations:
        raise ValueError(
            f"design_and_verify: LLM response appears truncated — "
            f"oo_design has {len(oo_design.associations)} associations but 0 "
            f"classes/interfaces/enums. Associations reference undefined class names: "
            f"{sorted({a.subject for a in oo_design.associations} | {a.object for a in oo_design.associations})[:5]}. "
            f"This typically means the commit_design_and_verifications output exceeded the "
            f"token budget. Consider increasing max_tokens or simplifying the design."
        )

    verifications = {}
    valid_llr_ids = {llr["id"] for llr in (llrs or [])}

    for llr_id_str, v_list in result.get("verifications", {}).items():
        # Attempt to parse key as LLR ID; handle non-numeric keys gracefully
        try:
            llr_id = int(llr_id_str)
        except (ValueError, TypeError):
            # LLM used a non-numeric key (e.g. test name) — try to match
            # to known LLRs, or distribute to all LLRs if unknown
            log.warning(
                "design_and_verify: non-numeric verification key '%s', "
                "distributing to all LLRs",
                llr_id_str,
            )
            for known_id in valid_llr_ids:
                parsed = [VerificationSchema.model_validate(v) for v in v_list]
                verifications.setdefault(known_id, []).extend(parsed)
            continue

        if valid_llr_ids and llr_id not in valid_llr_ids:
            log.warning(
                "design_and_verify: verification key %d not in known LLR IDs %s, "
                "distributing to first LLR",
                llr_id, valid_llr_ids,
            )
            fallback_id = min(valid_llr_ids)
            parsed = [VerificationSchema.model_validate(v) for v in v_list]
            verifications.setdefault(fallback_id, []).extend(parsed)
        else:
            verifications[llr_id] = [VerificationSchema.model_validate(v) for v in v_list]

    # Post-loop validation
    design_warnings = []
    verification_warnings = []

    # Collect verification quality warnings
    verification_warnings = _collect_verification_warnings(verifications)

    design_errors = validate_oo_design(
        oo_design,
        prior_class_lookup=prior_class_lookup or {},
        dependency_lookup=dep_lookup,
        intercomponent_classes=intercomponent_classes or [],
    )
    if design_errors:
        design_warnings.extend(design_errors)

    return DesignVerifyResult(
        oo_design=oo_design,
        verifications=verifications,
        design_warnings=design_warnings,
        verification_warnings=verification_warnings,
    )