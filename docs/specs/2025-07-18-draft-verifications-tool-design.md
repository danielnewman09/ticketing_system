# Draft Verifications Tool: Resolving Verification Stubs Against Design

**Date:** 2025-07-18  
**Status:** Approved

## Problem

The design_verify combined loop produces verification methods with references to design elements (qualified names), but the agent has no tool to iteratively draft and validate those references before committing. The seeded verification stubs from `decompose_hlr` contain placeholder references like `CalculationEngine.add.output` that never get properly resolved to actual design members like `calculation_engine::CalculationEngine::add`.

Two specific symptoms:

1. **Unresolved placeholder references**: Stubs encode test scenarios in plain language, but the agent creates new verification methods from scratch rather than resolving the stubs. Placeholder qnames like `CalculationEngine.add.output` are not valid `::`-separated qualified names and don't map to any `:Design` node in Neo4j.

2. **No iteration path for verifications**: The agent can iteratively draft and validate the OO design via `draft_design` → `validate_design`, but has no analogous path for verification methods. The only way to produce verification data is the terminal `commit_design_and_verifications` call. If verification references are wrong, the agent must re-emit the entire design AND all verifications.

Additional minor issues discovered in production output:

- Conditions with no `operator` field (should default to `"=="`)
- `caller_qualified_name` set to `"TestSuite"` — not a valid design element qname
- No suggestion mechanism when a reference nearly matches a design member

## Solution

Add a `draft_verifications` tool that mirrors the `draft_design` pattern for verification methods. The agent can submit verification data, get immediate feedback on whether all qualified name references resolve, and revise before committing.

### Architecture

```
Current workflow:
  draft_design → validate_design → commit_design_and_verifications
                                      ↑ (all-or-nothing, no iteration on verifications)

New workflow:
  draft_design → validate_design → draft_verifications → validate_qualified_names → commit
                                       ↑ iterative             ↑ cross-check
                                       ↓                       ↓
                                  (fix unresolved refs)    (fix qname errors)
                                       ↑                       ↓
                                  draft_design ←──────────────┘
                                  (add missing member)
```

### Section 1: `draft_verifications` Tool

**Purpose**: Submit or revise verification procedures for LLRs. Validates all qualified name references against the current design draft and design context (prior classes, dependency APIs, intercomponent). Returns a validation report showing which references resolved and which didn't, with suggestions for corrections.

**Tool definition**:

- Name: `draft_verifications`
- Input: `verifications` — map of LLR ID (integer string) to list of `VerificationSchema` objects. Keys MUST be LLR IDs like `"1"`, `"2"`, NOT test names.
- Output: Validation report with resolved/unresolved counts, error messages, and suggestions.

**Validation report format**:

```python
{
    "valid": True/False,
    "errors": [...],               # Unresolved qnames with suggestions
    "warnings": [...],             # Non-fatal issues (missing operators, unqualified callers)
    "verification_summary": {       # Per-LLR counts
        "1": {
            "methods": 2,
            "resolved_references": 8,
            "unresolved_references": 0,
        },
    },
    "unresolved_details": [        # Specific unresolved qnames with suggestions
        {
            "llr_id": "1",
            "verification": "test_add_returns_sum",
            "field": "subject_qualified_name",
            "value": "CalculationEngine.add.output",
            "suggestion": "calculation_engine::CalculationEngine::add",
        }
    ],
}
```

**Suggestion logic**: When a qname reference doesn't resolve, the tool searches for partial matches across:
1. Exact bare name match (e.g., `CalculationEngine` → `calculation_engine::CalculationEngine`)
2. Member name match in draft lookup (e.g., `add` → `calculation_engine::CalculationEngine::add`)
3. Substring match on qualified names

The tool also strips common stub suffixes (`.output`, `.result`, `.return_value`) before matching.

Note: `_suggest_qname` does NOT query Neo4j for suggestions — only in-memory lookups (draft, prior, dependency, intercomponent). Neo4j queries are too expensive for suggestion generation. The `_qname_resolves` helper DOES check Neo4j for existence validation, just not for suggestion matching.

**Behavior**:
- Stores drafted verifications in dispatcher state (`_draft_verifications`)
- Validates against current design draft. If no draft exists, accepts verifications but warns that validation is incomplete.
- Non-terminal: the agent can call multiple times, revising as it refines the design.
- Does NOT modify or replace the seeded stubs — the LLM produces complete verification data, using the stubs as a guide per the prompt instructions.

### Section 2: Commit Tool Integration and Post-Loop Flow

**Changes to `_dispatch_commit`**:

1. Consistency check: continues to validate references against the design provided in the commit call (not a previous draft), since the agent may have revised the design between drafting verifications and committing.

2. Better error messages: when an unresolved reference is found, the commit tool now includes suggestions for corrections, using the same `_suggest_qname` logic from `draft_verifications`:

```
"Unresolved reference: 'CalculationEngine.add.output' does not exist in the design context.
 Did you mean 'calculation_engine::CalculationEngine::add'?"
```

