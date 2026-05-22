# Neo4j Graph-Primary Design

## Objective

Move all graph-shaped data from SQLAlchemy/SQLite to Neo4j as the sole authority, eliminating the dual-write sync layer and enabling native graph traversals for requirement tracing, verification constraints, component hierarchies, and task coverage queries. SQLite reduces to flat configuration storage only.

## Current State

The system uses a dual-write, SQLite-primary pattern:

- **SQLite** (via SQLAlchemy/Alembic) is the source of truth for everything
- **Neo4j** is a read-optimized replica for graph queries only
- `backend/db/neo4j/sync.py` copies design nodes and triples from SQLite to Neo4j
- Requirements (HLR/LLR) and their M2M links to design nodes live entirely in SQLite
- Verification conditions/actions reference design nodes by string `member_qualified_name` with fragile longest-prefix matching
- Six M2M association tables bridge relational data to graph nodes
- The two-stage graph pipeline (Neo4j topology → SQLite enrichment) forces cross-store joins

### Problems

1. **Sync lag and consistency risk** — Neo4j is a best-effort secondary; writes can fail silently
2. **Awkward cross-store queries** — `fetch_hlr_subgraph()` queries SQLite for seed names, then Neo4j for the subgraph
3. **String-based verification references** — `member_qualified_name` strings resolved by longest-prefix match instead of structural graph edges
4. **M2M table proliferation** — Six association tables exist solely to link relational rows to graph nodes
5. **No structural verification model** — Conditions and actions are flat text records, not traversable graph elements

## Target State

Neo4j is the sole authority for all graph-shaped data. SQLite stores only flat configuration tables. No dual-write, no sync layer.

### Neo4j node labels

| Label | Current source | Key properties |
|-------|---------------|----------------|
| `:Design` | `OntologyNode` | `qualified_name`, `kind`, `specialization`, `visibility`, `description`, `refid`, `source_type`, `type_signature`, `argsstring`, `definition`, `file_path`, `line_number`, flags (`is_static`, `is_const`, `is_virtual`, `is_abstract`, `is_final`), `implementation_status`, `source_file`, `test_file` |
| `:Component` | `Component` | `name`, `namespace`, `description`, `language_id` |
| `:HLR` | `HighLevelRequirement` | `id`, `description`, `dependency_context` |
| `:LLR` | `LowLevelRequirement` | `id`, `description` |
| `:VerificationMethod` | `VerificationMethod` | `method`, `test_name`, `description` |
| `:VerificationStep` *(new)* | replaces `VerificationCondition` + `VerificationAction` | `phase` (pre/action/post), `order`, `args` |
| `:Constraint` *(new)* | structural redesign | `operator`, `value`, `description` |
| `:Task` | `Task` | `title`, `description`, `estimated_complexity`, `status`, `created_at`, `updated_at` |
| `:Ticket` | `Ticket` | `title`, `priority`, `complexity`, `author`, `summary`, `ticket_type`, `requires_math`, `generate_tutorial`, `language_id`, `created_at`, `updated_at` |
| `:AcceptanceCriteria` | `TicketAcceptanceCriteria` | `description` |
| `:TicketFile` | `TicketFile` | `file_path`, `change_type`, `description` |
| `:TicketReference` | `TicketReference` | `ref_type`, `ref_target` |
| `:Dependency` | `Dependency` | `name`, `version`, `github_url`, `is_dev`, `manager_id`, `index_file_patterns`, `index_subdir`, `index_exclude_patterns`, `index_recursive` |
| `:Recommendation` | `DependencyRecommendation` | `name`, `github_url`, `description`, `version`, `stars`, `license`, `last_updated`, `pros`, `cons`, `relevant_hlrs`, `relevant_structures`, `summary`, `status` |

As-built labels (`:Compound`, `:Member`, `:Namespace`, `:File`, `:Include`) are unchanged.

### Neo4j relationship types

