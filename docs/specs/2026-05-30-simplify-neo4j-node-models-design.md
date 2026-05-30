# Simplify Neo4j Node Models

**Date:** 2026-05-30
**Status:** designed

## Dependencies

The `codegraph` library is a separate local repo at `../codegraph` (installed as editable with
`pip install -e`). Changes to the base types must be made and committed there first before the
ticketing system can consume the new `component_id` field.

## Motivation

The ticketing system's Neo4j node models (`CompoundNode`, `MemberNode`, `NamespaceNode`) currently
add fields on top of the `codegraph` library base types. Some additions are redundant with base
fields, some are semantically misplaced, and one type (`NamespaceNode`) is essentially a thin wrapper
adding a single dubious field. This spec simplifies all three.

## Changes to the codegraph library

Add `component_id: int | None = None` to the base types in `codegraph`:

- `CompoundNode`
- `MemberNode`
- `NamespaceNode`

This is a non-breaking addition — all callers that don't use it will ignore it.

## Changes to the ticketing system

### 1. CompoundNode (`backend/db/neo4j/models/nodes/compound.py`)

**Remove:** `component_id` (moved to base), `source_file` (use base `file_path`).

**Keep:** `specialization`, `is_intercomponent`, `implementation_status`, `test_file`.

```python
class CompoundNode(BaseCompoundNode):
    model_config = {"from_attributes": True, "extra": "ignore"}

    specialization: str = ""
    is_intercomponent: bool = False
    implementation_status: Literal[
        "designed", "scaffolded", "tested", "implemented", "verified"
    ] = "designed"
    test_file: str = ""
```

### 2. MemberNode (`backend/db/neo4j/models/nodes/member.py`)

**Remove:** `is_abstract`, `is_final` (semantically wrong on members; never actually set to True),
`component_id` (moved to base).

Becomes an empty subclass with only config:

```python
class MemberNode(BaseMemberNode):
    model_config = {"from_attributes": True, "extra": "ignore"}
```

### 3. NamespaceNode (`backend/db/neo4j/models/nodes/namespace.py`)

**Remove:** entire file. Use `codegraph.nodes.NamespaceNode` directly.

The two fields it added (`file_path`, `component_id`) are handled by:
- `component_id` moves to the base `NamespaceNode`
- `file_path` on a namespace is semantically dubious (namespaces span multiple files) — dropped

### 4. Sync and query code

Replace all `source_file` references with `file_path`:
- `backend/db/neo4j/sync.py`
- `backend/db/neo4j/repositories/design.py`
- `backend/requirements/services/persistence.py`

### 5. Persistence layer

- Stop setting `source_file` on compounds — use `file_path` from base
- Stop setting `is_abstract` and `is_final` on members
- Stop setting `file_path` on namespaces
- Stop creating `NamespaceNode` — use `codegraph.nodes.NamespaceNode` directly

### 6. Imports

- `backend/db/neo4j/models/nodes/__init__.py`: remove `NamespaceNode` import, export
- `backend/db/neo4j/models/graph.py`: import `NamespaceNode` from `codegraph.nodes`
- Any other file importing `NamespaceNode` from the local models package

### 7. `map_to_ontology.py`

No changes needed — it uses `OntologyNodeSchema`, not the Neo4j models directly.

## What stays the same

- All edge types, predicates, and graph structure in Neo4j
- All query logic and repositories (beyond field name changes)
- `OntologyNodeSchema` and `OntologyTripleSchema` in the codebase schemas
- The `codegraph` library's `FileNode`, `ParameterNode`, and `CodebaseEdge`
