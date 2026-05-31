# Codegraph Atomized Node Refactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the ticketing system to use codegraph's new atomized node types
(ClassNode, MethodNode, etc.) instead of the deleted generic types (CompoundNode,
MemberNode, CodebaseEdge). Agents work in-memory; Neo4j is only touched by the
repository layer.

**Architecture:** All imports from deleted codegraph modules (`codegraph.designs`,
`codegraph.edges`) are replaced with imports from `codegraph.diagram` and
`codegraph.models`. `CodebaseEdge` is removed — relationships are expressed
through neomodel `RelationshipTo` fields on node models. The `map_to_ontology.py`
agent populates these relationships instead of building separate triple objects.
Repository layer uses neomodel `.connect()` / `.save()` instead of raw Cypher
MERGE for relationships.

**Tech Stack:** Python 3.12, neomodel, codegraph (external package), Pydantic

---

## File Structure

### Codegraph library (external repo — `/Users/danielnewman/dev/codegraph`)

| File | Change |
|---|---|
| `src/codegraph/models/compound.py` | Add relationship fields (depends_on, references, realizes, template_params to ClassNode; generalizes to InterfaceNode) |
| `src/codegraph/models/member.py` | Add relationship fields (has_argument, returns, invokes to MethodNode) |
| `src/codegraph/diagram.py` | Add `associations` field to ClassDiagram for LLM output shape |

### Ticketing system — files to DELETE

| File | Reason |
|---|---|
| `backend/db/neo4j/models/edges.py` | Only re-exported CodebaseEdge (deleted in codegraph) |
| `backend/db/neo4j/models/nodes/compound.py` | Only added ticketing extensions to CompoundNode (deleted in codegraph) |
| `backend/db/neo4j/models/nodes/member.py` | Only added model_config to MemberNode (deleted in codegraph) |
| `backend/design_data/models.py` | Shim re-exporting from codegraph.designs (deleted) |

### Ticketing system — files to MODIFY

| File | What changes |
|---|---|
| `backend/db/neo4j/models/nodes/__init__.py` | Remove CompoundNode/MemberNode, export atomized types |
| `backend/db/neo4j/models/__init__.py` | Remove edges import, export atomized types |
| `backend/db/neo4j/repositories/__init__.py` | Remove CodebaseEdge export |
| `backend/db/neo4j/repositories/design.py` | Major: replace CompoundNode/MemberNode dispatch with atomized types, remove merge_triple, use neomodel traversal for compound/ontology graph |
| `backend/db/neo4j/__init__.py` | Remove CodebaseEdge/CompoundNode/MemberNode exports |
| `backend/ticketing_agent/design/map_to_ontology.py` | Major: replace CompoundNode/MemberNode/CodebaseEdge with atomized types + neomodel relationship population. Rename CodebaseEdge -> remove. Use .connect() |
| `backend/codebase/schemas.py` | Remove CodebaseEdge import, change DesignSchema.triples type |
| `backend/requirements/services/persistence.py` | Update node dispatch to use atomized types, remove merge_triple usage |
| `backend/design_data/__init__.py` | Update re-exports source |
| `backend/design_data/transforms.py` | Update imports, ClassDiagram shape |
| `backend/design_data/repository.py` | Update imports |
| `backend/pipeline/orchestrator.py` | Update imports |
| `scripts/03_design_requirements.py` | Update imports |
| `frontend/data/ontology.py` | Update node type references |
| `frontend/data/hlr.py` | Update imports |
| `backend/ticketing_agent/mcp_server.py` | Update DesignSchema shape usage |
| `services/dependencies.py` | Update imports if needed |

### Test files to MODIFY

| File | What changes |
|---|---|
| `tests/test_codebase_schemas.py` | Remove CodebaseEdge tests, update imports |
| `tests/test_map_to_ontology.py` | Major rewrite for new mapper output |
| `tests/test_persistence.py` | Remove CodebaseEdge usage |
| `tests/test_design_data_models.py` | Update imports |
| `tests/test_design_data_transforms.py` | Update imports |
| `tests/test_oo_design_schema.py` | Update imports |
| `tests/test_design_oo_tools.py` | Update imports |
| `tests/test_design_oo_retry.py` | Update imports |
| `tests/test_container_mechanism.py` | Update imports |
| `tests/test_mechanism_and_references.py` | Update imports |
| `tests/test_combined_handlers.py` | Update imports |
| `tests/test_integration_combined_loop.py` | Update imports |
| `tests/unit/test_graph_models.py` | Update imports |
| `tests/test_graph_tags.py` | Update imports |
| `tests/test_graph_cross_layer.py` | Update imports |
| `tests/test_codebase_graph_primitives.py` | Update imports |
| `tests/test_design_repository.py` | Update imports |
| `tests/test_requirement_repository.py` | Update imports |
| `tests/test_verification_repository.py` | Update imports |
| `tests/test_container_lookup.py` | Update imports |
| `tests/test_design_data_repository.py` | Update imports |
| `tests/integration/test_design_repository_graph.py` | Update imports |
| `tests/integration/test_ontology_graph_rendering.py` | Update imports |
| `tests/conftest.py` | Update imports |

