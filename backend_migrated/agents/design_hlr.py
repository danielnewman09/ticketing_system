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
from neomodel import db as neomodel_db

from codegraph.models.tags import CodeGraphNode
from backend_migrated.models.requirement import HLR, LLR
from backend_migrated.models.verification import TestNode, AssertionNode, TestStepNode, get_typed_edge_targets
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
        tests = llr.verification_methods.all()
        if not tests:
            continue

        verifs_for_llr = []
        for test_node in tests:
            vm_dict = {
                "method": test_node.method,
                "test_name": test_node.test_name or "",
                "description": test_node.description or "",
                "preconditions": [],
                "actions": [],
                "postconditions": [],
            }

            assertions = test_node.assertions.all()
            for assertion in sorted(assertions, key=lambda a: a.order):
                # Traverse LEFT_OPERAND / RIGHT_OPERAND edges to get
                # the target qualified names.
                left_targets = get_typed_edge_targets(assertion, "LEFT_OPERAND")
                right_targets = get_typed_edge_targets(assertion, "RIGHT_OPERAND")
                cond_dict = {
                    "subject_qualified_name": left_targets[0]["qualified_name"] if left_targets else "",
                    "operator": assertion.operator or "==",
                    # expected_value is now a transient attr — traverse
                    # the RIGHT_OPERAND edge to get the value.  For
                    # LiteralNode targets, use .value; for scaffold
                    # nodes, use .qualified_name.
                    "expected_value": (
                        right_targets[0].get("value") or
                        right_targets[0]["qualified_name"]
                    ) if right_targets else "",
                    "object_qualified_name": right_targets[0]["qualified_name"] if right_targets else "",
                }
                if assertion.phase == "pre":
                    vm_dict["preconditions"].append(cond_dict)
                else:
                    vm_dict["postconditions"].append(cond_dict)

            steps = test_node.steps.all()
            for step in sorted(steps, key=lambda s: s.order):
                callee_targets = get_typed_edge_targets(step, "CALLEE")
                caller_targets = get_typed_edge_targets(step, "CALLER")
                vm_dict["actions"].append({
                    "description": step.description or "",
                    "callee_qualified_name": callee_targets[0]["qualified_name"] if callee_targets else "",
                    "caller_qualified_name": caller_targets[0]["qualified_name"] if caller_targets else "",
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
using placeholder references like "Thermostat.current_reading" or "Display.shown_temp".
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
  subject_qualified_name: "climate::Thermostat::error_state"
  operator: "=="
  expected_value: "SensorFault"
</FORMAT-CONTRACT>

<FORMAT-CONTRACT name="verification-key-format">
The `verifications` field in `draft_verifications` MUST be a JSON object
keyed by LLR refid (string), NOT by test name.

Example: "verifications": {{ "abc123": [...], "def456": [...] }}
Wrong:   "verifications": {{ "test_set_target": [...] }}
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
# Scaffold → design reconciliation helpers
# ══════════════════════════════════════════════════════════════════════════
#
# Instead of creating entirely new nodes via ``LayerGraph.to_neo4j()`` (which
# produces tag-less nodes that ``graph_fetch(tag="design")`` can't find), we
# *update* existing scaffold nodes in place — changing their ``tags`` from
# ``["scaffold"]`` to ``["design"]``, updating their ``qualified_name``/
# ``kind``/``visibility``/``type_signature`` to match the real design, and
# changing their Neo4j label when the node type changes (e.g.
# ``AttributeNode`` → ``MethodNode``).
#
# This preserves the verification edges (``LEFT_OPERAND``, ``CALLEE``, etc.)
# that already connect Conditions/Actions to scaffold nodes.  Those edges use
# Neo4j ``elementId`` (not the deterministic ``uid``), so updating a node's
# properties doesn't break its edges.
#
# For design nodes that have no scaffold equivalent (e.g. new ``NamespaceNode``,
# ``EnumNode``, private backing attributes), we create them fresh with
# ``tags=["design"]``.


def _last_segment(qn: str) -> str:
    """Extract the last segment from a qualified name.

    Handles both ``::`` (C++ convention) and ``.`` (notional convention)
    separators, and leaves ``literal::`` prefixed names intact.
    """
    if not qn:
        return ""
    if qn.startswith("literal::"):
        return qn
    if "::" in qn:
        return qn.rsplit("::", 1)[-1]
    if "." in qn:
        return qn.rsplit(".", 1)[-1]
    return qn


def _flatten_design_nodes(design_nodes: list[dict]) -> list[dict]:
    """Flatten nested design node dicts (with ``composes`` children) into a flat list."""
    flat: list[dict] = []

    def _walk(node: dict) -> None:
        flat.append(node)
        for child in node.get("composes", []):
            _walk(child)

    for d in design_nodes:
        _walk(d)
    return flat


def _update_scaffold_to_design(scaffold_node, design_dict: dict) -> bool:
    """Update a scaffold node in place to become a design node via raw Cypher.

    Changes the node's ``qualified_name``, ``name``, ``kind``, ``tags``,
    ``uid`` (recomputed deterministically), and optionally ``type_signature``,
    ``visibility``, ``brief_description``.  Also changes the Neo4j label when
    the node type changes (e.g. ``AttributeNode`` → ``MethodNode``).

    The node's ``elementId`` stays the same, so all existing edges
    (``LEFT_OPERAND``, ``CALLEE``, ``COMPOSES``, etc.) remain intact.
    """
    from codegraph.uid import compute_uid, normalize_argsstring

    dqn = design_dict.get("qualified_name", "")
    if not dqn:
        return False

    dname = design_dict.get("name", "") or _last_segment(dqn)
    dkind = design_dict.get("kind", "")
    dtype = design_dict.get("type", "")
    dts = design_dict.get("type_signature", "")
    dvis = design_dict.get("visibility", "")
    dbd = design_dict.get("brief_description", "")

    # Compute new deterministic uid
    if dtype == "MethodNode":
        argsstring = design_dict.get("argsstring", "") or dts
        new_uid = compute_uid(dqn, normalize_argsstring(argsstring))
    else:
        new_uid = compute_uid(dqn)

    sn_type = type(scaffold_node).__name__
    eid = neomodel_db.parse_element_id(scaffold_node.element_id)

    # Build SET clause
    set_parts = [
        "n.qualified_name = $qn",
        "n.name = $name",
        "n.kind = $kind",
        "n.tags = $tags",
        "n.uid = $uid",
    ]
    params: dict = {
        "eid": eid,
        "qn": dqn,
        "name": dname,
        "kind": dkind,
        "tags": ["design"],
        "uid": new_uid,
    }
    if dts:
        set_parts.append("n.type_signature = $ts")
        params["ts"] = dts
    if dvis:
        set_parts.append("n.visibility = $vis")
        params["vis"] = dvis
    if dbd:
        set_parts.append("n.brief_description = $bd")
        params["bd"] = dbd

    # Label change if type differs
    label_ops = ""
    if dtype and dtype != sn_type:
        label_ops = f"REMOVE n:`{sn_type}` SET n:`{dtype}` "

    query = (
        f"MATCH (n) WHERE elementId(n) = $eid "
        f"{label_ops}"
        f"SET {', '.join(set_parts)}"
    )
    try:
        neomodel_db.cypher_query(query, params)
        log.info("Updated scaffold %s → %s (%s → %s)",
                 getattr(scaffold_node, "qualified_name", "?"), dqn,
                 sn_type, dtype or sn_type)
        return True
    except Exception as exc:
        log.warning("Failed to update scaffold %s → %s: %s",
                     getattr(scaffold_node, "qualified_name", "?"), dqn, exc)
        return False


def _create_design_node_fresh(design_dict: dict) -> bool:
    """Create a new design node with ``tags=["design"]``.

    Used for design nodes that have no scaffold equivalent (e.g. new
    ``NamespaceNode``, ``EnumNode``, private backing attributes).
    """
    node_data = dict(design_dict)
    node_data["tags"] = ["design"]
    # Strip composes — we'll set up edges separately
    node_data.pop("composes", None)
    try:
        node = CodeGraphNode.deserialize(node_data)
        node.save()
        log.info("Created design node: %s (%s)",
                 node_data.get("qualified_name", "?"),
                 node_data.get("type", "?"))
        return True
    except Exception as exc:
        log.warning("Failed to create design node %s: %s",
                     node_data.get("qualified_name", "?"), exc)
        return False


def _link_design_composes(flat_design: list[dict]) -> int:
    """Create COMPOSES edges between design nodes based on qualified-name hierarchy.

    For each node with a ``::``-separated qualified_name, creates a COMPOSES
    edge from the parent (the prefix before the last ``::``) to this node.
    Uses raw Cypher MERGE so edges are idempotent.
    """
    edges = 0
    qnames = {d.get("qualified_name", "") for d in flat_design}
    for d in flat_design:
        qn = d.get("qualified_name", "")
        if not qn or "::" not in qn:
            continue
        parent_qn = qn.rsplit("::", 1)[0]
        if not parent_qn or parent_qn not in qnames:
            continue
        try:
            neomodel_db.cypher_query(
                "MATCH (s), (t) "
                "WHERE s.qualified_name = $sqn AND t.qualified_name = $tqn "
                "MERGE (s)-[:COMPOSES]->(t)",
                {"sqn": parent_qn, "tqn": qn},
            )
            edges += 1
        except Exception as exc:
            log.warning("Failed to COMPOSES %s → %s: %s", parent_qn, qn, exc)
    return edges


def _retag_remaining_scaffold() -> int:
    """Change ``tags`` from ``["scaffold"]`` to ``["design"]`` on scaffold
    nodes that still have verification edges.

    After matched scaffold nodes are updated, some scaffold-tagged nodes may
    remain — typically ``LiteralNode`` s referenced by ``RIGHT_OPERAND``
    edges from Conditions.  These are still part of the design's verification
    data, so they should carry the ``design`` tag.
    """
    retagged = 0
    try:
        results, _ = neomodel_db.cypher_query(
            "MATCH (n) WHERE 'scaffold' IN coalesce(n.tags, []) "
            "AND EXISTS { MATCH ()-[r]->(n) WHERE type(r) IN ['LEFT_OPERAND','RIGHT_OPERAND','CALLEE','CALLER'] } "
            "RETURN elementId(n)",
        )
        for (eid,) in results:
            try:
                neomodel_db.cypher_query(
                    "MATCH (n) WHERE elementId(n) = $eid "
                    "SET n.tags = ['design']",
                    {"eid": eid},
                )
                retagged += 1
            except Exception:
                pass
        if retagged:
            log.info("Re-tagged %d scaffold nodes (still referenced by edges) to design", retagged)
    except Exception as exc:
        log.warning("Re-tagging remaining scaffold nodes failed: %s", exc)
    return retagged


def _cleanup_orphaned_scaffold_nodes(hlr_refid: str) -> int:
    """Delete scaffold nodes that no longer have any relationships.

    After reconciliation, scaffold nodes that lost all their edges (because
    their referencing Conditions/Actions were from a different HLR that hasn't
    been designed yet, or because they were duplicates) become fully isolated.
    These are safe to delete.
    """
    cleaned = 0
    try:
        results, _ = neomodel_db.cypher_query(
            "MATCH (n) WHERE 'scaffold' IN coalesce(n.tags, []) "
            "AND NOT EXISTS { MATCH (n)-[r]-() } "
            "RETURN elementId(n)",
        )
        for (eid,) in results:
            try:
                neomodel_db.cypher_query(
                    "MATCH (n) WHERE elementId(n) = $eid "
                    "DETACH DELETE n",
                    {"eid": eid},
                )
                cleaned += 1
            except Exception:
                pass
        if cleaned:
            log.info("Cleaned up %d orphaned scaffold nodes for HLR %s",
                     cleaned, hlr_refid[:8])
    except Exception as exc:
        log.warning("Scaffold cleanup failed for HLR %s: %s", hlr_refid[:8], exc)
    return cleaned


def _reconcile_design_with_scaffold(
    hlr_refid: str,
    design_nodes: list[dict],
) -> dict:
    """Reconcile the design with existing scaffold nodes.

    Instead of creating entirely new nodes (which lose the verification-edge
    bridge), updates scaffold nodes in place to become design nodes and
    creates fresh nodes only for elements that have no scaffold equivalent.

    Steps:
      1. Flatten the nested design node dicts.
      2. Fetch all scaffold nodes and index by the last segment of their
         ``qualified_name`` (e.g. ``Thermostat::current_reading`` → ``current_reading``).
      3. For each design node, try to match it to a scaffold node by last
         segment.  If matched, update the scaffold node in place.
      4. For unmatched design nodes, create them fresh with ``tags=["design"]``.
      5. Create ``COMPOSES`` edges between all design nodes based on the
         ``::``-separated qualified-name hierarchy.
      6. Re-tag scaffold ``LiteralNode`` s that are still referenced by
         verification edges.
      7. Clean up orphaned scaffold nodes.

    Does **not** touch verification Conditions/Actions — their edges
    (``LEFT_OPERAND``, ``CALLEE``, etc.) already point to scaffold nodes
    that are now updated to design nodes, so the bridge is preserved.

    Returns:
        Dict with ``nodes_updated``, ``nodes_created``, ``edges_linked``,
        ``scaffold_retaged``, ``scaffold_cleaned``.
    """
    # 1. Flatten design nodes
    flat = _flatten_design_nodes(design_nodes)
    log.info("Reconciling design: %d flat nodes from %d root nodes",
             len(flat), len(design_nodes))

    # 2. Fetch scaffold nodes and index by last segment
    scaffold_nodes = CodeGraphNode.fetch_all_by_tag("scaffold")
    scaffold_by_seg: dict[str, list] = {}
    for sn in scaffold_nodes:
        qn = getattr(sn, "qualified_name", "") or ""
        seg = _last_segment(qn)
        if seg:
            scaffold_by_seg.setdefault(seg, []).append(sn)
    log.info("Found %d scaffold nodes indexed into %d segments",
             len(scaffold_nodes), len(scaffold_by_seg))

    # 3. Match design nodes to scaffold nodes
    matched_pairs: list[tuple[object, dict]] = []
    unmatched_design: list[dict] = []
    used_scaffold_eids: set[str] = set()

    for d in flat:
        dqn = d.get("qualified_name", "")
        dseg = _last_segment(dqn)
        matched_sn = None
        if dseg and dseg in scaffold_by_seg:
            for sn in scaffold_by_seg[dseg]:
                sn_eid = sn.element_id
                if sn_eid not in used_scaffold_eids:
                    matched_sn = sn
                    used_scaffold_eids.add(sn_eid)
                    break
        if matched_sn is not None:
            matched_pairs.append((matched_sn, d))
        else:
            unmatched_design.append(d)

    log.info("Matched %d design nodes to scaffold, %d unmatched",
             len(matched_pairs), len(unmatched_design))

    # 4. Update matched scaffold nodes in place
    nodes_updated = 0
    for sn, d in matched_pairs:
        if _update_scaffold_to_design(sn, d):
            nodes_updated += 1

    # 5. Create unmatched design nodes fresh
    nodes_created = 0
    for d in unmatched_design:
        if _create_design_node_fresh(d):
            nodes_created += 1

    # 6. Create COMPOSES edges between all design nodes
    edges_linked = _link_design_composes(flat)

    # 7. Re-tag scaffold LiteralNodes still referenced by verification edges
    scaffold_retaged = _retag_remaining_scaffold()

    # 8. Clean up orphaned scaffold nodes
    scaffold_cleaned = _cleanup_orphaned_scaffold_nodes(hlr_refid)

    return {
        "nodes_updated": nodes_updated,
        "nodes_created": nodes_created,
        "edges_linked": edges_linked,
        "scaffold_retaged": scaffold_retaged,
        "scaffold_cleaned": scaffold_cleaned,
    }


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
        Dict with keys ``nodes_updated``, ``nodes_created``, ``edges_linked``,
        ``verifications_resolved``, ``conditions_created``, ``actions_created``,
        ``links_applied``, ``scaffold_retaged``, ``scaffold_cleaned``.

    Raises:
        ValueError: If the HLR is not found or has no LLRs.
    """
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

    # --- Reconcile design with scaffold (update in place, preserve edges) ---
    # Instead of creating new tag-less nodes via graph.to_neo4j(),
    # update existing scaffold nodes to become design nodes.
    # This preserves the verification edges (LEFT_OPERAND, CALLEE, etc.)
    # that already connect Conditions/Actions to scaffold nodes.
    recon = {"nodes_updated": 0, "nodes_created": 0, "edges_linked": 0,
             "scaffold_retaged": 0, "scaffold_cleaned": 0}
    if result.design:
        try:
            recon = _reconcile_design_with_scaffold(refid, result.design)
        except Exception as exc:
            log.warning("Design reconciliation failed for HLR %s: %s",
                        refid[:8], exc, exc_info=True)

    # --- Verifications: keep existing, they already point to scaffold nodes ---
    # The decompose phase created VMs/Conditions/Actions with edges to
    # scaffold nodes.  The scaffold nodes are now updated to design nodes
    # (tags=["design"], new qualified_names, proper kinds).  The edges use
    # Neo4j elementId, so they still point to the same (now-updated) nodes.
    #
    # We do NOT delete/recreate verifications — the bridge is preserved.
    # The design agent's verification resolution was used for validation
    # (ensuring all references resolve) during the tool loop.
    verifications_resolved = len(result.verifications)
    conditions_created = 0
    actions_created = 0
    for llr_refid, verif_list in result.verifications.items():
        for v in verif_list:
            conditions_created += len(v.get("preconditions", []))
            conditions_created += len(v.get("postconditions", []))
            actions_created += len(v.get("actions", []))

    # --- Create COMPOSES edges from HLR to top-level design compounds ---
    links_applied = 0
    from codegraph.models.compound import CompoundNode

    for node_dict in result.design:
        qn = node_dict.get("qualified_name", "")
        if not qn:
            continue
        kind = node_dict.get("kind", "")
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
        "Design+verify complete for HLR %s: %d nodes updated, %d created, "
        "%d COMPOSES edges, %d verifications (preserved), %d conditions, "
        "%d actions, %d scaffold retaged, %d scaffold cleaned",
        refid[:8], recon["nodes_updated"], recon["nodes_created"],
        recon["edges_linked"], verifications_resolved,
        conditions_created, actions_created,
        recon["scaffold_retaged"], recon["scaffold_cleaned"],
    )

    return {
        "nodes_updated": recon["nodes_updated"],
        "nodes_created": recon["nodes_created"],
        "edges_linked": recon["edges_linked"],
        "verifications_resolved": verifications_resolved,
        "conditions_created": conditions_created,
        "actions_created": actions_created,
        "links_applied": links_applied,
        "scaffold_retaged": recon["scaffold_retaged"],
        "scaffold_cleaned": recon["scaffold_cleaned"],
    }