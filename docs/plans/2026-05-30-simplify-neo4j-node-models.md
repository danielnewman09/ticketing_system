# Simplify Neo4j Node Models — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove redundant and semantically-misplaced fields from ticketing-system Neo4j node models by moving `component_id` to codegraph base types and dropping dead fields.

**Architecture:** Add `component_id` to codegraph base types; drop `source_file` (use base `file_path`), `is_abstract`/`is_final` on members, and entire `NamespaceNode` ticketing wrapper. Rename Neo4j property `source_file` → `file_path` in Cypher queries.

**Tech Stack:** Python 3.12+, Pydantic, Neo4j, codegraph library (editable install at `../codegraph`)

---

### Task 1: Add `component_id` to codegraph base types

**Files:**
- Modify: `../codegraph/src/codegraph/nodes/compound_node.py`
- Modify: `../codegraph/src/codegraph/nodes/member_node.py`
- Modify: `../codegraph/src/codegraph/nodes/namespace_node.py`

- [ ] **Step 1: Add `component_id` to CompoundNode**

In `../codegraph/src/codegraph/nodes/compound_node.py`, add after `layer`:

```python
    #: Foreign key to the owning ticketing-system component (set by
    #: external consumers such as the ticketing agent). ``None`` when
    #: not yet assigned.
    component_id: int | None = None
```

- [ ] **Step 2: Add `component_id` to MemberNode**

In `../codegraph/src/codegraph/nodes/member_node.py`, add after `layer`:

```python
    #: Foreign key to the owning ticketing-system component. ``None``
    #: when not yet assigned.
    component_id: int | None = None
```

- [ ] **Step 3: Add `component_id` to NamespaceNode**

In `../codegraph/src/codegraph/nodes/namespace_node.py`, add after `layer`:

```python
    #: Foreign key to the owning ticketing-system component. ``None``
    #: when not yet assigned.
    component_id: int | None = None
```

- [ ] **Step 4: Verify codegraph tests pass**

Run: `cd /Users/danielnewman/dev/codegraph && python -m pytest -v`
Expected: PASS

- [ ] **Step 5: Commit codegraph changes**

```bash
cd /Users/danielnewman/dev/codegraph
git add src/codegraph/nodes/compound_node.py src/codegraph/nodes/member_node.py src/codegraph/nodes/namespace_node.py
git commit -m "feat: add component_id to CompoundNode, MemberNode, NamespaceNode"
```

---

### Task 2: Simplify ticketing CompoundNode

**File:**
- Modify: `backend/db/neo4j/models/nodes/compound.py`

- [ ] **Step 1: Remove `component_id` and `source_file`**

Replace the file content:

```python
"""CompoundNode — :Compound in Neo4j.

Compounds are top-level containers — classes, structs, interfaces, enums, unions —
that own members and participate in associations. The `kind` field refines
the specific type. The `layer` field indicates origin: 'design' (agent-created),
'as-built' (parsed from code), or 'dependency' (external library).

Ticketing-system extensions (specialization, implementation_status, etc.) are
added on top of the ``codegraph`` base model.
"""

from __future__ import annotations

from typing import Literal

from codegraph.nodes import CompoundNode as BaseCompoundNode


class CompoundNode(BaseCompoundNode):
    """A compound entity in the codebase graph (:Compound in Neo4j).

    Inherits core fields from ``codegraph.nodes.CompoundNode`` (including
    ``component_id`` and ``file_path``) and adds ticketing-system-specific
    fields for project context and implementation tracking.
    """

    model_config = {"from_attributes": True, "extra": "ignore"}

    # --- Ticketing-system extensions ---
    specialization: str = ""
    is_intercomponent: bool = False
    implementation_status: Literal[
        "designed", "scaffolded", "tested", "implemented", "verified"
    ] = "designed"
    test_file: str = ""
```

- [ ] **Step 2: Verify import works**

