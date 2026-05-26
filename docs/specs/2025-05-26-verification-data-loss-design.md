# Fix: Verification Data Loss from Decomposition to Design+Verify

## Problem

`persist_decomposition()` only stores verification method stubs (method, test_name, description) to Neo4j, discarding preconditions, actions, and postconditions from the LLM decomposition response. When `design_and_verify()` later reads from `VerificationRepository`, conditions and actions return empty, producing prompts where all verification detail is `(none)`.

## Root Cause

In `backend/requirements/services/persistence.py`, `persist_decomposition()` calls `ver_repo.create_verification()` without subsequently calling `ver_repo.add_condition()` and `ver_repo.add_action()`. The sibling function `persist_verification()` does this correctly.

## Design

### 1. Update `persist_decomposition()` to persist conditions and actions

Add condition and action persistence after each `create_verification()` call, matching the pattern already used in `persist_verification()`:

- Iterate `v.preconditions` → `ver_repo.add_condition(vm_id, phase="pre", ...)`
- Iterate `v.actions` → `ver_repo.add_action(vm_id, ...)`
- Iterate `v.postconditions` → `ver_repo.add_condition(vm_id, phase="post", ...)`

Update `DecompositionResult` dataclass to include `conditions_created` and `actions_created` counters alongside the existing `llrs_created` and `verifications_created`.

### 2. Add `VerificationRepository.get_verifications_for_llr()` convenience method

Encapsulate the "fetch VMs → fetch conditions → fetch actions → assemble dicts" pattern into a single method on `VerificationRepository`. Returns `list[dict]` where each dict has the shape expected by `format_llrs_with_verifications_for_prompt()`: method, test_name, description, preconditions, actions, postconditions (with each condition as a flat dict of subject_qualified_name, operator, expected_value, object_qualified_name; each action as description, callee_qualified_name, caller_qualified_name).

### 3. Simplify retrieval in `combined_loop.py`

Replace the 40-line manual assembly block (lines 96-137) with:

```python
llr_verifications: dict[int, list[dict]] = {}
if neo4j_session is not None and llrs:
    ver_repo = VerificationRepository(neo4j_session)
    for llr in llrs:
        verifs = ver_repo.get_verifications_for_llr(llr["id"])
        if verifs:
            llr_verifications[llr]["id"]] = verifs
```

## Files Changed

- `backend/requirements/services/persistence.py` — add condition/action persistence to `persist_decomposition()`, update `DecompositionResult`
- `backend/db/neo4j/repositories/verification.py` — add `get_verifications_for_llr()` method
- `backend/ticketing_agent/design_verify/combined_loop.py` — replace 40-line block with `get_verifications_for_llr()` calls