# Per-HLR Encapsulated Pipeline — Implementation Plan

> **Goal:** Restructure the design & validation pipeline so that each high-level requirement goes through the full decompose → design → verify → lock cycle as a self-contained unit before the next HLR begins. Previously designed HLRs are treated as immutable context; only genuine interconnectivity gaps may be raised as issues.

**Motivation:** The current pipeline processes all HLRs in batch phases (decompose all → design all → verify all). This means decomposition happens without visibility into prior designs, there's no concept of a "locked" HLR, and later HLRs that define inter-component interfaces (e.g., a frontend-backend interface HLR) cannot reason about what the backend actually exposes. The per-HLR encapsulated pipeline fixes this by inverting the loop nesting: the outer loop is over HLRs, the inner loop is over phases.

---

## Architecture Change

### Current loop nesting

```python
for phase in [decompose, design, verify]:
    for hlr in ordered_hlrs:
        phase(hlr)
```

### Target loop nesting

```python
for hlr in ordered_hlrs:          # outer: HLR serial
    for phase in [decompose, design, verify, lock]:
        phase(hlr)
```

### Pipeline flow diagram

```
┌──────────────────────────────────────────────────────────┐
│ Order HLRs (dependency sort — foundational first)        │
└──────────────────────────────────────────────────────────┘
                           │
              ┌────────────┼────────────────┐
              ▼                             ▼
┌──────────────────────────┐   ┌──────────────────────────┐
│ HLR1: FULL PASS         │   │ HLR2: FULL PASS          │
│                          │   │ (HLR1 is locked context)  │
│  1. DECOMPOSE → LLRs    │   │                          │
│  2. DESIGN (OO + onto)  │──▶│  1. DECOMPOSE → LLRs    │
│  3. VERIFY (vs LLRs)    │   │  2. DESIGN              │
│  4. LOCK (immutable)    │   │  3. VERIFY              │
│                          │   │  4. LOCK                │
└──────────────────────────┘   └──────────────────────────┘
                                          │
                              ┌───────────┘
                              ▼
               ┌──────────────────────────┐
               │ HLR3: FULL PASS         │
               │ (HLR1+2 locked)         │
               │                         │
               │  e.g. "Frontend-backend  │
               │  interface" HLR          │
               │                         │
               │  Can raise ISSUE only   │
               │  if prior design is     │
               │  missing an inter-      │
               │  connectivity surface   │
               └──────────────────────────┘
```

---

## Changes Required

### 1. Add `pipeline_status` to HLRNode

HLRs need a lifecycle status so the pipeline (and dashboard) know where each HLR stands.

**Statuses:**
- `pending` — created but not yet processed
- `decomposed` — LLRs generated, not yet designed
- `designed` — OO design + ontology persisted, not yet verified
- `verified` — verification procedures committed and validated
- `locked` — fully complete; immutable for subsequent HLRs

**Files:**
- Modify: `backend/db/neo4j/repositories/models/requirement.py` (add `pipeline_status` field)
- Modify: `backend/db/neo4j/repositories/requirement.py` (add `pipeline_status` to create/update/list queries)
- Test: `tests/test_requirement_repository.py`

### 2. Add `flag_missing_interface` tool to combined loop

When designing a later HLR, the agent needs a way to formally flag that a prior locked design is missing an interconnectivity capability. This is NOT a design revision — it's an issue that must be resolved by revisiting the prior HLR (unlocking and re-locking it).

**Tool definition:**
```
flag_missing_interface:
  description: >
    Flag that a prior locked HLR's design is missing an inter-component
    interface element needed by the current HLR. This creates a structured
    issue record that must be resolved before the current HLR can be
    completed.
  input:
    locked_hlr_id: int       — The HLR that is missing the interface
    missing_element: str     — What is missing (e.g. "public getter for last result")
    needed_by: str           — How the current HLR needs to use it
    suggested_resolution: str — Optional: what to add to the locked HLR
```

**Files:**
- Modify: `backend/ticketing_agent/design_verify/combined_tools.py` (add tool + dispatcher handler)
- Modify: `backend/ticketing_agent/design_verify/combined_prompt.py` (document the tool in prompt)
- Test: `tests/test_combined_tools.py`

### 3. Add `InterconnectivityIssue` model and persistence