**Post-loop verification quality checks** in `design_and_verify()`:

Add informational warnings to `DesignVerifyResult.verification_warnings`:

- Conditions with no operator (defaulting to `==`)
- Empty preconditions (may indicate missing setup)
- `caller_qualified_name` values that don't contain `::` (likely test harness references)

These are warnings, not errors — the pipeline logs them but doesn't fail.

**`DesignVerifyResult`**: No schema change needed. The `verification_warnings` field already exists; we just start populating it.

### Section 3: Prompt Changes

**Updated workflow diagram** — adds `draft_verifications` as a step between verification and commit:

```
discovery → design → verification (draft_verifications → validate_qualified_names) → commit
```

With bidirectional arrows:
- `verification → design`: missing member found, add to design
- `commit → verification`: commit fails (qname errors)

**New prompt section: "Resolving Verification Stubs"**:

Instructs the agent that:
1. The requirements include seeded verification stubs with placeholder references
2. Each stub's references must be translated to actual design member qnames
3. Common resolution patterns are provided (e.g., `result == X` → `ns::ResultClass::result_value == X`)
4. `draft_verifications` must be called to validate references before committing
5. If references can't resolve, either add the missing member to the design or use `expected_value` alone

**Updated guidelines**:

- Add mandatory `draft_verifications` step before committing
- Explicitly require operators for every condition
- Instruct agents to leave `caller_qualified_name` empty (not "TestSuite") when the caller is the test harness

**Tool list**: `DRAFT_VERIFICATIONS_TOOL` added to `ALL_TOOLS` between `LOOKUP_DESIGN_ELEMENT_TOOL` and `COMMIT_TOOL`.

### Section 4: Dispatcher Implementation

**`_dispatch_draft_verifications` function**: Follows the same pattern as `_dispatch_draft_design`. Parses verification input, validates qnames against design context, stores in `_draft_verifications` state, returns validation report.

**`_suggest_qname` helper**: Searches draft_lookup, prior_class_lookup, dep_lookup, and intercomponent classes for partial matches. Handles bare name matching, member matching, and substring matching. Strips stub suffixes (`.output`, `.result`, `.return_value`).

**`_qname_resolves` helper**: Shared function that checks whether a qualified name exists in any design context (draft, prior, dependency, intercomponent, Neo4j). Used by both `draft_verifications` and `_dispatch_commit`.

**`validate_qualified_names` enhancement**: When `_draft_verifications` state exists, the existing `validate_qualified_names` tool appends cross-check results flagging qnames referenced in verifications but not present in the design draft.

### Section 5: Minor Fixes

**`operator` default validator**: Add a Pydantic `field_validator` on `VerificationConditionSchema.operator` that defaults `None` or empty string to `"=="`:

```python
@field_validator("operator", mode="before")
@classmethod
def default_operator(cls, v):
    if v is None or v == "":
        return "=="
    return v
```

**`caller_qualified_name` guidance**: The `draft_verifications` tool warns when `caller_qualified_name` doesn't contain `::`. The prompt instructs agents to leave it empty for test harness callers. The `VerificationRepository.add_action` method already silently skips `:CALLER` edge creation when no matching `:Design` node exists — add a `log.debug` message for visibility.

**Enum value in `expected_value` detection**: When `expected_value` contains `::`, `draft_verifications` warns that it may be a design reference that should go in `object_qualified_name` instead.

**Refactor**: Extract shared `_qname_resolves` and `_suggest_qname` from `_dispatch_commit` so both `draft_verifications` and `_dispatch_commit` use the same resolution logic.

### Files Changed

| File | Change |
|------|--------|
| `backend/ticketing_agent/design_verify/combined_tools.py` | Add `DRAFT_VERIFICATIONS_TOOL`, `_dispatch_draft_verifications`, `_suggest_qname`, `_qname_resolves`; refactor `_dispatch_commit` to use shared helpers; add to `ALL_TOOLS` |
| `backend/ticketing_agent/design_verify/combined_prompt.py` | Add verification stub resolution section, update workflow diagram, update guidelines |
| `backend/ticketing_agent/design_verify/combined_loop.py` | Add verification quality checks to `DesignVerifyResult` |
| `backend/requirements/schemas.py` | Add `field_validator` for `operator` default on `VerificationConditionSchema` |
| `backend/db/neo4j/repositories/verification.py` | Add debug logging for unmatched `:CALLER`/`:CALLEE` edges |
| `tests/test_combined_tools.py` | Add tests for `draft_verifications` tool |

### Files Unchanged

- `backend/ticketing_agent/design_verify/__init__.py` — no change
- `backend/ticketing_agent/verify/` — the standalone verify agent remains unchanged; this fix is for the combined loop only
- `backend/requirements/formatting.py` — prompt formatting unchanged
- `backend/requirements/services/persistence.py` — persistence flow unchanged
- `backend/db/neo4j/repositories/models/verification.py` — model unchanged