# Unified Design-Discovery-Verify Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge the three-stage per-HLR pipeline (discover → design_oo → design_verify) into a single unified tool loop that discovers dependencies on-the-fly, designs, and verifies in one pass.

**Architecture:** Extend the existing `design_and_verify` combined loop with discovery tools (search_symbols, get_compound, browse_namespace, find_inheritance, list_sources) routed through the doxygen_index toolset. Simplify `design_hlr()` to call the unified loop directly. Collapse `scripts/03_design_requirements.py` from a two-pass per-HLR flow to one pass.

**Tech Stack:** Python 3.12, llm_caller tool loop, Neo4j, doxygen_index toolset

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/ticketing_agent/design_verify/combined_tools.py` | Modify | Add 5 discovery tool definitions + dispatcher routing |
| `backend/ticketing_agent/design_verify/combined_prompt.py` | Modify | Add discovery workflow section, remove full dependency dump |
| `backend/ticketing_agent/design_verify/combined_loop.py` | Modify | Add toolset param, discovery_failed param |
| `backend/ticketing_agent/design/design_hlr.py` | Modify | Simplify: call design_and_verify directly, remove discover + design_oo stages |
| `backend/ticketing_agent/design/design_per_hlr.py` | Modify | Pass toolset through to design_hlr |
| `scripts/03_design_requirements.py` | Modify | Collapse two-pass into one call per HLR |
| `tests/test_combined_tools.py` | Modify | Add tests for discovery tool routing |

---

### Task 1: Add discovery tool definitions to combined_tools.py

**Files:**
- Modify: `backend/ticketing_agent/design_verify/combined_tools.py`

- [ ] **Step 1: Add 5 discovery tool definition dicts**

Add these tool definitions after the existing `FIND_MECHANISM_TOOL` definition (around line 160), before `ALL_TOOLS`:

```python
SEARCH_SYMBOLS_TOOL = {
    "name": "search_symbols",
    "description": (
        "Full-text search across indexed symbol names and documentation. "
        "Use this to discover dependency or project classes relevant to "
        "the requirements when designing. Supports natural-language terms "
        "(e.g. 'window create', 'font rendering'). Returns matches with "
        "qualified_name, kind, source, and relevance score."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search terms (supports Lucene syntax — AND, OR, quotes).",
            },
            "source": {
                "type": "string",
                "description": "Optional dependency name to restrict results (e.g. 'fltk', 'boost').",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results.",
                "default": 20,
            },
        },
        "required": ["query"],
    },
}

GET_COMPOUND_TOOL = {
    "name": "get_compound",
    "description": (
        "Get full details of a class, struct, or enum and its members from "
        "the indexed codebase. Use this after search_symbols identifies a "
        "compound of interest. Returns the compound metadata plus all of "
        "its members with signatures. Essential for understanding the API "
        "of a class you plan to inherit from or reference."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Exact or qualified name (e.g. 'Fl_Window', 'boost::gregorian::date').",
            },
            "source": {
                "type": "string",
                "description": "Optional dependency name filter.",
            },
        },
        "required": ["name"],
    },
}

BROWSE_NAMESPACE_TOOL = {
    "name": "browse_namespace",
    "description": (
        "List classes, free functions, and other symbols within a namespace "
        "in the indexed codebase. Returns both nested compounds and "
        "namespace-level members. Use this to explore a dependency's top-level "
        "types when you don't know exact class names."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Namespace name (e.g. 'Fl', 'boost::asio').",
            },
            "source": {
                "type": "string",
                "description": "Optional dependency name filter.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum results.",
                "default": 50,
            },
        },
        "required": ["name"],
    },
}

FIND_INHERITANCE_TOOL = {
    "name": "find_inheritance",
    "description": (
        "Explore the inheritance hierarchy of a class in the indexed codebase. "
        "Use this to understand parent classes and derived classes — if a class "
        "is relevant, its base classes may also be. Essential for determining "
        "the correct inherits_from list in your design."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Exact or qualified class name.",
            },
            "direction": {
                "type": "string",
                "enum": ["up", "down", "both"],
                "description": 'Direction: "up" (base classes), "down" (derived), or "both".',
                "default": "both",
            },
            "max_depth": {
                "type": "integer",
                "description": "Maximum inheritance depth to traverse.",
                "default": 5,
            },
        },
        "required": ["name"],
    },
}

