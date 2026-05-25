# Unified Design-Discovery-Verify Pipeline

**Date:** 2026-06-15  
**Status:** Approved

## Problem

The current per-HLR pipeline has three sequential stages:

1. **discover_classes** — LLM tool loop finds dependency/as-built classes
2. **design_oo** — LLM tool loop produces an initial OO design
3. **design_and_verify** — LLM tool loop re-creates the design from scratch and writes verifications

The verify stage (3) does not receive the discovery output from (1) or the initial
design from (2). It receives only a `dependency_lookup` (bare name → qualified name)
and `existing_classes`/`intercomponent_classes` summaries. This causes two visible bugs:

- **Missing dependency links**: FLTK inheritance like `inherits_from: ["Fl_Double_Window"]`
  is created in stage 2 but lost when stage 3 reinvents the design without FLTK details.
  No `INHERITS_FROM` or `DEPENDS_ON` edges reach the dependency `:Compound` nodes.

- **Duplicate enums**: Each HLR's verify step independently invents enums, producing
  `ui_manager::Operator` and `calculation_engine::Operator` with identical values but
  different semantics. The `prior_class_lookup` doesn't propagate verified enums from
  previous HLRs.

## Solution

Merge discovery, design, and verification into a **single tool-loop per HLR**.
The agent discovers dependency classes on-the-fly using Neo4j search tools, drafts the
design, validates, verifies against LLRs, and commits — all within one loop with
shared draft state.

### Architecture

```
Current:  discover_classes → design_oo → design_and_verify
              (loop)          (loop)       (loop)

New:      design_and_verify (single loop)
          - discovery tools (search_symbols, get_compound, etc.)
          - design tools (draft_design, validate_design, etc.)
          - verification tools (commit_design_and_verifications)
```

One HLR at a time, processed in dependency order. Accumulated context
(`prior_class_lookup`, `existing_classes`, `intercomponent_classes`) carries
forward between HLRs as before.

### Tool Set

**Existing tools (unchanged):**

| Tool | Purpose |
|------|---------|
| `draft_design` | Submit/revise OO design draft, stored in dispatcher state |
| `validate_design` | Validate draft for structural consistency |
| `check_class_name` | Check if a class/interface/enum name exists in design context |
| `validate_qualified_names` | Validate qname format and existence |
| `lookup_design_element` | Search design elements in draft + persistent Neo4j |
| `commit_design_and_verifications` | Commit final design + verifications (terminates loop) |

**New tools (added from discovery):**

| Tool | Purpose |
|------|---------|
| `search_symbols` | Full-text search across indexed symbol names and docs |
| `get_compound` | Get full details of a class/struct/enum and its members |
| `browse_namespace` | List classes and symbols within a namespace |
| `find_inheritance` | Explore inheritance hierarchy of a class |
| `list_sources` | List all indexed dependency sources and their counts |
| `find_mechanism` | Discover container/collection mechanisms (from container_lookup) |

The `produce_discovered_classes` tool (from the old discover loop) is removed —
the agent no longer produces a separate discovery artifact. It discovers classes
and uses them directly in the design.

### Prompt Changes

The system prompt for the combined loop gains a discovery workflow section:

```
1. Role definition (software architect + verification engineer)
2. Workflow instructions:
   a. DISCOVER: Use list_sources, search_symbols, get_compound, etc.
      to find dependency classes relevant to the requirements.
   b. DESIGN: Draft OO design using draft_design tool.
   c. VALIDATE: Check references, validate design structure.
   d. VERIFY: Write verification procedures per LLR.
   e. COMMIT: Call commit_design_and_verifications.
3. Discovery guidelines:
   - When to search (any dependency referenced in requirements)
   - How to search (start broad, then get_compound for details)
   - What to include as inherits_from vs. association
4. Dependency hint list (bare name → qualified name mapping)
5. Existing classes section (from prior HLRs in same component)
6. Intercomponent section (public APIs from other components)
7. Namespace rules
8. Format contract for qualified names
```

**Key changes from current prompt:**

- The dependency API section no longer shows full class details (methods, attributes,
  inheritance). The agent discovers those on demand via tools. A hint list of bare
  name → qualified name mappings is provided so the agent knows what's indexable.

- A new section instructs the agent to discover dependency classes before drafting:
  *"Before drafting your design, use search_symbols and get_compound to examine any
  framework or library classes you plan to inherit from or reference. This ensures
  accurate inheritance hierarchies and method signatures."*

- The `as_built_section` and full `dependency_api_section` with class details are
  replaced by the discovery tools. The agent retrieves details on demand rather than
  receiving a pre-built dump.

**What stays in the prompt context:**