---

### Task 1: Extend codegraph node models with relationship fields

**Files:**
- Modify: `/Users/danielnewman/dev/codegraph/src/codegraph/models/compound.py`
- Modify: `/Users/danielnewman/dev/codegraph/src/codegraph/models/member.py`
- Modify: `/Users/danielnewman/dev/codegraph/src/codegraph/diagram.py`

- [ ] **Step 1: Add relationship fields to ClassNode**

In `/Users/danielnewman/dev/codegraph/src/codegraph/models/compound.py`, add these relationships to `ClassNode`:

```python
# Add to ClassNode's existing relationships section:
depends_on = RelationshipTo('ClassNode', 'DEPENDS_ON')
references = RelationshipTo('ClassNode', 'REFERENCES')
realizes = RelationshipTo('InterfaceNode', 'REALIZES')
template_params = RelationshipTo('ClassNode', 'TEMPLATE_PARAM')

# RelationshipFrom for incoming edges:
referred_by = RelationshipFrom('ClassNode', 'REFERENCES')
depended_on_by = RelationshipFrom('ClassNode', 'DEPENDS_ON')
```

Needs `RelationshipFrom` imported at top.

- [ ] **Step 2: Add relationship fields to InterfaceNode**

In the same file, add to `InterfaceNode`:

```python
# Add to InterfaceNode:
generalizes = RelationshipTo('InterfaceNode', 'GENERALIZES')
dependencies = RelationshipTo('ClassNode', 'DEPENDS_ON')
```

- [ ] **Step 3: Add relationship fields to MethodNode**

In `/Users/danielnewman/dev/codegraph/src/codegraph/models/member.py`, add to `MethodNode`:

```python
# Add to MethodNode's relationships:
has_argument = RelationshipTo('ClassNode', 'HAS_ARGUMENT')
returns = RelationshipTo('ClassNode', 'RETURNS')
invokes = RelationshipTo('MethodNode', 'INVOKES')
```

Needs `RelationshipTo` imported at top (already imported).

- [ ] **Step 4: Add associations field to ClassDiagram**

In `/Users/danielnewman/dev/codegraph/src/codegraph/diagram.py`, add an `associations` field for LLM output:

```python
from dataclasses import dataclass, field

@dataclass
class Association:
    """A relationship between two named entities in a ClassDiagram.
    
    This is the LLM-facing shape — not a neomodel node.
    """
    subject: str
    predicate: str
    object: str
    requirement_ids: list[str] = field(default_factory=list)
    mechanism: str = ""
    position: int | None = None
    name: str = ""
    display_name: str = ""


@dataclass
class ClassDiagram:
    # ... existing fields ...
    
    associations: list[Association] = field(default_factory=list)
```

- [ ] **Step 5: Add __label__ overrides for old-label compatibility**

Per spec section 6, each atomized model must write to the old Neo4j labels
(`:Compound`, `:Member`) until a future schema migration. Add `__label__`
overrides:

In `compound.py`, add at bottom of each class after the class body:

```python
# Old-label compatibility (remove after schema migration)
ClassNode.__label__ = "Compound"
InterfaceNode.__label__ = "Compound"
EnumNode.__label__ = "Compound"
UnionNode.__label__ = "Compound"
ModuleNode.__label__ = "Compound"
```

In `member.py`:

```python
# Old-label compatibility (remove after schema migration)
MethodNode.__label__ = "Member"
AttributeNode.__label__ = "Member"
EnumValueNode.__label__ = "Member"
FunctionNode.__label__ = "Member"
DefineNode.__label__ = "Member"
```

(Note: `NamespaceNode.__label__` is already `"Namespace"` — no change needed.)

- [ ] **Step 6: Verify codegraph imports work**

```bash
cd /Users/danielnewman/dev/codegraph && python -c "
from codegraph.models import ClassNode, InterfaceNode, MethodNode
from codegraph import ClassDiagram, Association
print('All imports OK')
"
```

Expected: "All imports OK"

- [ ] **Step 7: Commit codegraph changes**

```bash
cd /Users/danielnewman/dev/codegraph
git add -A
git commit -m "feat: add relationship fields and Association to atomized models"
```

---

### Task 2: Create atomized node shim module in ticketing system

**Files:**
- Modify: `backend/db/neo4j/models/nodes/__init__.py`
- Modify: `backend/db/neo4j/models/__init__.py`
- Delete: `backend/db/neo4j/models/edges.py`
- Delete: `backend/db/neo4j/models/nodes/compound.py`
- Delete: `backend/db/neo4j/models/nodes/member.py`

- [ ] **Step 1: Rewrite nodes __init__.py**

Replace `backend/db/neo4j/models/nodes/__init__.py`:

