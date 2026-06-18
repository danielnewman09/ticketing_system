"""LLR CRUD and detail data — migrated backend.

Uses neomodel models (LLR, HLR, VerificationMethod) for CRUD
operations and neomodel relationship managers for COMPOSES traversal.
Node identity is via ``refid`` (UniqueIdProperty), matching the
pattern used by HLR and FileNode.

Neomodel auto-initialises its database driver on first query, so no
explicit ``_ensure_driver()`` call is needed before neomodel
operations.  For raw Cypher, ``get_session()`` handles driver
initialisation internally.

No imports from backend/ anywhere in this module.
"""

from __future__ import annotations

import logging

from typing import TypedDict

from backend_migrated.models import HLR, LLR, VerificationMethod, Condition, Action

log = logging.getLogger(__name__)


class ConditionRow(TypedDict):
    subject_qualified_name: str
    operator: str
    expected_value: str


class ActionRow(TypedDict):
    order: int
    description: str
    callee_qualified_name: str | None
    caller_qualified_name: str | None


class VerificationDetail(TypedDict):
    id: str
    method: str
    test_name: str | None
    description: str | None
    preconditions: list[ConditionRow]
    actions: list[ActionRow]
    postconditions: list[ConditionRow]


class HLRSummary(TypedDict):
    id: str
    description: str
    component: str | None


class LLRDetail(TypedDict):
    id: str
    description: str
    hlr: HLRSummary | None
    verifications: list[VerificationDetail]
    components: list[str]
    triples: list[dict]


def fetch_llr_detail(refid: str) -> LLRDetail | None:
    """Fetch all data needed for LLR detail page.

    Uses neomodel objects for LLR/HLR/VM traversal and
    ``CodeGraphNode.serialize()`` for dict production.
    Returns ``None`` if the LLR is not found.
    """
    llr = LLR.nodes.get_or_none(refid=refid)
    if not llr:
        return None

    # Parent HLR
    hlr_nodes = llr.hlr.all()
    hlr_data: HLRSummary | None = None
    if hlr_nodes:
        hlr = hlr_nodes[0]
        comp_nodes = hlr.component.all()
        hlr_data = {
            "id": hlr.refid,
            "description": hlr.description,
            "component": comp_nodes[0].name if comp_nodes else None,
        }

    # Verification methods with conditions and actions
    verifications: list[VerificationDetail] = []
    for vm in llr.verification_methods.all():
        cond_nodes = vm.conditions.all()
        act_nodes = vm.actions.all()

        preconditions: list[ConditionRow] = [
            {
                "subject_qualified_name": c.subject_qualified_name,
                "operator": c.operator,
                "expected_value": c.expected_value,
            }
            for c in cond_nodes
            if c.phase == "pre"
        ]
        postconditions: list[ConditionRow] = [
            {
                "subject_qualified_name": c.subject_qualified_name,
                "operator": c.operator,
                "expected_value": c.expected_value,
            }
            for c in cond_nodes
            if c.phase == "post"
        ]
        actions: list[ActionRow] = [
            {
                "order": a.order,
                "description": a.description,
                "callee_qualified_name": a.callee_qualified_name,
                "caller_qualified_name": a.caller_qualified_name,
            }
            for a in act_nodes
        ]

        verifications.append({
            "id": vm.refid,
            "method": vm.method,
            "test_name": vm.test_name,
            "description": vm.description,
            "preconditions": preconditions,
            "actions": actions,
            "postconditions": postconditions,
        })

    # Component names (through HLR)
    components: list[str] = []
    if hlr_nodes:
        comp_nodes = hlr_nodes[0].component.all()
        components = [c.name for c in comp_nodes if c.name]

    # COMPOSES triples — walk via neomodel relationship managers
    triples: list[dict] = []
    try:
        seen = set()
        for target in llr.design_compounds.all():
            qn = getattr(target, "qualified_name", "")
            if not qn:
                continue
            # Walk the target's outgoing edges
            target_edges = target.serialize_edges()
            for edge in target_edges:
                if edge["relation_type"] in ("IMPLEMENTED_BY", "COMPOSES"):
                    continue
                tgt_qn = edge.get("target_uid", "")
                key = (qn, edge["relation_type"], tgt_qn)
                if key not in seen and all(key):
                    seen.add(key)
                    triples.append({
                        "subject": qn,
                        "predicate": edge["relation_type"],
                        "object": tgt_qn,
                    })
    except Exception:
        log.warning("Failed to fetch LLR triples", exc_info=True)

    return {
        "id": llr.refid,
        "description": llr.description,
        "hlr": hlr_data,
        "verifications": verifications,
        "components": components,
        "triples": triples,
    }


