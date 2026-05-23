# Phase 2: Requirements — HLR/LLR Move to Neo4j

## Objective

Promote HLR and LLR from SQLite table rows to full Neo4j `:HLR`/`:LLR` nodes,
eliminating the `sqlite_id` bridge and removing the SQLAlchemy models and M2M tables.

## Current State (after Phase 1)

- HLR/LLR data lives in `high_level_requirements` and `low_level_requirements` SQLite tables
- Neo4j has `:HLR`/`:LLR` stub nodes with `sqlite_id` properties for cross-referencing
- `TRACES_TO` edges link stubs to `:Design` nodes
- `DECOMPOSES_INTO` edges link `:HLR` → `:LLR`
- `persist_decomposition()` writes to both SQLite AND creates Neo4j stubs
- `fetch_hlr_detail()`, `fetch_llr_detail()`, `fetch_requirements_data()` still query SQLAlchemy
- `frontend/data/hlr.py` CRUD functions write to SQLite + create/update/delete Neo4j stubs
- `Component.high_level_requirements` relationship still uses SQLAlchemy
- `low_level_requirements_components` M2M table still exists

## Target State

- `RequirementRepository` provides full CRUD for HLR/LLR in Neo4j
- HLR/LLR nodes have full properties (description, component_id, dependency_context)
- `sqlite_id` property removed — HLR/LLR use Neo4j-native IDs
- SQLAlchemy `HighLevelRequirement` and `LowLevelRequirement` models deleted
- `low_level_requirements_components` M2M becomes `AFFECTS_COMPONENT` edges in Neo4j
- All frontend CRUD, dashboard, and agent code uses `RequirementRepository`
- Migration script copies all existing HLR/LLR data from SQLite to Neo4j

## Files Changed

### New Files
- `backend/db/neo4j/repositories/requirement.py` — RequirementRepository
- `backend/db/neo4j/repositories/models/requirement.py` — HLRNode, LLRNode Pydantic models
- `scripts/migrate_phase2_requirements_to_neo4j.py` — migration script

### Modified Files
- `backend/requirements/services/persistence.py` — `persist_decomposition()` uses RequirementRepository
- `backend/requirements/services/graph_tags.py` — remove `sqlite_id` from HLR/LLR queries
- `frontend/data/hlr.py` — all CRUD uses RequirementRepository
- `frontend/data/llr.py` — all CRUD uses RequirementRepository
- `frontend/data/ontology.py` — TRACES_TO queries drop `sqlite_id`
- `backend/db/neo4j/repositories/design.py` — `merge_hlr_stub`/`merge_llr_stub` become full node CRUD
- `backend/db/neo4j/connection.py` — add `ensure_requirement_constraints()`
- `backend/db/neo4j/__init__.py` — add RequirementRepository exports
- `backend/pipeline/orchestrator.py` — Phase 1-2 uses RequirementRepository
- `backend/pipeline/services.py` — remove HLR/LLR SQLAlchemy queries
- `backend/ticketing_agent/decompose/decompose_hlr.py` — fetch HLR from Neo4j
- `backend/ticketing_agent/design/design_per_hlr.py` — fetch HLR/LLR from Neo4j
- `backend/ticketing_agent/mcp_server.py` — HLR/LLR tool functions use Neo4j

### Deleted Files
- `backend/db/models/requirements.py` — HLR/LLR SQLAlchemy models
- Models removed from `backend/db/models/__init__.py`
- `ticket_requirements` table (if still present)

### Modified: Bridge Cleanup
- `backend/db/models/components.py` — remove `high_level_requirements` relationship
- `backend/db/models/associations.py` — remove `low_level_requirements_components` (becomes Neo4j edge)
- `backend/db/models/tasks.py` — remove task-related HLR/LLR references if any
- `backend/db/neo4j/sync.py` — remove HLR/LLR sync functions if any remain

## Implementation Steps

### Task 1: Create RequirementRepository and Pydantic Models

**Files:**
- Create: `backend/db/neo4j/repositories/models/requirement.py`
- Create: `backend/db/neo4j/repositories/requirement.py`
- Modify: `backend/db/neo4j/connection.py` — add `ensure_requirement_constraints()`

**HLRNode model:**
```python
class HLRNode(BaseModel):
    id: int  # Neo4j-native ID (replaces sqlite_id)
    description: str
    component_id: int | None = None
    dependency_context: dict | None = None
```

**LLRNode model:**
```python
class LLRNode(BaseModel):
    id: int
    description: str
    high_level_requirement_id: int  # references HLR.id
```