```python
"""Codebase graph node models — atomized types from codegraph.

All node types now come from codegraph.models directly. The old
CompoundNode/MemberNode subclasses are removed.
"""

from codegraph.models import (
    ClassNode, InterfaceNode, EnumNode, UnionNode, ModuleNode,
    MethodNode, AttributeNode, EnumValueNode, FunctionNode, DefineNode,
    NamespaceNode,
)

__all__ = [
    "ClassNode", "InterfaceNode", "EnumNode", "UnionNode", "ModuleNode",
    "MethodNode", "AttributeNode", "EnumValueNode", "FunctionNode", "DefineNode",
    "NamespaceNode",
]
```

- [ ] **Step 2: Rewrite models __init__.py**

Replace `backend/db/neo4j/models/__init__.py`:

```python
"""Neo4j codebase graph models — atomized types and constants."""

from backend.db.neo4j.models.nodes import (
    ClassNode, InterfaceNode, EnumNode, UnionNode, ModuleNode,
    MethodNode, AttributeNode, EnumValueNode, FunctionNode, DefineNode,
    NamespaceNode,
)
from codegraph.constants import PREDICATES

__all__ = [
    "ClassNode", "InterfaceNode", "EnumNode", "UnionNode", "ModuleNode",
    "MethodNode", "AttributeNode", "EnumValueNode", "FunctionNode", "DefineNode",
    "NamespaceNode",
    "PREDICATES",
]
```

- [ ] **Step 3: Delete old files**

```bash
rm backend/db/neo4j/models/edges.py
rm backend/db/neo4j/models/nodes/compound.py
rm backend/db/neo4j/models/nodes/member.py
```

- [ ] **Step 4: Verify module imports**

```bash
cd /Users/danielnewman/dev/ticketing_system && python -c "
from backend.db.neo4j.models.nodes import ClassNode, MethodNode, NamespaceNode
print('nodes __init__ OK')
from backend.db.neo4j.models import ClassNode, MethodNode
print('models __init__ OK')
"
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: replace CompoundNode/MemberNode shims with atomized type re-exports"
```

---

### Task 3: Update DesignSchema and codebase schemas

**Files:**
- Modify: `backend/codebase/schemas.py`

- [ ] **Step 1: Rewrite DesignSchema to use atomized types**

Replace `backend/codebase/schemas.py`:

```python
"""Ticketing-system schemas — requirement linkage and design aggregation.

LLM shapes and OO design models live in codegraph.
TypeRef moved to codegraph.type_parser.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from codegraph.constants import NODE_KIND_KEYS, VISIBILITY_CHOICES
from codegraph.diagram import ClassDiagram
from backend.requirements.schemas import VerificationSchema

NodeKind = Literal[tuple(NODE_KIND_KEYS)]
Visibility = Literal[tuple(k for k, _ in VISIBILITY_CHOICES)]
SourceType = Literal["compound", "member", "namespace"]


class RequirementTripleLinkSchema(BaseModel):
    """Maps a requirement to an ontology entity by qualified name."""
    requirement_type: Literal["hlr", "llr"]
    requirement_id: int
    subject_qualified_name: str = ""
    predicate: str = ""
    object_qualified_name: str = ""


class DesignSchema(BaseModel):
    """Stage 2 output: ontology design with nodes, associations, and requirement links.

    nodes are codegraph atomized neomodel types (ClassNode, MethodNode, etc.).
    associations replace the old CodebaseEdge triples.
    """
    nodes: list  # codegraph atomized neomodel types
    associations: list[dict] = []  # {subject, predicate, object, mechanism, position, name, display_name}
    requirement_links: list[RequirementTripleLinkSchema] = []


class DesignAndVerificationSchema(BaseModel):
    """Combined output for the design+verify tool loop."""
    oo_design: ClassDiagram
    verifications: dict[int, list[VerificationSchema]] = {}
```

- [ ] **Step 2: Verify imports work**

```bash
cd /Users/danielnewman/dev/ticketing_system && python -c "
from backend.codebase.schemas import DesignSchema, RequirementTripleLinkSchema
print('OK')
"
```

- [ ] **Step 3: Commit**

```bash
git add backend/codebase/schemas.py
git commit -m "refactor: replace CodebaseEdge with dict-based associations in DesignSchema"
```

---

### Task 4: Fix all simple import changes (non-agent, non-repo files)

**Files:** 15+ files with simple import fixes

- [ ] **Step 1: Fix all `from codegraph.designs import` → `from codegraph.diagram import ClassDiagram`**

Files to fix (replace `from codegraph.designs import ClassDiagram` with `from codegraph.diagram import ClassDiagram`):

```bash
# Agent files
sed -i '' 's/from codegraph\.designs import ClassDiagram/from codegraph.diagram import ClassDiagram/' \
  backend/ticketing_agent/design/design_oo_prompt.py \
  backend/ticketing_agent/design/design_per_hlr.py \
  backend/ticketing_agent/design/design_oo.py \
  backend/ticketing_agent/design/design_oo_tools.py \
  backend/ticketing_agent/design/design_hlr.py \
  backend/ticketing_agent/tools/design_verify/dispatcher.py \
  backend/ticketing_agent/tools/design_verify/draft_design.py \
  backend/ticketing_agent/tools/design_verify/validate_design.py \
  backend/ticketing_agent/tools/helpers/design_validation.py \
  backend/ticketing_agent/design_verify/combined_loop.py \
  backend/codebase/schemas.py \
  backend/pipeline/orchestrator.py

# Scripts
sed -i '' 's/from codegraph\.designs import ClassDiagram/from codegraph.diagram import ClassDiagram/' \
  scripts/03_design_requirements.py

# backend/design_data (these import more than just ClassDiagram)
```