| Type | From → To | Replaces |
|------|----------|----------|
| `ASSOCIATES`, `AGGREGATES`, `COMPOSES`, `DEPENDS_ON`, `GENERALIZES`, `REALIZES`, `INVOKES` | `:Design` → `:Design` / `:Compound` | `OntologyTriple` |
| `CONTAINS` | `:Component` → `:Component` | `Component.parent_id` FK |
| `BELONGS_TO` | `:Design` → `:Component` | `OntologyNode.component_id` FK |
| `HAS_HLR` | `:Component` → `:HLR` | `HLR.component_id` FK |
| `DECOMPOSES_INTO` | `:HLR` → `:LLR` | `LLR.high_level_requirement_id` FK |
| `TRACES_TO` | `:HLR` / `:LLR` → `:Design` | 4 M2M association tables |
| `COVERED_BY` | `:HLR` / `:LLR` → relationship | 2 M2M triple tables |
| `AFFECTS_COMPONENT` | `:LLR` → `:Component` | `low_level_requirements_components` M2M |
| `VERIFIED_BY` | `:LLR` → `:VerificationMethod` | `VerificationMethod.low_level_requirement_id` FK |
| `HAS_STEP` | `:VerificationMethod` → `:VerificationStep` | `VerificationCondition`/`Action` FK |
| `ENFORCES` | `:VerificationStep` → `:Constraint` | *(new structural edge)* |
| `LEFT_OPERAND` | `:Design` → `:Constraint` | `VerificationCondition.member_qualified_name` |
| `RIGHT_OPERAND` | `:Constraint` → `:Design` | *(new, for node-to-node comparisons)* |
| `CALLER` | `:Design` → `:Constraint` | `VerificationAction.member_qualified_name` |
| `CALLEE` | `:Constraint` → `:Design` | *(new, for call actions)* |
| `IMPLEMENTING` | `:Task` → `:Design` | `TaskDesignNode` association |
| `SATISFIES` | `:Task` → `:VerificationMethod` | `TaskVerification` association |
| `PARENT_TASK` | `:Task` → `:Task` | `Task.parent_id` FK |
| `HAS_TASK` | `:Component` → `:Task` | `Task.component_id` FK |
| `AFFECTS` | `:Ticket` → `:Component` | `tickets_components` M2M |
| `REQUIRES` | `:Ticket` → `:LLR` | `TicketRequirement` |
| `PARENT_TICKET` | `:Ticket` → `:Ticket` | `Ticket.parent_id` FK |
| `HAS_CRITERIA` | `:Ticket` → `:AcceptanceCriteria` | FK |
| `HAS_FILE` | `:Ticket` → `:TicketFile` | FK |
| `REFERENCES` | `:Ticket` → `:TicketReference` | FK |
| `USES_DEPENDENCY` | `:Component` → `:Dependency` | `dependency_components` M2M |
| `RECOMMENDED_FOR` | `:Recommendation` → `:Component` | FK |
| `IMPLEMENTED_BY` | `:Design` → `:Compound` / `:Member` | *(existing, stays)* |

### SQLite (retained)

| Table | Purpose |
|-------|---------|
| `project_meta` | Single-row project settings |
| `languages` | Flat config: language name + version |
| `build_systems` | Flat config: FK to languages |
| `test_frameworks` | Flat config: FK to languages |
| `dependency_managers` | Flat config: FK to languages |

Cross-store references are integer properties on Neo4j nodes (e.g. `language_id: 3` on `:Component`) that reference SQLite rows. The repository layer resolves them when the consumer needs the full config record.

### Removed (not migrated)

- All `ticket_embeddings*` tables and the `backend/search/` module — embedding search is removed entirely
- `backend/db/vec.py` — vec table setup
- The `sqlite-vec` event listener on the main engine
- The `Ticket.after_insert/after_update` embedding event handler

## Data Access Layer — Repository Pattern over Raw Cypher

### Repository classes

Each domain gets a repository that encapsulates Cypher queries and returns Pydantic models or dataclasses. No OGM framework.

```python
class DesignRepository:
    def __init__(self, session: Neo4jSession): ...
    def get_by_qualified_name(self, qname: str) -> DesignNode | None: ...
    def merge_node(self, node: DesignNode) -> DesignNode: ...
    def merge_triple(self, subj_qn: str, pred: str, obj_qn: str) -> None: ...
    def find_nodes(self, kind=None, search=None, component_id=None) -> list[DesignNode]: ...
    def delete_node(self, qname: str) -> bool: ...

class RequirementRepository: ...
class VerificationRepository: ...
class ComponentRepository: ...
class TaskRepository: ...
class TicketRepository: ...
class DependencyRepository: ...
```

### Pydantic models

