# Tool-Loop Agents for Design and Verification

**Date:** 2025-06-05
**Status:** Draft
**Branch:** feature/neo4j-graph-primary-phase2

## Problem

The `design_oo` and `verify_llr` agents use `call_tool` (single-shot) with
hand-rolled retry loops for validation. When the LLM produces invalid output,
our code catches the error, formats it as a user message, and retries. This
has several problems:

1. **The model doesn't see its own invalid output** — on API failures
   (RuntimeError, JSONDecodeError), we append a generic recovery message
   without showing the model what went wrong.
2. **Duplicated retry logic** — both agents have ~50 lines of nearly identical
   try/except/validate/format/append/retry scaffolding.
3. **Validation is hidden from the agent** — the model has no way to
   voluntarily check its work before committing. It produces a full design in
   one shot, and we retry if validation fails.
4. **No self-correction capability** — the model can't look up design elements
   it's unsure about. If it doesn't remember the exact qualified name from the
   context, it has to guess.

Meanwhile, the `discover_classes` agent already uses `call_tool_loop` with a
rich tool palette (8 codebase-search tools + `produce_discovered_classes`),
letting the LLM iteratively explore before producing output. It works well
without any external validation loop because the LLM can verify its own
assumptions through query tools.

## Design

Replace `call_tool` + manual retry loops in `design_oo` and `verify_llr` with
`call_tool_loop`, giving each agent intermediate tools for self-validation and
lookup. The model calls validation/lookup tools as needed, then calls the
final produce tool when confident.

### Agent: design_oo

**Tools:**

| Tool | Type | Purpose |
|------|------|---------|
| `validate_design` | intermediate | Takes full design JSON, runs association-target and intercomponent-coverage checks, returns structured error list |
| `check_class_name` | intermediate | Takes a name, checks if it exists in prior designs, dependency context, or intercomponent context. Returns matching entries. |
| `produce_oo_design` | final | Commits the design — terminates the loop. Same schema as current `TOOL_DEFINITION`. |

**`validate_design` tool:**
- Input: the full `OODesignSchema` JSON (same as `produce_oo_design`)
- Dispatcher: runs `_validate_oo_design()` with the same context parameters
- Output: `{ valid: bool, errors: ["..."], warnings: ["..."] }`
- The model can call this multiple times on drafts before producing the final design

**`check_class_name` tool:**
- Input: `{ name: string }` — a class/interface/enum name or qualified name
- Dispatcher: searches `prior_class_lookup`, `dependency_lookup`, `intercomponent_classes`
- Output: `{ found: bool, matches: [{ qualified_name, kind, source }] }`
- Source indicates where the match came from: `"prior_design"`, `"dependency"`, `"intercomponent"`
- Supports partial matching: searching for `Calc` would find `CalculationEngine`, `CalculationResult`, etc.

**System prompt changes:**
- Add tool descriptions for `validate_design` and `check_class_name`
- Encourage: "Call `validate_design` on your draft before `produce_oo_design` to check for issues."
- Keep existing `<CONTRACT>` blocks for intercomponent associations

### Agent: verify_llr

**Tools:**

| Tool | Type | Purpose |
|------|------|---------|
| `validate_qualified_names` | intermediate | Takes a list of qnames, checks format validity AND Neo4j existence. Returns per-qname status. |
| `lookup_design_element` | intermediate | Takes a name pattern, queries Neo4j for matching `:Design` nodes. Returns qualified names, kind, and member details. |
| `produce_verifications` | final | Commits verification procedures — terminates the loop. Same schema as current `TOOL_DEFINITION`. |

**`validate_qualified_names` tool:**
- Input: `{ qualified_names: [string] }`
- Dispatcher: runs `_validate_verification_qnames()` for format checks,
  `VerificationRepository.validate_references()` for Neo4j existence
- Output: `{ results: [{ qname, valid: bool, exists: bool, error: string|null }] }`
- Combines format validation (test\_ prefixes, bare names, dot separators) with
  reference validation (does this qname exist as a :Design node?) in one call

**`lookup_design_element` tool:**
- Input: `{ name: string, kind: string|null }` — a name pattern and optional kind filter
- Dispatcher: uses `DesignRepository.find_nodes(search=name)` for fuzzy matching,
  `DesignRepository.get_by_qualified_name()` for exact lookup
- Output: `{ elements: [{ qualified_name, kind, description, attributes: [...], methods: [...] }] }`
- Returns enough detail for the model to write correct conditions/actions
- Supports prefix and substring matching: searching for `Button` finds
  `user_interface::Button`, searching for `CalculationEngine::calculate` finds
  the method node

**System prompt changes:**
- Add tool descriptions for `validate_qualified_names` and `lookup_design_element`
- Encourage: "Use `lookup_design_element` to verify names before writing conditions.
  Call `validate_qualified_names` before `produce_verifications` to check your work."
- Keep existing `<FORMAT-CONTRACT>` block for qualified name formatting rules

### Implementation Plan

#### 1. Tool schemas and dispatcher functions

**`backend/ticketing_agent/design/design_oo_tools.py`** (new file):
- `VALIDATE_DESIGN_TOOL` dict — input schema mirrors `OODesignSchema`
- `CHECK_CLASS_NAME_TOOL` dict — input `{ name: string }`
- `PRODUCE_OO_DESIGN_TOOL` dict — same as current `TOOL_DEFINITION`
- `ALL_TOOLS` list — all three
- `make_design_dispatcher()` — returns a dispatcher function that:
  - `validate_design`: parses input as `OODesignSchema`, runs `_validate_oo_design()`, returns `{ valid, errors, warnings }`
  - `check_class_name`: searches `prior_class_lookup`, `dependency_lookup`, `intercomponent_classes`, returns matches
  - Unknown tool: returns `{ error: "Unknown tool" }`