- `dependency_lookup` as a hint list
- `existing_classes` from prior HLRs
- `intercomponent_classes` from other components
- `prior_class_lookup` for cross-HLR name resolution

### Pipeline Orchestration

`design_hlr()` simplifies from three stages to one:

```python
# Current:
dependency_classes = discover_classes(toolset, ...)
oo = design_oo(dependency_classes, as_built_classes, ...)
ontology = map_oo_to_ontology(oo, dependency_lookup, ...)

# New:
result = design_and_verify(toolset, ...)
ontology = map_oo_to_ontology(result.oo_design, dependency_lookup, ...)
```

The function signature gains a `toolset` parameter passed through to the combined
loop's dispatcher. `dependency_lookup` is built from `seed_container_lookup()` only
(standard containers like std::vector) — no separate discovery step, because the
agent discovers dependency classes on-the-fly and uses qualified names directly in
the design. Only container classes (which aren't searchable in the codebase index)
need to be pre-seeded.

**Changes to `scripts/03_design_requirements.py`:**

The `step_design_and_verify()` function currently runs two passes per HLR:
1. `design_hlr()` for initial design (not persisted)
2. `design_and_verify()` for verified design (persisted)

This collapses to a single call to `design_hlr()` which now internally calls the
unified `design_and_verify()` loop.

### Enum Deduplication

Two causes produce duplicate enums:

1. **Missing propagation**: `prior_class_lookup` was built from `design_oo` output,
   but the verified design may rename or add enums. Fix: the unified loop returns
   the verified `oo_design` and `_build_class_lookup()` picks up all enums.

2. **Independent invention**: The LLM invents an enum with the same name in different
   components. Fix: when `check_class_name` finds a collision with a name in
   `prior_class_lookup` from a different component, the `validate_design` tool emits
   a warning suggesting reuse or explicit justification. This nudges the agent toward
   deduplication without forbidding deliberate duplication.

### Error Handling

**Discovery tools unavailable:** The `design_and_verify` function already has a
`discovery_failed` parameter. If the Neo4j codebase index is unreachable, the
dispatcher returns an error message from tool calls, and the system prompt includes
the same warning paragraph: design self-contained classes, note where dependency
integration is needed.

**Discovery finds nothing relevant:** The agent searches, finds nothing, and proceeds
without dependency references. Same as current empty discover results — no change
needed. The agent is better positioned because it can verify the search was thorough
rather than receiving an empty list silently.

**Token budget:** Current `max_turns=75` should be sufficient. Discovery adds ~7-10
turns, design adds ~5-8 turns, verification adds ~20-30 turns. Total stays under 75.
A log warning should be added if the agent spends more than ~25 turns on discovery
without drafting a design.

**Concurrent Neo4j access:** The unified loop's dispatcher makes synchronous Neo4j
queries for `lookup_design_element` and `validate_qualified_names`. Discovery tools
add more Neo4j queries through the doxygen toolset. Both use their own sessions.
Per-HLR processing is sequential, so no conflicts arise.

### Files Changed

| File | Change |
|------|--------|
| `backend/ticketing_agent/design_verify/combined_loop.py` | Add `toolset` param, pass to dispatcher, update `design_and_verify` signature |
| `backend/ticketing_agent/design_verify/combined_tools.py` | Add 6 discovery tools, route through toolset, add collision warning in `validate_design` |
| `backend/ticketing_agent/design_verify/combined_prompt.py` | Add discovery workflow section, remove full dependency API dump, add dependency hint list |
| `backend/ticketing_agent/design/design_hlr.py` | Simplify: call `design_and_verify` directly, remove discover + design_oo stages |
| `backend/ticketing_agent/design/design_per_hlr.py` | Simplify: remove discovery toolset management, pass toolset to `design_hlr` |
| `scripts/03_design_requirements.py` | Collapse two-pass per HLR into one call per HLR |

### Files Kept (no longer called from main pipeline)

| Module | Status |
|--------|--------|
| `backend/ticketing_agent/design/discover_classes.py` | Available for standalone use |
| `backend/ticketing_agent/design/discover_classes_prompt.py` | Available for standalone use |
| `backend/ticketing_agent/design/design_oo.py` | Available for standalone use |
| `backend/ticketing_agent/design/design_oo_prompt.py` | Available for standalone use |
| `backend/ticketing_agent/design/design_oo_tools.py` | `produce_oo_design` no longer called; `_validate_oo_design` still imported by combined_tools |

### No Changes To

- `backend/ticketing_agent/design/map_to_ontology.py` — still called deterministically after the loop
- `backend/requirements/services/persistence.py` — still persists the same output format
- `backend/db/neo4j/` — no graph schema changes
- All verification code — `combined_tools` verification logic stays the same