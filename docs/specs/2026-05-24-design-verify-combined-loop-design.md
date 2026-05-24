# Design: Combined Design+Verify Tool Loop

**Date:** 2026-05-24  
**Status:** Approved

## Problem

The verification pipeline creates phantom design nodes through a feedback loop:

1. The verify agent references qnames that don't exist in the design (e.g., `CalculatorWindow::getOperatorButtons`, `CalculationEngine::CalculationEngine`).
2. `augment_missing_design_nodes` creates `:Design` stubs with `source_type='verification'`.
3. The next LLR's verify agent calls `lookup_design_element`, which returns these stubs as if they're real design elements.
4. The agent uses them, creating more invalid references.

Additional issues:
- `object_qualified_name` receives non-qname values (`×`, `"division operator button"`) instead of design references.
- Constructor references (`ClassName::ClassName`) are invented without backing design elements.
- No retry mechanism when validation catches errors — the pipeline logs warnings but persists broken data.

**Root cause:** Design and verification are separate phases. The verify agent can't add missing members to the design; it can only invent references. The stubs are a symptom of incomplete design, not a solution.

## Solution

Merge design and verification into a **single per-HLR tool loop** where the agent can design, verify, discover gaps, and revise — before committing anything.

### Architecture

**Current flow:**
```
discover_classes → design_oo → map_to_ontology → verify_llr (×N LLRs)
```

**New flow:**
```
discover_classes → [design + verify loop] → map_to_ontology
```

- `discover_classes` runs first (unchanged) — finds existing dependency classes.
- `map_to_ontology` runs last (unchanged) — deterministic transform.
- The combined loop replaces both `design_oo` and `verify_llr` tool loops.

### Combined Loop Structure

The agent has access to design and verification tools in a single conversation:

| Tool | Phase | Purpose |
|------|-------|---------|
| `draft_design` | Design | Submit/revise the OO design. Stores in dispatcher state, returns validation results. |
| `validate_design` | Design | Validate the current draft for structural consistency. |
| `check_class_name` | Design | Look up class names in prior designs, dependency APIs, and intercomponent context. |
| `validate_qualified_names` | Verify | Validate qname format and existence against draft + Neo4j. |
| `lookup_design_element` | Verify | Search for design elements in draft + Neo4j. |
| `commit_design_and_verifications` | Final | Atomically commit design + verifications. Terminates the loop. Rejects if errors remain. |

**Loop flow:**

1. System prompt provides design context, LLR list, and verification instructions.
2. Agent calls `draft_design` with its OO design. Dispatcher stores it and returns validation results.
3. Agent refines design using `validate_design` and `check_class_name`.
4. Agent shifts to verification, producing procedures per-LLR. Uses `validate_qualified_names` and `lookup_design_element` to check references (these query draft + Neo4j).
5. If a reference is missing from the design, agent calls `draft_design` again to add the member, then continues verifying.
6. When satisfied, agent calls `commit_design_and_verifications`.
7. If commit rejects (invalid qnames, unresolved references, etc.), agent revises and retries.
8. If `max_turns` is reached without commit, loop exits with errors logged and nothing persisted.

### Draft-State Lookup and Validation

Validation and lookup tools query **two sources** — the in-memory draft design and committed Neo4j data (from prior HLRs).

**`lookup_design_element` — merged search:**

1. Search the draft design's classes, attributes, and methods by name substring.
2. Search Neo4j `:Design` nodes by name substring, **excluding** `source_type='verification'` stubs.
3. Deduplicate by qualified name (draft takes priority if both exist).
4. Return up to 20 matches with kind, description, and `source` field (`"draft"` or `"persistent"`).

**`validate_qualified_names` — merged existence check:**

1. Format validation (regex, dot separator correction) — unchanged.
2. Existence check: check draft design first, then fall back to Neo4j.
3. For member references (`Ns::Class::method`), check draft and Neo4j.
4. Report `source: "draft"` or `source: "persistent"` for each found qname.

**`draft_design` — store and validate:**

1. Accepts `OODesignSchema`, stores as current draft.
2. Runs `_validate_oo_design` (existing validation) against the draft.
3. Returns validation results + draft summary (class count, member count).

**Poison filter:** All Neo4j queries exclude `source_type='verification'` nodes. These stubs must never appear in search results.

### Commit Tool and Schema

**`DesignAndVerificationSchema`:**

```python
class DesignAndVerificationSchema(BaseModel):
    oo_design: OODesignSchema
    verifications: dict[int, list[VerificationSchema]]
    # key = LLR id, value = verification procedures for that LLR
```

**`commit_design_and_verifications` validation:**