```bash
cd /Users/danielnewman/dev/ticketing_system && python -c "from backend.db.neo4j.models.nodes.compound import CompoundNode; print(CompoundNode.model_fields.keys())"
```
Expected: prints field names including `component_id` and `file_path` (from base), NOT `source_file`

---

### Task 3: Simplify ticketing MemberNode

**File:**
- Modify: `backend/db/neo4j/models/nodes/member.py`

- [ ] **Step 1: Remove `is_abstract`, `is_final`, `component_id`**

Replace the file content:

```python
"""MemberNode — :Member in Neo4j.

Members are owned by compounds — methods and variables on classes,
values inside enums, defines inside namespaces. The `kind` field refines
the specific member type. The `layer` field indicates origin.
"""

from __future__ import annotations

from codegraph.nodes import MemberNode as BaseMemberNode


class MemberNode(BaseMemberNode):
    """A member entity in the codebase graph (:Member in Neo4j).

    Inherits all core fields from ``codegraph.nodes.MemberNode``
    (including ``component_id``). Kept as a thin subclass for the
    ``extra: "ignore"`` model config and import compatibility.
    """

    model_config = {"from_attributes": True, "extra": "ignore"}
```

- [ ] **Step 2: Verify import works**

```bash
cd /Users/danielnewman/dev/ticketing_system && python -c "from backend.db.neo4j.models.nodes.member import MemberNode; print('is_abstract' in MemberNode.model_fields)"
```
Expected: `False` (field no longer exists on MemberNode)

---

### Task 4: Delete ticketing NamespaceNode and update imports

**Files:**
- Delete: `backend/db/neo4j/models/nodes/namespace.py`
- Modify: `backend/db/neo4j/models/nodes/__init__.py`
- Modify: `backend/db/neo4j/models/graph.py`
- Modify: `backend/db/neo4j/models/__init__.py`
- Modify: `backend/db/neo4j/__init__.py`
- Modify: `backend/db/neo4j/repositories/design.py` (import)
- Modify: `backend/db/neo4j/repositories/__init__.py`

- [ ] **Step 1: Delete the namespace.py file**

```bash
rm backend/db/neo4j/models/nodes/namespace.py
```

- [ ] **Step 2: Update nodes/__init__.py**

Import `NamespaceNode` from `codegraph.nodes` instead:

```python
"""Codebase graph node models — one per Neo4j label."""

from backend.db.neo4j.models.nodes.compound import CompoundNode
from backend.db.neo4j.models.nodes.member import MemberNode
from codegraph.nodes import NamespaceNode

__all__ = ["CompoundNode", "MemberNode", "NamespaceNode"]
```

- [ ] **Step 3: Verify graph.py import still resolves**

`graph.py` imports `NamespaceNode` from `backend.db.neo4j.models.nodes`, which now re-exports from `codegraph.nodes` via `nodes/__init__.py`. This is transparent — no code change needed in `graph.py`.

```bash
cd /Users/danielnewman/dev/ticketing_system && python -c "from backend.db.neo4j.models.graph import NamespaceGraph; print(type(NamespaceGraph.__dataclass_fields__['node'].type))"
```
Expected: prints `<class 'codegraph.nodes.namespace_node.NamespaceNode'>`

- [ ] **Step 4: Verify all imports resolve**

```bash
cd /Users/danielnewman/dev/ticketing_system && python -c "
from backend.db.neo4j.models.nodes import CompoundNode, MemberNode, NamespaceNode
from backend.db.neo4j.models.graph import NamespaceGraph
print('All imports OK')
"
```
Expected: `All imports OK`

---

### Task 5: Update sync.py — `source_file` → `file_path`

**File:**
- Modify: `backend/db/neo4j/sync.py`

- [ ] **Step 1: Update the sync_implementation_status function**

Lines 165-200: change all `source_file` references to `file_path`:

**Change the docstring and variable (lines ~169-182):**