- [ ] **Step 2: Fix backend/design_data/models.py (delete the shim)**

```bash
rm backend/design_data/models.py
```

Then update `backend/design_data/__init__.py` to import from codegraph directly:

```python
"""Design data module — typed read models and query API for class diagram data."""

from codegraph.diagram import ClassDiagram, Association
from codegraph.models import (
    ClassNode, InterfaceNode, EnumNode, UnionNode, ModuleNode,
    MethodNode, AttributeNode, EnumValueNode, FunctionNode, DefineNode,
)
from backend.design_data.repository import DesignDataRepository
from backend.design_data.transforms import (
    class_diagram_from_oo_design,
    oo_design_from_class_diagram,
)

__all__ = [
    "Association",
    "AttributeNode",
    "ClassDiagram",
    "ClassNode",
    "DesignDataRepository",
    "EnumNode",
    "EnumValueNode",
    "InterfaceNode",
    "MethodNode",
    "ModuleNode",
    "UnionNode",
    "class_diagram_from_oo_design",
    "oo_design_from_class_diagram",
]
```

- [ ] **Step 3: Fix backend/design_data/transforms.py**

Update imports at top:

```python
"""Transform functions for ClassDiagram enrichment."""

from codegraph.diagram import ClassDiagram
# (rest stays the same — already uses ClassDiagram)
```

- [ ] **Step 4: Fix backend/design_data/repository.py**

Update the imports at top to use codegraph directly instead of the shim.

- [ ] **Step 5: Fix remaining agent imports that use codegraph.designs for non-ClassDiagram types**

Files that import `ClassNode`, `Association`, etc. from `codegraph.designs`:

```bash
# Fix test files
# tests/test_design_oo_retry.py: from codegraph.designs import ClassDiagram, ClassNode, Association
# → from codegraph.diagram import ClassDiagram, Association
# → from codegraph.models import ClassNode
```

- [ ] **Step 6: Fix test_oo_design_schema.py**

```
tests/test_oo_design_schema.py:14:from codegraph.designs import (
```
→ `from codegraph.diagram import ClassDiagram` + `from codegraph.models import ClassNode, InterfaceNode, ...`

- [ ] **Step 7: Fix test_codebase_schemas.py**

Remove `from codegraph.edges import CodebaseEdge` line.
Remove `from codegraph.models import CompoundNode` line.
Remove `TestCodebaseEdge` class and all its methods.
Update other imports from `codegraph.designs`.

- [ ] **Step 8: Fix test_map_to_ontology.py**

Replace all `from codegraph.designs import ...` with `from codegraph.diagram` + `from codegraph.models`.

- [ ] **Step 9: Fix test_design_data_models.py and test_design_data_transforms.py**

Update imports from `backend.design_data.models` → `codegraph.models` + `codegraph.diagram`.

- [ ] **Step 10: Fix test_container_mechanism.py**

```
from codegraph.designs import ClassDiagram, Association, ClassNode
```
→ `from codegraph.diagram import ClassDiagram, Association` + `from codegraph.models import ClassNode`

- [ ] **Step 11: Fix test_mechanism_and_references.py**

Update imports similarly.

- [ ] **Step 12: Fix test_combined_handlers.py, test_integration_combined_loop.py**

Simple import fixes.

- [ ] **Step 13: Fix all remaining test imports**

Search for any remaining `codegraph.designs` or `codegraph.edges` imports in tests:

```bash
grep -rn "from codegraph\.designs\|from codegraph\.edges" tests/ --include="*.py"
```

Fix each one.

- [ ] **Step 14: Fix backend/db/neo4j/repositories/__init__.py**

Remove `CodebaseEdge` from imports and `__all__`.

- [ ] **Step 15: Fix backend/db/neo4j/__init__.py**

Remove `CodebaseEdge`, `CompoundNode`, `MemberNode` from imports and `__all__`.

- [ ] **Step 16: Fix scripts/ and frontend/ imports**

```bash
grep -rn "from codegraph\.designs\|from codegraph\.edges\|CompoundNode\|MemberNode\|CodebaseEdge" \
  scripts/ frontend/ services/ nicegui_app.py --include="*.py"
```

Fix each remaining reference.

- [ ] **Step 17: Verify all basic imports work**

```bash
cd /Users/danielnewman/dev/ticketing_system && python -c "
# Verify key modules import without errors
from backend.db.neo4j.models import ClassNode, MethodNode, NamespaceNode
from backend.codebase.schemas import DesignSchema
from backend.design_data import ClassDiagram, ClassNode
print('All critical imports OK')
"
```

- [ ] **Step 18: Commit**

```bash
git add -A
git commit -m "refactor: update all imports from codegraph.designs/edges to codegraph.diagram/models"
```

