# Container Mechanism Discovery & Design

**Date:** 2026-06-03  
**Status:** Draft

## Problem

When the design agent creates an `AGGREGATES` association, the `mechanism` field is
free-text. The current pipeline creates stub dependency nodes for known container
names (`std::vector`, etc.) via a hardcoded `_MECHANISM_DEPS` table, but these
stubs are disconnected from the rich cppreference-indexed data already in Neo4j.

Additionally:
- The LLM has no way to discover which containers are available
- `mechanism` on `aggregates` is optional, so many associations omit it
- Stub nodes lack methods, `#include` paths, and other real dependency data
- The validation tool only warns about missing mechanisms — no actionable guidance

## Design

### 1. Seed `dependency_lookup` with containers from Neo4j

At pipeline start (`design_hlr.py`, `combined_loop.py`), after the
`discover_classes` step builds its lookup, query Neo4j for a curated set of
standard containers and merge them into `dependency_lookup`:

**Curated containers (for `aggregates` mechanism):**

```python
_AGGREGATE_CONTAINER_QNAMES = [
    "std::vector", "std::list", "std::deque", "std::array",
    "std::set", "std::map", "std::unordered_set", "std::unordered_map",
    "std::stack", "std::queue", "std::priority_queue",
]
```

A `seed_container_lookup(neo4j_session)` function queries Neo4j for these
nodes and returns `bare_name → qualified_name` pairs (e.g., `"vector" → "std::vector"`,
`"std::vector" → "std::vector"`). This is merged into `dependency_lookup` before
the design loop starts.

The `neo4j_session` comes from the existing `DependencyGraphTools` session
(available via `toolset` in `design_hlr.py`) or the `neo4j_session` parameter
in `combined_loop.py`. No new connection infrastructure needed.

These same containers are also added to the dependency API section of the LLM
prompt so the agent knows they're available without searching.

### 2. `find_mechanism` tool for the design agent

A new tool alongside `validate_design` and `check_class_name`. The agent calls it
to discover container types beyond the pre-seeded set.

**Tool definition:**
- Name: `find_mechanism`
- Input: `query` (required), `library` (optional, e.g., "cppreference", "boost")
- Returns: list of `{qualified_name, name, kind, source, brief}` matches filtered
  to `class`/`struct` kinds, deduplicated by qualified_name
- Implementation: uses `DependencyGraphTools.search_symbols` against the Neo4j
  dependency graph

**Added to:** `design_oo_tools.py` `ALL_TOOLS` and `combined_tools.py` `ALL_TOOLS`,
with corresponding dispatcher cases.

**Prompt update:** The associations section of `design_oo_prompt.py` includes:

> For `aggregates`, use `find_mechanism` to look up the exact qualified name for
> the container mechanism. Common containers (std::vector, std::map, etc.) are
> pre-loaded in the dependency context and available without a search.

### 3. `map_to_ontology` — real nodes instead of stubs

Replace the `_MECHANISM_DEPS` dict with `dep_lookup` resolution:

**Processing order for `aggregates` mechanism:**
1. If mechanism is in `_NO_DEP_MECHANISMS` (`raw_pointer`, `reference`, `pointer`),
   skip — no dependency inferred
2. Try `_resolve_ref(mechanism)` — if found in `dependency_lookup`, create a
   `depends_on` triple to the real Neo4j node
3. If not in lookup but in `_FALLBACK_CONTAINERS`, create a stub node (current
   behavior, only as safety net)

This ensures `DEPENDS_ON` edges point to the actual cppreference-indexed nodes
with their methods, descriptions, and include paths — not disconnected stubs.

### 4. Validation — require mechanism on `aggregates`

In `validate_design` (`design_oo_tools.py`), make missing `mechanism` on
`aggregates` a **hard error** (not a warning):

```python
if assoc.kind == "aggregates" and not assoc.mechanism:
    errors.append(
        f"Association {assoc.from_class} -[aggregates]-> {assoc.to_class} "
        f"has no mechanism. Use find_mechanism to discover the container "
        f"type (e.g., std::vector, std::map) and specify it in the mechanism field."
    )
if assoc.kind == "aggregates" and assoc.mechanism:
    mechanism = assoc.mechanism
    if mechanism not in all_design_names and mechanism not in prior_class_lookup and mechanism not in dep_lookup:
        errors.append(
            f"Association {assoc.from_class} -[aggregates]-> {assoc.to_class} "
            f"has mechanism '{mechanism}' which is not a known class or dependency. "
            f"Use find_mechanism to search for the correct container name."
        )
```

The error message tells the LLM exactly what tool to call, so it can self-correct.

**`references` mechanism** stays recommended-but-not-required (out of scope for this
change).

### Scope exclusions

- **REFERENCES / smart pointers** — `std::unique_ptr`, `std::shared_ptr`, etc.
  are out of scope. The ownership semantics of `REFERENCES` vs `AGGREGATES` is a
  separate problem.
- **Graph rendering changes** — this design doesn't change how containers appear
  in Cytoscape; it changes how they're stored and linked in the ontology.

## Files to change

| File | Change |
|------|--------|
| `backend/ticketing_agent/design/design_hlr.py` | Call `seed_container_lookup()`, merge into `dependency_lookup` and prompt context |
| `backend/ticketing_agent/design_verify/combined_loop.py` | Same seeding for combined loop |
| `backend/ticketing_agent/design/map_to_ontology.py` | Replace `_MECHANISM_DEPS` with `dep_lookup` resolution, keep `_FALLBACK_CONTAINERS` as safety net |
| `backend/ticketing_agent/design/design_oo_prompt.py` | Update associations section, mention `find_mechanism` tool |
| `backend/ticketing_agent/design/design_oo_tools.py` | Add `find_mechanism` tool def + dispatcher case; upgrade `aggregates` mechanism validation to error |
| `backend/ticketing_agent/design_verify/combined_tools.py` | Add `find_mechanism` tool def + dispatcher case |
| `backend/requirements/services/persistence.py` | Ensure `mechanism` property flows through on `AGGREGATES` edges (already handled) |
| Tests | Add tests for: container seeding, `_resolve_ref` for mechanisms, validation errors, `find_mechanism` dispatcher |