LIST_SOURCES_TOOL = {
    "name": "list_sources",
    "description": (
        "List all indexed dependency sources and their symbol counts. "
        "Call this first to see which dependencies are available before "
        "searching for specific classes."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}
```

- [ ] **Step 2: Update ALL_TOOLS list**

Replace the `ALL_TOOLS` list to include the new discovery tools:

```python
ALL_TOOLS = [
    LIST_SOURCES_TOOL,
    SEARCH_SYMBOLS_TOOL,
    GET_COMPOUND_TOOL,
    BROWSE_NAMESPACE_TOOL,
    FIND_INHERITANCE_TOOL,
    DRAFT_DESIGN_TOOL,
    VALIDATE_DESIGN_TOOL,
    CHECK_CLASS_NAME_TOOL,
    FIND_MECHANISM_TOOL,
    VALIDATE_QNAMES_TOOL,
    LOOKUP_DESIGN_ELEMENT_TOOL,
    COMMIT_TOOL,
]
```

Note: Discovery tools are listed first so the agent sees them before design tools, reinforcing the discover-then-design workflow.

- [ ] **Step 3: Add discovery tool routing to the dispatcher**

Update `make_combined_dispatcher()` signature to accept `toolset`:

```python
def make_combined_dispatcher(
    prior_class_lookup: dict[str, str],
    dependency_lookup: dict[str, str] | None,
    intercomponent_classes: list[dict] | None,
    neo4j_session=None,
    toolset=None,
):
```

Add these dispatch routes inside the `dispatch` function, before the existing `draft_design` branch:

```python
        if tool_name == "list_sources":
            return _dispatch_discovery("list_sources", tool_input)
        elif tool_name == "search_symbols":
            return _dispatch_discovery("search_symbols", tool_input)
        elif tool_name == "get_compound":
            return _dispatch_discovery("get_compound", tool_input)
        elif tool_name == "browse_namespace":
            return _dispatch_discovery("browse_namespace", tool_input)
        elif tool_name == "find_inheritance":
            return _dispatch_discovery("find_inheritance", tool_input)
```

Add the `_dispatch_discovery` helper inside `make_combined_dispatcher`, before the `_dispatch_draft_design` function:

```python
    # -- discovery tools (routed to doxygen_index toolset) --------------------

    _DISCOVERY_METHOD_MAP = {
        "list_sources": "list_sources",
        "search_symbols": "search_symbols",
        "get_compound": "get_compound",
        "browse_namespace": "browse_namespace",
        "find_inheritance": "find_inheritance",
    }

    _DISCOVERY_SLIM = {
        "get_compound": _slim_compound,
    }

    def _dispatch_discovery(tool_name: str, tool_input: dict) -> str:
        if toolset is None:
            return json.dumps({
                "error": "Codebase index not available. Proceed with your design using general knowledge and note the gap.",
            })
        method_name = _DISCOVERY_METHOD_MAP.get(tool_name)
        method = getattr(toolset, method_name, None) if toolset else None
        if not method:
            return json.dumps({"error": f"Discovery tool {tool_name} not available"})
        try:
            result = method(**tool_input)
            slim = _DISCOVERY_SLIM.get(tool_name)
            if slim:
                result = slim(result)
            return json.dumps(result, default=str)
        except Exception as e:
            log.warning("Discovery tool %s failed: %s", tool_name, e)
            return json.dumps({"error": str(e)})
```

Add the slim helper at the module level (near the top of the file, after imports):

```python
def _slim_compound(records: list[dict]) -> list[dict]:
    """Strip heavyweight fields from get_compound results."""
    drop = {"detailed", "member_refid", "member_brief"}
    return [{k: v for k, v in r.items() if k not in drop} for r in records]
```

- [ ] **Step 4: Add enum collision warning to validate_design**

Inside `_dispatch_validate_design`, after the `_validate_oo_design` call, add a collision check:

```python
        # Check for enum name collisions across components
        warnings = []
        for enum in design.enums:
            enum_qname = f"{enum.module}::{enum.name}" if enum.module else enum.name
            if enum.name in prior_class_lookup:
                existing_qname = prior_class_lookup[enum.name]
                if existing_qname != enum_qname:
                    warnings.append(
                        f"Enum '{enum.name}' already exists as '{existing_qname}' in a prior design. "
                        f"Consider referencing the existing enum or renaming yours to avoid confusion."
                    )
```

Update the return to include warnings:

```python
        return json.dumps({
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        })
```

Also update `_dispatch_draft_design` to include warnings in the same way — add the same collision check after the `_validate_oo_design` call and include `"warnings"` in the returned dict.

- [ ] **Step 5: Commit this task**

```bash
git add backend/ticketing_agent/design_verify/combined_tools.py
git commit -m "Add discovery tools and enum collision warnings to combined dispatcher"
```

---

### Task 2: Update the combined loop entry point

**Files:**
- Modify: `backend/ticketing_agent/design_verify/combined_loop.py`

- [ ] **Step 1: Add toolset parameter to design_and_verify**

Update the function signature to accept `toolset`:

```python
def design_and_verify(
    hlr: dict,
    llrs: list[dict],
    existing_verifications: list[dict] | None = None,
    existing_classes: list[dict] | None = None,
    intercomponent_classes: list[dict] | None = None,
    dependency_contexts: dict[int, dict] | None = None,
    component_namespace: str = "",
    sibling_namespaces: list[str] | None = None,
    prior_class_lookup: dict[str, str] | None = None,
    dependency_lookup: dict[str, str] | None = None,
    neo4j_session=None,
    toolset=None,
    model: str = "",
    prompt_log_file: str = "",
    discovery_failed: bool = False,
) -> DesignVerifyResult:
```

- [ ] **Step 2: Pass toolset to the dispatcher**

In the section where `make_combined_dispatcher` is called (around line 220), add `toolset=toolset`:

```python
    dispatcher = make_combined_dispatcher(
        prior_class_lookup=prior_class_lookup or {},
        dependency_lookup=dep_lookup,
        intercomponent_classes=intercomponent_classes or [],
        neo4j_session=neo4j_session,
        toolset=toolset,
    )
```

- [ ] **Step 3: Add discovery budget logging**

After the `call_tool_loop` call, add a warning if discovery turns were excessive. Add this after the `result = call_tool_loop(...)` line:

```python
    # Warn if the agent spent too many turns on discovery without designing
    # (heuristic: if prompt log exists, check for excessive discovery calls)
    if prompt_log_file and os.path.exists(prompt_log_file):
        try:
            with open(prompt_log_file) as f:
                log_content = f.read()
            discovery_calls = log_content.count("dispatching search_symbols") + \
                              log_content.count("dispatching get_compound") + \
                              log_content.count("dispatching browse_namespace") + \
                              log_content.count("dispatching find_inheritance")
            if discovery_calls > 20:
                log.warning(
                    "design_and_verify: HLR %s used %d discovery tool calls — "
                    "consider tightening the discovery prompt",
                    hlr.get("id", "?"), discovery_calls,
                )
        except Exception:
            pass
```

- [ ] **Step 4: Commit this task**

```bash
git add backend/ticketing_agent/design_verify/combined_loop.py
git commit -m "Pass toolset through to combined dispatcher for discovery tools"
```

---

### Task 3: Update the combined prompt

**Files:**
- Modify: `backend/ticketing_agent/design_verify/combined_prompt.py`

- [ ] **Step 1: Replace the tool descriptions section**

Replace the current "You have six tools available" section with an expanded version that includes discovery tools. The new section replaces lines from `"You have six tools available"` through the workflow section.

In the `SYSTEM_PROMPT` string, replace:

```
You are a software architect and verification engineer. Given design context
and requirements, your job is to produce an object-oriented class design AND
verification procedures that validate the design satisfies those requirements.

You have six tools available:
```

with:

```
You are a software architect and verification engineer. Given design context
and requirements, your job is to produce an object-oriented class design AND
verification procedures that validate the design satisfies those requirements.

You have twelve tools available:

### Discovery tools

### list_sources
List all indexed dependency sources and their symbol counts. Call this first
to see which dependencies are available before searching for specific classes.

### search_symbols
Full-text search across indexed symbol names and documentation. Use this to
find dependency or project classes relevant to the requirements. Supports
natural-language terms. Returns matches with qualified_name, kind, source.

### get_compound
Get full details of a class, struct, or enum and its members. Use this after
search_symbols identifies a compound of interest. Essential for understanding
the API of a class you plan to inherit from or reference — especially to
verify method signatures, attributes, and inheritance before including them
in your design.

### browse_namespace
List classes and symbols within a namespace. Use this to explore a dependency's
top-level types when you don't know exact class names.

### find_inheritance
Explore the inheritance hierarchy of a class. Use this to determine the
correct inherits_from list for your design — a class's base classes may also
need to be referenced.

### Design & verification tools
```

- [ ] **Step 2: Update the recommended workflow**

Replace the current workflow section:

```
**Recommended workflow:**

1. DESIGN PHASE: Draft your OO design using draft_design. Use check_class_name
   to verify references to external classes. Use validate_design to check for
   structural issues. Revise until the design is clean.

2. VERIFICATION PHASE: For each LLR, write verification procedures that
   reference the design. Use lookup_design_element to find correct qualified
   names. Use validate_qualified_names to verify references. If you find a
   reference that doesn't exist in the design, call draft_design again to add
   the missing member, then continue verifying.

3. COMMIT: When both design and all verifications are clean, call
   commit_design_and_verifications.
```

with:

```
**Recommended workflow:**

1. DISCOVERY PHASE: Before designing, discover dependency classes relevant to
   the requirements. Use list_sources to see what's indexed, then search_symbols
   to find candidate classes. Use get_compound on promising classes to inspect
   their full API (methods, attributes, inheritance). Use find_inheritance to
   verify base classes for your inherits_from references. This ensures your
   design will have accurate dependency links.

2. DESIGN PHASE: Draft your OO design using draft_design. Use check_class_name
   to verify references to external classes. Use validate_design to check for
   structural issues (including enum name collisions with prior designs).
   Revise until the design is clean.

3. VERIFICATION PHASE: For each LLR, write verification procedures that
   reference the design. Use lookup_design_element to find correct qualified
   names. Use validate_qualified_names to verify references. If you find a
   reference that doesn't exist in the design, call draft_design again to add
   the missing member, then continue verifying.

4. COMMIT: When both design and all verifications are clean, call
   commit_design_and_verifications.
```

- [ ] **Step 3: Add discovery reminder to design guidance**

In the design guidance section (after "Keep classes focused and cohesive"), add:

```
- Before finalizing any class that inherits from or references a dependency
  class, use get_compound and find_inheritance to verify the correct qualified
  name, methods, and base classes. This prevents broken dependency links in
  the ontology graph.
```

- [ ] **Step 4: Commit this task**

```bash
git add backend/ticketing_agent/design_verify/combined_prompt.py
git commit -m "Add discovery tools and workflow to combined prompt"
```

---

### Task 4: Simplify design_hlr.py

**Files:**
- Modify: `backend/ticketing_agent/design/design_hlr.py`

- [ ] **Step 1: Replace the three-stage flow with a single call**

Replace the body of `design_hlr()` after the docstring. The new implementation calls `design_and_verify` directly with the toolset, then maps the result to ontology.

Replace the entire function body after the docstring with:

```python
    hlr_id = hlr.get("id", "?")

    # --- Step 1: Skip separate discovery + design_oo ---
    # Discovery is now handled inside the design_and_verify loop.
    # The agent discovers dependencies on-the-fly using search_symbols,
    # get_compound, etc.

    # --- Step 1.5: Seed standard containers from Neo4j ---
    container_classes = []
    if neo4j_session is not None:
        container_lookup = seed_container_lookup(neo4j_session)
        if container_lookup:
            container_classes = get_container_class_info(neo4j_session)
            log.info(
                "  HLR %s: seeded %d container entries from Neo4j",
                hlr_id,
                len(container_lookup),
            )

    # --- Build dependency_lookup for the combined loop ---
    # Discovery results come through the toolset at runtime.
    # We pre-seed standard containers since they aren't searchable.
    dep_lookup: dict[str, str] = {}
    if neo4j_session is not None:
        container_lookup = seed_container_lookup(neo4j_session)
        if container_lookup:
            dep_lookup.update(container_lookup)

    # --- Step 2: Combined design + verify (includes discovery) ---
    from backend.ticketing_agent.design_verify.combined_loop import design_and_verify

    discovery_failed = toolset is None

    verify_log = os.path.join(log_dir, f"design_verify_hlr{hlr_id}.md") if log_dir else ""
    result = design_and_verify(
        hlr=hlr,
        llrs=llrs,
        existing_classes=existing_classes,
        intercomponent_classes=intercomponent_classes,
        dependency_contexts=dependency_contexts,
        component_namespace=component_namespace,
        sibling_namespaces=sibling_namespaces,
        prior_class_lookup=prior_class_lookup,
        dependency_lookup=dep_lookup or None,
        neo4j_session=neo4j_session,
        toolset=toolset,
        model=model,
        prompt_log_file=verify_log,
        discovery_failed=discovery_failed,
    )

    oo = result.oo_design

    # --- Step 3: Map to ontology (deterministic) ---
    dependency_lookup = None
    if dep_lookup:
        dependency_lookup = dep_lookup

    ontology = map_oo_to_ontology(
        oo,
        component_id=component_id,
        prior_class_lookup=prior_class_lookup,
        component_namespace=component_namespace,
        dependency_lookup=dependency_lookup,
    )

    log.info(
        "  HLR %s: %d classes, %d interfaces, %d nodes, %d triples",
        hlr_id,
        len(oo.classes),
        len(oo.interfaces),
        len(ontology.nodes),
        len(ontology.triples),
    )

    return oo, ontology
```

- [ ] **Step 2: Remove unused imports**

At the top of `design_hlr.py`, remove the imports that are no longer needed:

```python
# Remove these — no longer called from design_hlr:
# from backend.ticketing_agent.design.design_oo import design_oo
# from backend.ticketing_agent.design.discover_classes import discover_classes
```

Keep the `discover_classes` and `design_oo` imports commented out so they're available for standalone use if needed, or just remove them entirely.

Also remove the `os` import if no longer needed (the `log_dir` variables are still used via `os.path.join`, so keep `os`).

- [ ] **Step 3: Commit this task**

```bash
git add backend/ticketing_agent/design/design_hlr.py
git commit -m "Simplify design_hlr: call unified design_and_verify directly"
```

---

### Task 5: Update design_per_hlr.py

**Files:**
- Modify: `backend/ticketing_agent/design/design_per_hlr.py`

- [ ] **Step 1: Remove the now-redundant context gathering for design_oo**

In `design_all_hlrs()`, the loop that processes each HLR currently gathers `existing_classes` and `intercomponent_classes` before calling `design_hlr`. These are still needed — `design_and_verify` receives them. No change needed here.

The `dep_toolset` lifecycle (created before the loop, closed after) also stays the same — it's now passed through to the combined loop's dispatcher.

No functional changes needed in this file. The `design_hlr()` call already passes `toolset=dep_toolset`, and since we simplified `design_hlr()` to pass it through to `design_and_verify`, the wiring is complete.

- [ ] **Step 2: Verify the call signature matches**

Confirm that in `design_all_hlrs()`, the `design_hlr()` call already passes all the parameters that the new `design_hlr()` expects. Check around line 270:

```python
            oo, ontology = design_hlr(
                hlr=hlr,
                llrs=hlr_llrs,
                language=language,
                existing_classes=existing_classes or None,
                intercomponent_classes=intercomponent_classes or None,
                other_hlr_summaries=other_hlr_summaries or None,
                dependency_contexts=dependency_contexts,
                component_namespace=component_namespace,
                sibling_namespaces=sibling_namespaces or None,
                component_id=component_id,
                prior_class_lookup=accumulated_class_lookup,
                toolset=dep_toolset,
                neo4j_session=neo4j_session,
                model=model,
                log_dir=log_dir,
            )
```

The `language` parameter is no longer used by `design_hlr()` since we removed the `design_oo` call. Leave it in the signature for backward compatibility but it won't be forwarded. The other params all map correctly.

No code changes needed in this file.

- [ ] **Step 3: Commit (if any changes made, otherwise skip)**

No changes to commit in this task — just verification.

---

### Task 6: Collapse scripts/03_design_requirements.py

**Files:**
- Modify: `scripts/03_design_requirements.py`

- [ ] **Step 1: Rewrite step_design_and_verify() to use the unified pipeline**

The current `step_design_and_verify()` runs two passes per HLR:
1. `design_hlr()` for initial design (not persisted)
2. `design_and_verify()` for verified design (persisted)

Now `design_hlr()` calls `design_and_verify()` internally. Replace the body of `step_design_and_verify()` with the simplified flow.

The key change is: replace the per-HLR loop body (from the `for i, hlr_id in enumerate(ordered_ids, 1):` line through the persistence block) with a single call to `design_hlr()` per HLR, then persist the result.

Replace the content inside the `try:` block of the per-HLR loop (roughly lines 440-690) with:

```python
        for i, hlr_id in enumerate(ordered_ids, 1):
            hlr = hlr_by_id.get(hlr_id)
            if not hlr:
                continue

            hlr_llrs = llrs_by_hlr.get(hlr_id, [])
            component_id = hlr.get("component_id")
            component_name = hlr.get("component_name", "")

            print(f"  [{i}/{len(ordered_ids)}] HLR {hlr_id}: {hlr['description'][:55]}...")

            # Gather in-memory context from prior designs
            existing_classes = []
            for prev_id, (prev_oo, prev_comp_id, _) in designed.items():
                if prev_comp_id == component_id:
                    existing_classes.extend(_extract_existing_classes(prev_oo))

            intercomponent_classes = []
            for prev_id, (prev_oo, prev_comp_id, prev_comp_name) in designed.items():
                intercomponent_classes.extend(
                    _extract_intercomponent_context(
                        prev_oo,
                        prev_comp_name,
                        component_id,
                        prev_comp_id,
                    )
                )

            dep_ctx = hlr.get("dependency_context")
            dependency_contexts = {hlr_id: dep_ctx} if dep_ctx else None

            component_namespace = hlr.get("component_namespace", "")
            sibling_namespaces = [
                h.get("component_namespace", "")
                for h in hlrs
                if h["id"] != hlr_id and h.get("component_namespace")
            ]

            # --- Single unified call: design_hlr now includes discovery + verify ---
            step_log.info("Designing + verifying HLR %d: %s", hlr_id, hlr['description'])
            try:
                oo, ontology, verifs = design_hlr(
                    hlr=hlr,
                    llrs=hlr_llrs,
                    existing_classes=existing_classes or None,
                    intercomponent_classes=intercomponent_classes or None,
                    dependency_contexts=dependency_contexts,
                    component_namespace=component_namespace,
                    sibling_namespaces=sibling_namespaces or None,
                    component_id=component_id,
                    prior_class_lookup=accumulated_class_lookup or None,
                    toolset=dep_toolset,
                    neo4j_session=neo4j_session,
                    log_dir=LOGS_DIR,
                )
            except Exception as e:
                step_log.exception("HLR %d design+verify failed: %s", hlr_id, e)
                print(f"    ERROR: HLR {hlr_id} design+verify failed: {e}")
                raise

            # Accumulate from the design output
            accumulated_class_lookup.update(_build_class_lookup(oo))
            designed[hlr_id] = (oo, component_id, component_name)

            # Persist design to Neo4j
            with get_neo4j().session() as ns:
                persisted = persist_design(ontology, ns, qname_to_node=qname_to_node)
            total_nodes += persisted.nodes_created
            total_triples += persisted.triples_created
            total_linked += persisted.links_applied
            total_skipped += persisted.links_skipped

            step_log.info(
                "HLR %d: %d nodes, %d triples persisted",
                hlr_id, persisted.nodes_created, persisted.triples_created,
            )

            # Persist verifications
            if verifs:
                with get_neo4j().session() as ns:
                    for llr_id, llr_verifs in verifs.items():
                        persisted_v = persist_verification(ns, llr_id, llr_verifs)
                        total_conditions += persisted_v.conditions_created
                        total_actions += persisted_v.actions_created

            # Print progress
            nodes_in_onto = len(ontology.nodes)
            triples_in_onto = len(ontology.triples)
            print(f"    {nodes_in_onto} design nodes, {triples_in_onto} triples")
```

- [ ] **Step 2: Return verifications from design_hlr**

In `backend/ticketing_agent/design/design_hlr.py`, change the return to include verifications:

```python
    return oo, ontology, result.verifications
```

- [ ] **Step 3: Remove the old separate discover + design_oo blocks**

Delete any code in `scripts/03_design_requirements.py` that references the old two-pass flow: the `design_hlr` call for the initial (unpersisted) design, the separate `design_and_verify` call, the `existing_verifications` gathering, the `build_verification_context` call. These are all replaced by the single `design_hlr()` call.

- [ ] **Step 4: Commit this task**

```bash
git add backend/ticketing_agent/design/design_hlr.py scripts/03_design_requirements.py
git commit -m "Collapse two-pass pipeline into single design_and_verify call per HLR"
```

---

### Task 7: Write tests for discovery tool routing

**Files:**
- Modify: `tests/test_combined_tools.py`

- [ ] **Step 1: Write test for discovery tool dispatch with toolset**

```python
class TestDiscoveryToolDispatch:
    """Test that discovery tool calls route through the toolset correctly."""

    def test_search_symbols_dispatches_to_toolset(self):
        """search_symbols should call toolset.search_symbols and return results."""
        mock_toolset = MagicMock()
        mock_toolset.search_symbols.return_value = [
            {"qualified_name": "Fl_Window", "kind": "class", "source": "fltk", "score": 10.0},
        ]

        dispatch = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            toolset=mock_toolset,
        )

        result = json.loads(dispatch("search_symbols", {"query": "window"}))
        mock_toolset.search_symbols.assert_called_once_with(query="window")
        assert len(result) == 1 or (isinstance(result, dict) and "error" not in result)

    def test_get_compound_dispatches_to_toolset(self):
        """get_compound should call toolset.get_compound with the name parameter."""
        mock_toolset = MagicMock()
        mock_toolset.get_compound.return_value = [
            {"qualified_name": "Fl_Window", "kind": "class", "members": []},
        ]

        dispatch = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            toolset=mock_toolset,
        )

        result = json.loads(dispatch("get_compound", {"name": "Fl_Window"}))
        mock_toolset.get_compound.assert_called_once_with(name="Fl_Window")

    def test_list_sources_dispatches_to_toolset(self):
        """list_sources should call toolset.list_sources."""
        mock_toolset = MagicMock()
        mock_toolset.list_sources.return_value = [
            {"source": "fltk", "node_type": "Compound", "count": 212},
        ]

        dispatch = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            toolset=mock_toolset,
        )

        result = json.loads(dispatch("list_sources", {}))
        mock_toolset.list_sources.assert_called_once_with()

    def test_browse_namespace_dispatches_to_toolset(self):
        """browse_namespace should call toolset.browse_namespace."""
        mock_toolset = MagicMock()
        mock_toolset.browse_namespace.return_value = [
            {"qualified_name": "Fl_Window", "kind": "class"},
        ]

        dispatch = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            toolset=mock_toolset,
        )

        result = json.loads(dispatch("browse_namespace", {"name": "Fl"}))
        mock_toolset.browse_namespace.assert_called_once_with(name="Fl")

    def test_find_inheritance_dispatches_to_toolset(self):
        """find_inheritance should call toolset.find_inheritance."""
        mock_toolset = MagicMock()
        mock_toolset.find_inheritance.return_value = [
            {"qualified_name": "Fl_Group", "kind": "class", "direction": "up"},
        ]

        dispatch = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            toolset=mock_toolset,
        )

        result = json.loads(dispatch("find_inheritance", {"name": "Fl_Window"}))
        mock_toolset.find_inheritance.assert_called_once_with(name="Fl_Window")

    def test_discovery_without_toolset_returns_error(self):
        """When toolset is None, discovery tools should return a helpful error."""
        dispatch = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            toolset=None,
        )

        result = json.loads(dispatch("search_symbols", {"query": "window"}))
        assert "error" in result
        assert "not available" in result["error"]

    def test_discovery_tool_failure_returns_error(self):
        """If the toolset method raises, the dispatcher should return error JSON."""
        mock_toolset = MagicMock()
        mock_toolset.search_symbols.side_effect = RuntimeError("Neo4j down")

        dispatch = make_combined_dispatcher(
            prior_class_lookup={},
            dependency_lookup=None,
            intercomponent_classes=None,
            toolset=mock_toolset,
        )

        result = json.loads(dispatch("search_symbols", {"query": "window"}))
        assert "error" in result