---

### Task 5: Refactor map_to_ontology.py to use atomized types

**Files:**
- Modify: `backend/ticketing_agent/design/map_to_ontology.py`

This is the core refactoring. The function `map_oo_to_ontology()` currently:
1. Creates `CompoundNode`/`MemberNode`/`NamespaceNode` objects
2. Creates `CodebaseEdge` objects for triples
3. Returns `DesignSchema(nodes=..., triples=..., links=...)`

After refactoring it:
1. Creates atomized neomodel node objects (`ClassNode`, `MethodNode`, etc.)
2. Uses `.connect()` to create relationships directly on nodes
3. Returns `DesignSchema(nodes=..., associations=..., links=...)`

- [ ] **Step 1: Replace imports at top**

Remove:
```python
from codegraph.models import CompoundNode, MemberNode, NamespaceNode
from codegraph.edges import CodebaseEdge
```

Replace with:
```python
from codegraph.models import (
    ClassNode, InterfaceNode, EnumNode, MethodNode, AttributeNode,
    EnumValueNode, NamespaceNode,
)
```

Also update `from codegraph.designs import ClassDiagram` → `from codegraph.diagram import ClassDiagram`

- [ ] **Step 2: Rewrite _add_node() helper**

Currently dispatches to `CompoundNode`/`MemberNode`/`NamespaceNode`. Replace with atomized dispatch:

```python
def _add_node(kind: str, name: str, qualified_name: str, is_intercomponent=False, **kwargs):
    if qualified_name in node_index:
        return qualified_name
    node_index[qualified_name] = len(nodes)
    
    source_type = kwargs.pop("source_type", "")
    layer = "dependency" if source_type == "dependency" else "design"
    description = kwargs.pop("description", "")
    visibility = kwargs.pop("visibility", "")
    
    common = dict(
        qualified_name=qualified_name,
        name=name,
        kind=kind,
        layer=layer,
        brief_description=description,
    )
    
    if kind == "class":
        node = ClassNode(**common, **kwargs)
    elif kind == "interface":
        node = InterfaceNode(**common, is_abstract=True, **kwargs)
    elif kind == "enum":
        node = EnumNode(**common, **kwargs)
    elif kind == "method":
        node = MethodNode(**common, protection=visibility, **kwargs)
    elif kind in ("variable", "attribute"):
        node = AttributeNode(
            qualified_name=qualified_name, name=name, kind="variable",
            layer=layer, brief_description=description,
            protection=visibility, **kwargs,
        )
    elif kind == "enumvalue":
        node = EnumValueNode(**common, **kwargs)
    elif kind in ("module", "namespace", "package"):
        node = NamespaceNode(**common, **kwargs)
    else:
        raise ValueError(f"Unknown kind: {kind}")
    
    nodes.append(node)
    return qualified_name
```

- [ ] **Step 3: Rewrite _add_triple() → _add_association()**

Remove the `triples: list[CodebaseEdge]` variable and `_add_triple()` function.
Replace with `associations: list[dict]` and `_add_association()`:

```python
associations: list[dict] = []

def _add_association(subject_qname, predicate, object_qname, mechanism="", position=None, name="", display_name=""):
    idx = len(associations)
    assoc = {"subject": subject_qname, "predicate": predicate, "object": object_qname}
    if mechanism:
        assoc["mechanism"] = mechanism
    if position is not None:
        assoc["position"] = position
    if name:
        assoc["name"] = name
    if display_name:
        assoc["display_name"] = display_name
    associations.append(assoc)
    return idx
```

- [ ] **Step 4: Update all _add_triple() calls to _add_association()**

Replace every `_add_triple(...)` call with `_add_association(...)` throughout the function.

- [ ] **Step 5: Update the _add_type_argument_edge() function**

Replace:
```python
def _add_type_argument_edge(template_qname, arg_qname, position, display_name):
    t = CodebaseEdge(...)
    triples.append(t)
    return len(triples) - 1
```
With:
```python
def _add_type_argument_edge(template_qname, arg_qname, position, display_name):
    return _add_association(
        template_qname, "type_argument", arg_qname,
        position=position, display_name=display_name,
    )
```

- [ ] **Step 6: Update _resolve_type_refs to call _add_association**

Instead of `_add_triple(subject_qname, predicate, resolved_name)`, use:
```python
_add_association(subject_qname, predicate, resolved_name)
```

- [ ] **Step 7: Update return value**

Change:
```python
return DesignSchema(
    nodes=nodes,
    triples=triples,
    requirement_links=links,
)
```
To:
```python
return DesignSchema(
    nodes=nodes,
    associations=associations,
    requirement_links=links,
)
```

- [ ] **Step 8: Update persistence_service to read associations instead of triples**

In the `persist_design()` function and throughout `backend/requirements/services/persistence.py`:

Replace `design.triples` → `design.associations`
Replace `triple_data.subject_qualified_name` → `assoc["subject"]`
Replace `triple_data.predicate` → `assoc["predicate"]`
Replace `triple_data.object_qualified_name` → `assoc["object"]`

