# Move Neo4j Connection to Codegraph

**Date:** 2026-05-31
**Status:** draft

## Summary

Relocate `backend/db/neo4j/connection.py` into the shared `codegraph` library
as `src/codegraph/neo4j/connection.py`. The ticketing system imports its Neo4j
driver from codegraph instead of owning it directly. Framework-coupling
(NiceGUI) is already absent from the connection module — this is a pure import
relocation.

Ticketing-specific constraint/index DDL stays in the ticketing system in a new
`backend/db/neo4j/constraints.py`. Generic DDL for shared labels (`File`,
`Compound`, `Member`, `Namespace`) moves to codegraph via the existing
`CONSTRAINTS_AND_INDEXES` constant.

## Motivation

- Single shared driver avoids dual-connection risk between repositories
- Follows the prior pattern of moving shared data model code to codegraph
- Decouples Neo4j connectivity from the ticketing system's internal DB package
- Generic constraint DDL belongs alongside the node models it indexes

## Design

### New files in codegraph

**`src/codegraph/neo4j/__init__.py`** — re-exports the public API:

```python
from codegraph.neo4j.connection import (
    NEO4J_PASSWORD,
    NEO4J_URI,
    NEO4J_USER,
    Neo4jConnection,
    close_standalone_driver,
    get_standalone_driver,
    get_standalone_session,
)

__all__ = [
    "Neo4jConnection",
    "NEO4J_URI",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
    "get_standalone_driver",
    "get_standalone_session",
    "close_standalone_driver",
]
```

**`src/codegraph/neo4j/connection.py`** — copy of current
`backend/db/neo4j/connection.py` with these changes:

1. Remove `ensure_constraints()`, `ensure_design_constraints()`,
   `ensure_requirement_constraints()` (all three methods)
2. Add a single `ensure_constraints()` that runs `CONSTRAINTS_AND_INDEXES`
   from `codegraph.constants`

### Updated files in codegraph

**`src/codegraph/__init__.py`** — add `neo4j` import and exports:

```python
from codegraph.neo4j import (
    NEO4J_PASSWORD,
    NEO4J_URI,
    NEO4J_USER,
    Neo4jConnection,
    close_standalone_driver,
    get_standalone_driver,
    get_standalone_session,
)
```

**`src/codegraph/constants.py`** — fix two discrepancies against the
ticketing system's actual indexes:

1. Add `namespace_qualified_name` index (ticketing has it, codegraph doesn't):
   ```python
   "CREATE INDEX namespace_qualified IF NOT EXISTS FOR (n:Namespace) ON (n.qualified_name)",
   ```
2. No rename needed for `compound_qualified` — codegraph's shorter name is
   canonical; the ticketing system's `compound_qualified_name` index will be
   replaced on next `ensure_constraints()` run.

**`codegraph/pyproject.toml`** — add `neo4j` to dependencies.

### New files in ticketing system

**`backend/db/neo4j/constraints.py`** — ticketing-specific DDL only:

| Index/Constraint | Label |
|---|---|
| `hlr_id` CONSTRAINT | `:HLR` |
| `llr_id` CONSTRAINT | `:LLR` |
| `verification_method_id` CONSTRAINT | `:VerificationMethod` |
| `condition_id` CONSTRAINT | `:Condition` |
| `action_id` CONSTRAINT | `:Action` |
| `compound_component_id` INDEX | `:Compound` |
| `compound_implementation_status` INDEX | `:Compound` |

### Updated files in ticketing system

**`backend/db/neo4j/connection.py`** — becomes a re-export shim (kept
temporarily to ensure no missed imports break at runtime):

```python
"""Re-export shim — imports actual connection from codegraph."""
from codegraph.neo4j.connection import *  # noqa: F401, F403
```

**`backend/db/neo4j/__init__.py`** — import connection from codegraph:

```python
from codegraph.neo4j import (
    NEO4J_PASSWORD,
    NEO4J_URI,
    NEO4J_USER,
    Neo4jConnection,
    close_standalone_driver,
    get_standalone_driver,
    get_standalone_session,
)
from backend.db.neo4j.constraints import ensure_ticketing_constraints
```

**Import path updates** — ~21 files change `from backend.db.neo4j.connection`
→ `from codegraph.neo4j`:

| File | Import used |
|---|---|
| `nicegui_app.py` | `Neo4jConnection` |
| `frontend/data/hlr.py` | `Neo4jConnection` |
| `frontend/data/llr.py` | `Neo4jConnection` |
| `frontend/data/ontology.py` | `Neo4jConnection` |
| `frontend/data/dependencies.py` | `Neo4jConnection` |
| `frontend/pages/node_detail.py` | `Neo4jConnection` |
| `backend/ticketing_agent/mcp_server.py` | `Neo4jConnection`, `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` |
| `backend/ticketing_agent/design/*` (various) | `Neo4jConnection` |
| `backend/ticketing_agent/verify/*` (various) | `Neo4jConnection` |
| `backend/ticketing_agent/tools/*` (various) | `Neo4jConnection` |
| `backend/pipeline/services.py` | `Neo4jConnection` |
| `backend/pipeline/orchestrator.py` | `Neo4jConnection` |
| `backend/requirements/services/persistence.py` | `Neo4jConnection` |
| `backend/requirements/services/graph_tags.py` | `Neo4jConnection` |
| `services/dependencies.py` | `Neo4jConnection` |
| `scripts/01_flush_db.py` | `Neo4jConnection` |
| `scripts/02_setup_project.py` | `Neo4jConnection` |
| `scripts/05a_build_and_index.py` | `Neo4jConnection` |
| `scripts/05_benchmark_calculator.py` | `Neo4jConnection` |
| `scripts/05_generate_skeleton.py` | `Neo4jConnection` |
| `scripts/migrate_design_labels.py` | `Neo4jConnection` |
| `scripts/import_fixtures.py` | `Neo4jConnection` |
| `scripts/export_fixtures.py` | `Neo4jConnection` |
| `tests/conftest.py` | `Neo4jConnection` |
| `tests/test_*` (various) | `get_standalone_driver`, `Neo4jConnection` |

### Deleted from ticketing system

Nothing deleted — `backend/db/neo4j/connection.py` becomes a re-export shim.

### What stays the same

- All Neo4j session usage patterns (`.session()`, `.verify_connectivity()`,
  `.get_driver()`)
- All constraint/index semantics — same Cypher, same labels
- Standalone driver functions — identical API, just different import path
- `nicegui_app.py` `app.storage.user` binding — unchanged, just imports from
  codegraph

## Migration order

1. **Codegraph**: update `pyproject.toml` (add `neo4j` dep), update
   `constants.py` (add `namespace_qualified` index), create
   `src/codegraph/neo4j/` package, update `src/codegraph/__init__.py`
2. **Codegraph**: `pip install -e .` to pick up `neo4j` dependency
3. **Ticketing**: create `backend/db/neo4j/constraints.py`, update
   `backend/db/neo4j/__init__.py`
4. **Ticketing**: update all import paths (~21 files)
5. **Ticketing**: convert `backend/db/neo4j/connection.py` to re-export shim
6. **Verify**: `pytest` in both repos

## Test plan

- Run codegraph's existing test suite for constants changes
- Run ticketing's full test suite (`pytest`) for import path resolution
- No new tests — relocation only, no behavior changes

## Rollback

- `backend/db/neo4j/connection.py` re-export shim ensures old imports still work
- Revert in codegraph: delete `src/codegraph/neo4j/`, revert `__init__.py`,
  revert `pyproject.toml`
- Revert in ticketing: restore `connection.py`, revert import paths
