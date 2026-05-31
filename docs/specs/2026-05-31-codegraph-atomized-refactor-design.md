# Spec: Refactor to Codegraph Atomized Node Types

**Date**: 2026-05-31
**Status**: Approved

## Goal

Agents work purely with in-memory codegraph atomized node types. Neo4j is only
touched by the repository layer for persistence. `CodebaseEdge` is removed
entirely.

## Background

The `codegraph` shared library was refactored to atomized neomodel node types
(`ClassNode`, `InterfaceNode`, `EnumNode`, `MethodNode`, `AttributeNode`, etc.)
replacing the generic `CompoundNode`/`MemberNode` pattern. The `codegraph.edges`
module and `codegraph.designs` package were removed. The ticketing system's
imports are now broken and must be updated.

## Non-Goals

- **No Neo4j schema migration** — existing `:Compound`, `:Member`, `:Namespace`
  labels stay; new atomized labels deferred
- **No frontend changes** — visualization and UI unchanged

## Design

### 1. Codegraph Node Model Extensions

Add missing relationship types to atomized node models so agents can express
all design intent through neomodel relationships without a separate edge type.

**ClassNode** gains:
- `aggregates = RelationshipTo('ClassNode', 'AGGREGATES')`
- `depends_on = RelationshipTo('ClassNode', 'DEPENDS_ON')`
- `references = RelationshipTo('ClassNode', 'REFERENCES')`
- `realizes = RelationshipTo('InterfaceNode', 'REALIZES')`
- `template_params = RelationshipTo('ClassNode', 'TEMPLATE_PARAM')`

**MethodNode** gains:
- `has_argument = RelationshipTo('ClassNode', 'HAS_ARGUMENT')`
- `returns = RelationshipTo('ClassNode', 'RETURNS')`
- `invokes = RelationshipTo('MethodNode', 'INVOKES')`

**InterfaceNode** gains:
- `generalizes = RelationshipTo('InterfaceNode', 'GENERALIZES')`
- `dependencies = RelationshipTo('ClassNode', 'DEPENDS_ON')`

### 2. Agent Changes

Agents become purely in-memory. Pipeline:
```
LLM → ClassDiagram (in-memory)
   → map_to_ontology → ClassDiagram (enriched, in-memory)
   → repository.save_design(diagram) → Neo4j
```

**`backend/ticketing_agent/design/design_oo.py`**:
- Update imports: `codegraph.designs` → `codegraph.diagram`
- No behavioral changes

**`backend/ticketing_agent/design/map_to_ontology.py`**:
- Remove all `CompoundNode`, `MemberNode`, `CodebaseEdge` usage
- Work purely with atomized types from `codegraph.models`
- Populate neomodel relationships directly (e.g., `class_node.depends_on.connect(other)`)
- Return enriched `ClassDiagram` instead of `DesignSchema`

**Other agent files** (design_hlr, design_verify, etc.):
- Update imports: `codegraph.designs` → `codegraph.diagram`
- No behavioral changes

### 3. Repository & Persistence Layer

All Neo4j interaction concentrated in `DesignRepository` at
`backend/db/neo4j/repositories/design.py`.

**Node operations**:
- `save_node(node)` → `node.save()` (neomodel)
- `get_node(qualified_name)` → `NodeClass.nodes.get_or_none(qn=...)`
- `find_nodes(...)` → `.filter()` across types
- `delete_node(qualified_name)` → `node.delete()`

**Relationship operations**:
- `merge_triple()` → **removed** (handled by neomodel `.connect()`)
- `get_compound_graph()` → neomodel traversal (`.methods.all()`, etc.)
- `get_ontology_graph()` → neomodel traversal

**What stays raw Cypher**: bulk operations (`clear_design_graph`),
aggregate queries (`get_graph_stats`).

### 4. Imports to Fix (Complete List)

All files importing from deleted codegraph modules:

| Current Import | Replace With |
|---|---|
| `from codegraph.designs import ClassDiagram` | `from codegraph.diagram import ClassDiagram` |
| `from codegraph.edges import CodebaseEdge` | Remove — use node relationships |
| `from codegraph.models import CompoundNode` | `from codegraph.models import ClassNode, InterfaceNode, EnumNode, ...` |
| `from codegraph.models import MemberNode` | `from codegraph.models import MethodNode, AttributeNode, ...` |

### 5. Files to Remove

- `backend/db/neo4j/models/edges.py` — only re-exported CodebaseEdge
- `backend/db/neo4j/models/nodes/compound.py` — only added ticketing extensions to CompoundNode
- `backend/db/neo4j/models/nodes/member.py` — only added model_config to MemberNode

Ticketing-specific fields (`specialization`, `is_intercomponent`, `implementation_status`, `test_file`) that were on the CompoundNode subclass need a new home — stored as plain properties on the atomized nodes during save, or via a separate metadata mechanism. Decision: store as regular properties on the atomized neomodel nodes at save time (neomodel allows extra properties not declared in the model).

### 6. Label Compatibility

No Neo4j schema migration. Existing `:Compound`, `:Member`, `:Namespace` labels
stay. To keep neomodel writing to these labels, each atomized codegraph model
must override its `__label__` class attribute:

```python
class ClassNode(_CompoundMixin):
    __label__ = "Compound"
```

Similarly for all atomized types:
- Compounds (ClassNode, InterfaceNode, EnumNode, UnionNode, ModuleNode) → `__label__ = "Compound"`
- Members (MethodNode, AttributeNode, EnumValueNode, FunctionNode, DefineNode) → `__label__ = "Member"`
- NamespaceNode → `__label__ = "Namespace"` (already correct)

This is a temporary bridge. When schema migration happens in a future phase, the
`__label__` overrides are simply removed.

## Verification

- All existing tests pass after import fixes
- `python -c "from backend.db.neo4j.models.edges import CodebaseEdge"` no longer works (by design)
- Agent scripts (`scripts/03_design_requirements.py`) complete successfully
- Frontend ontology graph renders correctly
