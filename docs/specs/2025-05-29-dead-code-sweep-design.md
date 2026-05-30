# Dead Code Sweep — Design Spec

**Date:** 2025-05-29  
**Scope:** One-time surgical removal of confirmed dead code across backend/ and frontend/

## Summary

Remove ~200 lines of definitively dead code: deprecated functions with existing replacements, unused modules, dead helper functions, and commented-out imports. Leave `__init__.py` re-exports, duplicate constants, and comment blocks untouched — low payoff, higher risk.

## Section 1: Deprecated Functions Removal

### `build_verification_context()` — `backend/requirements/services/persistence.py`

- Delete the function body (approximately lines 70–138) and its docstring
- Keep `build_verification_context_from_diagram()` untouched — it is the replacement
- Update the docstring of `build_verification_context_from_diagram()` to remove the comparison reference to the old function

### `_extract_existing_classes()`, `_extract_intercomponent_context()`, `_build_class_lookup()` — `backend/ticketing_agent/design/design_per_hlr.py`

- All three have replacements in the `design_data` module (see commits `9ea27ab`, `7b96aa4`, `3f0ff80`)
- Migrate the two call sites (lines ~238 and ~243) to use `design_data.transforms` equivalents (e.g., `class_diagram_from_oo_design` + `to_verification_dicts`), consistent with how other callers were already migrated
- `_build_class_lookup` has zero callers — delete directly

### `build_draft_lookup()` and `draft_summary()` — `backend/ticketing_agent/tools/helpers/draft_state.py`

- Still called from `dispatcher.py`, `draft_design.py`, and `commit.py`
- Migrate all three call sites:
  - `build_draft_lookup(design)` → `ClassDiagram.to_draft_lookup()` on the appropriate `ClassDiagram` instance
  - `draft_summary(design)` → `ClassDiagram.to_verification_dicts()` (or equivalent `design_data` method)
- After migration, delete `backend/ticketing_agent/tools/helpers/draft_state.py` entirely
- Remove import statements from the three consumer files

## Section 2: Unused Functions and Dead Modules

### Dead formatting functions — `backend/requirements/verification_formatting.py`

- Delete `format_action()`, `format_condition()`, `format_verification_method()`, and `format_verification_method_prompt()`
- These have working replacements in `formatting.py` (as `_format_action`, `_format_condition`, etc.) which are the ones actually used throughout the codebase
- Keep the module-level constants `VERIFICATION_METHODS` and `CONDITION_OPERATORS` — they are re-exported through `models/__init__.py`

### Dead module — `backend/services/neo4j_service.py`

- The entire module is never imported anywhere
- `get_neo4j_session()`, `close_driver()`, and `verify_connection()` have zero callers
- Active Neo4j session management lives in `backend/db/neo4j/`
- Delete the file; remove the `services/` directory if it becomes empty after deletion

### Dead MCP tool — `apply_remediation()` in `backend/ticketing_agent/mcp_server.py`

- Registered with `@mcp.tool()` decorator but never invoked by any agent, pipeline step, script, or test
- Remove the function and its decorator

## Section 3: Commented-Out Code and Scope Boundaries

### Commented-out imports — `backend/ticketing_agent/design/design_hlr.py`

- Lines 14–15: two commented-out imports with notes "no longer called from pipeline" — delete them

### Explicitly NOT in scope

The following were identified but are excluded from this sweep:

- **`__init__.py` re-exports** (`backend/db/models/__init__.py`, `frontend/data/__init__.py`) — these form an explicit API surface; removing them risks breaking `from X import Y` patterns without exhaustive call-site tracing. Low cost to leave.
- **Duplicate `VERIFICATION_METHODS` constant** — exists in both `verification_formatting.py` and `schemas.py`, re-exported through `models/__init__.py`. Consolidating requires updating import paths in multiple files. Low payoff for this pass.
- **Large comment blocks** in `map_to_ontology.py`, `transforms.py`, `review_class_design.py`, etc. — these encode design intent or historical context; better removed file-by-file while working on those modules.
- **NiceGUI page imports in `frontend/pages/__init__.py`** — AST scanner flags these as unused, but NiceGUI's registration pattern means they have side effects on import. These are false positives.

## Risk Assessment

- All removals target code with confirmed zero callers or confirmed existing replacements
- The two migrations (`_extract_existing_classes` → `design_data` and `draft_state` → `design_data`) follow patterns already established in recent commits
- No changes to test files, no changes to database models, no changes to public API surfaces