Also update `_ontology_node_to_model()` to dispatch to atomized types (mirroring the dispatch in map_to_ontology above).

- [ ] **Step 9: Update requirement link resolution**

Where the persistence code iterates `design.triples` by index, now iterate `design.associations` by index.

- [ ] **Step 10: Update _add_node in persistence_service for dependency stubs**

In the mechanism fallback code, replace `CompoundNode` with `ClassNode`:

```python
node = ClassNode(
    qualified_name=dep_qname,
    name=mechanism_name,
    kind="class",
    layer="dependency",
    brief_description=f"Standard library: {dep_qname}",
)
```

And similarly for `_resolve_ref` where it creates dependency stubs.

- [ ] **Step 11: Verify map_to_ontology module imports**

```bash
cd /Users/danielnewman/dev/ticketing_system && python -c "
from backend.ticketing_agent.design.map_to_ontology import map_oo_to_ontology
print('map_to_ontology imports OK')
"
```

- [ ] **Step 12: Commit**

```bash
git add -A
git commit -m "refactor: rewrite map_to_ontology to use atomized types and associations"
```

---

### Task 6: Refactor DesignRepository to use neomodel atomized types

**Files:**
- Modify: `backend/db/neo4j/repositories/design.py`

- [ ] **Step 1: Update imports**

Replace:
```python
from backend.db.neo4j.models.edges import CodebaseEdge
from backend.db.neo4j.models.nodes import CompoundNode, MemberNode, NamespaceNode
```
With:
```python
from codegraph.models import (
    ClassNode, InterfaceNode, EnumNode, UnionNode, ModuleNode,
    MethodNode, AttributeNode, EnumValueNode, FunctionNode, DefineNode,
    NamespaceNode,
)
```

Replace `NodeModel = Union[CompoundNode, MemberNode, NamespaceNode]` with:
```python
NodeModel = (
    ClassNode | InterfaceNode | EnumNode | UnionNode | ModuleNode |
    MethodNode | AttributeNode | EnumValueNode | FunctionNode | DefineNode |
    NamespaceNode
)
```

- [ ] **Step 2: Update _determine_node_type() dispatch**

Replace the kind-based dispatch with atomized type dispatch:

```python
def _determine_node_type(kind: str) -> type[NodeModel]:
    """Return the correct model class for a given kind value."""
    if kind in ("class", "struct", "template_class", "abstract_class"):
        return ClassNode
    elif kind == "interface":
        return InterfaceNode
    elif kind in ("enum", "enum_class"):
        return EnumNode
    elif kind == "union":
        return UnionNode
    elif kind in ("module", "namespace", "package"):
        return NamespaceNode
    elif kind == "method":
        return MethodNode
    elif kind in ("variable", "attribute"):
        return AttributeNode
    elif kind == "enumvalue":
        return EnumValueNode
    elif kind == "function":
        return FunctionNode
    elif kind == "define":
        return DefineNode
    else:
        log.debug("Unknown kind %r — defaulting to ClassNode", kind)
        return ClassNode
```

- [ ] **Step 3: Update _determine_label()**

Map kinds to Neo4j labels:

```python
def _determine_label(kind: str) -> str:
    if kind in ("class", "struct", "template_class", "abstract_class",
                "interface", "enum", "enum_class", "union"):
        return "Compound"
    elif kind in ("method", "variable", "attribute", "enumvalue",
                   "function", "define"):
        return "Member"
    elif kind in ("module", "namespace", "package"):
        return "Namespace"
    else:
        return "Compound"
```

- [ ] **Step 4: Update merge_node()**

Replace `isinstance(node, CompoundNode)` checks with atomized type checks, or use the existing `_determine_label(node.kind)`:

```python
def merge_node(self, node: NodeModel) -> NodeModel:
    kind = getattr(node, 'kind', '')
    label = _determine_label(kind)
    
    props = {k: v for k, v in node.__properties__.items()
             if v is not None and v != ""}
    layer = props.pop("layer", "design")
    
    cypher = f"""
    MERGE (n:{label} {{qualified_name: $qualified_name}})
    SET n += $props, n.layer = $layer
    """
    self._session.run(cypher, {
        "qualified_name": node.qualified_name,
        "props": props,
        "layer": layer,
    })
    return node
```

- [ ] **Step 5: Update get_compound_graph()**

Replace `CompoundNode(**c_props)` with atomized type dispatch. Replace `MemberNode(**dict(m))` with atomized type dispatch.

- [ ] **Step 6: Update get_ontology_graph()**

Same atomized type replacements.

- [ ] **Step 7: Update get_dependency_links()**

Same atomized type replacements.

- [ ] **Step 8: Remove merge_triple()**

Delete the `merge_triple()` method entirely — relationships are now handled via neomodel `.connect()` in the persistence layer.

- [ ] **Step 9: Update _hydrate_graph_edge() → keep as-is**

This already creates `GraphEdge` which is for visualization, not domain modeling. It stays.

- [ ] **Step 10: Add save_associations() method**

New method to create relationships from the association dicts stored in DesignSchema:

