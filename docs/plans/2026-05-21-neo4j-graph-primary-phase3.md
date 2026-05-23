# Phase 3: Verification Structural Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote `VerificationMethod`, `VerificationCondition`, and `VerificationAction` from SQLite table rows to full Neo4j nodes (`:VerificationMethod`, `:Condition`, `:Action`) with typed operand edges (`LEFT_OPERAND`, `RIGHT_OPERAND`, `CALLER`, `CALLEE`). Eliminate `member_qualified_name` string-matching in favor of direct graph edges to `:Design` nodes. Remove the SQLAlchemy models and their tables.

**Architecture:** A new `VerificationRepository` owns all verification CRUD in Neo4j. Conditions and Actions become `:Condition`/`:Action` nodes linked to `:VerificationMethod` via `HAS_CONDITION`/`HAS_ACTION` edges, and linked to `:Design` nodes via `LEFT_OPERAND`, `RIGHT_OPERAND`, `CALLER`, `CALLEE` edges. `resolve_ontology_node()`, `validate_verification_references()`, and `augment_design_for_unresolved()` are replaced by Cypher-based structural resolution. The old `VerificationMethod`, `VerificationCondition`, `VerificationAction` SQLAlchemy models and their tables are deleted.

**Tech Stack:** Python 3.12+, Neo4j 5.x, Pydantic v2, SQLAlchemy (remaining models only)

---

## Current State (after Phase 2)

- `VerificationMethod` lives in SQLite with `low_level_requirement_id` as a plain integer (no FK)
- `VerificationCondition` and `VerificationAction` live in SQLite with `ontology_node_id` FK to `OntologyNode`
- `member_qualified_name` strings on conditions/actions are resolved via longest-prefix match against `OntologyNode.qualified_name`
- `build_verification_context()` queries both Neo4j `:Design` nodes and SQLAlchemy `OntologyNode` for context
- `resolve_ontology_node()` does longest-prefix match against SQLAlchemy `OntologyNode.qualified_name`
- `augment_design_for_unresolved()` creates new `OntologyNode`/`OntologyTriple` rows and syncs them to Neo4j
- `validate_verification_references()` checks `member_qualified_name` strings against a flat list
- `persist_verification()` writes `VerificationMethod` + `VerificationCondition` + `VerificationAction` to SQLite
- `TaskVerification.verification_method_id` has a FK to `verification_methods.id`
- `OntologyNode` and `OntologyTriple` still live in SQLite (Phase 4 territory)

## Target State

- `:VerificationMethod` nodes in Neo4j with properties `id`, `method`, `test_name`, `description`
- `(:LLR)-[:VERIFIES]->(:VerificationMethod)` edges replace `low_level_requirement_id`
- `:Condition` nodes in Neo4j with properties `id`, `phase` ("pre"/"post"), `order`, `operator`, `expected_value`
- `(:VerificationMethod)-[:HAS_CONDITION]->(:Condition)` edges
- `(:Condition)-[:LEFT_OPERAND]->(:Design)` edges replace `member_qualified_name` for conditions
- `(:Condition)-[:RIGHT_OPERAND]->(:Design)` edges for expected_value references (when pointing to a Design node)
- `:Action` nodes in Neo4j with properties `id`, `order`, `description`
- `(:VerificationMethod)-[:HAS_ACTION]->(:Action)` edges
- `(:Action)-[:CALLER]->(:Design)` edges (the object performing the action)
- `(:Action)-[:CALLEE]->(:Design)` edges (the method being invoked)
- `build_verification_context()` queries Neo4j only (no SQLAlchemy bridge fallback)
- `resolve_ontology_node()` removed — replaced by Cypher direct edge resolution
- `validate_verification_references()` replaced by Cypher: verify `:Design` nodes exist for all operand edges
- `augment_design_for_unresolved()` replaced by Cypher: auto-create missing `:Design` stubs
- `persist_verification()` uses `VerificationRepository` for all writes
- `VerificationMethod`, `VerificationCondition`, `VerificationAction` SQLAlchemy models deleted
- `verification_methods`, `verification_conditions`, `verification_actions` tables dropped
- `TaskVerification.verification_method_id` becomes a plain integer (no FK)

---

## File Impact Map

### New Files
- `backend/db/neo4j/repositories/verification.py` — `VerificationRepository` class
- `backend/db/neo4j/repositories/models/verification.py` — `VerificationMethodNode`, `ConditionNode`, `ActionNode` Pydantic models
- `scripts/migrate_phase3_verification_to_neo4j.py` — data migration script
- `tests/test_verification_repository.py` — unit + integration tests for `VerificationRepository`

