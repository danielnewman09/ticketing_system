# Implementation Plan: Container Mechanism Discovery

**Spec:** `docs/specs/2026-06-03-container-mechanism-discovery-design.md`

## Tasks

### 1. Create `seed_container_lookup()` function

**File:** `backend/ticketing_agent/design/container_lookup.py` (new file)

Create a utility module with:
- `_AGGREGATE_CONTAINER_QNAMES` — curated list of standard container qualified names
- `seed_container_lookup(neo4j_session)` — queries Neo4j for those containers, returns `dict[str, str]` (bare_name → qualified_name, plus qname → qname for direct lookup)
- Bare name is `qn.rsplit("::", 1)[-1]` (e.g., `"vector"` from `"std::vector"`)
- Also add a `get_container_class_info(neo4j_session)` function that returns a list of dicts (qualified_name, name, kind, source, description) for the prompt's dependency API section

**Test:** Test that `seed_container_lookup` with real Neo4j returns entries for `std::vector`, `std::map`, etc. Mock test for when they're absent.

### 2. Integrate seeding into `design_hlr.py`

**File:** `backend/ticketing_agent/design/design_hlr.py`

After the `dependency_lookup` is built from discovery results (lines ~131-137), call `seed_container_lookup()` using the toolset's Neo4j session and merge the results into `dependency_lookup`. Also build container class info for the prompt.

The `DependencyGraphTools` instance (`toolset`) has an internal `self._driver` — but we should not reach into it. Instead, we need to get the Neo4j session from the pipeline. Looking at the calling code in `scripts/03_design_requirements.py`, it uses `get_neo4j().session()`. We should pass the Neo4j session to `design_hlr()` as a new optional parameter.

Actually, simpler approach: `design_hlr` already has `toolset`, and `DependencyGraphTools` has a `close()` method. Let's add a method to get the session or driver. Or better — `seed_container_lookup` can accept `toolset` directly and call `toolset.search_symbols` to find the containers, sidestepping the need for a raw session.

Actually, simplest: query Neo4j directly with a Cypher query. The `design_hlr` function doesn't currently receive a Neo4j session, but the calling pipeline (`scripts/03_design_requirements.py`) has `get_neo4j().session()`. We should pass the session or driver through.

Wait — re-reading the spec, `combined_loop.py` already receives `neo4j_session`. Let's do the same for `design_hlr.py`: add an optional `neo4j_session` parameter and use it for the container lookup.

**Steps:**
- Add `neo4j_session=None` parameter to `design_hlr`
- After building `dependency_lookup` from discovery, call `seed_container_lookup(neo4j_session)` and merge
- Update `scripts/03_design_requirements.py` to pass `neo4j_session` to `design_hlr()`

### 3. Integrate seeding into `combined_loop.py`

**File:** `backend/ticketing_agent/design_verify/combined_loop.py`

The `design_and_verify()` function already receives `neo4j_session`. Call `seed_container_lookup(neo4j_session)` at the top of the function and merge results into `dependency_lookup`. Also add container classes to the dependency API prompt section.

### 4. Add `find_mechanism` tool to `design_oo_tools.py`

**File:** `backend/ticketing_agent/design/design_oo_tools.py`

- Add `FIND_MECHANISM_TOOL` dict with input schema `{query: string, library?: string}`
- Add to `ALL_TOOLS` list
- Add dispatcher case in `make_design_dispatcher`:
  - Use `DependencyGraphTools.search_symbols(query, source=library)` to search the dependency graph
  - Filter results to `kind in ("class", "struct")`
  - Deduplicate by `qualified_name`
  - Also check `dep_lookup` for prefix matches
  - Return `{containers: [{qualified_name, name, kind, source, brief}]}`
- The dispatcher needs a `toolset` parameter (or just `neo4j_session`) — add to `make_design_dispatcher`

**Challenge:** The standalone `design_oo_tools.py` dispatcher currently doesn't have access to Neo4j. We need to add a `toolset` or `neo4j_session` parameter to `make_design_dispatcher`.

Looking at the code, `make_design_dispatcher` in `design_oo_tools.py` takes `prior_class_lookup`, `dependency_lookup`, and `intercomponent_classes`. We'll add `neo4j_session=None` and use it to instantiate a `DependencyGraphTools` for the search (or create a lightweight Cypher query helper).