Issues flagged by `flag_missing_interface` need to be stored so they can be reviewed and resolved.

**Storage:** Neo4j `:Issue` nodes linked to `:HLR` nodes via `:FLAGGED_AGAINST` and `:NEEDED_BY` edges.

**Files:**
- Modify: `backend/db/neo4j/repositories/requirement.py` (add issue CRUD methods)
- New: `backend/db/neo4j/repositories/models/issue.py` (Pydantic model)
- Test: `tests/test_requirement_repository.py`

### 4. Restructure `scripts/03_design_requirements.py`

Replace the batch-first `step_decompose()` + `step_design_and_verify()` with a single `step_per_hlr_pipeline()` that processes each HLR through the full cycle:

```python
def step_per_hlr_pipeline():
    # 1. Order HLRs (foundational first)
    ordered = order_hlrs(hlrs, ...)

    for hlr in ordered:
        # 2. Decompose (with visibility into locked HLR designs)
        decompose_hlr(hlr, locked_designs=accumulated_locked_context)
        persist_decomposition(...)

        # 3. Design + Verify (combined loop — single design pass)
        result = design_and_verify(hlr, llrs, locked_designs=..., ...)
        persist_design(verified_ontology, ...)
        persist_verification(result.verifications, ...)

        # 4. Lock
        req_repo.update_hlr(hlr.id, pipeline_status="locked")
        accumulated_locked_context.update(extract_context(result.oo_design))
```

Key changes:
- Decompose is called per-HLR, not in a batch
- `design_hlr()` (the initial throwaway design) is removed — `design_and_verify()` is the only design pass
- After verify, the HLR is marked `locked`
- The decomposer receives context about prior locked designs (class summaries, intercomponent APIs)

**Files:**
- Modify: `scripts/03_design_requirements.py` (restructure as described)
- Keep: `step_summary()` (no change)

### 5. Restructure `backend/pipeline/orchestrator.py`

Same structural change as the script but in the orchestrator. The `run_pipeline()` function currently has 10 sequential batch phases. Change to:

```python
def run_pipeline(...) -> PipelineResult:
    # Phase 0: Order HLRs
    # Phase 1-N: Per-HLR loop
    for hlr in ordered_hlrs:
        decompose(hlr, locked_context=...)
        design_and_verify(hlr, ...)
        persist + lock
    # Post-loop: tasks, skeleton, tests, impl, sync
```

**Files:**
- Modify: `backend/pipeline/orchestrator.py`

### 6. Update decomposer to accept locked design context

The `decompose_hlr.py` decomposer currently receives `other_hlrs` (sibling HLRs) but no information about their designs. Add an optional `locked_designs_context` parameter that provides class/interface summaries from prior locked HLRs so the decomposer can make informed decisions about what LLRs to generate (especially for interconnectivity HLRs).

**Files:**
- Modify: `backend/ticketing_agent/decompose/decompose_hlr.py` (add `locked_designs_context` param, include in prompt)
- Modify: `backend/ticketing_agent/decompose/decompose_hlr.py` SYSTEM_PROMPT (add guidance for referencing locked designs)
- Test: `tests/test_requirements_schemas.py` (or new test)

### 7. Remove `design_hlr()` as the initial pass from `step_design_and_verify`

Currently `step_design_and_verify()` calls `design_hlr()` first (producing a throwaway initial design), then calls `design_and_verify()` (the combined loop that produces the actual persisted design). This double-design is wasteful and confusing. The combined loop is the authoritative design pass.