### Modified Files (~20 files)
- `backend/db/neo4j/repositories/models/__init__.py` — add verification model exports
- `backend/db/neo4j/repositories/__init__.py` — add `VerificationRepository` export
- `backend/db/neo4j/__init__.py` — add `VerificationRepository` exports
- `backend/db/neo4j/connection.py` — add `:VerificationMethod`, `:Condition`, `:Action` uniqueness constraints in `ensure_requirement_constraints()`
- `backend/requirements/schemas.py` — add `subject_qualified_name`/`callee_qualified_name` fields; make `VERIFICATION_METHODS` self-contained (no import from deleted model)
- `backend/requirements/services/persistence.py` — rewrite `persist_verification()` for Neo4j; remove `resolve_ontology_node()`, `validate_verification_references()`, `augment_design_for_unresolved()`; update `build_verification_context()` to query Neo4j only
- `backend/ticketing_agent/verify/verify_llr.py` — remove SQLAlchemy VerificationMethod import, use VerificationRepository
- `backend/ticketing_agent/verify/verify_llr_prompt.py` — update prompt to request `subject_qualified_name` and `callee_qualified_name`
- `backend/ticketing_agent/mcp_server.py` — replace VerificationMethod queries with VerificationRepository
- `backend/pipeline/orchestrator.py` — replace VerificationMethod queries with VerificationRepository
- `backend/pipeline/services.py` — replace VerificationMethod queries with VerificationRepository
- `frontend/data/hlr.py` — replace VerificationMethod queries with VerificationRepository
- `frontend/data/llr.py` — replace VerificationMethod/Condition/Action queries with VerificationRepository
- `scripts/03_design_requirements.py` — replace verification queries
- `scripts/05_generate_tasks.py` — replace verification queries
- `scripts/import_fixtures.py` — skip verification table loading (now in Neo4j)
- `scripts/export_fixtures.py` — export verification data from Neo4j
- `scripts/01_flush_db.py` — add flushing of `:VerificationMethod`, `:Condition`, `:Action` nodes

### Deleted Files
- `backend/db/models/verification.py` — `VerificationMethod`, `VerificationCondition`, `VerificationAction` models

### Modified Files (model cleanup)
- `backend/db/models/__init__.py` — remove `VerificationMethod`, `VerificationCondition`, `VerificationAction`, `CONDITION_OPERATORS`, `VERIFICATION_METHODS` exports
- `backend/db/models/tasks.py` — remove FK on `TaskVerification.verification_method_id` (make plain integer)
- `alembic/versions/` — new migration to drop `verification_methods`, `verification_conditions`, `verification_actions` tables and remove FK

---

## Task 1: VerificationMethodNode/ConditionNode/ActionNode Pydantic Models

**Files:**
- Create: `backend/db/neo4j/repositories/models/verification.py`
- Modify: `backend/db/neo4j/repositories/models/__init__.py`

- [ ] **Step 1: Write failing test for verification models**

Create `tests/test_verification_neo4j_models.py`:

```python
"""Tests for VerificationMethod/Condition/Action Pydantic models for Neo4j."""
from backend.db.neo4j.repositories.models.verification import (
    VerificationMethodNode,
    ConditionNode,
    ActionNode,
)


def test_verification_method_node_defaults():
    vm = VerificationMethodNode(id=1, llr_id=10, method="automated")
    assert vm.id == 1
    assert vm.llr_id == 10
    assert vm.method == "automated"
    assert vm.test_name == ""
    assert vm.description == ""


def test_verification_method_node_full():
    vm = VerificationMethodNode(
        id=1, llr_id=10, method="review",
        test_name="test_addition", description="Verifies addition",
    )
    assert vm.test_name == "test_addition"
    assert vm.description == "Verifies addition"


def test_condition_node_defaults():
    c = ConditionNode(
        id=1, verification_method_id=5, phase="pre", order=0,
        operator="==", expected_value="0",
    )
    assert c.id == 1
    assert c.phase == "pre"
    assert c.operator == "=="


def test_condition_node_with_design_references():
    c = ConditionNode(
        id=1, verification_method_id=5, phase="pre", order=0,
        operator="==", expected_value="0",
        subject_qualified_name="Calculator::result",
    )
    assert c.subject_qualified_name == "Calculator::result"


def test_action_node_defaults():
    a = ActionNode(id=1, verification_method_id=5, order=1, description="Press + button")
    assert a.id == 1
    assert a.order == 1
    assert a.description == "Press + button"


def test_action_node_with_design_references():
    a = ActionNode(
        id=1, verification_method_id=5, order=1, description="Call add()",
        caller_qualified_name="Calculator",
        callee_qualified_name="Calculator::add",
    )
    assert a.caller_qualified_name == "Calculator"
    assert a.callee_qualified_name == "Calculator::add"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_verification_neo4j_models.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the models**

Create `backend/db/neo4j/repositories/models/verification.py`:

```python
"""Pydantic models for verification nodes in Neo4j.

Replaces SQLAlchemy VerificationMethod/VerificationCondition/VerificationAction.
Conditions and Actions are promoted from table rows to full nodes with
typed operand edges to :Design nodes.
"""

from __future__ import annotations

from pydantic import BaseModel


class VerificationMethodNode(BaseModel):
    """A verification method node in Neo4j.

    Stored as :VerificationMethod nodes linked to :LLR via :VERIFIES edges.
    """
    id: int
    llr_id: int
    method: str
    test_name: str = ""
    description: str = ""

    model_config = {"from_attributes": True}


