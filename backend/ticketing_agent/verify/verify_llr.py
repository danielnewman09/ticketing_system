"""
Agent that fleshes out verification procedures for low-level requirements.

Takes existing LLRs (with basic verification stubs from decompose_hlr) and
the ontology design (nodes from design_ontology), and produces structured
verification specifications with:
- Pre-conditions: member state assertions before the stimulus
- Actions: ordered steps/stimuli referencing ontology members
- Post-conditions: expected member state after the stimulus

Runs after design_ontology so it can reference concrete ontology members.

Phase 3: Validation uses VerificationRepository.validate_references() which
checks references against :Design nodes in Neo4j.
"""

import json
import logging

from llm_caller import call_tool
from backend.requirements.schemas import VerificationSchema

from backend.ticketing_agent.verify.verify_llr_prompt import (
    SYSTEM_PROMPT,
    TOOL_DEFINITION,
    format_structured_context,
)

log = logging.getLogger("agents.verify")

MAX_TOOL_RETRIES = 2


def _format_verification_validation_errors(unresolved: list[str]) -> str:
    """Format unresolved qualified name errors into a retry message.

    Includes formatting guidance so the LLM sees the syntax rules again.
    """
    issue_lines = "\n".join(f'{i+1}. "{qn}"' for i, qn in enumerate(unresolved))
    return (
        "Your previous output referenced qualified names that do not exist "
        "in the design context:\n\n"
        f"<issues>\n{issue_lines}\n</issues>\n\n"
        "Please correct these issues by referencing ONLY names that appear "
        "in the design context section above. Use :: separators (not dots). "
        "Do not fabricate test-local variable names.\n\n"
        "Respond again with the corrected verifications."
    )


class VerifyResult:
    """Wrapper for the agent's structured output with validation report."""

    def __init__(self, verifications: list[VerificationSchema], resolved: list[str] | None = None, unresolved: list[str] | None = None):
        self.verifications = verifications
        self.resolved = resolved or []
        self.unresolved = unresolved or []

    @property
    def all_resolved(self) -> bool:
        return len(self.unresolved) == 0


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

    verifications = []
    resolved = []
    unresolved = []

    for attempt in range(MAX_TOOL_RETRIES + 1):
        result = call_tool(
            system=system_prompt,
            messages=messages,
            tools=[TOOL_DEFINITION],
            tool_name="produce_verifications",
            model=model,
            prompt_log_file=prompt_log_file if attempt == 0 else "",
        )

        verifications = [VerificationSchema.model_validate(v) for v in result["verifications"]]

        # Validate references against :Design nodes in Neo4j
        if neo4j_session is not None:
            from backend.db.neo4j.repositories.verification import VerificationRepository

            qnames = _collect_qualified_names(verifications)
            if qnames:
                repo = VerificationRepository(neo4j_session)
                resolved, unresolved = repo.validate_references(qnames)
            else:
                unresolved = []

        if not unresolved:
            break  # All references valid, proceed

        if attempt < MAX_TOOL_RETRIES:
            log.warning(
                "verify: %d unresolved references on attempt %d/%d: %s",
                len(unresolved), attempt + 1, MAX_TOOL_RETRIES + 1, unresolved,
            )
            error_msg = _format_verification_validation_errors(unresolved)
            messages.append({"role": "assistant", "content": json.dumps(result)})
            messages.append({"role": "user", "content": error_msg})
            continue

        # Final attempt still has unresolved — log and proceed
        log.warning(
            "verify: %d unresolved references after %d attempts: %s",
            len(unresolved), MAX_TOOL_RETRIES + 1, unresolved,
        )

    return VerifyResult(verifications=verifications, resolved=resolved, unresolved=unresolved)


if __name__ == "__main__":
    import os
    import sys

    from backend.db.neo4j.repositories.requirement import RequirementRepository
    from backend.db.neo4j.repositories.verification import VerificationRepository
    from backend.requirements.services.persistence import build_verification_context
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

        class_contexts = build_verification_context(ns)

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