```python
def save_associations(
    self,
    associations: list[dict],
    qname_to_node: dict[str, NodeModel],
) -> int:
    """Create Neo4j relationships from association dicts using neomodel .connect().
    
    Returns count of relationships created.
    """
    created = 0
    for assoc in associations:
        subj_qn = assoc["subject"]
        obj_qn = assoc["object"]
        predicate = assoc["predicate"]
        
        subj = qname_to_node.get(subj_qn)
        obj = qname_to_node.get(obj_qn)
        if not subj or not obj:
            continue
        
        rel_type = PREDICATE_TO_REL_TYPE.get(predicate, "").upper()
        if not rel_type:
            continue
        
        mechanism = assoc.get("mechanism", "")
        position = assoc.get("position")
        name = assoc.get("name", "")
        display_name = assoc.get("display_name", "")
        
        # Create the relationship via Cypher MERGE (neomodel .connect()
        # doesn't support extra properties easily)
        cypher = f"""
        MATCH (s {{qualified_name: $subj_qn}})
        MATCH (t {{qualified_name: $obj_qn}})
        MERGE (s)-[r:{rel_type}]->(t)
        """
        params = {"subj_qn": subj_qn, "obj_qn": obj_qn}
        set_clauses = []
        if mechanism:
            set_clauses.append("r.mechanism = $mechanism")
            params["mechanism"] = mechanism
        if position is not None:
            set_clauses.append("r.position = $position")
            params["position"] = position
        if name:
            set_clauses.append("r.name = $name")
            params["name"] = name
        if display_name:
            set_clauses.append("r.display_name = $display_name")
            params["display_name"] = display_name
        
        if set_clauses:
            cypher += "\nSET " + ", ".join(set_clauses)
        
        self._session.run(cypher, params)
        created += 1
    
    return created
```

- [ ] **Step 11: Verify repository imports**

```bash
cd /Users/danielnewman/dev/ticketing_system && python -c "
from backend.db.neo4j.repositories.design import DesignRepository
print('DesignRepository imports OK')
"
```

- [ ] **Step 12: Commit**

```bash
git add -A
git commit -m "refactor: DesignRepository uses atomized types, remove merge_triple"
```

---

### Task 7: Update persistence service to use atomized types and new DesignSchema

**Files:**
- Modify: `backend/requirements/services/persistence.py`

- [ ] **Step 1: Update _ontology_node_to_model()**

Dispatch to atomized types instead of `CompoundNode`/`MemberNode`/`NamespaceNode`:

```python
def _ontology_node_to_model(node_data) -> NodeModel:
    """Convert node data to the correct atomized neomodel type based on kind."""
    kind = node_data.kind
    shared = dict(
        qualified_name=node_data.qualified_name,
        name=node_data.name,
        kind=kind,
        layer=_map_source_type_to_layer(...),
        brief_description=node_data.description or "",
        refid=getattr(node_data, 'refid', ''),
        source=getattr(node_data, 'source', ''),
    )
    
    if kind in ("class", "struct", "template_class", "abstract_class"):
        return ClassNode(
            **shared,
            specialization=node_data.specialization or "",
            component_id=node_data.component_id,
            is_abstract=kind == "abstract_class",
        )
    elif kind == "interface":
        return InterfaceNode(**shared, is_abstract=True, component_id=node_data.component_id)
    elif kind in ("enum", "enum_class"):
        return EnumNode(**shared, component_id=node_data.component_id)
    elif kind == "union":
        return UnionNode(**shared, component_id=node_data.component_id)
    elif kind == "method":
        return MethodNode(
            **shared,
            protection=node_data.visibility or "",
            type_signature=node_data.type_signature or "",
            argsstring=node_data.argsstring or "",
            is_static=node_data.is_static or False,
            is_const=node_data.is_const or False,
            is_virtual=node_data.is_virtual or False,
            component_id=node_data.component_id,
        )
    elif kind in ("variable", "attribute"):
        return AttributeNode(
            **shared,
            protection=node_data.visibility or "",
            type_signature=node_data.type_signature or "",
            is_static=node_data.is_static or False,
            is_const=node_data.is_const or False,
        )
    elif kind == "enumvalue":
        return EnumValueNode(**shared)
    elif kind == "function":
        return FunctionNode(
            **shared,
            type_signature=node_data.type_signature or "",
            argsstring=node_data.argsstring or "",
        )
    elif kind == "define":
        return DefineNode(**shared)
    elif kind in ("module", "namespace", "package"):
        return NamespaceNode(**shared, component_id=node_data.component_id)
    else:
        return ClassNode(**shared, component_id=node_data.component_id)
```

- [ ] **Step 2: Update persist_design() to use design.associations**

Replace the triples processing block with:

```python
# --- Associations (was Triples) ---
created = repo.save_associations(
    design.associations,
    qname_to_node=qname_to_node,
)
result.triples_created = created
```

- [ ] **Step 3: Update DesignResult field name**

Keep `triples_created` field name for backward compatibility, or rename to `associations_created` if safe.

- [ ] **Step 4: Update requirement link resolution**