def create_llr(hlr_refid: str, description: str) -> str:
    """Create a new LLR under an HLR in Neo4j. Returns the new LLR's refid.

    Uses ``CodeGraphNode.save_new()`` to validate, construct, and persist
    the node in one call.  Creates a COMPOSES edge from the parent HLR.
    """
    hlr = HLR.nodes.get_or_none(refid=hlr_refid)
    if not hlr:
        raise ValueError(f"HLR {hlr_refid} not found")

    llr = LLR.save_new(description=description, layer="design")
    hlr.llrs.connect(llr)

    log.info("Created LLR refid=%s under HLR refid=%s", llr.refid, hlr_refid)
    return llr.refid


def update_llr(refid: str, description: str) -> bool:
    """Update an LLR's description in Neo4j. Returns True on success.

    Uses ``CodeGraphNode.update()`` to validate and persist the change.
    """
    llr = LLR.nodes.get_or_none(refid=refid)
    if not llr:
        return False

    llr.update(description=description)
    return True


def delete_llr(refid: str) -> bool:
    """Delete an LLR and its COMPOSES subtree from Neo4j. Returns True on success.

    ``CodeGraphNode.delete()`` cascades through all outgoing COMPOSES
    children (depth-first, leaves first), disconnects remaining
    relationships, then removes the node.
    """
    llr = LLR.nodes.get_or_none(refid=refid)
    if not llr:
        return False

    llr.delete()
    return True


def update_verification(vm_refid: str, data: dict) -> bool:
    """Replace a verification method's conditions and actions from raw dict data.

    Updates the VM's ``method``, ``test_name``, and ``description`` properties.
    Deletes all existing Condition and Action children, then recreates them
    from the ``preconditions``, ``actions``, and ``postconditions`` keys in
    *data*.

    Args:
        vm_refid: The VerificationMethod's ``refid``.
        data: Dict with keys ``method``, ``test_name``, ``description``,
            ``preconditions`` (list of condition dicts), ``actions``
            (list of action dicts), and ``postconditions`` (list of
            condition dicts).  All condition dicts must have
            ``subject_qualified_name``, ``operator``, and
            ``expected_value``.  All action dicts must have
            ``description``.

    Returns:
        ``True`` on success, ``False`` if the VM is not found.
    """
    vm = VerificationMethod.nodes.get_or_none(refid=vm_refid)
    if not vm:
        log.warning("VerificationMethod %s not found", vm_refid[:8])
        return False

    # Update basic properties
    vm.method = data.get("method", vm.method)
    vm.test_name = data.get("test_name", vm.test_name)
    vm.description = data.get("description", vm.description)
    vm.save()

    # Delete existing conditions and actions
    for c in vm.conditions.all():
        vm.conditions.disconnect(c)
        c.delete()
    for a in vm.actions.all():
        vm.actions.disconnect(a)
        a.delete()

    # Recreate preconditions
    for i, cond in enumerate(data.get("preconditions", [])):
        try:
            c = Condition.save_new(
                phase="pre",
                order=i,
                operator=cond.get("operator", "=="),
                expected_value=cond.get("expected_value", ""),
                subject_qualified_name=cond.get("subject_qualified_name", ""),
                object_qualified_name=cond.get("object_qualified_name", ""),
                layer="design",
            )
            vm.conditions.connect(c)
        except Exception as exc:
            log.warning("Failed to save precondition[%d] for VM %s: %s", i, vm_refid[:8], exc)

    # Recreate actions
    for i, action in enumerate(data.get("actions", [])):
        try:
            a = Action.save_new(
                order=i,
                description=action.get("description", ""),
                caller_qualified_name=action.get("caller_qualified_name", ""),
                callee_qualified_name=action.get("callee_qualified_name", ""),
                layer="design",
            )
            vm.actions.connect(a)
        except Exception as exc:
            log.warning("Failed to save action[%d] for VM %s: %s", i, vm_refid[:8], exc)

    # Recreate postconditions
    for i, cond in enumerate(data.get("postconditions", [])):
        try:
            c = Condition.save_new(
                phase="post",
                order=i,
                operator=cond.get("operator", "=="),
                expected_value=cond.get("expected_value", ""),
                subject_qualified_name=cond.get("subject_qualified_name", ""),
                object_qualified_name=cond.get("object_qualified_name", ""),
                layer="design",
            )
            vm.conditions.connect(c)
        except Exception as exc:
            log.warning("Failed to save postcondition[%d] for VM %s: %s", i, vm_refid[:8], exc)

    log.info("Updated VerificationMethod %s", vm_refid[:8])
    return True