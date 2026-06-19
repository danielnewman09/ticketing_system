"""Migrated design agent — the canonical HLR design pipeline for
``backend_migrated``.

Runs a single tool loop that designs the OO class structure and
resolves notional verification stubs to qualified design names.
Uses the :class:`DesignToolDispatcher` (design + codegraph tools) and
:class:`VerificationDispatcher` (verification resolution) together.

No imports from ``backend.ticketing_agent`` — fully migrated.

Usage::

    from backend_migrated.agents.design_hlr import design_and_persist_hlr

    summary = design_and_persist_hlr(
        refid="2c3463b2…",
        log_dir="/path/to/logs",
    )
    # → {"nodes_created": 5, "verifications_resolved": 8, "links_applied": 3}
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field

from llm_caller import call_tool_loop

from backend_migrated.models.requirement import HLR, LLR
from backend_migrated.models.verification import VerificationMethod, Condition, Action
from backend_migrated.tools.dispatcher import (
    DesignToolDispatcher,
    VerificationDispatcher,
)
from backend_migrated.requirements.formatting import format_hlrs_for_prompt

log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# Result dataclass
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class DesignHLRResult:
    """Output of ``design_hlr()``.

    Carries the LayerGraph-format design (list of CodeGraphNode dicts)
    and resolved verifications (dict of LLR refid → verification method
    lists).
    """

    design: list[dict] = field(default_factory=list)
    verifications: dict[str, list[dict]] = field(default_factory=dict)


# ══════════════════════════════════════════════════════════════════════════
# Notional verification stub loading
# ══════════════════════════════════════════════════════════════════════════

def _load_notional_verifications(llrs: list[LLR]) -> dict[str, list[dict]]:
    """Load existing notional verification stubs from Neo4j for each LLR.

    Returns a dict mapping LLR refid → list of verification dicts in
    the format expected by the agent prompt.
    """
    llr_verifications: dict[str, list[dict]] = {}

    for llr in llrs:
        vms = llr.verification_methods.all()
        if not vms:
            continue

        verifs_for_llr = []
        for vm in vms:
            vm_dict = {
                "method": vm.method,
                "test_name": vm.test_name or "",
                "description": vm.description or "",
                "preconditions": [],
                "actions": [],
                "postconditions": [],
            }

            conditions = vm.conditions.all()
            for cond in sorted(conditions, key=lambda c: c.order):
                # Traverse LEFT_OPERAND / RIGHT_OPERAND edges to get
                # the target qualified names.
                left_targets = cond.left_operand.all()
                right_targets = cond.right_operand.all()
                cond_dict = {
                    "subject_qualified_name": left_targets[0].qualified_name if left_targets else "",
                    "operator": cond.operator or "==",
                    # expected_value is now a transient attr — traverse
                    # the RIGHT_OPERAND edge to get the value.  For
                    # LiteralNode targets, use .value; for scaffold
                    # nodes, use .qualified_name.
                    "expected_value": (
                        getattr(right_targets[0], "value", None) or
                        right_targets[0].qualified_name
                    ) if right_targets else "",
                    "object_qualified_name": right_targets[0].qualified_name if right_targets else "",
                }
                if cond.phase == "pre":
                    vm_dict["preconditions"].append(cond_dict)
                else:
                    vm_dict["postconditions"].append(cond_dict)

            actions = vm.actions.all()
            for action in sorted(actions, key=lambda a: a.order):
                callee_targets = action.callee.all()
                caller_targets = action.caller.all()
                vm_dict["actions"].append({
                    "description": action.description or "",
                    "callee_qualified_name": callee_targets[0].qualified_name if callee_targets else "",
                    "caller_qualified_name": caller_targets[0].qualified_name if caller_targets else "",
                })

            verifs_for_llr.append(vm_dict)

        if verifs_for_llr:
            llr_verifications[llr.refid] = verifs_for_llr

    return llr_verifications


def _format_verifications_for_prompt(
    llrs: list[LLR],
    notional_verifications: dict[str, list[dict]],
) -> str:
    """Format LLRs with their notional verification stubs for the prompt."""
    lines = []
    for llr in llrs:
        lines.append(f"LLR {llr.refid}: {llr.description}")
        verifs = notional_verifications.get(llr.refid, [])
        if verifs:
            lines.append("  Verifications (notional — resolve to qualified names):")
            for v in verifs:
                label = v.get("test_name", "") or v.get("method", "")
                lines.append(f"    [{v['method']}] {label}: {v.get('description', '')}")
                if v.get("preconditions"):
                    lines.append("      Pre-conditions:")
                    for c in v["preconditions"]:
                        lines.append(
                            f"        {c.get('subject_qualified_name', '')} "
                            f"{c.get('operator', '==')} "
                            f"{c.get('expected_value', '')}"
                        )
                if v.get("actions"):
                    lines.append("      Actions:")
                    for a in v["actions"]:
                        callee = a.get("callee_qualified_name", "")
                        lines.append(
                            f"        {a.get('description', '')}"
                            + (f" → {callee}" if callee else "")
                        )
                if v.get("postconditions"):
                    lines.append("      Post-conditions:")
                    for c in v["postconditions"]:
                        lines.append(
                            f"        {c.get('subject_qualified_name', '')} "
                            f"{c.get('operator', '==')} "
                            f"{c.get('expected_value', '')}"
                        )
        else:
            lines.append("  (No verification stubs)")
        lines.append("")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════
# Prompt
# ══════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """\
You are a software architect and verification engineer. Given design context
and requirements, your job is to produce an object-oriented class design AND
resolve verification stubs to reference real design elements.