class ConditionNode(BaseModel):
    """A pre/post-condition node in Neo4j.

    Stored as :Condition nodes linked to :VerificationMethod via :HAS_CONDITION edges.
    Linked to :Design nodes via :LEFT_OPERAND (subject) and :RIGHT_OPERAND (object) edges.
    """
    id: int
    verification_method_id: int
    phase: str  # "pre" or "post"
    order: int = 0
    subject_qualified_name: str = ""
    operator: str = "=="
    expected_value: str = ""

    model_config = {"from_attributes": True}


class ActionNode(BaseModel):
    """An action step node in Neo4j.

    Stored as :Action nodes linked to :VerificationMethod via :HAS_ACTION edges.
    Linked to :Design nodes via :CALLER and :CALLEE edges.
    """
    id: int
    verification_method_id: int
    order: int = 0
    description: str = ""
    caller_qualified_name: str = ""
    callee_qualified_name: str = ""

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Update models/__init__.py**

Add exports for the new models.

- [ ] **Step 5: Run tests to verify they pass**

- [ ] **Step 6: Commit**

```bash
git add backend/db/neo4j/repositories/models/verification.py backend/db/neo4j/repositories/models/__init__.py tests/test_verification_neo4j_models.py
git commit -m "feat(phase3): add VerificationMethodNode, ConditionNode, ActionNode Pydantic models"
```

---

## Task 2: VerificationRepository with Full CRUD and Constraints

**Files:**
- Create: `backend/db/neo4j/repositories/verification.py`
- Modify: `backend/db/neo4j/repositories/__init__.py`
- Modify: `backend/db/neo4j/connection.py` — add verification constraints

- [ ] **Step 1: Write failing test for VerificationRepository**

Create `tests/test_verification_repository.py` with integration tests for:
- `create_verification(llr_id, method, test_name, description)` → creates `:VerificationMethod` node with `(:LLR)-[:VERIFIES]->(:VerificationMethod)`
- `get_verification(vm_id)` → fetch single verification
- `list_verifications(llr_id)` → list all verifications for an LLR
- `update_verification(vm_id, **kwargs)` → update method/test_name/description
- `delete_verification(vm_id)` → cascade delete conditions and actions
- `add_condition(vm_id, phase, order, operator, expected_value, subject_qualified_name)` → creates `:Condition` node with `(:VerificationMethod)-[:HAS_CONDITION]->(:Condition)` and `(:Condition)-[:LEFT_OPERAND]->(:Design)`
- `add_action(vm_id, order, description, caller_qualified_name, callee_qualified_name)` → creates `:Action` node with `(:VerificationMethod)-[:HAS_ACTION]->(:Action)` and edges to `:Design`
- `augment_missing_design_nodes(qualified_names)` → creates missing `:Design` stubs for unresolved references
- `validate_references(qualified_names)` → checks which `:Design` nodes exist

- [ ] **Step 2: Run test to verify it fails**

- [ ] **Step 3: Implement VerificationRepository**

```python
class VerificationRepository:
    """CRUD operations for :VerificationMethod, :Condition, :Action nodes in Neo4j."""

    def __init__(self, session: Neo4jSession) -> None:
        self._session = session

    # --- VerificationMethod ---

    def create_verification(self, llr_id: int, method: str, test_name: str = "", description: str = "") -> VerificationMethodNode:
        """Create a :VerificationMethod node linked to :LLR via :VERIFIES edge."""

    def get_verification(self, vm_id: int) -> VerificationMethodNode | None:
        ...

    def list_verifications(self, llr_id: int) -> list[VerificationMethodNode]:
        ...

    def update_verification(self, vm_id: int, **kwargs) -> VerificationMethodNode | None:
        ...

    def delete_verification(self, vm_id: int) -> bool:
        """Cascade delete: removes all :Condition/:Action nodes and edges."""

    # --- Conditions ---

    def add_condition(self, vm_id: int, phase: str, order: int = 0,
                      operator: str = "==", expected_value: str = "",
                      subject_qualified_name: str = "",
                      object_qualified_name: str = "") -> ConditionNode:
        """Create :Condition node with :HAS_CONDITION edge and optional :LEFT_OPERAND/:RIGHT_OPERAND edges."""

    def list_conditions(self, vm_id: int, phase: str | None = None) -> list[ConditionNode]:
        ...

    # --- Actions ---

    def add_action(self, vm_id: int, order: int = 0, description: str = "",
                   caller_qualified_name: str = "",
                   callee_qualified_name: str = "") -> ActionNode:
        """Create :Action node with :HAS_ACTION edge and optional :CALLER/:CALLEE edges."""

    def list_actions(self, vm_id: int) -> list[ActionNode]:
        ...

    # --- Design node augmentation ---

    def augment_missing_design_nodes(self, qualified_names: list[str]) -> list[str]:
        """For each qualified_name that doesn't match a :Design node, create a stub.
        Returns list of qualified_names that were created."""

    def validate_references(self, qualified_names: list[str]) -> tuple[list[str], list[str]]:
        """Check which qualified_names exist as :Design nodes.
        Returns (resolved, unresolved) lists."""
```