Typed Python models replace SQLAlchemy ORM objects as the contract between Neo4j and the application:

```python
class DesignNode(BaseModel):
    qualified_name: str
    name: str
    kind: str
    specialization: str = ""
    visibility: str = ""
    description: str = ""
    # ... all current OntologyNode fields
```

No ORM lazy loading. Relationships are fetched explicitly via repository methods or included in query results.

### Session management

The existing `Neo4jConnection.session()` context manager continues. Repositories receive a session:

```python
with get_neo4j().session() as session:
    repo = DesignRepository(session)
    node = repo.get_by_qualified_name("Calculator::display")
```

Cypher writes are transactional within the session — committed on context exit, rolled back on exception.

### Idempotent upsert

MERGE in Cypher replaces the `get_or_create` pattern. Each repository's `merge_*` method is the idempotent upsert.

### Cascade deletes

Handled explicitly in repository delete methods via Cypher `DETACH DELETE` and subgraph matching:

```python
def delete_hlr(self, hlr_id: str) -> None:
    self._session.run("""
        MATCH (h:HLR {id: $hid})
        OPTIONAL MATCH (h)-[:DECOMPOSES_INTO]->(llr:LLR)
        OPTIONAL MATCH (llr)-[:VERIFIED_BY]->(vm:VerificationMethod)
        OPTIONAL MATCH (vm)-[:HAS_STEP]->(step:VerificationStep)
        OPTIONAL MATCH (step)-[:ENFORCES]->(c:Constraint)
        DETACH DELETE h, llr, vm, step, c
    """, {"hid": hlr_id})
```

### Cross-store resolution

When a Neo4j node has a property like `language_id: 3`, the consumer does a two-step lookup:

```python
def fetch_component_detail(component_id: str) -> dict:
    with get_neo4j().session() as neo:
        comp = ComponentRepository(neo).get_by_id(component_id)
    language = None
    if comp.language_id:
        with get_session() as sql:
            lang = sql.query(Language).filter_by(id=comp.language_id).first()
            language = repr(lang) if lang else None
    return {"name": comp.name, "language": language, ...}
```

The number of cross-store lookups is small: `language_id` and `manager_id` are the two cases.

### SQLAlchemy DB events removal

The `Language.after_insert` event that auto-creates an Environment component becomes an explicit call in the service layer. The `Ticket.after_insert/after_update` embedding event is removed along with embedding search.

## Structural Verification Model

### Constraint node types

Verification conditions and actions are replaced by reified `:Constraint` nodes with typed edges to `:Design` nodes.

**Comparison constraint** (precondition/postcondition):
```
(:Design "Calculator.display")-[:LEFT_OPERAND]->(:Constraint {operator: "EQUALS", value: "0"})
(:PreconditionStep {order: 0})-[:ENFORCES]->(:Constraint)
```

**Node-to-node comparison**:
```
(:Design "Foo.bar_count")-[:LEFT_OPERAND]->(:Constraint {operator: "LESS_THAN"})
(:Constraint)-[:RIGHT_OPERAND]->(:Design "Baz.max_items")
(:PreconditionStep {order: 0})-[:ENFORCES]->(:Constraint)
```

**Call constraint** (action):
```
(:Design "calculator")-[:CALLER]->(:Constraint {operator: "CALLS", args: "5"})
(:Constraint)-[:CALLEE]->(:Design "Calculator.press_button")
(:ActionStep {order: 0})-[:ENFORCES]->(:Constraint)
```

### Constraint operator vocabulary

| Operator | Type | LEFT_OPERAND | RIGHT_OPERAND | value |
|----------|------|-------------|---------------|-------|
| `EQUALS` | comparison | Design node | *(absent for literal)* | expected literal |
| `NOT_EQUALS` | comparison | Design node | *(absent for literal)* | expected literal |
| `LESS_THAN` | comparison | Design node | optional Design node | literal if no RIGHT_OPERAND |
| `GREATER_THAN` | comparison | Design node | optional Design node | literal if no RIGHT_OPERAND |
| `LESS_THAN_OR_EQUAL` | comparison | Design node | optional Design node | literal if no RIGHT_OPERAND |
| `GREATER_THAN_OR_EQUAL` | comparison | Design node | optional Design node | literal if no RIGHT_OPERAND |
| `IS_TRUE` | unary | Design node | *(absent)* | *(absent)* |
| `IS_FALSE` | unary | Design node | *(absent)* | *(absent)* |
| `IS_NULL` | unary | Design node | *(absent)* | *(absent)* |
| `IS_NOT_NULL` | unary | Design node | *(absent)* | *(absent)* |
| `CONTAINS` | comparison | Design node | *(absent for literal)* | expected substring |
| `CALLS` | action | *(use CALLER)* | *(use CALLEE)* | *(use CALLER/CALLEE)* |