**Workflow:**

1. **Design** — Use validate_design and check_class_name to produce a
   sound OO class design. Call produce_oo_design when ready.
2. **Resolve verifications** — Map each notional verification stub to
   qualified names from your design. Call draft_verifications to check
   that all references resolve.
3. **Commit** — Call commit_design_and_verifications with the final
   design and verifications as arguments.

{specializations_section}
{namespace_section}
{as_built_section}
{existing_classes_section}
{intercomponent_section}

### Design rules

- Reference ONLY qualified names from the design context, dependency APIs,
  intercomponent boundaries, or your own draft
- Qualified names follow C++ convention: Namespace::ClassName::memberName
- Use check_class_name to verify association targets before including them
- Keep classes focused and cohesive

### Verification resolution

For each LLR, the notional verification stubs describe test scenarios
using placeholder references like "Engine.result" or "Display.current_value".
Your job is to translate each stub into a fully resolved verification
method that references actual design members.

For each verification stub:
1. Identify what design element each reference targets
2. Replace placeholder references with qualified names from your design
3. Call draft_verifications to validate that every reference resolves
4. If a reference can't resolve, either add the missing member to your
   design via produce_oo_design, or use expected_value alone for literals

<FORMAT-CONTRACT name="qualified-names">
All `subject_qualified_name`, `object_qualified_name`, `callee_qualified_name`,
and `caller_qualified_name` fields MUST use qualified names that exactly match
the design context or the current draft.

Pattern: <namespace>::<ClassName>::<memberName>

Leave `caller_qualified_name` empty if the caller is the test harness.

**Enum values:** When comparing against an enum value, reference the enum
*attribute* as `subject_qualified_name` and put the enum *value* in
`expected_value`. Do NOT use enum values as `subject_qualified_name`.

Example:
  subject_qualified_name: "calc::Calculator::error_signal"
  operator: "=="
  expected_value: "InvalidInput"
</FORMAT-CONTRACT>

<FORMAT-CONTRACT name="verification-key-format">
The `verifications` field in `draft_verifications` MUST be a JSON object
keyed by LLR refid (string), NOT by test name.

Example: "verifications": {{ "abc123": [...], "def456": [...] }}
Wrong:   "verifications": {{ "test_add": [...] }}
</FORMAT-CONTRACT>