Implementation details:
- `create_verification`: Creates `:VerificationMethod` node and `(:LLR {id: $llr_id})-[:VERIFIES]->(:VerificationMethod)` edge
- `add_condition`: Creates `:Condition` node, `(:VerificationMethod)-[:HAS_CONDITION]->(:Condition)` edge, and optionally `(:Condition)-[:LEFT_OPERAND]->(:Design)` and `(:Condition)-[:RIGHT_OPERAND]->(:Design)` edges
- `add_action`: Creates `:Action` node, `(:VerificationMethod)-[:HAS_ACTION]->(:Action)` edge, and optionally `(:Action)-[:CALLER]->(:Design)` and `(:Action)-[:CALLEE]->(:Design)` edges
- `augment_missing_design_nodes`: For each missing qualified name, creates a `:Design` stub node with `kind="member"`, `source_type="verification"` (marks it as auto-created)
- `delete_verification`: `MATCH (vm:VerificationMethod {id: $id}) DETACH DELETE vm` — cascade deletes conditions and actions via DETACH

- [ ] **Step 4: Add Neo4j constraints**

In `connection.py` `ensure_requirement_constraints()`, add:
```python
"CREATE CONSTRAINT verification_method_id IF NOT EXISTS FOR (n:VerificationMethod) REQUIRE n.id IS UNIQUE",
"CREATE CONSTRAINT condition_id IF NOT EXISTS FOR (n:Condition) REQUIRE n.id IS UNIQUE",
"CREATE CONSTRAINT action_id IF NOT EXISTS FOR (n:Action) REQUIRE n.id IS UNIQUE",
```

- [ ] **Step 5: Update repository __init__.py and neo4j/__init__.py**

- [ ] **Step 6: Run integration tests**

- [ ] **Step 7: Commit**

```bash
git add backend/db/neo4j/repositories/verification.py backend/db/neo4j/repositories/__init__.py backend/db/neo4j/__init__.py backend/db/neo4j/connection.py tests/test_verification_repository.py
git commit -m "feat(phase3): add VerificationRepository with full CRUD and constraints"
```

---

## Task 3: Update Schemas — Add Qualified Name References

**Files:**
- Modify: `backend/requirements/schemas.py`

Currently `VerificationConditionSchema` has `member_qualified_name` and `VerificationActionSchema` has `member_qualified_name`. We add parallel fields for structural edges:

- [ ] **Step 1: Update schemas.py**

```python
# Make VERIFICATION_METHODS self-contained (no import from deleted model file)
VERIFICATION_METHODS = ["automated", "review", "inspection"]

VerificationMethodType = Literal["automated", "review", "inspection"]

class VerificationConditionSchema(BaseModel):
    member_qualified_name: str  # legacy — kept for prompt/output compatibility
    subject_qualified_name: str = ""  # NEW — references :Design node via LEFT_OPERAND edge
    operator: str = "=="
    expected_value: str
    object_qualified_name: str = ""  # NEW — optional RIGHT_OPERAND reference

class VerificationActionSchema(BaseModel):
    description: str
    member_qualified_name: str = ""  # legacy — kept for backward compatibility
    caller_qualified_name: str = ""  # NEW — :CALLER edge target
    callee_qualified_name: str = ""  # NEW — :CALLEE edge target
```

The prompt/output format transition:
- `subject_qualified_name` is the canonical reference (used for `LEFT_OPERAND` edge)
- `member_qualified_name` is kept as fallback for prompts that haven't been updated yet
- When both are provided, `subject_qualified_name` takes precedence
- When only `member_qualified_name` is provided, it's used as both the edge target and the legacy string

- [ ] **Step 2: Update literal sync check**

Remove the import from `backend.db.models.verification` and use the local `VERIFICATION_METHODS` list.

- [ ] **Step 3: Run tests**

- [ ] **Step 4: Commit**

```bash
git add backend/requirements/schemas.py
git commit -m "feat(phase3): add subject/callee/object qualified name fields to verification schemas"
```

---

## Task 4: Rewrite persist_verification for Neo4j

**Files:**
- Modify: `backend/requirements/services/persistence.py`

This is the largest single change. `persist_verification()` currently writes to SQLite. It needs to write to Neo4j via `VerificationRepository`. The `resolve_ontology_node()`, `validate_verification_references()`, and `augment_design_for_unresolved()` functions are removed or replaced.

- [ ] **Step 1: Rewrite `persist_verification()`**

New signature:
```python
def persist_verification(
    neo4j_session: Neo4jSession,
    llr_id: int,
    verifications: list[VerificationSchema],
) -> VerificationResult:
```

Key changes:
- Takes `neo4j_session` instead of `sql_session`
- Uses `VerificationRepository` to create `:VerificationMethod`, `:Condition`, `:Action` nodes
- For each condition: `subject_qualified_name` → `LEFT_OPERAND` edge, `object_qualified_name` → `RIGHT_OPERAND` edge
- For each action: `caller_qualified_name` → `CALLER` edge, `callee_qualified_name` → `CALLEE` edge
- Falls back to `member_qualified_name` when `subject_qualified_name`/`caller_qualified_name` are empty (backward compat)
- Calls `augment_missing_design_nodes()` to create stubs for unresolved references
- No longer writes to SQLite at all