### Unlocked queries

**Which verification methods constrain this class?**
```cypher
MATCH (d:Design {qualified_name: "Calculator"})-[:LEFT_OPERAND]->(c:Constraint)
      <-[:ENFORCES]-(step:VerificationStep)<-[:HAS_STEP]-(vm:VerificationMethod)
RETURN vm, step, c
```

**Which test covers the Calculator.display attribute?**
```cypher
MATCH (d:Design {qualified_name: "Calculator.display"})-[:LEFT_OPERAND]->(c:Constraint)
      <-[:ENFORCES]-(step)<-[:HAS_STEP]-(vm:VerificationMethod {method: "automated"})
RETURN vm.test_name
```

**Are there any unverified design nodes?**
```cypher
MATCH (d:Design)
WHERE NOT EXISTS {
    MATCH (d)-[:LEFT_OPERAND]->(:Constraint)<-[:ENFORCES]-(:VerificationStep)
}
RETURN d
```

### Agent output schema changes

The verification agent schema shifts from string references to qualified names:

```python
class ConditionSchema(BaseModel):
    subject_qualified_name: str    # was: member_qualified_name
    operator: str                  # "EQUALS", "LESS_THAN", etc.
    expected_value: str | None = None   # literal value
    object_qualified_name: str | None = None  # for node-to-node comparisons

class ActionSchema(BaseModel):
    caller_qualified_name: str | None = None  # the object making the call
    callee_qualified_name: str               # the method being called
    args: str = ""                              # literal arguments
    description: str = ""                       # free-text fallback
```

Actions with only `description` (no `callee_qualified_name`) create a `:Constraint {operator: "DESCRIPTION", description: "..."}` node with no operand edges, preserving the free-text fallback.

## Migration Strategy — Incremental Inversion (4 Phases)

### Phase 1: Design + Ontology

**What moves:** `OntologyNode`, `OntologyTriple`, `Predicate` → Neo4j-primary.

**What's eliminated:**
- SQLAlchemy models: `OntologyNode`, `OntologyTriple`, `Predicate`
- 4 M2M association tables: `high_level_requirements_nodes`, `high_level_requirements_triples`, `low_level_requirements_nodes`, `low_level_requirements_triples`
- Entire `backend/db/neo4j/sync.py` module
- All Neo4j sync calls in `persistence.py`, `orchestrator.py`

**New:**
- `DesignRepository` with merge/get/find/delete for design nodes and triples
- `:Design` unique constraint on `qualified_name`

**Cross-store bridge:** HLR and LLR are still in SQLite this phase. The M2M link tables are gone, so HLR↔Design links become Neo4j edges from stub `:HLR`/`:LLR` nodes (with `sqlite_id` property) to `:Design` nodes. This is temporary — Phase 2 makes HLR/LLR fully native.

**Simplification:** The requirement-tag enrichment (`graph_tags.py`) is rewritten to traverse Neo4j edges instead of querying SQLite M2M tables. The two-stage pipeline (Neo4j topology → SQLite enrichment) collapses into single Cypher queries starting from `:HLR`/`:LLR` stubs.

**Predicate handling:** Predicates become Cypher relationship types. The `PREDICATE_TO_REL_TYPE` mapping and `DEFAULT_PREDICATES` list move to a constants module. No more `Predicate.ensure_defaults()`.

**Files changed:**