The `design_hlr()` function should remain available for standalone use (e.g., `design_per_hlr.py`'s `design_and_persist_hlr()`), but `scripts/03_design_requirements.py` and `orchestrator.py` should call `design_and_verify()` directly.

**Discovery (dependency graph class lookup) should feed into the combined loop**, not require a separate `design_hlr()` call. This means:
- If a dependency toolset is available, call `discover_classes()` before the combined loop
- Feed discovery results into `design_and_verify()` as `dependency_classes` / `as_built_classes`
- The combined loop handles the rest

**Files:**
- Modify: `scripts/03_design_requirements.py` (remove `design_hlr()` call, add explicit `discover_classes()` before the combined loop)
- Modify: `backend/pipeline/orchestrator.py` (same)

### 8. Update benchmark script to use third HLR

The `scripts/02_setup_project.py` already has 3 HLR descriptions including the interconnectivity one. The `scripts/04_benchmark_calculator.py` only has 2. Sync them.

**Files:**
- Modify: `scripts/04_benchmark_calculator.py` (add third HLR, add component assignment)

---

## Detailed Implementation Tasks

### Task 1: Add `pipeline_status` to HLRNode

**Step 1:** Add test for HLRNode with pipeline_status

Add to `tests/test_requirement_models.py` (or `test_requirement_repository.py`):

```python
def test_hlr_node_has_pipeline_status():
    from backend.db.neo4j.repositories.models.requirement import HLRNode
    hlr = HLRNode(id=1, description="Test", pipeline_status="pending")
    assert hlr.pipeline_status == "pending"

def test_hlr_node_pipeline_status_defaults_to_pending():
    from backend.db.neo4j.repositories.models.requirement import HLRNode
    hlr = HLRNode(id=1, description="Test")
    assert hlr.pipeline_status == "pending"
```

**Step 2:** Add `pipeline_status` field to `HLRNode` in `backend/db/neo4j/repositories/models/requirement.py`:

```python
class HLRNode(BaseModel):
    id: int
    description: str
    component_id: int | None = None
    dependency_context: dict | None = None
    pipeline_status: str = "pending"  # pending | decomposed | designed | verified | locked
```

**Step 3:** Update `RequirementRepository` CRUD to include `pipeline_status`:
- `create_hlr()`: persist `pipeline_status` (default `"pending"`)
- `get_hlr()`: read `pipeline_status`
- `update_hlr()`: allow updating `pipeline_status` (add to `allowed` set)
- `list_hlrs()`: include `pipeline_status` in returned `HLRNode`

**Step 4:** Add test for repository-level pipeline_status operations:

```python
def test_update_hlr_pipeline_status(neo4j_session):
    repo = RequirementRepository(neo4j_session)
    hlr = repo.create_hlr(description="Test HLR")
    assert hlr.pipeline_status == "pending"

    repo.update_hlr(hlr.id, pipeline_status="decomposed")
    updated = repo.get_hlr(hlr.id)
    assert updated.pipeline_status == "decomposed"

    repo.update_hlr(hlr.id, pipeline_status="locked")
    locked = repo.get_hlr(hlr.id)
    assert locked.pipeline_status == "locked"
```

**Step 5:** Run tests, commit.

---

### Task 2: Add `InterconnectivityIssue` model and persistence

**Step 1:** Create `backend/db/neo4j/repositories/models/issue.py`:

```python
class InterconnectivityIssue(BaseModel):
    id: int
    locked_hlr_id: int       # HLR with missing interface
    needed_by_hlr_id: int     # HLR that needs it
    missing_element: str      # What's missing
    needed_for: str           # How it's needed
    suggested_resolution: str = ""
    status: str = "open"      # open | resolved | deferred
```

**Step 2:** Add issue CRUD methods to `RequirementRepository`:

```python
def create_issue(self, locked_hlr_id, needed_by_hlr_id, missing_element, needed_for, suggested_resolution="") -> InterconnectivityIssue
def list_issues(self, hlr_id=None, status=None) -> list[InterconnectivityIssue]
def resolve_issue(self, issue_id) -> InterconnectivityIssue | None
```

Cypher pattern:
```cypher
CREATE (i:Issue {id: $id, missing_element: $me, needed_for: $nf, suggested_resolution: $sr, status: 'open'})
MATCH (h:HLR {id: $locked_id}) MERGE (i)-[:FLAGGED_AGAINST]->(h)
MATCH (h:HLR {id: $needed_id}) MERGE (i)-[:NEEDED_BY]->(h)
```

**Step 3:** Write tests, commit.

---

### Task 3: Add `flag_missing_interface` tool to combined loop

**Step 1:** Add tool definition to `combined_tools.py`:

```python
FLAG_MISSING_INTERFACE_TOOL = {
    "name": "flag_missing_interface",
    "description": (
        "Flag that a prior locked HLR's design is missing an inter-component "
        "interface element needed by the current HLR. Creates an issue record. "
        "Use this ONLY when the current HLR's design requires interacting with "
        "a prior HLR's classes but the necessary public API (method, attribute, "
        "interface) is not present in that locked design. Do NOT use this for "
        "classes that exist but you haven't found yet — use lookup_design_element "
        "first."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "locked_hlr_id": {
                "type": "integer",
                "description": "ID of the locked HLR whose design is missing the interface element"
            },
            "missing_element": {
                "type": "string",
                "description": "Description of the missing interface element (e.g., 'public method to get last calculation result')"
            },
            "needed_for": {
                "type": "string",
                "description": "How the current HLR needs to use this element"
            },
            "suggested_resolution": {
                "type": "string",
                "description": "Optional suggestion for what to add to the locked HLR's design"
            },
        },
        "required": ["locked_hlr_id", "missing_element", "needed_for"],
    },
}
```

**Step 2:** Add tool to `ALL_TOOLS` list and dispatcher:

The dispatcher's `flag_missing_interface` handler:
1. Creates an `:Issue` node via `RequirementRepository.create_issue()`
2. Returns `{"flagged": true, "issue_id": <id>}`

**Step 3:** Update `combined_prompt.py`:

Add a section explaining when and how to use `flag_missing_interface`:
- Only flag when `lookup_design_element` confirms the needed element doesn't exist
- The flag does NOT unlock the prior HLR — it creates an issue for human review
- The current HLR should still complete its design (possibly with a placeholder or alternative approach)

**Step 4:** The `commit_design_and_verifications` tool should NOT fail if there are open issues. Issues are informational, not blocking. The design will note them in `design_warnings`.

**Step 5:** Write tests, commit.

---

### Task 4: Update decomposer with locked design context

**Step 1:** Add `locked_designs_context` parameter to `decompose()`:

```python
def decompose(
    description: str,
    other_hlrs: list[dict] | None = None,
    component: str = "",
    dependency_context: dict | None = None,
    locked_designs_context: list[dict] | None = None,  # NEW
    model: str = "",
    prompt_log_file: str = "",
) -> DecomposedRequirement:
```

**Step 2:** Update SYSTEM_PROMPT to include a section about locked designs:

```
## Previously Designed HLRs

The following HLRs have already been designed and locked. Their class
structures are available as context for decomposition. When decomposing
the current HLR:
- Reference these designs when the current HLR interacts with them
- Do NOT generate LLRs for functionality already covered by a locked design
- If the current HLR defines an interface between components, generate LLRs
  that specify the interaction contract (what is called, what is returned)

{locked_designs_section}
```

**Step 3:** Format the locked designs section similar to `intercomponent_classes`:
- qualified_name, kind, description, methods (name + visibility), attributes (name + type)
- Mark which HLR each design belongs to
- Only include `is_intercomponent=True` classes for cross-component context

**Step 4:** Write tests, commit.

---

### Task 5: Restructure `scripts/03_design_requirements.py`

**Step 1:** Replace `step_decompose() + step_design_and_verify()` with a single `step_per_hlr_pipeline()`:

```python
def step_per_hlr_pipeline():
    """Process each HLR through the full cycle: decompose → design+verify → lock."""

    # --- Load all HLRs ---
    with get_neo4j().session() as ns:
        repo = RequirementRepository(ns)
        hlrs_neo4j = repo.list_hlrs()

    hlrs = [_format_hlr_dict(h) for h in hlrs_neo4j]

    if not hlrs:
        print("  No HLRs found. Run setup_project.py first.\n")
        return

    # --- Order HLRs (foundational first) ---
    ordered = order_hlrs(hlrs, prompt_log_file=...)
    ordered_ids = [entry["id"] for entry in ordered]

    # --- Accumulate locked context ---
    designed: dict[int, tuple[OODesignSchema, int | None, str]] = {}
    accumulated_class_lookup: dict[str, str] = {}
    qname_to_node: dict = {}

    # --- Per-HLR loop ---
    for i, hlr_id in enumerate(ordered_ids, 1):
        hlr = hlr_by_id[hlr_id]

        # === DECOMPOSE ===
        if hlr_is_pending(hlr):
            llrs = decompose_hlr(hlr, locked_context=...)
            persist_decomposition(...)
            req_repo.update_hlr(hlr_id, pipeline_status="decomposed")

        # === DESIGN + VERIFY ===
        discovery_classes = discover_classes(hlr, ...) if dep_toolset else None
        result = design_and_verify(hlr, llrs, ..., locked_designs=...)
        persist_design(verified_ontology, ...)
        persist_verification(result.verifications, ...)
        req_repo.update_hlr(hlr_id, pipeline_status="verified")

        # === LOCK ===
        accumulated_class_lookup.update(_build_class_lookup(result.oo_design))
        designed[hlr_id] = (result.oo_design, component_id, component_name)
        req_repo.update_hlr(hlr_id, pipeline_status="locked")

        # Report any interconnectivity issues
        if result.design_warnings:
            ...
```

**Step 2:** Remove `step_decompose()` and the old `step_design_and_verify()`. Keep `step_summary()`.

**Step 3:** Update `if __name__ == "__main__":` to call `step_per_hlr_pipeline()`.

**Step 4:** Commit.

---

### Task 6: Restructure `backend/pipeline/orchestrator.py`

**Step 1:** Rewrite `run_pipeline()` to use the per-HLR loop structure:

```python
def run_pipeline(...) -> PipelineResult:
    # --- Order HLRs ---
    # --- Per-HLR loop:
    #   Decompose → Design+Verify → Lock ---
    # --- Post-loop: Tasks, Skeleton, Tests, Impl, Sync ---
```

The post-loop phases (task generation, skeleton, tests, implementation, sync) remain batch across all HLRs since they operate on the accumulated design.

**Step 2:** Ensure `PipelineResult` still captures the same metrics.

**Step 3:** Commit.

---

### Task 7: Update benchmark calculator script

**Step 1:** Add third HLR to `scripts/04_benchmark_calculator.py`:

```python
CALCULATOR_HLRS = [
    "The calculator application provides a GUI with a numeric display and buttons "
    "for digits 0-9, operators (+, -, *, /), clear, and equals. Display shows current "
    "input and result.",
    "The calculator performs addition, subtraction, multiplication, and division with "
    "proper input validation. Division by zero raises an error. Invalid expressions "
    "are rejected. Results are returned immediately.",
    "The calculator backend exposes an interface that clearly encapsulates the backend "
    "engine while making it straightforward to call necessary functions and retrieve "
    "operational data from the user interface.",
]
```

**Step 2:** Add component setup (CalculatorEngine, CalculatorUI components with namespaces).

**Step 3:** Commit.

---

### Task 8: Handle HLR resume/skip for partially processed pipelines

When re-running the pipeline (e.g., after adding a new HLR), already-locked HLRs should be skipped. The `pipeline_status` field enables this:

```python
for hlr_id in ordered_ids:
    hlr = repo.get_hlr(hlr_id)
    if hlr.pipeline_status == "locked":
        # Already processed — load its design context and continue
        accumulated_context.update(load_locked_design_context(hlr_id))
        continue

    # Process as normal...
```

If an HLR is partially processed (e.g., `decomposed` but not `designed`), the pipeline should resume from the appropriate phase. This makes the pipeline idempotent and resumable.

**Files:**
- Already covered by Task 5 (the `step_per_hlr_pipeline` function should check `pipeline_status`)
- Add `load_locked_design_context()` helper

---

## What Does NOT Change

These components remain as-is:

| Component | Reason |
|-----------|--------|
| `order_hlrs.py` | Still used to determine HLR processing order |
| `design_and_verify/combined_loop.py` | Already per-HLR; just called in new order |
| `design_and_verify/combined_tools.py` | Only adds the `flag_missing_interface` tool |
| `design_hlr.py` | Kept for standalone use; not called in main pipeline |
| `verify/verify_llr.py` | Kept for standalone use; combined loop replaces it in main pipeline |
| All frontend code | Status display can be added later |
| Persistence layer | No structural changes, just new `pipeline_status` and `:Issue` nodes |

---

## Execution Order

```
Task 1  ──→  Task 2  ──→  Task 3
  (status)     (issues)     (tool)

Task 4 (decomposer context) ── independent

Task 5  ──→  Task 6
(scripts)    (orchestrator)

Task 7 (benchmark) ── independent

Task 8 (resume) ── depends on Task 5
```

Tasks 1, 4, 7 can be done in parallel.
Tasks 2, 3 must be sequential (3 depends on 2).
Tasks 5, 6 can be done after Tasks 1-4 (they consume all the new APIs).
Task 8 is last.