**`backend/ticketing_agent/verify/verify_llr_tools.py`** (new file):
- `VALIDATE_QNAMES_TOOL` dict — input `{ qualified_names: [string] }`
- `LOOKUP_DESIGN_ELEMENT_TOOL` dict — input `{ name: string, kind: string|null }`
- `PRODUCE_VERIFICATIONS_TOOL` dict — same as current `TOOL_DEFINITION`
- `ALL_TOOLS` list — all three
- `make_verify_dispatcher(neo4j_session)` — returns a dispatcher function that:
  - `validate_qualified_names`: runs format checks + Neo4j reference validation, returns per-qname results
  - `lookup_design_element`: queries `DesignRepository.find_nodes()` with fuzzy matching, returns element details
  - Unknown tool: returns `{ error: "Unknown tool" }`

#### 2. Refactor design_oo.py

- Remove the `for attempt in range(MAX_TOOL_RETRIES + 1)` retry loop
- Remove `_format_design_validation_errors()` (the model reads validation output directly)
- Keep `_validate_oo_design()` (called by the dispatcher)
- Build dispatcher via `make_design_dispatcher(prior_class_lookup, dependency_lookup, intercomponent_classes)`
- Call `call_tool_loop(system, messages, ALL_TOOLS, "produce_oo_design", dispatcher, ...)`
- Post-loop: pydantic-validate the final result, run `_validate_oo_design()` as a sanity check and log any remaining warnings
- Return `OODesignSchema` result (same as current public API)

#### 3. Refactor verify_llr.py

- Remove the `for attempt in range(MAX_TOOL_RETRIES + 1)` retry loop
- Remove `_format_verification_validation_errors()` (the model reads validate output directly)
- Keep `_validate_verification_qnames()` (called by the dispatcher)
- Build dispatcher via `make_verify_dispatcher(neo4j_session)`
- Call `call_tool_loop(system, messages, ALL_TOOLS, "produce_verifications", dispatcher, ...)`
- Post-loop: run `_validate_verification_qnames()` as a sanity check and log any remaining format issues
- Return `VerifyResult` (same as current public API)

#### 4. Update prompts

**design_oo_prompt.py:**
- Add `VALIDATE_DESIGN_TOOL` and `CHECK_CLASS_NAME_TOOL` descriptions to system prompt
- Add guidance: "Before producing your final design, call `validate_design` to check for issues."
- Keep all existing `<CONTRACT>` blocks

**verify_llr_prompt.py:**
- Add `VALIDATE_QNAMES_TOOL` and `LOOKUP_DESIGN_ELEMENT_TOOL` descriptions to system prompt
- Add guidance: "Before producing your final output, call `validate_qualified_names` to verify references."
- Keep `<FORMAT-CONTRACT>` block

#### 5. Update tests and pipeline script

- Update `test_design_oo_retry.py` to test the dispatcher functions instead of retry-loop logic
- Update `test_verify_retry.py` similarly
- Add tests for `validate_design` dispatcher (valid design returns no errors, invalid returns specific errors)
- Add tests for `check_class_name` dispatcher (known name found, unknown name not found, partial matches)
- Add tests for `validate_qualified_names` dispatcher (format errors, Neo4j resolution)
- Add tests for `lookup_design_element` dispatcher (exact match, fuzzy match, no match)
- Update `design_hlr.py` only if function signatures change (they shouldn't — `design_oo()` returns the same type)

### What Gets Simpler

Each agent drops ~50 lines of retry/error/formatting logic and gains ~20 lines
of dispatcher wiring. The `call_tool_loop` handles:

- JSON parse errors (appends malformed call + error message to history, lets model self-correct)
- No-tool-call nudges (appends a nudge message)
- Conversation logging (writes full conversation after every turn)
- Turn limit safety (`max_turns` parameter)

Error logging for API failures (`_attemptN_failed.txt` files) is no longer needed
— `call_tool_loop`'s conversation log captures everything.

### What Gets Harder

- New tool schema definitions and dispatcher functions
- The `validate_design` dispatcher needs access to `prior_class_lookup`,
  `dependency_lookup`, and `intercomponent_classes` — passed via closure
- The verify dispatcher needs a Neo4j session — passed via closure
- System prompts get longer (tool descriptions)
- Need to handle the case where the model calls `produce_oo_design` on the first
  turn without validating (valid but risky)

### Edge Cases

1. **Agent calls produce without validating** — valid behavior. Post-loop we
   still pydantic-validate the result and log warnings about any issues the
   validation tools would have caught.
2. **Agent validates multiple times** — fine, each call is cheap (no LLM cost,
   just Python validation). The loop allows it.
3. **Agent validates, gets errors, produces without fixing all** — post-loop
   logging catches this. The model is trusted to self-correct but we still check.
4. **Agent produces on first turn** — same as current `call_tool` behavior,
   but now the full conversation is logged via `call_tool_loop`'s turn logger.
5. **validate_design input fails pydantic validation** — the dispatcher returns
   `{ valid: false, errors: ["Invalid design format: ..."] }`. The model can
   then fix its draft and try again.

### Not In Scope

- Exposing the doxygen codebase-search tools to design/verify agents (the
  project has no existing codebase to search)
- Changing `design_ontology.py` or other agents to use tool loops (incremental rollout)
- Modifying `call_tool_loop` itself (it already handles everything we need)
- Changing pipeline scripts (`03_design_requirements.py`) — the agent functions
  keep the same signatures and return types