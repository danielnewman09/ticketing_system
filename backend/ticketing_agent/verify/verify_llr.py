"""
Agent that fleshes out verification procedures for low-level requirements.

Takes existing LLRs (with basic verification stubs from decompose_hlr) and
the ontology design (nodes from design_ontology), and produces structured
verification specifications with:
- Pre-conditions: member state assertions before the stimulus
- Actions: ordered steps/stimuli referencing ontology members
- Post-conditions: expected member state after the stimulus

Uses call_tool_loop with intermediate tools (validate_qualified_names,
lookup_design_element) so the LLM can self-correct before committing the
final verification procedures.
"""

import json
import logging
import os

from llm_caller import call_tool_loop
from backend.requirements.schemas import VerificationSchema

from backend.ticketing_agent.verify.verify_llr_prompt import (
    SYSTEM_PROMPT,
    format_structured_context,
)
from backend.ticketing_agent.verify.verify_llr_tools import (
    ALL_TOOLS,
    make_verify_dispatcher,
)

log = logging.getLogger("agents.verify")


# ---------------------------------------------------------------------------
# Validation helpers (used by dispatcher and post-loop check)
# ---------------------------------------------------------------------------


def _validate_verification_qnames(verifications: list[VerificationSchema]) -> list[str]:
    """Check for invalid qualified name patterns in verification output.

    Returns a list of error messages for any qnames that fail format validation.
    Catches test artifacts, bare lowercase identifiers, dot separators, etc.
    """
    from backend.db.neo4j.repositories.verification import _is_valid_verification_qname

    errors: list[str] = []
    for v in verifications:
        for cond in v.preconditions + v.postconditions:
            for qn_field in ("subject_qualified_name", "object_qualified_name"):
                qn = getattr(cond, qn_field, "")
                if qn:
                    is_valid, corrected = _is_valid_verification_qname(qn)
                    if not is_valid:
                        errors.append(f"Invalid qname in precondition/postcondition: {qn_field}={qn}")
                    elif corrected:
                        errors.append(f"Dot separator in qname: {qn_field}={qn} (should be {corrected})")
        for action in v.actions:
            for qn_field in ("callee_qualified_name", "caller_qualified_name"):
                qn = getattr(action, qn_field, "")
                if qn:
                    is_valid, corrected = _is_valid_verification_qname(qn)
                    if not is_valid:
                        errors.append(f"Invalid qname in action: {qn_field}={qn} (not a design element)")
                    elif corrected:
                        errors.append(f"Dot separator in qname: {qn_field}={qn} (should be {corrected})")
    return errors


def _collect_qualified_names(verifications: list[VerificationSchema]) -> list[str]:
    """Collect all qualified names referenced in verification conditions and actions."""
    qnames = []
    for v in verifications:
        for cond in v.preconditions + v.postconditions:
            if cond.subject_qualified_name:
                qnames.append(cond.subject_qualified_name)
            if cond.object_qualified_name:
                qnames.append(cond.object_qualified_name)
        for action in v.actions:
            if action.caller_qualified_name:
                qnames.append(action.caller_qualified_name)
            if action.callee_qualified_name:
                qnames.append(action.callee_qualified_name)
    return qnames