| File | Action |
|------|--------|
| `backend/db/models/ontology.py` | Delete |
| `backend/db/models/associations.py` | Remove 4 M2M tables |
| `backend/db/models/__init__.py` | Remove OntologyNode/OntologyTriple/Predicate re-exports |
| `backend/db/neo4j/sync.py` | Delete entirely |
| `backend/db/neo4j/repositories/design.py` | New |
| `backend/db/neo4j/repositories/models/design.py` | New — DesignNode, DesignTriple Pydantic models |
| `backend/db/neo4j/connection.py` | Add `ensure_design_constraints()` |
| `backend/db/neo4j/queries/graph.py` | Rewrite to use repository + Cypher traversals |
| `backend/db/neo4j/queries/detail.py` | Simplify (no separate requirement lookup) |
| `backend/requirements/services/graph_tags.py` | Rewrite to use Cypher traversal |
| `backend/requirements/services/persistence.py` | Remove OntologyNode/OntologyTriple writes, call DesignRepository |
| `backend/pipeline/orchestrator.py` | Remove Neo4j sync phase; use DesignRepository directly |
| `frontend/data/ontology.py` | Call repository + Cypher enrichment instead of two-stage pipeline |
| `frontend/data/hlr.py` | Update to query via Neo4j edges |

### Phase 2: Requirements

**What moves:** `HighLevelRequirement`, `LowLevelRequirement` → Neo4j as full `:HLR`/`:LLR` nodes with `DECOMPOSES_INTO`, `TRACES_TO`, `AFFECTS_COMPONENT` edges.

**What's eliminated:**
- SQLAlchemy models: `HighLevelRequirement`, `LowLevelRequirement`, `TicketRequirement`
- SQLite tables: `high_level_requirements`, `low_level_requirements`, `low_level_requirements_components`, `ticket_requirements`

**New:**
- `RequirementRepository` with CRUD + design-trace linking

**Resolution:** The temporary `sqlite_id` property on `:HLR`/`:LLR` stubs from Phase 1 is replaced by native Neo4j IDs. The `TicketRequirement` association becomes a `REQUIRES` edge from `:Ticket` → `:LLR`.

**Agent code:** The `decompose_hlr`, `design_per_hlr`, and other agent workflows shift from opening SQLAlchemy sessions to opening Neo4j sessions and calling `RequirementRepository`. The agent logic itself (prompts, LLM calls) is unchanged — only the data access layer shifts.

**Files changed:**

| File | Action |
|------|--------|
| `backend/db/models/requirements.py` | Delete |
| `backend/db/models/associations.py` | Remove `low_level_requirements_components` |
| `backend/db/models/__init__.py` | Remove HLR/LLR re-exports |
| `backend/db/neo4j/repositories/requirement.py` | New |
| `backend/db/neo4j/repositories/models/requirement.py` | New — HLRNode, LLRNode |
| `backend/requirements/services/persistence.py` | Rewrite `persist_decomposition()` |
| `backend/requirements/services/graph_tags.py` | Simplify — no more `sqlite_id` intermediaries |
| `frontend/data/hlr.py` | Rewrite all CRUD to use RequirementRepository |
| `frontend/data/llr.py` | Rewrite all CRUD to use RequirementRepository |
| `frontend/data/requirements.py` | Rewrite for dashboard summaries |
| `backend/ticketing_agent/decompose/decompose_hlr.py` | Fetch HLR from repository |
| `backend/ticketing_agent/design/design_per_hlr.py` | Fetch HLR from repository |
| `backend/pipeline/orchestrator.py` | Update HLR/LLR queries |

### Phase 3: Verification Structural Redesign

**What moves:** `VerificationMethod`, `VerificationCondition`, `VerificationAction` → Neo4j with structural `:Constraint` nodes and typed operand edges.

**What's eliminated:**
- SQLAlchemy models: `VerificationMethod`, `VerificationCondition`, `VerificationAction`
- SQLite tables: `verification_methods`, `verification_conditions`, `verification_actions`
- String-based `member_qualified_name` resolution via `resolve_ontology_node()` longest-prefix matching
- `validate_verification_references()`, `augment_design_for_unresolved()` — replaced by Cypher-based structural references

**New:**
- `VerificationRepository` with `add_comparison_step()`, `add_call_step()`, `get_constraints_on_design_node()`
- `:VerificationStep` node label (replaces both Condition and Action)
- `:Constraint` node label with typed operand edges (`LEFT_OPERAND`, `RIGHT_OPERAND`, `CALLER`, `CALLEE`)

**Schema changes:** The agent output schema (`ConditionSchema`, `ActionSchema`) shifts from `member_qualified_name` strings to `subject_qualified_name` / `callee_qualified_name` references that resolve to real Design nodes.

