# Decompose HLR Prompt Restructure Design

## Goal

Restructure the `decompose_hlr` system prompt to enforce interface contracts for externally-visible LLRs, using superpowers-style formatting (HARD-GATE, CONTRACT, FORMAT-CONTRACT, anti-patterns) for stronger compliance.

## Problem

The decompose agent produces LLRs that under-define the component's external API — descriptions like "correctly computes the sum" leave inputs, outputs, and error conditions unspecified. An implementer or downstream agent reading such an LLR cannot determine how to interact with the component. Additionally, LLRs sometimes leak scope across component boundaries.

## Scope

- **File changed:** `backend/ticketing_agent/decompose/decompose_hlr.py` (the `SYSTEM_PROMPT` string only)
- **Not changed:** `TOOL_DEFINITION`, `DecomposedRequirementSchema`, `decompose()` function, any other files

## Design

### Section ordering

| # | Section | Purpose |
|---|---------|---------|
| 1 | Role definition | Who the agent is and what it produces — anchors on interface contracts |
| 2 | `<HARD-GATE>` | Every externally-visible LLR must define inputs, outputs, and error conditions |
| 3 | `<CONTRACT>` | Inviolable rules: atomicity, verification coverage, description specificity, scope, testability |
| 4 | `<FORMAT-CONTRACT>` | Test name format with [Good]/[Bad] examples |
| 5 | Anti-patterns | `<Bad>`/`<Good>` pairs + scannable table |
| 6 | Guidelines | Soft preferences: atomicity tradeoffs, verification method selection, scope |
| 7 | Tool call | "You MUST use the decompose_requirement tool" |

### Key changes from current prompt

1. **HARD-GATE for interface contracts** — every externally-visible LLR must define inputs, outputs, and error conditions. The current prompt has no such requirement.
2. **CONTRACT-level specificity** — descriptions must be specific enough for an engineer to implement and test. "Correctly computes" is called out as too vague.
3. **CONTRACT-level scope boundary** — LLRs must stay within their component. The current prompt mentions this only in the user message, not the system prompt.
4. **FORMAT-CONTRACT for test names** — pattern + [Good]/[Bad] examples, following the same style as `assign_components`.
5. **Anti-patterns with concrete examples** — two `<Bad>`/`<Good>` pairs showing under-defined APIs, plus a scannable table for three failure modes.
6. **Atomicity as a guideline, not a hard rule** — the user identified that grouping vs. atomic LLRs is a tradeoff. Atomicity is preferred in guidelines but not enforced as a CONTRACT.

### Notation

Using `[Good]`/`[Bad]` labels in FORMAT-CONTRACT, consistent with the `assign_components` prompt.

### Behavioral changes

- **Externally-visible LLRs must define interface contracts** — new hard requirement (HARD-GATE + CONTRACT)
- **"automated" verification required for externally-visible LLRs** — elevated from soft guideline to CONTRACT
- **Description specificity** — elevated from general guidance to CONTRACT-level requirement with explicit quality bar
- **Atomicity preference** — moved from a "Key Principles" bullet to guidelines, acknowledging it as a tradeoff rather than an absolute rule