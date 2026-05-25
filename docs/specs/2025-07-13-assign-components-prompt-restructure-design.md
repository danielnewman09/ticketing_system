# Assign Components Prompt Restructure

## Goal

Restructure the `assign_components` system prompt to use proven formatting patterns (`<HARD-GATE>`, `<CONTRACT>`, `<FORMAT-CONTRACT>`, anti-patterns) so the agent complies with its principal rules instead of violating them.

## Problem

The agent creates too many components (one per HLR instead of grouping) and ignores existing components when it should reuse them. The current prompt states these rules but buries them in a flat bullet list with soft language ("should", "Reuse… where appropriate"). The rules don't stick because they lack strong framing.

## Scope

- **File changed:** `backend/ticketing_agent/design/assign_components_prompt.py`
- **Changed:** `SYSTEM_PROMPT` string only
- **Not changed:** `TOOL_DEFINITION`, agent code in `assign_components.py`, any other prompt files

## Design

The prompt is restructured following the project's `prompt-formatting-guide.md` and the patterns already in `design_oo_prompt.py` and `verify_llr_prompt.py`.

### Section ordering

| # | Section | Purpose |
|---|---------|---------|
| 1 | Role definition | Who the agent is and what it produces (2 sentences) |
| 2 | `<HARD-GATE>` | Non-negotiable: group HLRs, don't create one per HLR |
| 3 | `<CONTRACT>` | Inviolable structural rules (assignment, reuse, required fields, nesting) |
| 4 | `<FORMAT-CONTRACT>` | Namespace syntax with [Good]/[Bad] examples + fallback |
| 5 | Anti-patterns | `<Bad>`/`<Good>` pairs + scannable table |
| 6 | Guidelines | Soft preferences (naming, description quality, grouping heuristics) |
| 7 | Tool call | "You MUST use the assign_components tool" |

### Key changes from current prompt

1. **Hard gate for component sprawl** — the dominant failure mode gets the strongest framing, placed immediately after role definition
2. **Component reuse elevated to CONTRACT** — "Reuse existing components where they fit" is now a MUST, not a bullet point
3. **Description quality in CONTRACT** — descriptions must be "specific enough that an engineer reading only this description would understand the component's role"
4. **FORMAT-CONTRACT for namespaces** — pattern + [Good]/[Bad] examples + fallback rule, following pattern from `verify_llr_prompt.py`
5. **Anti-pattern pairs + table** — concrete examples of each failure mode, not just abstract rules
6. **Guidelines section for soft preferences** — everything that's not a hard rule (naming conventions, grouping heuristics) moves here
7. **Decision framing** — "The question is not 'could this HLR have its own component?' but 'does it need to?'" directly targets the sprawl failure mode

### Behavioral changes

No new behaviors. Two existing behaviors are strengthened through stronger framing:
- **Reuse existing components** — elevated from soft guidance to CONTRACT
- **Substantive descriptions** — elevated from "must have a description" to contract-level requirement with explicit quality criteria

### Notation choice

Using `[Good]` / `[Bad]` labels in FORMAT-CONTRACT instead of ✓/✗ — the word tags are clearer and harder to gloss over. This is scoped to this prompt only; existing prompts retain their ✓/✗ notation.