You MUST use commit_design_and_verifications to return your final result.
Pass the design (same list of CodeGraphNode dicts from produce_oo_design)
and the verifications dict (same structure from draft_verifications) as
arguments to commit_design_and_verifications.
"""


# ══════════════════════════════════════════════════════════════════════════
# Core pipeline
# ══════════════════════════════════════════════════════════════════════════

def design_hlr(
    hlr: HLR,
    llrs: list[LLR],
    *,
    prior_class_lookup: dict[str, str] | None = None,
    dependency_lookup: dict[str, str] | None = None,
    intercomponent_classes: list[dict] | None = None,
    component_namespace: str = "",
    sibling_namespaces: list[str] | None = None,
    model: str = "",
    log_dir: str = "",
) -> DesignHLRResult:
    """Design a single HLR and resolve its verification stubs.

    Runs a single tool loop that:
    1. Designs the OO class structure (using DesignToolDispatcher)
    2. Resolves notional verification stubs to qualified names (using
       VerificationDispatcher)
    3. Commits the combined result

    Args:
        hlr: Neomodel HLR instance.
        llrs: Neomodel LLR instances belonging to this HLR.
        prior_class_lookup: Name → qualified_name from prior designs.
        dependency_lookup: Name → qualified_name for dependency API classes.
        intercomponent_classes: Inter-component boundary class dicts.
        component_namespace: Required C++ namespace for this component.
        sibling_namespaces: Other component namespaces.
        model: LLM model override.
        log_dir: Directory for per-step prompt logs.

    Returns:
        ``DesignHLRResult`` with ``design`` (LayerGraph-format nodes)
        and ``verifications`` (LLR refid → verification method lists).
    """
    from backend_migrated.agents.design_oo_prompt import (
        build_existing_classes_section,
        build_intercomponent_section,
        build_namespace_section,
    )

    # --- Load notional verification stubs from Neo4j ---
    notional_verifications = _load_notional_verifications(llrs)

    # --- Build requirements text for the prompt ---
    hlr_line = f"HLR: {hlr.description}"
    verifs_text = _format_verifications_for_prompt(llrs, notional_verifications)
    requirements_text = f"{hlr_line}\n\n{verifs_text}"

    # --- Build prompt sections ---
    namespace_section = (
        build_namespace_section(component_namespace, sibling_namespaces or [])
        if component_namespace
        else ""
    )
    existing_section = (
        build_existing_classes_section(intercomponent_classes or [])
        if intercomponent_classes
        else ""
    )
    intercomp_section = (
        build_intercomponent_section(intercomponent_classes or [])
        if intercomponent_classes
        else ""
    )

    system = SYSTEM_PROMPT.format(
        specializations_section="",
        namespace_section=namespace_section,
        as_built_section="",
        existing_classes_section=existing_section,
        intercomponent_section=intercomp_section,
    )

    # --- Component hint for user prompt ---
    comp_nodes = hlr.component.all()
    component_hint = ""
    if comp_nodes:
        comp = comp_nodes[0]
        comp_name = comp.name or ""
        if comp_name:
            component_hint = (
                f"\n\nThis requirement belongs to the architectural "
                f"component: **{comp_name}**"
            )
            if component_namespace:
                component_hint += f" (namespace: `{component_namespace}`)"
            component_hint += (
                ". Your class design should be scoped to this component.\n"
            )
            if comp.description:
                component_hint += (
                    f"\n### Component Description\n\n{comp.description}\n"
                )

    user_message = {
        "role": "user",
        "content": (
            "Design the object-oriented class structure and resolve "
            "verification stubs for the following requirements:\n\n"
            f"{requirements_text}{component_hint}"
        ),
    }

    messages = [user_message]

    # --- Build dispatchers ---
    design_disp = DesignToolDispatcher(
        prior_class_lookup=prior_class_lookup or {},
        dependency_lookup=dependency_lookup or {},
        intercomponent_classes=intercomponent_classes or [],
        component_namespace=component_namespace,
        sibling_namespaces=sibling_namespaces or [],
    )
    verif_disp = VerificationDispatcher(design_dispatcher=design_disp)

    # --- Composite dispatch function ---
    def dispatch(tool_name: str, tool_input: dict) -> str:
        if tool_name in verif_disp._handlers:
            return verif_disp.dispatch(tool_name, tool_input)
        return design_disp.dispatch(tool_name, tool_input)

    # --- Combined tool schemas ---
    all_tools = design_disp.all_tool_schemas + verif_disp.all_tool_schemas

    # --- Run the tool loop ---
    prompt_log = ""
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        prompt_log = os.path.join(log_dir, f"design_verify_hlr_{hlr.refid[:8]}.md")

    log.info(
        "design_hlr: starting tool loop for HLR %s with %d tools",
        hlr.refid[:8], len(all_tools),
    )
    try:
        result = call_tool_loop(
            system=system,
            messages=messages,
            tools=all_tools,
            final_tool_name="commit_design_and_verifications",
            tool_dispatcher=dispatch,
            model=model,
            max_tokens=65536,
            max_turns=75,
            prompt_log_file=prompt_log,
        )
    except Exception as exc:
        log.error(
            "design_hlr: tool loop failed for HLR %s: %s",
            hlr.refid[:8], exc, exc_info=True,
        )
        raise

    # --- Extract result ---
    design_nodes = result.get("design", [])
    verifications = result.get("verifications", {})

    log.info(
        "Design complete for HLR %s: %d design nodes, %d LLRs with verifications",
        hlr.refid[:8], len(design_nodes), len(verifications),
    )

    return DesignHLRResult(
        design=design_nodes,
        verifications=verifications,
    )


# ══════════════════════════════════════════════════════════════════════════
# Full entry point — context loading + pipeline + persistence
# ══════════════════════════════════════════════════════════════════════════

def design_and_persist_hlr(
    refid: str,
    *,
    log_dir: str = "",
) -> dict:
    """Design a single HLR end-to-end: load context → design + verify → persist.

    Reads the HLR and its LLRs from Neo4j via neomodel, gathers component
    and namespace context, runs the design+verification agent, persists
    the resulting design nodes and resolved verifications, and returns
    a summary.

    Args:
        refid: The HLR's ``refid`` (hex UUID string).
        log_dir: Directory for per-step prompt logs.

    Returns:
        Dict with keys ``nodes_created``, ``verifications_resolved``,
        ``conditions_created``, ``actions_created``, ``links_applied``.

    Raises:
        ValueError: If the HLR is not found or has no LLRs.
    """
    from codegraph.connection import get_session as get_neo
    from codegraph.graph import LayerGraph

    # --- Load data from Neo4j via neomodel ---
    log.info("design_and_persist_hlr: loading HLR %s", refid[:8])
    hlr = HLR.nodes.get_or_none(refid=refid)
    if not hlr:
        raise ValueError(f"HLR {refid} not found")

    llr_nodes = hlr.llrs.all()
    if not llr_nodes:
        raise ValueError(f"HLR {refid} has no LLRs — decompose it first")
    log.info(
        "design_and_persist_hlr: found HLR %s with %d LLRs",
        refid[:8], len(llr_nodes),
    )

    # Component context
    comp_nodes = hlr.component.all()
    component_namespace = getattr(comp_nodes[0], "namespace", "") if comp_nodes else ""

    # Sibling namespaces
    sibling_namespaces: list[str] = []
    for s in HLR.nodes.all():
        if s.refid == refid:
            continue
        sc = s.component.all()
        if sc:
            ns = getattr(sc[0], "namespace", "")
            if ns and ns not in sibling_namespaces:
                sibling_namespaces.append(ns)

    # Build intercomponent classes from previously designed HLRs
    intercomponent_classes: list[dict] = []
    for other_hlr in HLR.nodes.all():
        if other_hlr.refid == refid:
            continue
        for target in other_hlr.design_compounds.all():
            intercomponent_classes.append({
                "qualified_name": target.qualified_name,
                "name": target.name or "",
                "kind": getattr(target, "kind", "class"),
            })

    # --- Run the design pipeline ---
    log.info("design_and_persist_hlr: running design_hlr for %s", refid[:8])
    result = design_hlr(
        hlr=hlr,
        llrs=llr_nodes,
        intercomponent_classes=intercomponent_classes or None,
        component_namespace=component_namespace,
        sibling_namespaces=sibling_namespaces or None,
        log_dir=log_dir,
    )
    log.info(
        "design_and_persist_hlr: design_hlr returned %d design nodes, %d LLR verifications",
        len(result.design), len(result.verifications),
    )

    # --- Persist design to Neo4j via LayerGraph ---
    nodes_created = 0
    if result.design:
        try:
            graph = LayerGraph.deserialize(result.design)
            graph.to_neo4j()
            nodes_created = len(result.design)
        except Exception as exc:
            log.warning("Failed to persist design for HLR %s: %s", refid[:8], exc)

    # --- Persist resolved verifications ---
    verifications_resolved = 0
    conditions_created = 0
    actions_created = 0

    for llr_refid, verif_list in result.verifications.items():
        llr = next((l for l in llr_nodes if l.refid == llr_refid), None)
        if not llr:
            log.warning("LLR refid %s not found, skipping verification persist", llr_refid)
            continue

        # Delete existing notional verifications for this LLR
        for old_vm in llr.verification_methods.all():
            old_vm.delete()

        # Create resolved verifications
        for v in verif_list:
            vm, conditions, actions = VerificationMethod.from_llm_dict(v)
            vm.save()
            llr.verification_methods.connect(vm)
            verifications_resolved += 1

            for cond in conditions:
                cond.save()
                vm.conditions.connect(cond)
                conditions_created += 1

            for action in actions:
                action.save()
                vm.actions.connect(action)
                actions_created += 1

    # --- Create COMPOSES edges from HLR to design nodes ---
    links_applied = 0
    from codegraph.models.compound import CompoundNode

    for node_dict in result.design:
        qn = node_dict.get("qualified_name", "")
        if not qn:
            continue
        kind = node_dict.get("kind", "")
        # Only link HLR to top-level compound/class nodes (not members)
        if kind not in ("class", "struct", "interface", "enum"):
            continue
        target_node = CompoundNode.nodes.get_or_none(qualified_name=qn)
        if not target_node:
            continue
        try:
            hlr.design_compounds.connect(target_node)
            links_applied += 1
        except Exception as exc:
            log.warning("Failed to COMPOSES link HLR %s -> %s: %s", refid[:8], qn, exc)

    log.info(
        "Design+verify complete for HLR %s: %d nodes, %d verifications, "
        "%d conditions, %d actions",
        refid[:8], nodes_created, verifications_resolved,
        conditions_created, actions_created,
    )

    return {
        "nodes_created": nodes_created,
        "verifications_resolved": verifications_resolved,
        "conditions_created": conditions_created,
        "actions_created": actions_created,
        "links_applied": links_applied,
    }