Replace `design.triples[link.triple_index]` with `design.associations[link.triple_index]`.

- [ ] **Step 5: Update imports**

Remove:
```python
from backend.db.neo4j.models.nodes import CompoundNode, MemberNode
```
Add:
```python
from codegraph.models import (
    ClassNode, InterfaceNode, EnumNode, MethodNode, AttributeNode,
    EnumValueNode, NamespaceNode,
)
```

- [ ] **Step 6: Commit**

```bash
git add backend/requirements/services/persistence.py
git commit -m "refactor: persistence service uses atomized types and associations"
```

---

### Task 8: Fix MCP server and remaining backend files

**Files:**
- Modify: `backend/ticketing_agent/mcp_server.py`
- Modify: `backend/db/neo4j/__init__.py`
- Modify: `backend/db/neo4j/repositories/__init__.py`

- [ ] **Step 1: Update mcp_server.py**

In `save_ontology_design()`, replace `triples` parameter with `associations`:

```python
@mcp.tool()
def save_ontology_design(
    nodes: list[dict],
    associations: list[dict],
    requirement_links: list[dict] | None = None,
) -> str:
    """Save ontology nodes, associations, and requirement links to Neo4j."""
    with get_neo4j().session() as neo4j_session:
        design = DesignSchema.model_validate(
            {
                "nodes": nodes,
                "associations": associations,
                "requirement_links": requirement_links or [],
            }
        )
        result = persist_design(design, neo4j_session)
        return json.dumps({
            "nodes_created": result.nodes_created,
            "associations_created": result.triples_created,
            "links_applied": result.links_applied,
        })
```

- [ ] **Step 2: Update backend/db/neo4j/__init__.py**

Remove `CodebaseEdge`, `CompoundNode`, `MemberNode` from imports and `__all__`.

- [ ] **Step 3: Update backend/db/neo4j/repositories/__init__.py**

Remove `CodebaseEdge`, `CompoundNode`, `MemberNode` from imports and `__all__`.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: update MCP server and Neo4j module exports for atomized types"
```

---

### Task 9: Fix tests

**Files:** ~20 test files

- [ ] **Step 1: Fix test_codebase_schemas.py**

Remove the entire `TestCodebaseEdge` class and all `CodebaseEdge` imports.
Update `from codegraph.designs import` → `from codegraph.diagram import`.

- [ ] **Step 2: Fix test_map_to_ontology.py**

Replace all `from codegraph.designs import` with `from codegraph.diagram` + `from codegraph.models`.
Update test assertions that check for `CodebaseEdge` objects or `CompoundNode` types.
Replace `design.triples` references with `design.associations`.

- [ ] **Step 3: Fix test_persistence.py**

Remove `CodebaseEdge` imports and usage. Replace `CompoundNode`/`MemberNode` with atomized types.

- [ ] **Step 4: Fix test_container_mechanism.py and test_mechanism_and_references.py**

Update imports:
```python
from codegraph.diagram import ClassDiagram, Association
from codegraph.models import ClassNode
```

- [ ] **Step 5: Fix remaining test files**

Run grep to find all remaining `CodebaseEdge` / `CompoundNode` / `MemberNode` references in tests and fix:

```bash
cd /Users/danielnewman/dev/ticketing_system && grep -rn "CodebaseEdge\|CompoundNode\|MemberNode" tests/ --include="*.py" | grep -v "CompoundGraph\|_MEMBER_KIND\|#\|test_compound_node\|MemberNodeType"
```

Fix each reference.

- [ ] **Step 6: Run the test suite**

```bash
cd /Users/danielnewman/dev/ticketing_system && python -m pytest tests/ -x --tb=short 2>&1 | head -100
```

Expected: Tests pass (or have expected failures related to Neo4j not running locally)

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "test: update all tests for atomized types and associations"
```

---

### Task 10: End-to-end verification

- [ ] **Step 1: Run all tests**

```bash
cd /Users/danielnewman/dev/ticketing_system && python -m pytest tests/ -v 2>&1 | tail -50
```

- [ ] **Step 2: Verify agent pipeline imports**

```bash
cd /Users/danielnewman/dev/ticketing_system && python -c "
# Verify the full agent pipeline is importable
from backend.ticketing_agent.design.design_oo import design_oo
from backend.ticketing_agent.design.map_to_ontology import map_oo_to_ontology
from backend.requirements.services.persistence import persist_design
from backend.codebase.schemas import DesignSchema
print('Full agent pipeline imports OK')
"
```

- [ ] **Step 3: Verify no remaining references to deleted modules**

```bash
cd /Users/danielnewman/dev/ticketing_system && grep -rn "codegraph\.edges\|codegraph\.designs" backend/ tests/ scripts/ --include="*.py" | grep -v __pycache__
```

Expected: No output (all references migrated)

- [ ] **Step 4: Verify no remaining CodebaseEdge references**

```bash
cd /Users/danielnewman/dev/ticketing_system && grep -rn "CodebaseEdge" backend/ tests/ --include="*.py" | grep -v __pycache__
```

Expected: No output

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore: final verification — all imports migrated, tests pass"
```