**RequirementRepository methods:**
- `create_hlr(description, component_id=None) -> HLRNode`
- `get_hlr(id) -> HLRNode | None`
- `update_hlr(id, **kwargs) -> HLRNode | None`
- `delete_hlr(id) -> bool`
- `list_hlrs(component_id=None) -> list[HLRNode]`
- `create_llr(hlr_id, description) -> LLRNode`
- `get_llr(id) -> LLRNode | None`
- `update_llr(id, **kwargs) -> LLRNode | None`
- `delete_llr(id) -> bool`
- `list_llrs(hlr_id=None) -> list[LLRNode]`
- `link_component(llr_id, component_id) -> None`  (AFFECTS_COMPONENT edge)
- `unlink_component(llr_id, component_id) -> None`

**Neo4j constraints:**
```cypher
CREATE CONSTRAINT IF NOT EXISTS FOR (h:HLR) REQUIRE h.id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (l:LLR) REQUIRE l.id IS UNIQUE;
```

### Task 2: Rewrite hlr.py and llr.py Data Access

**Files:**
- Modify: `frontend/data/hlr.py`
- Modify: `frontend/data/llr.py`

Replace all SQLAlchemy CRUD with `RequirementRepository` calls. Keep `fetch_requirements_data()` dashboard summary but get counts from Neo4j.

### Task 3: Rewrite persist_decomposition()

**Files:**
- Modify: `backend/requirements/services/persistence.py`

`persist_decomposition()` currently writes to SQLite AND creates Neo4j stubs.
Rewrite to use `RequirementRepository` as primary, with SQLite as secondary
for the Phase 2 bridge (any SQLite-only consumers like verification).

### Task 4: Update Agent Code

**Files:**
- Modify: `backend/ticketing_agent/decompose/decompose_hlr.py`
- Modify: `backend/ticketing_agent/design/design_per_hlr.py`
- Modify: `backend/ticketing_agent/mcp_server.py`
- Modify: `backend/ticketing_agent/review/review_class_design.py`
- Modify: `backend/ticketing_agent/review/challenge_design.py`

Replace SQLAlchemy HLR/LLR queries with `RequirementRepository` calls.

### Task 5: Remove sqlite_id Bridge

**Files:**
- Modify: `backend/db/neo4j/repositories/design.py` — update `merge_hlr_stub()`, `merge_llr_stub()`, `trace_design_to_hlr()`, `trace_design_to_llr()` to use native Neo4j IDs
- Modify: `backend/db/neo4j/queries/graph.py` — update `fetch_hlr_subgraph()` to use `id` instead of `sqlite_id`
- Modify: `backend/requirements/services/graph_tags.py` — update all `sqlite_id` references to use `id`
- Modify: `frontend/data/ontology.py` — update TRACES_TO queries to use `id`
- Modify: `frontend/data/hlr.py` — update all `sqlite_id` references

### Task 6: Delete SQLAlchemy HLR/LLR Models and M2M Tables

**Files:**
- Delete HLR/LLR models from `requirements.py` (or make them read-only bridges)
- Remove `low_level_requirements_components` from `associations.py`
- Remove `HighLevelRequirement`, `LowLevelRequirement`, `TicketRequirement` from `__init__.py`
- Remove `Component.high_level_requirements` relationship
- Update or remove SQLAlchemy migration for dropped tables
- Update `conftest.py` to remove HLR/LLR fixtures (or use Neo4j)

### Task 7: Data Migration Script

**Files:**
- Create: `scripts/migrate_phase2_requirements_to_neo4j.py`

Migration steps:
1. Query all HLRs from SQLite, create `:HLR` nodes with full properties
2. Create `DECOMPOSES_INTO` edges from HLR → LLR
3. Create `AFFECTS_COMPONENT` edges for `low_level_requirements_components`
4. Create `TRACES_TO` edges from `:HLR`/`:LLR` to `:Design` (using existing stub data)
5. Drop `sqlite_id` property from all `:HLR`/`:LLR` nodes
6. Verify counts match

### Task 8: Integration Testing and Cleanup

- Run full test suite
- Verify dashboard, HLR detail, LLR detail pages work
- Verify decomposition and design pipelines work end-to-end
- Remove any remaining `sqlite_id` fallback code

## Risks and Mitigations

1. **HLR/LLR SQLite ID references everywhere** — Need comprehensive grep for `sqlite_id` and `hlr.id`/`llr.id` in agent code, fix each one
2. **Decomposition agent writes to SQLite** — Phase 2 bridge: write to Neo4j first, then optionally sync to SQLite for verification (which still uses SQLAlchemy FKs)
3. **Verification still uses SQLAlchemy** — Phase 3 concern; Phase 2 keeps `VerificationMethod` in SQLite with `low_level_requirement_id` FK pointing to SQLite HLR ID. Need a lookup layer.
4. **Dashboard queries** — `fetch_requirements_data()` needs to query Neo4j for HLR/LLR data, may need performance tuning