- [ ] **Step 2: Remove `resolve_ontology_node()`**

This function did longest-prefix matching against `OntologyNode.qualified_name` in SQLite. It's replaced by Cypher-based edge resolution in `VerificationRepository`.

- [ ] **Step 3: Remove `validate_verification_references()`**

Replaced by `VerificationRepository.validate_references()` which checks `:Design` nodes in Neo4j.

- [ ] **Step 4: Replace `augment_design_for_unresolved()`**

Replaced by `VerificationRepository.augment_missing_design_nodes()` which creates `:Design` stubs in Neo4j via Cypher. The old function created `OntologyNode`/`OntologyTriple` in SQLAlchemy and synced to Neo4j — now it's a single Cypher operation.

- [ ] **Step 5: Update `build_verification_context()`**

Remove the SQLAlchemy bridge fallback. The function now queries Neo4j only for design context used by the verification agent.

- [ ] **Step 6: Keep `persist_decomposition()` and `persist_design()` as-is**

These were updated in Phase 2 and don't need changes. `persist_decomposition()` still creates verification stubs — but now via `VerificationRepository` instead of SQLAlchemy.

**Wait** — actually `persist_decomposition()` currently writes verification stubs to SQLite. This needs updating:

- [ ] **Step 5b: Update `persist_decomposition()` verification stub creation**

Change the verification stub creation in `persist_decomposition()` from SQLAlchemy `VerificationMethod()` to `VerificationRepository.create_verification()`. The function already takes `neo4j_session` — just remove the `sql_session` parameter and the SQLAlchemy writes.

- [ ] **Step 7: Run tests**

- [ ] **Step 8: Commit**

```bash
git add backend/requirements/services/persistence.py
git commit -m "feat(phase3): rewrite persist_verification for Neo4j, remove resolve_ontology_node and validate_verification_references"
```

---

## Task 5: Update Agent Code — verify_llr, mcp_server, pipeline

**Files:**
- Modify: `backend/ticketing_agent/verify/verify_llr.py`
- Modify: `backend/ticketing_agent/verify/verify_llr_prompt.py`
- Modify: `backend/ticketing_agent/mcp_server.py`
- Modify: `backend/pipeline/orchestrator.py`
- Modify: `backend/pipeline/services.py`

- [ ] **Step 1: Update verify_llr_prompt.py**

Add guidance for the LLM to output `subject_qualified_name` (for conditions) and `caller_qualified_name`/`callee_qualified_name` (for actions). Keep `member_qualified_name` as an accepted fallback in the schema.

Update `SYSTEM_PROMPT` to instruct:
- Conditions: use `subject_qualified_name` for the left operand (the member being asserted about)
- Actions: use `caller_qualified_name` for the invoker and `callee_qualified_name` for the method being called
- `member_qualified_name` is still accepted but deprecated

- [ ] **Step 2: Update verify_llr.py**

- Remove `from backend.db.models import VerificationMethod`
- Use `VerificationRepository` to fetch existing verifications for an LLR
- Use `VerificationRepository.validate_references()` instead of `validate_verification_references()`
- Pass `neo4j_session` instead of `sql_session`

- [ ] **Step 3: Update mcp_server.py**

- Remove `VerificationMethod` import
- `list_requirements()`: use `VerificationRepository` to list verifications per LLR
- `save_verification()`: use `VerificationRepository` via `persist_verification()`
- `apply_remediation()`: use `VerificationRepository` to delete verifications when deleting LLRs; use `VerificationRepository` to create new verification stubs

- [ ] **Step 4: Update pipeline/orchestrator.py**

- Remove `VerificationMethod` import
- Phase 3 (verification): use `VerificationRepository` to list verifications per LLR
- Use `VerificationRepository` instead of SQLAlchemy queries for `_get_verification_dicts()`
- Use `persist_verification()` with `neo4j_session` instead of `sql_session`

- [ ] **Step 5: Update pipeline/services.py**

- Remove `VerificationMethod` import from `pipeline/services.py`
- `_find_verification_by_test_name()`: query `VerificationRepository` instead of SQLAlchemy
- `TaskVerification.verification_method_id` stays as a plain integer (no FK) — the migration in Task 9 will handle this

- [ ] **Step 6: Run tests**

- [ ] **Step 7: Commit**

```bash
git add backend/ticketing_agent/verify/verify_llr.py backend/ticketing_agent/verify/verify_llr_prompt.py backend/ticketing_agent/mcp_server.py backend/pipeline/orchestrator.py backend/pipeline/services.py
git commit -m "feat(phase3): update agent code and pipeline to use VerificationRepository"
```

---

## Task 6: Rewrite frontend/data/hlr.py and llr.py — Verification via Neo4j

**Files:**
- Modify: `frontend/data/hlr.py`
- Modify: `frontend/data/llr.py`

- [ ] **Step 1: Rewrite verification data access in hlr.py**

