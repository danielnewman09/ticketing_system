# Per-HLR Encapsulated Pipeline — Design Specification

## Problem

The current design pipeline processes all HLRs in batch phases: decompose all → design all → verify all. This has three critical issues:

1. **Decomposition is blind to design.** LLRs are generated for all HLRs before any design exists, so the decomposer cannot reference the concrete API surface of prior HLRs. For the calculator benchmark, an interconnectivity HLR cannot be decomposed with knowledge of what the backend engine actually exposes.

2. **No design encapsulation.** Each HLR's design is not self-contained within its requirements. The pipeline treats all HLRs as a single design space, making it unclear which design elements belong to which requirement and whether a requirement's design is complete.

3. **No immutability guarantee.** After an HLR is designed, there is no "locked" status. Later HLRs could in principle depend on design elements that haven't been solidified, and there's no mechanism to flag that a prior design is missing an interconnectivity surface.

## Solution

Invert the loop nesting. Instead of processing all HLRs through each phase, process each HLR through all phases:

```
Current:   for phase in [decompose, design, verify]: for hlr in hlrs: phase(hlr)
Proposed:  for hlr in ordered_hlrs: for phase in [decompose, design, verify, lock]: phase(hlr)
```

Each HLR goes through the complete decompose → design → verify → lock cycle before the next HLR starts. The `order_hlrs` step still determines processing order (foundational first).

### Key Concepts

**HLR Pipeline Status:**
- `pending` — created but not yet processed
- `decomposed` — LLRs generated
- `designed` — OO design + ontology persisted
- `verified` — verification procedures committed
- `locked` — fully complete, immutable for subsequent HLRs

**Locked Design Context:**
When designing a later HLR, all previously locked HLRs' designs are available as read-only context. The designer treats these designs as facts about the system — they can reference their classes, methods, and attributes but cannot modify them.

**Interconnectivity Issues:**
If a later HLR needs an interface element that doesn't exist in a prior locked design, the agent can flag it via the `flag_missing_interface` tool. This creates a structured issue record without unlocking the prior HLR. Issues are for human review and may result in unlocking and re-processing the prior HLR.

**Idempotent Resume:**
The `pipeline_status` field allows the pipeline to resume after partial processing. If an HLR is already `locked`, its design context is loaded and the pipeline continues. If it's `decomposed` but not `designed`, the pipeline resumes from the design phase.

### Data Model Changes

**HLRNode** gains `pipeline_status: str = "pending"`.

**New: `:Issue` nodes in Neo4j:**
```
(:Issue {id, missing_element, needed_for, suggested_resolution, status})
(:Issue)-[:FLAGGED_AGAINST]->(:HLR)   -- HLR with missing interface
(:Issue)-[:NEEDED_BY]->(:HLR)          -- HLR that needs the interface
```

### Pipeline Changes

**Scripts (03_design_requirements.py):**
- Replace `step_decompose() + step_design_and_verify()` with `step_per_hlr_pipeline()`
- Each HLR: decompose → design+verify (combined loop) → lock
- Remove the initial `design_hlr()` call that produced a throwaway design
- Add explicit `discover_classes()` before the combined loop for dependency graph lookups

**Orchestrator (pipeline/orchestrator.py):**
- Same structural change as the script
- Post-loop phases (tasks, skeleton, tests, impl, sync) remain batch

**Decomposer (decompose_hlr.py):**
- Accept optional `locked_designs_context` parameter
- Include locked design class summaries in the decomposition prompt
- Enables the decomposer to generate LLRs that reference concrete prior designs

**Combined Loop (design_verify/combined_loop.py):**
- Add `flag_missing_interface` tool
- Add `current_hlr_id` parameter so the tool knows which HLR is being designed
- Include locked design context in the prompt

### What Doesn't Change

- `order_hlrs.py` — still determines processing order
- `design_and_verify/combined_loop.py` — already per-HLR
- `design_hlr.py` — kept for standalone use
- Frontend — status display can be added incrementally

### Calculator Benchmark

The benchmark now has 3 HLRs:
1. GUI with display and buttons (designed first → locked)
2. Backend calculation engine (designed second → locked)
3. Frontend-backend interface (designed third → references HLR1+2 locked designs)

The third HLR demonstrates the pipeline's ability to design inter-component interfaces based on concrete prior designs. The decomposer can reference `CalculatorEngine::add()`, `CalculatorEngine::getLastResult()`, etc. because those classes exist in the locked context.

## Test Strategy

1. Unit tests for `HLRNode.pipeline_status` and `RequirementRepository` status transitions
2. Unit tests for `InterconnectivityIssue` CRUD
3. Unit test for `flag_missing_interface` tool in the combined dispatcher
4. Unit test for decomposer with `locked_designs_context`
5. Integration test: run the pipeline on the calculator benchmark and verify that HLR3's design references HLR1+2's locked classes
6. Integration test: run the pipeline, interrupt after HLR2 is locked, re-run and verify HLR1+2 are skipped