Old:
```python
    Phase 1: accepts either an OntologyNode (with .qualified_name,
    .implementation_status, .source_file, .test_file) or a
    (qualified_name, status, source_file, test_file) tuple.
```
New:
```python
    Phase 1: accepts either an OntologyNode (with .qualified_name,
    .implementation_status, .file_path, .test_file) or a
    (qualified_name, status, file_path, test_file) tuple.
```

Old:
```python
        source_file = getattr(node, "source_file", "") or ""
```
New:
```python
        source_file = getattr(node, "file_path", "") or ""
```

Old:
```python
        source_file = node.get("source_file", "")
```
New:
```python
        source_file = node.get("file_path", "")
```

Old:
```python
    SET d.implementation_status = $status,
        d.source_file = $source_file,
```
New:
```python
    SET d.implementation_status = $status,
        d.file_path = $source_file,
```

- [ ] **Step 2: Verify syntax**

```bash
cd /Users/danielnewman/dev/ticketing_system && python -c "import backend.db.neo4j.sync; print('OK')"
```
Expected: `OK`

---

### Task 6: Update design repository — `source_file` → `file_path`

**File:**
- Modify: `backend/db/neo4j/repositories/design.py`

- [ ] **Step 1: Update sync_implementation_status method (~line 857)**

Old:
```python
    def sync_implementation_status(self, qualified_name: str, status: str, source_file: str = "", test_file: str = "") -> None:
```

New:
```python
    def sync_implementation_status(self, qualified_name: str, status: str, file_path: str = "", test_file: str = "") -> None:
```

Old:
```python
            SET n.implementation_status = $status,
                n.source_file = $source_file,
```

New:
```python
            SET n.implementation_status = $status,
                n.file_path = $file_path,
```

Old:
```python
            "source_file": source_file,
```

New:
```python
            "file_path": file_path,
```

- [ ] **Step 2: Check for any other `source_file` references in this file**

```bash
grep -n "source_file" backend/db/neo4j/repositories/design.py
```
Expected: no results (all changed to `file_path`)

- [ ] **Step 3: Verify import**

```bash
cd /Users/danielnewman/dev/ticketing_system && python -c "from backend.db.neo4j.repositories.design import DesignRepository; print('OK')"
```
Expected: `OK`

---

### Task 7: Update persistence.py — stop setting removed fields

**File:**
- Modify: `backend/requirements/services/persistence.py`

- [ ] **Step 1: Update the import**

Old:
```python
from backend.db.neo4j.models.nodes import CompoundNode, MemberNode, NamespaceNode
```

New:
```python
from backend.db.neo4j.models.nodes import CompoundNode, MemberNode
from codegraph.nodes import NamespaceNode
```

- [ ] **Step 2: Update _ontology_node_to_model — Compound branch (~lines 85-96)**

Remove `is_abstract`, `is_final`, `source_file` (these are on the base now; `is_abstract` and `is_final` are base CompoundNode fields, `file_path` is base too):

Old:
```python
            file_path=node_data.file_path or "",
            line_number=node_data.line_number,
            is_abstract=node_data.is_abstract or False,
            is_final=node_data.is_final or False,
            component_id=node_data.component_id,
            is_intercomponent=node_data.is_intercomponent or False,
            implementation_status=getattr(node_data, 'implementation_status', 'designed') or 'designed',
            source_file=getattr(node_data, 'source_file', '') or '',
            test_file=getattr(node_data, 'test_file', '') or '',
```

New:
```python
            file_path=node_data.file_path or "",
            line_number=node_data.line_number,
            is_abstract=node_data.is_abstract or False,
            is_final=node_data.is_final or False,
            component_id=node_data.component_id,
            is_intercomponent=node_data.is_intercomponent or False,
            implementation_status=getattr(node_data, 'implementation_status', 'designed') or 'designed',
            test_file=getattr(node_data, 'test_file', '') or '',
```

- [ ] **Step 3: Update _ontology_node_to_model — Member branch (~lines 99-112)**

