# Move graph.py to codegraph library

**Date:** 2026-05-30  
**Status:** approved

## Summary

Relocate `GraphEdge`, `CompoundGraph`, `NamespaceGraph`, and `OntologyGraph` dataclasses from `backend/db/neo4j/models/graph.py` into the external `codegraph` library as `codegraph/graph/` (a package with `__init__.py`).

## Motivation

These typed graph containers are structural wrappers around the codegraph node models (`CompoundNode`, `MemberNode`, `NamespaceNode`). They have no ticketing-system-specific logic and belong alongside the node models in the shared `codegraph` library.

## Design

### New file

**`src/codegraph/graph/__init__.py`** — contents of current `backend/db/neo4j/models/graph.py` with one change: the import becomes `from codegraph.nodes import CompoundNode, MemberNode, NamespaceNode`.

### Updated files

| File | Change |
|---|---|
| `src/codegraph/__init__.py` | Add `from codegraph.graph import GraphEdge, CompoundGraph, NamespaceGraph, OntologyGraph` and export them in `__all__` |
| `backend/graph/__init__.py` | Change import from `backend.db.neo4j.models.graph` → `codegraph.graph` |
| `backend/db/neo4j/repositories/design.py` | Same import change |

### Deleted files

| File | Reason |
|---|---|
| `backend/db/neo4j/models/graph.py` | Moved to codegraph |

### Compatibility

The ticketing_system's `CompoundNode` and `MemberNode` are subclasses of codegraph's base node models. The graph containers reference the base types, so subclass instances work without any changes. `NamespaceNode` is already re-exported directly from codegraph.

No runtime behavior changes — pure import relocation.

## Test plan

- Run existing test suite: `pytest`
- Verify imports resolve correctly in both ticketing_system and codegraph