1. **Design validation** — run `_validate_oo_design` checks.
2. **Qname validation** — for every qname in every condition and action:
   - Format check via `_is_valid_verification_qname`.
   - Existence check against draft + Neo4j.
   - `object_qualified_name`, if populated, must be a valid qname from the design context. Literal values (`"×"`, `"division operator button"`) belong in `expected_value`. Reject with clear error if non-qname found.
3. **Constructor validation** — reject `ClassName::ClassName` references unless they exist as explicit design methods.

If validation fails, return structured errors. The agent revises and retries. No partial data is persisted on rejection.

On success, the caller persists:
- Design to Neo4j via `persist_design`.
- Verifications to Neo4j via `persist_verification`.
- **No stub creation** — `augment_missing_design_nodes` is removed from `persist_verification`.

### System Prompt

The combined agent prompt covers both design and verification responsibilities with clear phase instructions:

```
## Role
You are a software architect and verification engineer. Given requirements
and design context, you produce an object-oriented design AND verification
procedures that validate the design satisfies those requirements.

## Design Context
{prior designs, dependencies, intercomponent classes, discover results}

## Requirements
{LLRs for this HLR}

## Workflow
1. DESIGN PHASE: Draft your OO design. Use draft_design to store and
   validate it. Use check_class_name to verify references to external
   classes. Use validate_design to check for structural issues.
   Revise until the design is clean.

2. VERIFICATION PHASE: For each LLR, write verification procedures that
   reference the design. Use lookup_design_element to find correct
   qualified names. Use validate_qualified_names to verify references.
   If you find a reference that doesn't exist in the design, add it
   via draft_design and re-verify.

3. COMMIT: When both design and all verifications are clean, call
   commit_design_and_verifications.

## FORMAT-CONTRACT (qualified names)
{existing FORMAT-CONTRACT, plus:}

- object_qualified_name must be a qualified name from the design context.
  Use expected_value for literal values and constants.
  ✓ object_qualified_name: "Operator::MULTIPLY", expected_value: "active"
  ✗ object_qualified_name: "×"  ← label, use expected_value instead
  ✗ object_qualified_name: "division operator button"  ← description, not qname

- Do not reference constructors (ClassName::ClassName) unless they are
  explicitly designed as methods in the design context.
```

LLRs are processed one at a time during the verification phase (keeping per-LLR focus), but the agent can go back and revise the design between LLRs.

### Error Handling

**Commit rejection:** The tool returns structured errors listing every issue. The agent revises and retries. If `max_turns` is reached, nothing is persisted and the failure is logged.

**Stale draft detection:** If the agent revises the design to remove a member, subsequent `validate_qualified_names` calls flag references to the removed member as unresolved. The agent must fix the verifications.

**Cross-HLR references:** `lookup_design_element` and `validate_qualified_names` query Neo4j for prior HLR designs, so intercomponent references work naturally.

**Neo4j unavailability:** The loop degrades gracefully — tools fall back to draft-only results when Neo4j is unavailable.

### File Changes

**New files:**

| File | Purpose |
|------|---------|
| `backend/ticketing_agent/design_verify/__init__.py` | Package init |
| `backend/ticketing_agent/design_verify/combined_loop.py` | Main entry point: `design_and_verify_hlr()` |
| `backend/ticketing_agent/design_verify/combined_tools.py` | Tool definitions, schema, dispatcher with draft-state |
| `backend/ticketing_agent/design_verify/combined_prompt.py` | Combined system prompt template |

**Modified files:**

| File | Change |
|------|--------|
| `scripts/03_design_requirements.py` | Replace separate design + verify steps with combined loop call. Pipeline: decompose → design+verify → summary. |
| `backend/requirements/services/persistence.py` | Remove `augment_missing_design_nodes` call from `persist_verification`. Log unresolved references instead. |
| `backend/db/neo4j/repositories/verification.py` | Remove `augment_missing_design_nodes` method. Add `source_type` filter to queries. |
| `backend/db/neo4j/repositories/design.py` | Add `source_type` filter to `find_nodes` to exclude verification stubs by default. |
| `backend/pipeline/orchestrator.py` | Update to call combined function instead of separate design + verify steps. |

**Unchanged files (kept for standalone use):**

- `backend/ticketing_agent/design/design_oo.py`
- `backend/ticketing_agent/design/design_oo_tools.py`
- `backend/ticketing_agent/verify/verify_llr.py`
- `backend/ticketing_agent/verify/verify_llr_tools.py`

**One-time cleanup:**

Delete all `:Design` nodes where `source_type = 'verification'` from Neo4j. Add this to `01_flush_db.py` so a fresh pipeline start is always clean.