Remove `is_abstract`, `is_final`:

Old:
```python
            is_virtual=node_data.is_virtual or False,
            is_abstract=node_data.is_abstract or False,
            is_final=node_data.is_final or False,
            component_id=node_data.component_id,
```

New:
```python
            is_virtual=node_data.is_virtual or False,
            component_id=node_data.component_id,
```

- [ ] **Step 4: Update _ontology_node_to_model — Namespace branch (~lines 114-117)**

Remove `file_path`:

Old:
```python
        return NamespaceNode(
            **shared,
            file_path=node_data.file_path or "",
            component_id=node_data.component_id,
        )
```

New:
```python
        return NamespaceNode(
            **shared,
            component_id=node_data.component_id,
        )
```

- [ ] **Step 5: Update _ontology_node_to_model — fallback branch (~lines 120-129)**

Remove `source_file`:

Old:
```python
        return CompoundNode(
            **shared,
            specialization=node_data.specialization or "",
            component_id=node_data.component_id,
            is_intercomponent=node_data.is_intercomponent or False,
            implementation_status="designed",
            source_file="",
            test_file="",
        )
```

New:
```python
        return CompoundNode(
            **shared,
            specialization=node_data.specialization or "",
            component_id=node_data.component_id,
            is_intercomponent=node_data.is_intercomponent or False,
            implementation_status="designed",
            test_file="",
        )
```

- [ ] **Step 6: Update type annotation (~line 57)**

Old:
```python
def _ontology_node_to_model(node_data) -> CompoundNode | MemberNode | NamespaceNode:
```

New:
```python
def _ontology_node_to_model(node_data) -> CompoundNode | MemberNode | NamespaceNode:
```

(No change — NamespaceNode from codegraph.nodes has the same type identity as the old one.)

- [ ] **Step 7: Verify import**

```bash
cd /Users/danielnewman/dev/ticketing_system && python -c "from backend.requirements.services.persistence import _ontology_node_to_model; print('OK')"
```
Expected: `OK`

---

### Task 8: Update design_data — remove `source_file` from models and repository

**Files:**
- Modify: `backend/design_data/models.py`
- Modify: `backend/design_data/repository.py`

- [ ] **Step 1: Remove `source_file` from DiagramNode**

In `backend/design_data/models.py`, remove the line:

Old:
```python
    source_file: str = ""
```

(Delete just this line; keep `test_file`.)

- [ ] **Step 2: Remove `source_file` from ClassNode hydration**

In `backend/design_data/repository.py`, in `_hydrate_class` (~line 425), remove:

```python
            source_file=d.get("source_file", ""),
```

- [ ] **Step 3: Do the same for InterfaceNode hydration (~line 461)**

Find and remove `source_file` from the InterfaceNode constructor:

```bash
grep -n "source_file" backend/design_data/repository.py
```

If found in `_hydrate_interface`, remove that line as well.

- [ ] **Step 4: Verify imports**

```bash
cd /Users/danielnewman/dev/ticketing_system && python -c "from backend.design_data.models import ClassNode; print('source_file' in ClassNode.model_fields)"
```
Expected: `False`

---

### Task 9: Run full test suite and verify

- [ ] **Step 1: Run all tests**

```bash
cd /Users/danielnewman/dev/ticketing_system && python -m pytest -v
```
Expected: all tests PASS (or same failures as before this change)

- [ ] **Step 2: Verify the app starts**

```bash
cd /Users/danielnewman/dev/ticketing_system && timeout 5 python nicegui_app.py 2>&1 || true
```
Expected: no import errors or `source_file`-related AttributeErrors

- [ ] **Step 3: Commit all ticketing changes**

```bash
cd /Users/danielnewman/dev/ticketing_system
git add -A
git commit -m "refactor: simplify Neo4j node models — move component_id to codegraph, drop source_file/is_abstract/is_final/NamespaceNode"
```