```

- [ ] **Step 2: Run tests to verify they pass**

```bash
cd /Users/danielnewman/dev/ticketing_system && python -m pytest tests/test_combined_tools.py -v
```

Expected: All tests pass.

- [ ] **Step 3: Commit this task**

```bash
git add tests/test_combined_tools.py
git commit -m "Add tests for discovery tool routing in combined dispatcher"
```

---

### Task 8: Integration test — run the pipeline end-to-end

**Files:**
- No code changes — manual verification

- [ ] **Step 1: Flush the Neo4j design graph**

```bash
cd /Users/danielnewman/dev/ticketing_system
source .venv/bin/activate
python -c "
from services.dependencies import init_neo4j, get_neo4j
init_neo4j()
with get_neo4j().session() as s:
    s.run('MATCH (n:Design) DETACH DELETE n')
    print('Design graph cleared')
"
```

- [ ] **Step 2: Run the design pipeline**

```bash
cd /Users/danielnewman/dev/ticketing_system
source .venv/bin/activate
python scripts/03_design_requirements.py
```

Expected: The pipeline runs the unified loop, discovers FLTK classes, and produces a design with `INHERITS_FROM` edges to dependency `:Compound` nodes. No duplicate `Operator` enum (or a warning is emitted if one appears).

- [ ] **Step 3: Verify the Neo4j graph has dependency links**

```bash
python -c "
from services.dependencies import init_neo4j, get_neo4j
init_neo4j()
with get_neo4j().session() as s:
    # Check INHERITS_FROM edges to dependency Compounds
    ih = s.run('''
        MATCH (d:Design)-[r:INHERITS_FROM]->(c:Compound)
        RETURN d.qualified_name as src, c.qualified_name as tgt
    ''').data()
    print('INHERITS_FROM to dependencies:', len(ih))
    for r in ih:
        print(f'  {r[\"src\"]} --> {r[\"tgt\"]}')

    # Check for duplicate enums
    dups = s.run('''
        MATCH (d:Design {kind: 'enum'})
        WITH d.name as name, collect(d.qualified_name) as qns, count(d) as cnt
        WHERE cnt > 1
        RETURN name, qns
    ''').data()
    print()
    print('Duplicate enums:', len(dups))
    for d in dups:
        print(f'  {d[\"name\"]}: {d[\"qns\"]}')

    # Check DEPENDS_ON edges
    deps = s.run('''
        MATCH (d:Design)-[r:DEPENDS_ON]->(t)
        RETURN d.qualified_name as src, type(r) as rtype, t.qualified_name as tgt
    ''').data()
    print()
    print('DEPENDS_ON edges:', len(deps))
    for r in deps:
        print(f'  {r[\"src\"]} --{r[\"rtype\"]}--> {r[\"tgt\"]}')
"
```

Expected:
- `INHERITS_FROM` edges connect design classes to FLTK dependency Compounds
- Either no duplicate enums, or the agent produced a warning about the collision
- `DEPENDS_ON` edges exist between components

- [ ] **Step 4: Commit the final state**

```bash
git add -A
git commit -m "Complete unified design-discovery-verify pipeline implementation"
```