Replace `session.query(VerificationMethod)` calls with `VerificationRepository` calls:
- `fetch_requirements_data()`: get verification counts via `VerificationRepository`
- `decompose_hlr()`: remove `sql_session` from `persist_verification` call chain

- [ ] **Step 2: Rewrite verification data access in llr.py**

Replace all `VerificationMethod`/`VerificationCondition`/`VerificationAction` queries with `VerificationRepository`:
- `fetch_llr_detail()`: get verifications from Neo4j
- `_get_verification_detail()`: rewrite to use `VerificationRepository.list_verifications()` + `list_conditions()` + `list_actions()`
- Remove all SQLAlchemy verification imports

- [ ] **Step 3: Run import checks**

- [ ] **Step 4: Commit**

```bash
git add frontend/data/hlr.py frontend/data/llr.py
git commit -m "feat(phase3): rewrite frontend verification data access for Neo4j"
```

---

## Task 7: Drop Verification SQLAlchemy Models and Create Formatting Module

**Files:**
- Delete: `backend/db/models/verification.py`
- Create: `backend/requirements/verification_formatting.py` — replaces model `__repr__` and `to_prompt_text()` methods
- Modify: `backend/db/models/__init__.py` — remove verification model exports
- Modify: `backend/db/models/tasks.py` — remove `VerificationMethod` FK, make `verification_method_id` a plain integer

- [ ] **Step 1: Create verification_formatting.py**

Extract the `__repr__` and `to_prompt_text` methods from `VerificationMethod`, `VerificationCondition`, `VerificationAction`:

```python
"""Formatting helpers for verification data — replaces SQLAlchemy model __repr__
and to_prompt_text methods that were removed in Phase 3."""

from backend.db.neo4j.repositories.models.verification import (
    VerificationMethodNode,
    ConditionNode,
    ActionNode,
)

def format_verification(vm: VerificationMethodNode) -> str:
    """Format a VerificationMethodNode for display."""
    parts = [vm.method]
    if vm.test_name:
        parts.append(f"[{vm.test_name}]")
    return " - ".join(parts)

def format_verification_prompt(vm: VerificationMethodNode) -> str:
    """Format a VerificationMethodNode for LLM prompts."""
    parts = [vm.method]
    if vm.test_name:
        parts.append(vm.test_name)
    if vm.description:
        parts.append(vm.description)
    return " — ".join(parts)

def format_condition(c: ConditionNode) -> str:
    ...

def format_action(a: ActionNode) -> str:
    ...

VERIFICATION_METHODS = ["automated", "review", "inspection"]

CONDITION_OPERATORS = [
    ("==", "equals"), ("!=", "not equals"), ("<", "less than"),
    (">", "greater than"), ("<=", "less than or equal"), (">=", "greater than or equal"),
    ("is_true", "is true"), ("is_false", "is false"),
    ("contains", "contains"), ("not_null", "is not null"),
]
```

- [ ] **Step 2: Delete verification.py**

- [ ] **Step 3: Update models/__init__.py**

Remove all verification model exports. Import `VERIFICATION_METHODS` and `CONDITION_OPERATORS` from the new formatting module.

- [ ] **Step 4: Update tasks.py**

Change `TaskVerification.verification_method_id` from an FK to a plain integer:
```python
verification_method_id: Mapped[int] = mapped_column(Integer, nullable=False)
```
Remove the `VerificationMethod` import and relationship.

- [ ] **Step 5: Update all imports**

Search for any remaining imports of `VerificationMethod`, `VerificationCondition`, `VerificationAction` from `backend.db.models.verification` or `backend.db.models` and update them to either:
- Use the Neo4j repository models (`backend.db.neo4j.repositories.models.verification`)
- Use the formatting module (`backend.requirements.verification_formatting`)
- Use the repository directly (`VerificationRepository`)

- [ ] **Step 6: Run tests and fix failures**

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(phase3): drop SQLAlchemy verification models, create verification_formatting.py"
```

---

## Task 8: Alembic Migration to Drop Verification Tables and FK Constraints

**Files:**
- Create: `alembic/versions/<hash>_drop_verification_tables_and_fk_constraints.py`
- Modify: (none — just the new migration file)

- [ ] **Step 1: Create the migration**

```python
"""Drop verification tables and FK constraints.

Revision ID: <hash>
Replaces: verification_methods, verification_conditions, verification_actions
TaskVerification.verification_method_id FK removed (plain integer reference).
"""
from alembic import op
import sqlalchemy as sa

revision = "<hash>"
down_revision = "9a25f7d000a3"  # Phase 2 migration
branch_labels = None
depends_on = None

def upgrade():
    # Drop FK on task_verifications
    op.drop_constraint("fk_task_verifications_verification_method_id", "task_verifications", type_="foreignkey")
    # Drop verification tables (order matters — conditions/actions reference methods)
    op.drop_table("verification_actions")
    op.drop_table("verification_conditions")
    op.drop_table("verification_methods")