class VerifyResult:
    """Wrapper for the agent's structured output with validation report."""

    def __init__(self, verifications: list[VerificationSchema], resolved: list[str] | None = None, unresolved: list[str] | None = None):
        self.verifications = verifications
        self.resolved = resolved or []
        self.unresolved = unresolved or []

    @property
    def all_resolved(self) -> bool:
        return len(self.unresolved) == 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def verify(
    llr: dict,
    existing_verifications: list[dict],
    class_contexts: list[dict],
    neo4j_session=None,
    model: str = "",
    prompt_log_file: str = "",
) -> VerifyResult:
    """
    Takes an LLR dict, its existing verifications, and structured design context.
    Returns fleshed-out verification procedures with a validation report.

    Uses call_tool_loop with validate_qualified_names and lookup_design_element
    tools so the LLM can self-correct before committing the final output.

    llr: {id, description}
    existing_verifications: [{method, test_name, description}, ...]
    class_contexts: [{qualified_name, kind, description, attributes, methods, relationships}, ...]
    neo4j_session: optional Neo4j session for reference validation
    """
    context_text = format_structured_context(class_contexts)
    system_prompt = SYSTEM_PROMPT.format(design_context=context_text)

    verifications_text = "\n".join(
        f"  - [{v['method']}] {v['test_name']}: {v['description']}" for v in existing_verifications
    )

    user_message = (
        f"Flesh out the verification procedures for this LLR:\n\n"
        f"LLR {llr['id']}: {llr['description']}\n\n"
        f"Existing verification stubs:\n{verifications_text}"
    )

    messages = [{"role": "user", "content": user_message}]

    # Build tool dispatcher with Neo4j session for lookups
    dispatcher = make_verify_dispatcher(neo4j_session=neo4j_session)

    # Run the tool loop
    result = call_tool_loop(
        system=system_prompt,
        messages=messages,
        tools=ALL_TOOLS,
        final_tool_name="produce_verifications",
        tool_dispatcher=dispatcher,
        model=model,
        max_tokens=4096,
        max_turns=50,
        prompt_log_file=prompt_log_file,
    )

    # Parse the final result
    verifications = [VerificationSchema.model_validate(v) for v in result["verifications"]]

    # Post-loop: validate qname format and resolve references
    format_errors = _validate_verification_qnames(verifications)
    if format_errors:
        log.warning(
            "verify: %d qname format issues remain after tool loop for LLR %s: %s",
            len(format_errors), llr.get('id', '?'), format_errors[:5],
        )

    # Resolve references against Neo4j
    resolved = []
    unresolved = []
    if neo4j_session is not None:
        from backend.db.neo4j.repositories.verification import VerificationRepository
        qnames = _collect_qualified_names(verifications)
        if qnames:
            repo = VerificationRepository(neo4j_session)
            resolved, unresolved = repo.validate_references(qnames)
        if unresolved:
            log.warning(
                "verify: %d unresolved references after tool loop for LLR %s: %s",
                len(unresolved), llr.get('id', '?'), unresolved[:5],
            )

    return VerifyResult(verifications=verifications, resolved=resolved, unresolved=unresolved)


if __name__ == "__main__":
    import os
    import sys

    from backend.db.neo4j.repositories.requirement import RequirementRepository
    from backend.db.neo4j.repositories.verification import VerificationRepository
    from backend.requirements.services.persistence import build_verification_context_from_diagram
    from services.dependencies import get_neo4j

    llr_id = int(sys.argv[1]) if len(sys.argv) > 1 else None
    if not llr_id:
        print("Usage: python -m agents.verify_llr <llr_id>")
        sys.exit(1)

    with get_neo4j().session() as ns:
        req_repo = RequirementRepository(ns)
        ver_repo = VerificationRepository(ns)
        llr = req_repo.get_llr(llr_id)
        if not llr:
            print(f"LLR {llr_id} not found")
            sys.exit(1)
        llr_dict = {"id": llr.id, "description": llr.description}

        existing_vms = ver_repo.list_verifications(llr_id)
        existing = [
            {"method": vm.method, "test_name": vm.test_name, "description": vm.description}
            for vm in existing_vms
        ]

        class_contexts = build_verification_context_from_diagram(ns)

        result = verify(llr_dict, existing, class_contexts, neo4j_session=ns)

    if not result.all_resolved:
        print(f"WARNING: {len(result.unresolved)} unresolved references:")
        for qname in result.unresolved:
            print(f"  - {qname}")
        print()

    print(
        json.dumps(
            [v.model_dump() for v in result.verifications],
            indent=2,
        )
    )