**Closed-loop augmentation:** The current Python-based `augment_design_for_unresolved()` function becomes a Cypher query detecting steps whose operand edges point to non-existent Design nodes, with the repository creating the missing nodes directly in Neo4j.

**Files changed:**

| File | Action |
|------|--------|
| `backend/db/models/verification.py` | Delete |
| `backend/db/models/__init__.py` | Remove VerificationMethod/Condition/Action re-exports |
| `backend/db/neo4j/repositories/verification.py` | New |
| `backend/db/neo4j/repositories/models/verification.py` | New |
| `backend/requirements/schemas.py` | Update ConditionSchema/ActionSchema |
| `backend/requirements/services/persistence.py` | Rewrite `persist_verification()`, remove `resolve_ontology_node()`, `validate_verification_references()`, `augment_design_for_unresolved()`, `build_verification_context()` |
| `backend/ticketing_agent/verify/verify_llr.py` | Update to output new schema format |
| `backend/ticketing_agent/verify/verify_llr_prompt.py` | Update prompt to request qualified_name references |
| `backend/pipeline/orchestrator.py` | Remove VerificationMethod SQLAlchemy queries |
| `frontend/data/llr.py` | Rewrite to use VerificationRepository |

### Phase 4: Component Tree, Tasks, Tickets, Dependencies

**What moves:** All remaining graph-shaped data to Neo4j.

**What's eliminated:**
- SQLAlchemy models: `Component`, `Dependency`, `DependencyRecommendation`, `Task`, `TaskDesignNode`, `TaskVerification`, `Ticket`, `TicketAcceptanceCriteria`, `TicketFile`, `TicketReference`
- All remaining M2M tables: `dependency_components`, `tickets_components`, `tickets_languages`
- SQLAlchemy DB events module
- Embedding search: `backend/search/`, `backend/db/vec.py`, all `ticket_embeddings*` tables, `sqlite-vec` engine listener

**New:**
- `ComponentRepository`, `TaskRepository`, `TicketRepository`, `DependencyRepository`
- Component tree as `CONTAINS` edges
- Ticket relationships as native edges

**SQLite final state:**

| Table | Purpose |
|-------|---------|
| `project_meta` | Single-row project settings |
| `languages` | Language name + version |
| `build_systems` | FK to languages |
| `test_frameworks` | FK to languages |
| `dependency_managers` | FK to languages |

**Alembic:** Continues managing the remaining flat config tables. Graph-related migration files are preserved but no longer apply to active models.

**Files changed:**

| File | Action |
|------|--------|
| `backend/db/models/components.py` | Delete |
| `backend/db/models/tasks.py` | Delete |
| `backend/db/models/tickets.py` | Delete |
| `backend/db/models/associations.py` | Delete (all M2M tables gone) |
| `backend/db/models/__init__.py` | Slim to Language, BuildSystem, TestFramework, DependencyManager, ProjectMeta |
| `backend/db/events.py` | Delete (events moved to explicit service calls) |
| `backend/search/embeddings.py` | Delete |
| `backend/search/` | Delete directory |
| `backend/db/vec.py` | Delete |
| `backend/db/__init__.py` | Remove `sqlite-vec` event listener |
| `backend/db/neo4j/repositories/component.py` | New |
| `backend/db/neo4j/repositories/task.py` | New |
| `backend/db/neo4j/repositories/ticket.py` | New |
| `backend/db/neo4j/repositories/dependency.py` | New |
| `backend/db/neo4j/repositories/models/` | New Pydantic models per domain |
| `backend/pipeline/services.py` | Rewrite `persist_tasks()` to use TaskRepository |
| `backend/pipeline/orchestrator.py` | Final cleanup — no SQLAlchemy model imports |
| `frontend/data/components.py` | Rewrite to use ComponentRepository |
| `frontend/data/dependencies.py` | Rewrite to use DependencyRepository |
| `scripts/01_flush_db.py` through `scripts/05_generate_tasks.py` | Update to use repositories |
| `services/dependencies.py` | Remove standalone neo4j_service (handled by Neo4jConnection) |

## Non-goals

- Changes to the as-built codebase ingestion pipeline (Doxygen → Neo4j)
- Changes to the `codebase.sqlite3` read-only database
- OGM framework adoption (neomodel, py2neo)
- Audit log / event sourcing for graph mutations
- Changes to agent LLM prompt logic (only data access changes)