Actually, simplest approach: pass a `DependencyGraphTools` instance. But `design_oo.py` (the standalone version) doesn't currently have one. The `design_hlr.py` pipeline does have `toolset`.

For `design_oo.py` (standalone), we can pass `neo4j_session` and do a direct Cypher query. For `combined_tools.py`, we already have `neo4j_session`.

**Implementation:**
- `make_design_dispatcher` gets new param `neo4j_session=None`
- `_dispatch_find_mechanism` uses `neo4j_session` to run a Cypher query against the Compound nodes
- `design_oo.py` passes `neo4j_session` to `make_design_dispatcher`
- `design_hlr.py` passes `neo4j_session` to `design_oo()`

### 5. Add `find_mechanism` tool to `combined_tools.py`

**File:** `backend/ticketing_agent/design_verify/combined_tools.py`

- Add `FIND_MECHANISM_TOOL` tool definition
- Add to `ALL_TOOLS` list
- Add dispatcher case in `make_combined_dispatcher` using the existing `neo4j_session`

### 6. Update `design_oo_prompt.py` — associations section

**File:** `backend/ticketing_agent/design/design_oo_prompt.py`

Update the associations guidance to:
- Make `mechanism` **required** for `aggregates` (mention it's validated)
- Point to `find_mechanism` tool for discovery
- List pre-seeded containers briefly

### 7. Update `map_to_ontology.py` — real node resolution

**File:** `backend/ticketing_agent/design/map_to_ontology.py`

Replace the `_MECHANISM_DEPS` dict + `_ensure_mechanism_dep` function with the new resolution logic:

- Rename `_MECHANISM_DEPS` to `_FALLBACK_CONTAINERS`
- Remove `_ensure_mechanism_dep`
- In the association processing loop, for `aggregates` with `mechanism`:
  1. Skip if in `_NO_DEP_MECHANISMS`
  2. Try `_resolve_ref(mechanism)` — if found, create `depends_on` to the real node
  3. If not found but in `_FALLBACK_CONTAINERS`, create stub

### 8. Update validation in `design_oo_tools.py`

**File:** `backend/ticketing_agent/design/design_oo_tools.py`

In `_validate_oo_design`:
- Make missing `mechanism` on `aggregates` a **hard error**
- Add validation that `mechanism` on `aggregates` is a known name (in design classes, prior classes, or dependency lookup)
- Error messages should reference `find_mechanism`

### 9. Update `combined_tools.py` validation

**File:** `backend/ticketing_agent/design_verify/combined_tools.py`

The combined loop also validates designs. The `_validate_oo_design` function is shared (imported from `design_oo_tools.py`), so this is already covered by Task 8.

### 10. Update `design_oo.py` to pass `neo4j_session`

**File:** `backend/ticketing_agent/design/design_oo.py`

The standalone `design_oo` function needs to receive and pass `neo4j_session` to `make_design_dispatcher`. Currently it doesn't have it. Add `neo4j_session=None` parameter.

Also update `design_hlr.py` to pass the session when calling `design_oo`.

### 11. Tests

**New file:** `tests/test_container_mechanism.py`

- Test `seed_container_lookup` with mock Neo4j
- Test that merging container lookup into `dependency_lookup` works
- Test `find_mechanism` dispatcher (mock Neo4j responses)
- Test `map_to_ontology` mechanism resolution via `_resolve_ref` vs fallback
- Test validation: `aggregates` without mechanism → error, with unknown mechanism → error
- Test validation: `references` without mechanism → still just a warning

**Update existing tests:** `tests/test_map_to_ontology.py` — update mechanism-related tests to reflect new resolution logic.

### Task Order

1. Task 1 (container_lookup.py) — foundation module
2. Task 7 (map_to_ontology.py) — core resolution logic
3. Tasks 4+5 (find_mechanism tools) — new tools
4. Tasks 2+3 (pipeline integration) — wire it all up
5. Tasks 6+8 (prompt + validation) — LLM-facing changes
6. Task 10 (design_oo.py neo4j_session) — pass-through
7. Task 11 (tests) — verify everything

Tasks 2 and 3 can be done in parallel. Tasks 4 and 5 can be done in parallel. Tasks 6 and 8 should come after 4+5 so the tool name is finalized.