def downgrade():
    # Recreate tables (minimal — just the schema, no data)
    op.create_table("verification_methods",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("low_level_requirement_id", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(20), nullable=False),
        sa.Column("test_name", sa.String(300), server_default="", nullable=True),
        sa.Column("description", sa.Text(), server_default="", nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table("verification_conditions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("verification_id", sa.Integer(), nullable=False),
        sa.Column("phase", sa.String(4), nullable=False),
        sa.Column("order", sa.Integer(), server_default="0", nullable=True),
        sa.Column("ontology_node_id", sa.Integer(), nullable=True),
        sa.Column("ontology_node_qualified_name", sa.String(500), server_default="", nullable=True),
        sa.Column("member_qualified_name", sa.String(500), nullable=False),
        sa.Column("operator", sa.String(20), server_default="==", nullable=True),
        sa.Column("expected_value", sa.String(500), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["verification_id"], ["verification_methods.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ontology_node_id"], ["ontology_nodes.id"], ondelete="SET NULL"),
    )
    op.create_table("verification_actions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("verification_id", sa.Integer(), nullable=False),
        sa.Column("order", sa.Integer(), server_default="0", nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("ontology_node_id", sa.Integer(), nullable=True),
        sa.Column("ontology_node_qualified_name", sa.String(500), server_default="", nullable=True),
        sa.Column("member_qualified_name", sa.String(500), server_default="", nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["verification_id"], ["verification_methods.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ontology_node_id"], ["ontology_nodes.id"], ondelete="SET NULL"),
    )
```

- [ ] **Step 2: Run migration**

```bash
alembic upgrade head
```

- [ ] **Step 3: Verify tables are dropped**

```bash
python -c "from backend.db import init_db, get_session; init_db(); s = get_session(); print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/<hash>_drop_verification_tables_and_fk_constraints.py
git commit -m "feat(phase3): Alembic migration to drop verification tables and FK constraints"
```

---

## Task 9: Data Migration Script — Verification from SQLite to Neo4j

**Files:**
- Create: `scripts/migrate_phase3_verification_to_neo4j.py`

- [ ] **Step 1: Write the migration script**

The script should:
1. Read all `VerificationMethod`, `VerificationCondition`, `VerificationAction` rows from SQLite
2. For each `VerificationMethod`, create a `:VerificationMethod` node in Neo4j with `(:LLR {id: llr_id})-[:VERIFIES]->(:VerificationMethod)` edge
3. For each `VerificationCondition`, create a `:Condition` node with `(:VerificationMethod)-[:HAS_CONDITION]->(:Condition)` edge and `(:Condition)-[:LEFT_OPERAND]->(:Design)` edge (using `member_qualified_name`)
4. For each `VerificationAction`, create a `:Action` node with `(:VerificationMethod)-[:HAS_ACTION]->(:Action)` edge and `(:Action)-[:CALLEE]->(:Design)` edge (using `member_qualified_name`)
5. Preserve the SQLite `id` as the Neo4j `id` (like Phase 2 did for HLR/LLR)
6. Drop duplicate constraints if needed

- [ ] **Step 2: Test the migration script**

```bash
python scripts/migrate_phase3_verification_to_neo4j.py
```

- [ ] **Step 3: Commit**

```bash
git add scripts/migrate_phase3_verification_to_neo4j.py
git commit -m "feat(phase3): data migration script from SQLite verification tables to Neo4j"
```

---

## Task 10: Update Tests for Neo4j-Primary Verification

**Files:**
- Delete: `tests/test_verification_models.py` (tests SQLAlchemy models that no longer exist)
- Modify: `tests/test_persistence.py` — update persist_verification tests
- Modify: `tests/conftest.py` — remove verification-related fixtures
- Modify: other test files that reference verification models

- [ ] **Step 1: Audit all test files for verification model references**

```bash
grep -rn "VerificationMethod\|VerificationCondition\|VerificationAction" tests/
```

- [ ] **Step 2: Delete test_verification_models.py**

These tests validate SQLAlchemy model behavior that no longer exists. The replacement tests are in `test_verification_repository.py` (Task 2).

- [ ] **Step 3: Update test_persistence.py**

Update `persist_verification` tests to use `VerificationRepository` and Neo4j sessions.

- [ ] **Step 4: Update test_conftest_smoke.py and test_requirements_models.py if needed**

- [ ] **Step 5: Run all tests**

```bash
pytest tests/ -v --ignore=tests/integration
```

- [ ] **Step 6: Commit**

```bash
git add tests/
git commit -m "feat(phase3): update tests for Neo4j-primary verification"
```

---

## Task 11: Update Scripts — 03, 05, import, export, flush

**Files:**
- Modify: `scripts/03_design_requirements.py`
- Modify: `scripts/05_generate_tasks.py`
- Modify: `scripts/import_fixtures.py`
- Modify: `scripts/export_fixtures.py`
- Modify: `scripts/01_flush_db.py`

- [ ] **Step 1: Update 03_design_requirements.py**

Replace all `VerificationMethod`/`VerificationCondition`/`VerificationAction` imports and queries with `VerificationRepository` calls.

- [ ] **Step 2: Update 05_generate_tasks.py**

Replace verification queries with `VerificationRepository`. `persist_verification()` now takes `neo4j_session` instead of `sql_session`.

- [ ] **Step 3: Update import_fixtures.py**

Skip `verification_methods`, `verification_conditions`, `verification_actions` table loading (now in Neo4j). Add a Neo4j fixture section that creates `:VerificationMethod`, `:Condition`, `:Action` nodes.

- [ ] **Step 4: Update export_fixtures.py**

Export verification data from Neo4j instead of SQLite.

- [ ] **Step 5: Update 01_flush_db.py**

Add flushing of `:VerificationMethod`, `:Condition`, `:Action` nodes:
```python
session.run("MATCH (n:VerificationMethod) DETACH DELETE n")
session.run("MATCH (n:Condition) DETACH DELETE n")
session.run("MATCH (n:Action) DETACH DELETE n")
```

- [ ] **Step 6: Run syntax checks and commit**

```bash
git add scripts/
git commit -m "feat(phase3): update scripts for Neo4j-primary verification"
```

---

## Task 12: Integration Verification, Deprecation Notes, Cleanup

- [ ] **Step 1: Run full pipeline end-to-end**

```bash
python scripts/01_flush_db.py
python scripts/02_setup_project.py
python scripts/03_design_requirements.py
```

Verify: HLRs, LLRs, Verifications, Design nodes, and Tasks all created correctly.

- [ ] **Step 2: Run integration tests**

```bash
RUN_NEO4J_INTEGRATION=1 pytest tests/integration/ -v
```

- [ ] **Step 3: Search for remaining references to deleted models**

```bash
grep -rn "from backend.db.models.verification import\|from backend.db.models import.*VerificationMethod\|from backend.db.models import.*VerificationCondition\|from backend.db.models import.*VerificationAction" backend/ frontend/ scripts/ --include="*.py"
```

All should be gone. Any remaining references to `VerificationMethod` etc. in `backend/db/models/__init__.py` should use the neo4j repository or formatting module.

- [ ] **Step 4: Add deprecation notes**

Add comments in `backend/requirements/services/persistence.py`:
```python
# Phase 3: VerificationMethod, VerificationCondition, VerificationAction
# are now Neo4j nodes (:VerificationMethod, :Condition, :Action).
# Use VerificationRepository for all verification CRUD.
```

- [ ] **Step 5: Update this plan document**

Mark all tasks as complete.

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "feat(phase3): integration verification, deprecation notes, cleanup"
```

---

## Dependency Graph

```
Task 1 (Pydantic models)
  └── Task 2 (VerificationRepository) ── depends on Task 1
       ├── Task 3 (Schemas) ── can be done in parallel with Task 2
       └── Task 4 (persist_verification) ── depends on Tasks 2, 3
            ├── Task 5 (Agent code) ── depends on Tasks 2, 3, 4
            ├── Task 6 (Frontend) ── depends on Tasks 2, 4
            └── Task 7 (Drop models) ── depends on Tasks 4, 5, 6
                 └── Task 8 (Alembic) ── depends on Task 7
                      ├── Task 9 (Migration script) ── depends on Task 8
                      ├── Task 10 (Tests) ── depends on Tasks 1, 2, 4, 7
                      └── Task 11 (Scripts) ── depends on Tasks 4, 5
                           └── Task 12 (Integration) ── depends on all
```

## Key Decisions

- **`subject_qualified_name` alongside `member_qualified_name`**: Both fields coexist during transition. The repository uses `subject_qualified_name` when present, falling back to `member_qualified_name`. This allows gradual prompt updates.
- **`:Condition` and `:Action` as separate node labels**: Rather than storing conditions/actions as JSON blobs on `:VerificationMethod`, they get their own labels. This enables Cypher queries like "find all conditions referencing `Calculator::result`" and supports future graph-based verification analysis.
- **`LEFT_OPERAND`/`RIGHT_OPERAND`/`CALLER`/`CALLEE` edge types**: These replace `member_qualified_name` string matching. A condition `Calculator::status == true` becomes `(:Condition)-[:LEFT_OPERAND]->(:Design {qualified_name: "Calculator::status"})`. An action "Call Calculator::add(2,3)" becomes `(:Action)-[:CALLEE]->(:Design {qualified_name: "Calculator::add"})`.
- **`VerificationMethod.low_level_requirement_id` → `(:LLR)-[:VERIFIES]->(:VerificationMethod)`**: The FK column becomes an edge, consistent with the graph-primary pattern from Phase 2.
- **`TaskVerification.verification_method_id` stays as plain integer**: No FK constraint. Phase 4 may promote Tasks to Neo4j nodes.
- **`augment_design_for_unresolved()` replaced by Cypher**: Instead of creating `OntologyNode`+`OntologyTriple` rows in SQLAlchemy and syncing to Neo4j, we create `:Design` stubs directly in Neo4j with `source_type="verification"`.
- **`build_verification_context()` queries Neo4j only**: The SQLAlchemy bridge fallback (for `OntologyNode` rows not yet in Neo4j) is removed. All design context comes from `:Design` nodes.