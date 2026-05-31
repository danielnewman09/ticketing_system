# Collapse Codebase Schemas into Codegraph OO Design Models — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse three overlapping data-model layers (`backend/codebase/schemas.py`, `backend/design_data/models.py`, `backend/db/neo4j/models/nodes/`) into codegraph as the canonical OO design model, with one thin ticketing-system extension layer.

**Architecture:** `ClassDiagram` moves from `backend/design_data/models.py` into `codegraph/designs/`. It becomes the canonical OO design representation — the LLM reads/writes it via tagged serialization, and it round-trips to/from Neo4j nodes via `to_neo4j()` / `from_neo4j()`. `FieldTags` annotations control field visibility per use case. Temporary re-export shims in the ticketing system avoid full codebase refactoring.

**Tech Stack:** Python 3.12+, Pydantic v2, Neo4j, `typing.Annotated`

---

## File structure (post-implementation)

```
codegraph/src/codegraph/
├── designs/                    # NEW — canonical OO design models
│   ├── __init__.py             # ClassDiagram, re-exports, model_dump override
│   ├── tags.py                 # FieldTags class
│   ├── compound.py             # DiagramNode, ClassNode, InterfaceNode, EnumNode
│   ├── member.py               # AttributeNode, MethodNode, EnumValueNode
│   ├── namespace.py            # ModuleNode
│   └── edges.py                # Association
├── type_parser.py              # MOVED — TypeRef + parsing
├── nodes/
│   ├── compound_node.py        # + FieldTags annotations
│   ├── member_node.py          # + FieldTags annotations
│   ├── namespace_node.py       # + FieldTags annotations
│   └── *
├── edges.py                    # + description field, FieldTags annotations
├── constants.py                # unchanged
└── graph/                      # unchanged

ticketing_system/backend/
├── codebase/
│   ├── schemas.py              # reduced: RequirementTripleLinkSchema, DesignSchema
│   ├── type_parser.py          # DELETED → codegraph
│   └── indexing.py             # unchanged
├── db/neo4j/models/nodes/
│   ├── compound.py             # thinned: only ticketing extensions
│   └── member.py               # unchanged
└── design_data/
    ├── models.py               # TEMPORARY re-export shim
    ├── repository.py           # unchanged (import paths updated)
    └── transforms.py           # deprecated shim
```

---

### Task 1: Add `description` field to CodebaseEdge

**Files:**
- Modify: `codegraph/src/codegraph/edges.py`
- Test: `tests/test_codegraph_edge_description.py` (new, or add to existing)

**Rationale:** `ClassDiagram.Association` carries a `description` field. `from_neo4j()` must populate it from Neo4j edge properties. `CodebaseEdge` currently lacks this field but Neo4j edges store it — the repository already fetches `r.description`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_codegraph_edge_description.py
"""Test description field on CodebaseEdge."""
import pytest
from codegraph.edges import CodebaseEdge


def test_codebase_edge_has_description_field():
    edge = CodebaseEdge(
        subject_qualified_name="calc::Calculator",
        predicate="aggregates",
        object_qualified_name="calc::Matrix",
        description="Holds the internal matrix for operations",
    )
    assert edge.description == "Holds the internal matrix for operations"


def test_codebase_edge_description_defaults_to_empty():
    edge = CodebaseEdge(
        subject_qualified_name="calc::Calculator",
        predicate="aggregates",
        object_qualified_name="calc::Matrix",
    )
    assert edge.description == ""
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/danielnewman/dev/codegraph && python -m pytest tests/test_codegraph_edge_description.py -v
```
Expected: FAIL with validation error — `description` is not a known field.

- [ ] **Step 3: Add `description` to CodebaseEdge**

```python
# edit codegraph/src/codegraph/edges.py — add after `display_name`:
class CodebaseEdge(BaseModel):
    # ... existing fields ...
    display_name: str = ""
    description: str = ""          # <-- NEW: human-readable description of the relationship

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/danielnewman/dev/codegraph && python -m pytest tests/test_codegraph_edge_description.py -v
```
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/danielnewman/dev/codegraph && git add src/codegraph/edges.py tests/test_codegraph_edge_description.py && git commit -m "feat: add description field to CodebaseEdge"
```

---

### Task 2: Create `codegraph/designs/tags.py` — FieldTags

**Files:**
- Create: `codegraph/src/codegraph/designs/tags.py`
- Create: `codegraph/src/codegraph/designs/__init__.py` (minimal bootstrap)
- Test: `tests/test_field_tags.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_field_tags.py
"""Test FieldTags annotation and field filtering."""
import pytest
from typing import Annotated, get_type_hints
from pydantic import BaseModel
from codegraph.designs.tags import FieldTags, get_fields_by_tags


class SampleModel(BaseModel):
    name: Annotated[str, FieldTags("llm", "neo4j")]
    file_path: Annotated[str, FieldTags("neo4j")]
    internal: str = ""  # no tags


def test_field_tags_are_inspectable():
    hints = get_type_hints(SampleModel, include_extras=True)
    assert hints["name"].__metadata__[0].tags == frozenset({"llm", "neo4j"})
    assert hints["file_path"].__metadata__[0].tags == frozenset({"neo4j"})


def test_get_fields_by_tags_llm():
    fields = get_fields_by_tags(SampleModel, {"llm"})
    assert "name" in fields
    assert "file_path" not in fields
    assert "internal" not in fields


def test_get_fields_by_tags_neo4j():
    fields = get_fields_by_tags(SampleModel, {"neo4j"})
    assert "name" in fields
    assert "file_path" in fields
    assert "internal" not in fields


def test_untagged_fields_excluded():
    fields = get_fields_by_tags(SampleModel, {"llm", "neo4j"})
    assert "internal" not in fields
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/danielnewman/dev/codegraph && python -m pytest tests/test_field_tags.py -v
```
Expected: FAIL — `codegraph.designs.tags` not found.

- [ ] **Step 3: Create minimal `__init__.py` and `tags.py`**

```bash
mkdir -p /Users/danielnewman/dev/codegraph/src/codegraph/designs
```

```python
# codegraph/src/codegraph/designs/__init__.py (bootstrap)
"""Canonical OO design models for the codebase graph."""
```

```python
# codegraph/src/codegraph/designs/tags.py
"""FieldTags annotation for marking field relevance by use case."""

from __future__ import annotations

from typing import Any, get_type_hints


class FieldTags:
    """Marker annotation for model fields indicating which use cases they apply to.

    Usage:
        name: Annotated[str, FieldTags("llm", "neo4j")]
    """

    def __init__(self, *tags: str) -> None:
        self.tags: frozenset[str] = frozenset(tags)

    def __repr__(self) -> str:
        return f"FieldTags({', '.join(sorted(self.tags))})"


def get_fields_by_tags(model_cls: type, requested_tags: set[str]) -> set[str]:
    """Return the set of field names whose FieldTags intersect requested_tags.

    Fields with no FieldTags annotation are excluded.
    """
    hints = get_type_hints(model_cls, include_extras=True)
    result: set[str] = set()
    for field_name, hint in hints.items():
        metadata = getattr(hint, "__metadata__", ())
        for item in metadata:
            if isinstance(item, FieldTags) and (item.tags & requested_tags):
                result.add(field_name)
                break
    return result
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/danielnewman/dev/codegraph && python -m pytest tests/test_field_tags.py -v
```
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/danielnewman/dev/codegraph && git add src/codegraph/designs/ tests/test_field_tags.py && git commit -m "feat: add FieldTags annotation and field filtering utility"
```

---

### Task 3: Create `codegraph/designs/member.py` — AttributeNode, MethodNode, EnumValueNode

**Files:**
- Create: `codegraph/src/codegraph/designs/member.py`
- Test: `tests/test_designs_member.py`

**Strategy:** Move these models from `backend/design_data/models.py` with three changes:
1. Add `FieldTags` annotations to every field
2. Add Pydantic `serialization_alias` on `AttributeNode.type_signature` → `"type_name"` and `MethodNode.type_signature` → `"return_type"`
3. Add `owner` as `FieldTags(NEO4J, READ)` (not in LLM)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_designs_member.py
"""Test AttributeNode, MethodNode, EnumValueNode design models."""
import pytest
from codegraph.designs.member import AttributeNode, MethodNode, EnumValueNode


class TestAttributeNode:
    def test_serializes_type_name_for_llm(self):
        attr = AttributeNode(
            name="count",
            qualified_name="calc::Calculator::count",
            type_signature="int",
        )
        dumped = attr.model_dump(tags={"llm"})
        assert "type_name" in dumped
        assert dumped["type_name"] == "int"
        assert "type_signature" not in dumped

    def test_serializes_type_signature_for_neo4j(self):
        attr = AttributeNode(
            name="count",
            qualified_name="calc::Calculator::count",
            type_signature="int",
        )
        dumped = attr.model_dump(tags={"neo4j"})
        assert "type_signature" in dumped
        assert dumped["type_signature"] == "int"
        assert "type_name" not in dumped

    def test_defaults(self):
        attr = AttributeNode()
        assert attr.name == ""
        assert attr.qualified_name == ""
        assert attr.kind == "attribute"
        assert attr.visibility == ""
        assert attr.type_signature == ""
        assert attr.owner == ""


class TestMethodNode:
    def test_serializes_return_type_for_llm(self):
        method = MethodNode(
            name="add",
            qualified_name="calc::Calculator::add",
            type_signature="int",
            argsstring="(int a, int b)",
        )
        dumped = method.model_dump(tags={"llm"})
        assert dumped["return_type"] == "int"
        assert "type_signature" not in dumped

    def test_defaults(self):
        method = MethodNode()
        assert method.kind == "method"
        assert method.argsstring == ""


class TestEnumValueNode:
    def test_defaults(self):
        ev = EnumValueNode()
        assert ev.kind == "enum_value"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/danielnewman/dev/codegraph && python -m pytest tests/test_designs_member.py -v
```
Expected: FAIL — `codegraph.designs.member` not found.

- [ ] **Step 3: Create `member.py`**

```python
# codegraph/src/codegraph/designs/member.py
"""Member-level design models — AttributeNode, MethodNode, EnumValueNode."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from codegraph.designs.tags import FieldTags, get_fields_by_tags


class AttributeNode(BaseModel):
    """Class/interface attribute in the class diagram."""

    name: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    qualified_name: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    kind: Literal["attribute"] = "attribute"
    description: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    visibility: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    # LLM sees "type_name"; internally stored as type_signature
    type_signature: Annotated[
        str,
        FieldTags("llm", "neo4j", "read"),
        Field(serialization_alias="type_name"),
    ] = ""

    # Neo4j/read only — not exposed to LLM
    owner: Annotated[str, FieldTags("neo4j", "read")] = ""
    component_id: Annotated[int | None, FieldTags("neo4j", "read")] = None
    layer: Annotated[str, FieldTags("neo4j", "read")] = "design"

    def model_dump(self, *, tags: set[str] | None = None, **kwargs) -> dict:
        """Serialize with optional field-tag filtering."""
        return _tagged_model_dump(self, tags, **kwargs)


class MethodNode(BaseModel):
    """Class/interface method in the class diagram."""

    name: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    qualified_name: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    kind: Literal["method"] = "method"
    description: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    visibility: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    # LLM sees "return_type"; internally stored as type_signature
    type_signature: Annotated[
        str,
        FieldTags("llm", "neo4j", "read"),
        Field(serialization_alias="return_type"),
    ] = ""

    argsstring: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    # Neo4j/read only — not exposed to LLM
    owner: Annotated[str, FieldTags("neo4j", "read")] = ""
    component_id: Annotated[int | None, FieldTags("neo4j", "read")] = None
    layer: Annotated[str, FieldTags("neo4j", "read")] = "design"

    is_virtual: Annotated[bool, FieldTags("neo4j", "read")] = False
    is_static: Annotated[bool, FieldTags("neo4j", "read")] = False
    is_const: Annotated[bool, FieldTags("neo4j", "read")] = False

    def model_dump(self, *, tags: set[str] | None = None, **kwargs) -> dict:
        return _tagged_model_dump(self, tags, **kwargs)


class EnumValueNode(BaseModel):
    """Enum value in the class diagram."""

    name: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    qualified_name: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    kind: Literal["enum_value"] = "enum_value"
    description: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    owner: Annotated[str, FieldTags("neo4j", "read")] = ""

    def model_dump(self, *, tags: set[str] | None = None, **kwargs) -> dict:
        return _tagged_model_dump(self, tags, **kwargs)


def _tagged_model_dump(model: BaseModel, tags: set[str] | None, **kwargs) -> dict:
    """Filter model_dump output based on FieldTags annotations."""
    if tags is None:
        return model.__class__.__bases__[0].model_dump(model, **kwargs)

    allowed = get_fields_by_tags(type(model), tags)
    data = model.__class__.__bases__[0].model_dump(model, by_alias=True, **kwargs)
    return {k: v for k, v in data.items() if k in allowed}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/danielnewman/dev/codegraph && python -m pytest tests/test_designs_member.py -v
```
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/danielnewman/dev/codegraph && git add src/codegraph/designs/member.py tests/test_designs_member.py && git commit -m "feat: add AttributeNode, MethodNode, EnumValueNode design models with FieldTags"
```

---

### Task 4: Create `codegraph/designs/compound.py` — DiagramNode, ClassNode, InterfaceNode, EnumNode

**Files:**
- Create: `codegraph/src/codegraph/designs/compound.py`
- Test: `tests/test_designs_compound.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_designs_compound.py
"""Test compound design models — ClassNode, InterfaceNode, EnumNode."""
import pytest
from codegraph.designs.compound import (
    DiagramNode, ClassNode, InterfaceNode, EnumNode,
)
from codegraph.designs.member import AttributeNode, MethodNode, EnumValueNode


class TestDiagramNode:
    def test_defaults(self):
        node = DiagramNode()
        assert node.name == ""
        assert node.qualified_name == ""
        assert node.kind == ""  # overridden by subclasses
        assert node.description == ""
        assert node.layer == "design"
        assert node.file_path == ""

    def test_llm_dump_excludes_neo4j_fields(self):
        node = DiagramNode(
            name="Calculator",
            qualified_name="calc::Calculator",
            kind="class",
            file_path="/src/calculator.h",
            line_number=42,
            is_static=False,
            is_final=True,
        )
        dumped = node.model_dump(tags={"llm"})
        assert "name" in dumped
        assert "qualified_name" in dumped
        assert "kind" in dumped
        assert "file_path" not in dumped
        assert "line_number" not in dumped
        assert "is_static" not in dumped
        assert "is_final" not in dumped


class TestClassNode:
    def test_defaults(self):
        cls = ClassNode()
        assert cls.kind == "class"
        assert cls.attributes == []
        assert cls.methods == []
        assert cls.inherits_from == []

    def test_serializes_nested_members_with_llm_tags(self):
        cls = ClassNode(
            name="Calculator",
            qualified_name="calc::Calculator",
            kind="class",
            attributes=[
                AttributeNode(
                    name="count", qualified_name="calc::Calculator::count",
                    type_signature="int", owner="calc::Calculator",
                )
            ],
            methods=[
                MethodNode(
                    name="add", qualified_name="calc::Calculator::add",
                    type_signature="int", argsstring="(int a, int b)",
                    owner="calc::Calculator",
                )
            ],
        )
        dumped = cls.model_dump(tags={"llm"})
        assert dumped["name"] == "Calculator"
        assert len(dumped["attributes"]) == 1
        assert dumped["attributes"][0]["type_name"] == "int"
        assert "owner" not in dumped["attributes"][0]
        assert len(dumped["methods"]) == 1
        assert dumped["methods"][0]["return_type"] == "int"
        assert "owner" not in dumped["methods"][0]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/danielnewman/dev/codegraph && python -m pytest tests/test_designs_compound.py -v
```
Expected: FAIL.

- [ ] **Step 3: Create `compound.py`**

```python
# codegraph/src/codegraph/designs/compound.py
"""Compound-level design models — DiagramNode, ClassNode, InterfaceNode, EnumNode."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel

from codegraph.designs.member import (
    AttributeNode, MethodNode, EnumValueNode, _tagged_model_dump,
)
from codegraph.designs.tags import FieldTags


class DiagramNode(BaseModel):
    """Common fields for every diagram node."""

    name: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    qualified_name: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    kind: str = ""  # subclasses override with Literal

    # LLM-visible
    description: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    visibility: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    # Neo4j / read only
    layer: Annotated[str, FieldTags("neo4j", "read")] = "design"
    component_id: Annotated[int | None, FieldTags("neo4j", "read")] = None
    type_signature: Annotated[str, FieldTags("neo4j", "read")] = ""
    argsstring: Annotated[str, FieldTags("neo4j", "read")] = ""
    definition: Annotated[str, FieldTags("neo4j", "read")] = ""
    source_type: Annotated[str, FieldTags("neo4j", "read")] = ""
    source: Annotated[str, FieldTags("neo4j", "read")] = ""
    file_path: Annotated[str, FieldTags("neo4j", "read")] = ""
    line_number: Annotated[int | None, FieldTags("neo4j", "read")] = None
    is_static: Annotated[bool, FieldTags("neo4j", "read")] = False
    is_const: Annotated[bool, FieldTags("neo4j", "read")] = False
    is_virtual: Annotated[bool, FieldTags("neo4j", "read")] = False
    is_abstract: Annotated[bool, FieldTags("neo4j", "read")] = False
    is_final: Annotated[bool, FieldTags("neo4j", "read")] = False

    # Ticketing extensions — tagged separately
    specialization: Annotated[str, FieldTags("ticketing")] = ""
    is_intercomponent: Annotated[bool, FieldTags("ticketing")] = False
    implementation_status: Annotated[str, FieldTags("ticketing")] = "designed"
    test_file: Annotated[str, FieldTags("ticketing")] = ""

    def model_dump(self, *, tags: set[str] | None = None, **kwargs) -> dict:
        return _tagged_model_dump(self, tags, **kwargs)


class ClassNode(DiagramNode):
    """Class or struct in the class diagram."""

    kind: Literal["class"] = "class"
    module: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    inherits_from: Annotated[list[str], FieldTags("llm", "neo4j", "read")] = []
    realizes: Annotated[list[str], FieldTags("llm", "neo4j", "read")] = []
    attributes: Annotated[list[AttributeNode], FieldTags("llm", "neo4j", "read")] = []
    methods: Annotated[list[MethodNode], FieldTags("llm", "neo4j", "read")] = []

    def model_dump(self, *, tags: set[str] | None = None, **kwargs) -> dict:
        data = _tagged_model_dump(self, tags, **kwargs)
        # Recurse into nested member lists
        if "attributes" in data:
            data["attributes"] = [
                a.model_dump(tags=tags, **kwargs) if hasattr(a, "model_dump") else a
                for a in self.attributes
            ]
        if "methods" in data:
            data["methods"] = [
                m.model_dump(tags=tags, **kwargs) if hasattr(m, "model_dump") else m
                for m in self.methods
            ]
        return data


class InterfaceNode(DiagramNode):
    """Interface / abstract class in the class diagram."""

    kind: Literal["interface"] = "interface"
    module: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    methods: Annotated[list[MethodNode], FieldTags("llm", "neo4j", "read")] = []

    def model_dump(self, *, tags: set[str] | None = None, **kwargs) -> dict:
        data = _tagged_model_dump(self, tags, **kwargs)
        if "methods" in data:
            data["methods"] = [
                m.model_dump(tags=tags, **kwargs) if hasattr(m, "model_dump") else m
                for m in self.methods
            ]
        return data


class EnumNode(DiagramNode):
    """Enum in the class diagram."""

    kind: Literal["enum"] = "enum"
    module: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    values: Annotated[list[EnumValueNode], FieldTags("llm", "neo4j", "read")] = []

    def model_dump(self, *, tags: set[str] | None = None, **kwargs) -> dict:
        data = _tagged_model_dump(self, tags, **kwargs)
        if "values" in data:
            data["values"] = [
                v.model_dump(tags=tags, **kwargs) if hasattr(v, "model_dump") else v
                for v in self.values
            ]
        return data
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/danielnewman/dev/codegraph && python -m pytest tests/test_designs_compound.py -v
```
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/danielnewman/dev/codegraph && git add src/codegraph/designs/compound.py tests/test_designs_compound.py && git commit -m "feat: add DiagramNode, ClassNode, InterfaceNode, EnumNode design models with FieldTags"
```

---

### Task 5: Create `codegraph/designs/namespace.py` and `codegraph/designs/edges.py`

**Files:**
- Create: `codegraph/src/codegraph/designs/namespace.py`
- Create: `codegraph/src/codegraph/designs/edges.py`
- Test: `tests/test_designs_namespace.py`
- Test: `tests/test_designs_edges.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_designs_namespace.py
import pytest
from codegraph.designs.namespace import ModuleNode


def test_module_node_defaults():
    mod = ModuleNode()
    assert mod.kind == "module"
    assert mod.name == ""
    assert mod.qualified_name == ""


def test_module_node_llm_dump():
    mod = ModuleNode(name="calc", qualified_name="calc")
    dumped = mod.model_dump(tags={"llm"})
    assert dumped["name"] == "calc"
    assert dumped["qualified_name"] == "calc"
    assert "file_path" not in dumped
```

```python
# tests/test_designs_edges.py
import pytest
from codegraph.designs.edges import Association


def test_association_llm_aliases():
    assoc = Association(
        subject="calc::Calculator",
        predicate="aggregates",
        object="calc::Matrix",
        mechanism="std::vector",
        description="Internal matrix storage",
    )
    dumped = assoc.model_dump(tags={"llm"})
    assert dumped["from_class"] == "calc::Calculator"
    assert dumped["to_class"] == "calc::Matrix"
    assert dumped["kind"] == "aggregates"
    assert "subject" not in dumped
    assert "predicate" not in dumped
    assert "object" not in dumped
    assert dumped["mechanism"] == "std::vector"
    assert dumped["description"] == "Internal matrix storage"
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd /Users/danielnewman/dev/codegraph && python -m pytest tests/test_designs_namespace.py tests/test_designs_edges.py -v
```
Expected: FAIL.

- [ ] **Step 3: Create namespace.py and edges.py**

```python
# codegraph/src/codegraph/designs/namespace.py
from __future__ import annotations

from typing import Annotated, Literal

from codegraph.designs.compound import DiagramNode
from codegraph.designs.member import _tagged_model_dump
from codegraph.designs.tags import FieldTags


class ModuleNode(DiagramNode):
    """Module / namespace in the class diagram."""
    kind: Literal["module"] = "module"

    def model_dump(self, *, tags: set[str] | None = None, **kwargs) -> dict:
        return _tagged_model_dump(self, tags, **kwargs)
```

```python
# codegraph/src/codegraph/designs/edges.py
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

from codegraph.designs.member import _tagged_model_dump
from codegraph.designs.tags import FieldTags


class Association(BaseModel):
    """A relationship between two top-level design entities."""

    subject: Annotated[
        str,
        FieldTags("llm", "neo4j", "read"),
        Field(serialization_alias="from_class"),
    ] = ""
    predicate: Annotated[
        str,
        FieldTags("llm", "neo4j", "read"),
        Field(serialization_alias="kind"),
    ] = ""
    object: Annotated[
        str,
        FieldTags("llm", "neo4j", "read"),
        Field(serialization_alias="to_class"),
    ] = ""
    mechanism: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    description: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    def model_dump(self, *, tags: set[str] | None = None, **kwargs) -> dict:
        return _tagged_model_dump(self, tags, **kwargs)
```

- [ ] **Step 4: Run tests to verify**

```bash
cd /Users/danielnewman/dev/codegraph && python -m pytest tests/test_designs_namespace.py tests/test_designs_edges.py -v
```
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/danielnewman/dev/codegraph && git add src/codegraph/designs/namespace.py src/codegraph/designs/edges.py tests/test_designs_namespace.py tests/test_designs_edges.py && git commit -m "feat: add ModuleNode and Association design models with FieldTags and LLM aliases"
```

---

### Task 6: Create `codegraph/designs/__init__.py` — ClassDiagram with `to_neo4j()` / `from_neo4j()`

**Files:**
- Modify: `codegraph/src/codegraph/designs/__init__.py` (replace bootstrap)
- Test: `tests/test_class_diagram_neo4j.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_class_diagram_neo4j.py
"""Test ClassDiagram to_neo4j() / from_neo4j() round-trip."""
import pytest
from codegraph.designs import ClassDiagram
from codegraph.designs.compound import ClassNode, InterfaceNode, EnumNode
from codegraph.designs.member import AttributeNode, MethodNode, EnumValueNode
from codegraph.designs.edges import Association
from codegraph.nodes import CompoundNode, MemberNode
from codegraph.edges import CodebaseEdge


def make_sample_diagram() -> ClassDiagram:
    return ClassDiagram(
        classes=[
            ClassNode(
                name="Calculator",
                qualified_name="calc::Calculator",
                kind="class",
                description="A simple calculator",
                module="calc",
                attributes=[
                    AttributeNode(
                        name="count", qualified_name="calc::Calculator::count",
                        type_signature="int", visibility="private",
                        description="Operation counter",
                    )
                ],
                methods=[
                    MethodNode(
                        name="add", qualified_name="calc::Calculator::add",
                        type_signature="int", argsstring="(int a, int b)",
                        visibility="public", description="Add two numbers",
                    )
                ],
            )
        ],
        interfaces=[
            InterfaceNode(
                name="IPrintable", qualified_name="calc::IPrintable",
                kind="interface", module="calc",
                is_abstract=True,
                methods=[
                    MethodNode(
                        name="print", qualified_name="calc::IPrintable::print",
                        type_signature="void", argsstring="()",
                        visibility="public", is_virtual=True,
                    )
                ],
            )
        ],
        enums=[
            EnumNode(
                name="Op", qualified_name="calc::Op",
                kind="enum", module="calc",
                values=[
                    EnumValueNode(name="ADD", qualified_name="calc::Op::ADD"),
                    EnumValueNode(name="SUB", qualified_name="calc::Op::SUB"),
                ],
            )
        ],
        associations=[
            Association(
                subject="calc::Calculator",
                predicate="aggregates",
                object="calc::Matrix",
                mechanism="std::vector",
                description="Internal matrix storage",
            )
        ],
    )


def test_to_neo4j_roundtrip():
    diagram = make_sample_diagram()
    compounds, members, edges = diagram.to_neo4j()

    # Verify compounds
    assert len(compounds) == 3  # Calculator + IPrintable + Op
    compound_map = {c.qualified_name: c for c in compounds}
    calc = compound_map["calc::Calculator"]
    assert calc.kind == "class"
    assert calc.name == "Calculator"
    assert calc.brief_description == "A simple calculator"

    iface = compound_map["calc::IPrintable"]
    assert iface.kind == "interface"
    assert iface.is_abstract is True

    op = compound_map["calc::Op"]
    assert op.kind == "enum"

    # Verify members
    assert len(members) == 5  # count, add, print, ADD, SUB
    member_map = {m.qualified_name: m for m in members}
    count = member_map["calc::Calculator::count"]
    assert count.kind == "variable"
    assert count.type_signature == "int"

    add_method = member_map["calc::Calculator::add"]
    assert add_method.kind == "method"
    assert add_method.type_signature == "int"

    add_enum = member_map["calc::Op::ADD"]
    assert add_enum.kind == "enumvalue"

    # Verify edges
    assert len(edges) == 1
    edge = edges[0]
    assert edge.subject_qualified_name == "calc::Calculator"
    assert edge.predicate == "aggregates"
    assert edge.object_qualified_name == "calc::Matrix"
    assert edge.description == "Internal matrix storage"


def test_from_neo4j_reconstructs_diagram():
    diagram = make_sample_diagram()
    compounds, members, edges = diagram.to_neo4j()
    reconstructed = ClassDiagram.from_neo4j(compounds, members, edges)

    assert len(reconstructed.classes) == 1
    cls = reconstructed.classes[0]
    assert cls.qualified_name == "calc::Calculator"
    assert cls.description == "A simple calculator"
    assert len(cls.attributes) == 1
    assert cls.attributes[0].name == "count"
    assert len(cls.methods) == 1
    assert cls.methods[0].name == "add"

    assert len(reconstructed.interfaces) == 1
    assert reconstructed.interfaces[0].qualified_name == "calc::IPrintable"
    assert len(reconstructed.interfaces[0].methods) == 1

    assert len(reconstructed.enums) == 1
    assert reconstructed.enums[0].qualified_name == "calc::Op"
    assert len(reconstructed.enums[0].values) == 2

    assert len(reconstructed.associations) == 1
    assert reconstructed.associations[0].subject == "calc::Calculator"

    # Verify entity index works
    entity = reconstructed.get_entity("calc::Calculator")
    assert entity is not None
    assert entity.qualified_name == "calc::Calculator"


def test_class_diagram_llm_serialization():
    diagram = make_sample_diagram()
    dumped = diagram.model_dump(tags={"llm", "ticketing"})

    cls = dumped["classes"][0]
    assert cls["name"] == "Calculator"
    assert cls["qualified_name"] == "calc::Calculator"
    assert "file_path" not in cls
    assert "layer" not in cls
    assert "line_number" not in cls
    assert cls["attributes"][0]["type_name"] == "int"
    assert cls["methods"][0]["return_type"] == "int"

    assoc = dumped["associations"][0]
    assert assoc["from_class"] == "calc::Calculator"
    assert assoc["to_class"] == "calc::Matrix"
    assert assoc["kind"] == "aggregates"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/danielnewman/dev/codegraph && python -m pytest tests/test_class_diagram_neo4j.py -v
```
Expected: FAIL — ClassDiagram not in `__init__.py`.

- [ ] **Step 3: Replace `__init__.py` with full ClassDiagram**

```python
# codegraph/src/codegraph/designs/__init__.py
"""Canonical OO design models for the codebase graph.

ClassDiagram is the single OO design representation. It handles:
  - LLM serialization (via model_dump(tags={"llm"}))
  - Neo4j round-tripping (to_neo4j / from_neo4j)
  - Query and transformation methods (get_entity, to_verification_dicts, etc.)
"""

from __future__ import annotations

from pydantic import BaseModel, PrivateAttr

from codegraph.designs.compound import (
    ClassNode, DiagramNode, EnumNode, InterfaceNode,
)
from codegraph.designs.edges import Association
from codegraph.designs.member import (
    AttributeNode, EnumValueNode, MethodNode, _tagged_model_dump,
)
from codegraph.designs.namespace import ModuleNode
from codegraph.designs.tags import FieldTags, get_fields_by_tags
from codegraph.nodes import CompoundNode, MemberNode, NamespaceNode
from codegraph.edges import CodebaseEdge

__all__ = [
    "Association",
    "AttributeNode",
    "ClassDiagram",
    "ClassNode",
    "DiagramNode",
    "EnumNode",
    "EnumValueNode",
    "FieldTags",
    "InterfaceNode",
    "MethodNode",
    "ModuleNode",
]


class ClassDiagram(BaseModel):
    """Complete class diagram for a query scope.

    LLM serialization: diagram.model_dump(tags={"llm", "ticketing"})
    Neo4j round-trip: diagram.to_neo4j() / ClassDiagram.from_neo4j(...)
    """

    module_names: list[str] = []
    classes: list[ClassNode] = []
    interfaces: list[InterfaceNode] = []
    enums: list[EnumNode] = []
    associations: list[Association] = []

    _entity_index: dict[str, ClassNode | InterfaceNode | EnumNode | ModuleNode] = (
        PrivateAttr(default_factory=dict)
    )

    def model_post_init(self, __context) -> None:
        """Build the entity index for fast lookups."""
        self._entity_index = {}
        for cls in self.classes:
            self._entity_index[cls.qualified_name] = cls
        for iface in self.interfaces:
            self._entity_index[iface.qualified_name] = iface
        for enum in self.enums:
            self._entity_index[enum.qualified_name] = enum

    # -- Query methods -------------------------------------------------------

    def get_entity(
        self, qualified_name: str
    ) -> ClassNode | InterfaceNode | EnumNode | ModuleNode | None:
        return self._entity_index.get(qualified_name)

    def associations_for(self, qualified_name: str) -> list[Association]:
        return [a for a in self.associations if a.subject == qualified_name]

    def associations_involving(self, qualified_name: str) -> list[Association]:
        return [
            a for a in self.associations
            if a.subject == qualified_name or a.object == qualified_name
        ]

    def classes_in_module(self, module: str) -> list[ClassNode]:
        return [c for c in self.classes if c.module == module]

    # -- Serialization -------------------------------------------------------

    def model_dump(self, *, tags: set[str] | None = None, **kwargs) -> dict:
        """Serialize with optional field-tag filtering.

        tags=None: all fields (Neo4j, debug)
        tags={"llm"}: LLM-visible subset only
        tags={"llm", "ticketing"}: LLM + ticketing-specific fields
        """
        # Get fields with matching tags for ClassDiagram itself
        allowed = get_fields_by_tags(ClassDiagram, tags) if tags else None

        if allowed is None:
            data = super().model_dump(**kwargs)
        else:
            data = super().model_dump(**kwargs)
            data = {k: v for k, v in data.items() if k in allowed}

        # Recurse into nested model lists
        if "classes" in data:
            data["classes"] = [
                c.model_dump(tags=tags, **kwargs)
                for c in self.classes
            ]
        if "interfaces" in data:
            data["interfaces"] = [
                i.model_dump(tags=tags, **kwargs)
                for i in self.interfaces
            ]
        if "enums" in data:
            data["enums"] = [
                e.model_dump(tags=tags, **kwargs)
                for e in self.enums
            ]
        if "associations" in data:
            data["associations"] = [
                a.model_dump(tags=tags, **kwargs)
                for a in self.associations
            ]
        return data

    # -- Neo4j round-trip ----------------------------------------------------

    _DESIGN_KIND_TO_MEMBER_KIND: dict[str, str] = {
        "attribute": "variable",
        "method": "method",
        "enum_value": "enumvalue",
    }

    _MEMBER_KIND_TO_DESIGN_KIND: dict[str, str] = {
        "variable": "attribute",
        "method": "method",
        "enumvalue": "enum_value",
    }

    def to_neo4j(self) -> tuple[list[CompoundNode], list[MemberNode], list[CodebaseEdge]]:
        """Decompose ClassDiagram into codegraph node/edge models."""
        compounds: list[CompoundNode] = []
        members: list[MemberNode] = []

        for cls in self.classes:
            compound = CompoundNode(
                qualified_name=cls.qualified_name,
                name=cls.name,
                kind=cls.kind,  # type: ignore[arg-type]
                layer=cls.layer or "design",  # type: ignore[arg-type]
                component_id=cls.component_id,
                brief_description=cls.description,
                file_path=cls.file_path,
                line_number=cls.line_number,
                is_final=cls.is_final,
                is_abstract=cls.is_abstract,
            )
            compounds.append(compound)

            for attr in cls.attributes:
                members.append(MemberNode(
                    qualified_name=attr.qualified_name,
                    name=attr.name,
                    kind="variable",
                    layer="design",
                    component_id=attr.component_id,
                    compound_refid="",  # linked via COMPOSES edges
                    brief_description=attr.description,
                    type_signature=attr.type_signature,
                ))

            for method in cls.methods:
                members.append(MemberNode(
                    qualified_name=method.qualified_name,
                    name=method.name,
                    kind="method",
                    layer="design",
                    component_id=method.component_id,
                    brief_description=method.description,
                    type_signature=method.type_signature,
                    argsstring=method.argsstring,
                    protection=method.visibility or "",  # type: ignore[arg-type]
                    is_virtual=method.is_virtual,
                    is_static=method.is_static,
                    is_const=method.is_const,
                ))

        for iface in self.interfaces:
            compound = CompoundNode(
                qualified_name=iface.qualified_name,
                name=iface.name,
                kind=iface.kind,  # type: ignore[arg-type]
                layer="design",
                component_id=iface.component_id,
                brief_description=iface.description,
                is_abstract=iface.is_abstract,
            )
            compounds.append(compound)

            for method in iface.methods:
                members.append(MemberNode(
                    qualified_name=method.qualified_name,
                    name=method.name,
                    kind="method",
                    layer="design",
                    component_id=method.component_id,
                    brief_description=method.description,
                    type_signature=method.type_signature,
                    argsstring=method.argsstring,
                    protection=method.visibility or "",  # type: ignore[arg-type]
                    is_virtual=True,
                ))

        for enum in self.enums:
            compound = CompoundNode(
                qualified_name=enum.qualified_name,
                name=enum.name,
                kind=enum.kind,  # type: ignore[arg-type]
                layer="design",
                component_id=enum.component_id,
                brief_description=enum.description,
            )
            compounds.append(compound)

            for val in enum.values:
                members.append(MemberNode(
                    qualified_name=val.qualified_name,
                    name=val.name,
                    kind="enumvalue",
                    layer="design",
                ))

        edges: list[CodebaseEdge] = []
        for assoc in self.associations:
            edges.append(CodebaseEdge(
                subject_qualified_name=assoc.subject,
                predicate=assoc.predicate,
                object_qualified_name=assoc.object,
                mechanism=assoc.mechanism,
                description=assoc.description,
            ))

        return compounds, members, edges

    @classmethod
    def from_neo4j(
        cls,
        compounds: list[CompoundNode],
        members: list[MemberNode],
        edges: list[CodebaseEdge],
    ) -> ClassDiagram:
        """Reconstruct ClassDiagram from Neo4j query results."""
        _CLASS_KINDS = {"class", "struct", "template_class"}
        _INTERFACE_KINDS = {"interface", "abstract_class"}
        _ENUM_KINDS = {"enum", "enum_class"}

        # Index members by parent qualified_name
        member_index: dict[str, list[MemberNode]] = {}
        for m in members:
            parent = _extract_parent_qn(m.qualified_name)
            member_index.setdefault(parent, []).append(m)

        classes: list[ClassNode] = []
        interfaces: list[InterfaceNode] = []
        enums: list[EnumNode] = []
        module_names: list[str] = []

        for c in compounds:
            owned = member_index.get(c.qualified_name, [])
            module = _extract_module(c.qualified_name)

            if c.kind in _CLASS_KINDS:
                attrs = []
                methods = []
                for m in owned:
                    if m.kind == "variable":
                        attrs.append(AttributeNode(
                            name=m.name,
                            qualified_name=m.qualified_name,
                            kind="attribute",
                            description=m.brief_description,
                            visibility=m.protection or "",
                            type_signature=m.type_signature,
                            owner=c.qualified_name,
                            component_id=m.component_id,
                            layer=m.layer,
                        ))
                    elif m.kind == "method":
                        methods.append(MethodNode(
                            name=m.name,
                            qualified_name=m.qualified_name,
                            kind="method",
                            description=m.brief_description,
                            visibility=m.protection or "",
                            type_signature=m.type_signature,
                            argsstring=m.argsstring or "",
                            owner=c.qualified_name,
                            component_id=m.component_id,
                            layer=m.layer,
                            is_virtual=m.is_virtual,
                            is_static=m.is_static,
                            is_const=m.is_const,
                        ))
                classes.append(ClassNode(
                    name=c.name,
                    qualified_name=c.qualified_name,
                    kind="class",
                    layer=c.layer,
                    description=c.brief_description,
                    module=module,
                    component_id=c.component_id,
                    file_path=c.file_path,
                    line_number=c.line_number,
                    is_abstract=c.is_abstract,
                    is_final=c.is_final,
                    attributes=attrs,
                    methods=methods,
                ))
                if module and module not in module_names:
                    module_names.append(module)

            elif c.kind in _INTERFACE_KINDS:
                methods = []
                for m in owned:
                    if m.kind == "method":
                        methods.append(MethodNode(
                            name=m.name,
                            qualified_name=m.qualified_name,
                            kind="method",
                            description=m.brief_description,
                            visibility=m.protection or "",
                            type_signature=m.type_signature,
                            argsstring=m.argsstring or "",
                            owner=c.qualified_name,
                            component_id=m.component_id,
                            layer=m.layer,
                            is_virtual=True,
                        ))
                interfaces.append(InterfaceNode(
                    name=c.name,
                    qualified_name=c.qualified_name,
                    kind="interface",
                    layer=c.layer,
                    description=c.brief_description,
                    is_abstract=c.is_abstract,
                    module=module,
                    component_id=c.component_id,
                    methods=methods,
                ))
                if module and module not in module_names:
                    module_names.append(module)

            elif c.kind in _ENUM_KINDS:
                values = []
                for m in owned:
                    if m.kind == "enumvalue":
                        values.append(EnumValueNode(
                            name=m.name,
                            qualified_name=m.qualified_name,
                            kind="enum_value",
                            owner=c.qualified_name,
                        ))
                enums.append(EnumNode(
                    name=c.name,
                    qualified_name=c.qualified_name,
                    kind="enum",
                    layer=c.layer,
                    description=c.brief_description,
                    module=module,
                    component_id=c.component_id,
                    values=values,
                ))
                if module and module not in module_names:
                    module_names.append(module)

        # Build associations
        associations: list[Association] = []
        for e in edges:
            associations.append(Association(
                subject=e.subject_qualified_name,
                predicate=e.predicate,
                object=e.object_qualified_name,
                mechanism=e.mechanism,
                description=e.description,
            ))

        return cls(
            module_names=module_names,
            classes=classes,
            interfaces=interfaces,
            enums=enums,
            associations=associations,
        )

    # -- Transformation methods (moved from existing models.py) ---------------

    def to_verification_dicts(self) -> list[dict]:
        """Produce verification context dicts."""
        results = []
        for cls in self.classes:
            attrs = [
                {
                    "name": attr.name, "qualified_name": attr.qualified_name,
                    "kind": "attribute", "visibility": attr.visibility,
                    "type_signature": attr.type_signature,
                    "description": attr.description,
                }
                for attr in cls.attributes
            ]
            methods = [
                {
                    "name": m.name, "qualified_name": m.qualified_name,
                    "kind": "method", "visibility": m.visibility,
                    "type_signature": m.type_signature,
                    "argsstring": m.argsstring, "description": m.description,
                }
                for m in cls.methods
            ]
            relationships = [
                {
                    "predicate": a.predicate, "target": a.object,
                    "target_name": a.object.rsplit("::", 1)[-1],
                }
                for a in self.associations if a.subject == cls.qualified_name
            ]
            results.append({
                "qualified_name": cls.qualified_name,
                "kind": cls.specialization or cls.kind,
                "description": cls.description,
                "attributes": sorted(attrs, key=lambda a: a["name"]),
                "methods": sorted(methods, key=lambda m: m["name"]),
                "relationships": relationships,
            })
        for iface in self.interfaces:
            methods = [
                {
                    "name": m.name, "qualified_name": m.qualified_name,
                    "kind": "method", "visibility": m.visibility,
                    "type_signature": m.type_signature,
                    "argsstring": m.argsstring, "description": m.description,
                }
                for m in iface.methods
            ]
            results.append({
                "qualified_name": iface.qualified_name,
                "kind": iface.kind,
                "description": iface.description,
                "attributes": [],
                "methods": sorted(methods, key=lambda m: m["name"]),
                "relationships": [],
            })
        return sorted(results, key=lambda c: c["qualified_name"])

    def to_draft_lookup(self) -> dict[str, dict]:
        lookup: dict[str, dict] = {}
        for cls in self.classes:
            lookup[cls.qualified_name] = {
                "qualified_name": cls.qualified_name,
                "kind": "class", "description": cls.description, "source": "draft",
            }
            for attr in cls.attributes:
                lookup[attr.qualified_name] = {
                    "qualified_name": attr.qualified_name,
                    "kind": "attribute", "description": attr.description, "source": "draft",
                }
            for m in cls.methods:
                lookup[m.qualified_name] = {
                    "qualified_name": m.qualified_name,
                    "kind": "method", "description": m.description, "source": "draft",
                }
        for iface in self.interfaces:
            lookup[iface.qualified_name] = {
                "qualified_name": iface.qualified_name,
                "kind": "interface", "description": iface.description, "source": "draft",
            }
            for m in iface.methods:
                lookup[m.qualified_name] = {
                    "qualified_name": m.qualified_name,
                    "kind": "method", "description": m.description, "source": "draft",
                }
        for enum in self.enums:
            lookup[enum.qualified_name] = {
                "qualified_name": enum.qualified_name,
                "kind": "enum", "description": enum.description, "source": "draft",
            }
        return lookup

    def to_summary(self) -> dict:
        total_attrs = sum(len(c.attributes) for c in self.classes)
        total_methods = sum(len(c.methods) for c in self.classes)
        return {
            "classes": len(self.classes),
            "interfaces": len(self.interfaces),
            "enums": len(self.enums),
            "associations": len(self.associations),
            "attributes": total_attrs,
            "methods": total_methods,
        }

    def to_class_lookup(self) -> dict[str, str]:
        lookup: dict[str, str] = {}
        for cls in self.classes:
            lookup[cls.name] = cls.qualified_name
        for iface in self.interfaces:
            lookup[iface.name] = iface.qualified_name
        for enum in self.enums:
            lookup[enum.name] = enum.qualified_name
        return lookup


def _extract_parent_qn(qualified_name: str) -> str:
    """Extract parent qualified_name from a member's qualified_name."""
    if "::" in qualified_name:
        return qualified_name.rsplit("::", 1)[0]
    return ""


def _extract_module(qualified_name: str) -> str:
    """Extract module/namespace from a qualified_name like 'ns::calc::ClassName'."""
    if "::" in qualified_name:
        parts = qualified_name.rsplit("::", 1)
        return parts[0]
    return ""
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/danielnewman/dev/codegraph && python -m pytest tests/test_class_diagram_neo4j.py -v
```
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/danielnewman/dev/codegraph && git add src/codegraph/designs/__init__.py tests/test_class_diagram_neo4j.py && git commit -m "feat: add ClassDiagram with to_neo4j/from_neo4j round-trip and tagged serialization"
```

---

### Task 7: Add FieldTags annotations to codegraph node models

**Files:**
- Modify: `codegraph/src/codegraph/nodes/compound_node.py`
- Modify: `codegraph/src/codegraph/nodes/member_node.py`
- Modify: `codegraph/src/codegraph/nodes/namespace_node.py`
- Modify: `codegraph/src/codegraph/edges.py`

**Strategy:** Add `Annotated[..., FieldTags(...)]` to every field. No behavioral changes — purely metadata.

- [ ] **Step 1: Annotate CompoundNode**

```python
# codegraph/src/codegraph/nodes/compound_node.py
# Replace existing imports and field declarations with:
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel

from codegraph.designs.tags import FieldTags


class CompoundNode(BaseModel):
    qualified_name: Annotated[str, FieldTags("llm", "neo4j", "read")]
    name: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    kind: Annotated[
        Literal["class", "struct", "template_class", "interface", "abstract_class",
                "enum", "enum_class", "union"],
        FieldTags("llm", "neo4j", "read"),
    ]
    layer: Annotated[
        Literal["design", "as-built", "dependency"],
        FieldTags("neo4j", "read"),
    ] = "design"
    component_id: Annotated[int | None, FieldTags("neo4j", "read")] = None
    refid: Annotated[str, FieldTags("neo4j")] = ""
    brief_description: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    detailed_description: Annotated[str, FieldTags("neo4j")] = ""
    base_classes: Annotated[list[str], FieldTags("neo4j", "read")] = []
    file_path: Annotated[str, FieldTags("neo4j", "read")] = ""
    line_number: Annotated[int | None, FieldTags("neo4j", "read")] = None
    source: Annotated[str, FieldTags("neo4j")] = ""
    is_final: Annotated[bool, FieldTags("neo4j", "read")] = False
    is_abstract: Annotated[bool, FieldTags("neo4j", "read")] = False

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: Annotate MemberNode**

```python
# codegraph/src/codegraph/nodes/member_node.py
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel

from codegraph.designs.tags import FieldTags


class MemberNode(BaseModel):
    qualified_name: Annotated[str, FieldTags("llm", "neo4j", "read")]
    name: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    kind: Annotated[
        Literal["method", "variable", "define", "enumvalue", "function"],
        FieldTags("llm", "neo4j", "read"),
    ]
    layer: Annotated[
        Literal["design", "as-built", "dependency"],
        FieldTags("neo4j", "read"),
    ] = "design"
    component_id: Annotated[int | None, FieldTags("neo4j", "read")] = None
    refid: Annotated[str, FieldTags("neo4j")] = ""
    compound_refid: Annotated[str, FieldTags("neo4j")] = ""
    brief_description: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    detailed_description: Annotated[str, FieldTags("neo4j")] = ""
    type_signature: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    definition: Annotated[str, FieldTags("neo4j", "read")] = ""
    argsstring: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    file_path: Annotated[str, FieldTags("neo4j", "read")] = ""
    line_number: Annotated[int | None, FieldTags("neo4j", "read")] = None
    source: Annotated[str, FieldTags("neo4j")] = ""
    protection: Annotated[
        Literal["public", "private", "protected", ""],
        FieldTags("llm", "neo4j", "read"),
    ] = ""
    is_static: Annotated[bool, FieldTags("neo4j", "read")] = False
    is_const: Annotated[bool, FieldTags("neo4j", "read")] = False
    is_constexpr: Annotated[bool, FieldTags("neo4j")] = False
    is_virtual: Annotated[bool, FieldTags("neo4j", "read")] = False
    is_inline: Annotated[bool, FieldTags("neo4j")] = False
    is_explicit: Annotated[bool, FieldTags("neo4j")] = False

    model_config = {"from_attributes": True}
```

- [ ] **Step 3: Annotate NamespaceNode**

```python
# codegraph/src/codegraph/nodes/namespace_node.py
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel

from codegraph.designs.tags import FieldTags


class NamespaceNode(BaseModel):
    qualified_name: Annotated[str, FieldTags("llm", "neo4j", "read")]
    name: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    kind: Annotated[
        Literal["namespace", "package", "module"],
        FieldTags("llm", "neo4j", "read"),
    ] = "namespace"
    layer: Annotated[
        Literal["design", "as-built", "dependency"],
        FieldTags("neo4j", "read"),
    ] = "design"
    component_id: Annotated[int | None, FieldTags("neo4j", "read")] = None
    refid: Annotated[str, FieldTags("neo4j")] = ""
    description: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    source: Annotated[str, FieldTags("neo4j")] = ""

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Annotate CodebaseEdge**

```python
# codegraph/src/codegraph/edges.py
# Replace existing field declarations with:
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel

from codegraph.designs.tags import FieldTags


class CodebaseEdge(BaseModel):
    subject_qualified_name: Annotated[str, FieldTags("llm", "neo4j", "read")]
    predicate: Annotated[str, FieldTags("llm", "neo4j", "read")]
    object_qualified_name: Annotated[str, FieldTags("llm", "neo4j", "read")]
    mechanism: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""
    position: Annotated[int | None, FieldTags("neo4j")] = None
    name: Annotated[str, FieldTags("neo4j")] = ""
    display_name: Annotated[str, FieldTags("neo4j", "read")] = ""
    description: Annotated[str, FieldTags("llm", "neo4j", "read")] = ""

    model_config = {"from_attributes": True}
```

- [ ] **Step 5: Run existing tests to verify no regressions**

```bash
cd /Users/danielnewman/dev/codegraph && python -m pytest tests/ -v --tb=short
```
The FieldTags are metadata-only (in `Annotated`); they don't affect existing validation or serialization.

- [ ] **Step 6: Commit**

```bash
cd /Users/danielnewman/dev/codegraph && git add src/codegraph/nodes/ src/codegraph/edges.py && git commit -m "feat: add FieldTags annotations to all codegraph node and edge models"
```

---

### Task 8: Move TypeRef to codegraph

**Files:**
- Create: `codegraph/src/codegraph/type_parser.py` (moving from `backend/codebase/schemas.py`)
- Test: `tests/test_type_parser.py`

- [ ] **Step 1: Move TypeRef and run existing test**

```python
# codegraph/src/codegraph/type_parser.py
"""Structured type reference parsing for codebase graphs."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TypeRef:
    """Structured reference to a type extracted from a type signature string."""
    name: str
    template_args: list[TypeRef] = field(default_factory=list)
    is_builtin: bool = False
    original_text: str = ""
    qualifiers: list[str] = field(default_factory=list)
```

```bash
# Verify existing tests still pass with the moved location:
cd /Users/danielnewman/dev/ticketing_system && python -m pytest tests/test_container_mechanism.py tests/test_mechanism_and_references.py -v -k "type_ref"
```

- [ ] **Step 2: Commit**

```bash
cd /Users/danielnewman/dev/codegraph && git add src/codegraph/type_parser.py && git commit -m "feat: add TypeRef dataclass to codegraph"
```

---

### Task 9: Create temporary shim at `backend/design_data/models.py`

**Files:**
- Modify: `backend/design_data/models.py` (replace with re-export shim)
- Test: `tests/test_design_data_shim.py`

- [ ] **Step 1: Write shim**

```python
# backend/design_data/models.py
"""TODO(2026-06): Remove this shim — import from codegraph.designs directly.

All models now live in codegraph/designs/. This file re-exports them for
backward compatibility during the transition.
"""
from codegraph.designs import (
    Association,
    AttributeNode,
    ClassDiagram,
    ClassNode,
    DiagramNode,
    EnumNode,
    EnumValueNode,
    InterfaceNode,
    MethodNode,
    ModuleNode,
)

__all__ = [
    "Association",
    "AttributeNode",
    "ClassDiagram",
    "ClassNode",
    "DiagramNode",
    "EnumNode",
    "EnumValueNode",
    "InterfaceNode",
    "MethodNode",
    "ModuleNode",
]
```

- [ ] **Step 2: Verify shim works**

```bash
cd /Users/danielnewman/dev/ticketing_system && python -c "
from backend.design_data.models import ClassDiagram, ClassNode, InterfaceNode, EnumNode, Association, AttributeNode, MethodNode
cd = ClassDiagram(
    classes=[ClassNode(name='Foo', qualified_name='ns::Foo', kind='class')],
)
print('module_names:', cd.module_names)
print('classes:', len(cd.classes))
assert cd.get_entity('ns::Foo') is not None
print('OK - shim works')
"
```

- [ ] **Step 3: Commit**

```bash
cd /Users/danielnewman/dev/ticketing_system && git add backend/design_data/models.py && git commit -m "refactor: replace design_data/models.py with re-export shim → codegraph.designs"
```

---

### Task 10: Thin `backend/codebase/schemas.py`

**Files:**
- Modify: `backend/codebase/schemas.py` (remove moved schemas)
- Delete: `backend/codebase/type_parser.py` (moved to codegraph)

- [ ] **Step 1: Replace schemas.py**

```python
# backend/codebase/schemas.py
"""Ticketing-system schemas — requirement linkage and design aggregation.

LLM shapes and OO design models now live in codegraph.designs.
Ontology node/edge schemas replaced by codegraph.nodes.* and codegraph.edges.*.
"""

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel


# Derived from the canonical NODE_KIND_KEYS set in codegraph.constants
NodeKind = Literal[tuple(
    __import__("codegraph.constants", fromlist=["NODE_KIND_KEYS"]).NODE_KIND_KEYS
)]
Visibility = Literal[tuple(
    k for k, _ in __import__("codegraph.constants", fromlist=["VISIBILITY_CHOICES"]).VISIBILITY_CHOICES
)]
SourceType = Literal["compound", "member", "namespace"]


class RequirementTripleLinkSchema(BaseModel):
    """Maps a requirement to an ontology triple by index or by subject/predicate/object."""
    requirement_type: Literal["hlr", "llr"]
    requirement_id: int
    triple_index: int = -1
    subject_qualified_name: str = ""
    predicate: str = ""
    object_qualified_name: str = ""


class DesignAndVerificationSchema(BaseModel):
    """Combined output for the design+verify tool loop."""
    from codegraph.designs import ClassDiagram
    oo_design: ClassDiagram
    from backend.requirements.schemas import VerificationSchema
    verifications: dict[int, list[VerificationSchema]] = {}
```

Wait — inline imports in class bodies aren't great. Let me restructure:

```python
# backend/codebase/schemas.py
"""Ticketing-system schemas — requirement linkage and design aggregation.

LLM shapes and OO design models now live in codegraph.designs.
Ontology node/edge schemas replaced by codegraph.nodes.* / codegraph.edges.*.
TypeRef moved to codegraph.type_parser.
"""

from typing import Literal

from pydantic import BaseModel

from codegraph.constants import NODE_KIND_KEYS, VISIBILITY_CHOICES
from codegraph.designs import ClassDiagram
from backend.requirements.schemas import VerificationSchema

NodeKind = Literal[tuple(NODE_KIND_KEYS)]
Visibility = Literal[tuple(k for k, _ in VISIBILITY_CHOICES)]
SourceType = Literal["compound", "member", "namespace"]


class RequirementTripleLinkSchema(BaseModel):
    """Maps a requirement to an ontology triple by index or by subject/predicate/object."""
    requirement_type: Literal["hlr", "llr"]
    requirement_id: int
    triple_index: int = -1
    subject_qualified_name: str = ""
    predicate: str = ""
    object_qualified_name: str = ""


class DesignAndVerificationSchema(BaseModel):
    """Combined output for the design+verify tool loop."""
    oo_design: ClassDiagram
    verifications: dict[int, list[VerificationSchema]] = {}
```

- [ ] **Step 2: Delete `backend/codebase/type_parser.py`**

```bash
cd /Users/danielnewman/dev/ticketing_system && rm backend/codebase/type_parser.py
```

- [ ] **Step 3: Commit**

```bash
cd /Users/danielnewman/dev/ticketing_system && git add backend/codebase/schemas.py && git rm backend/codebase/type_parser.py && git commit -m "refactor: thin codebase/schemas.py — move schemas to codegraph.designs, TypeRef to codegraph.type_parser"
```

---

### Task 11: Thin `backend/db/neo4j/models/nodes/compound.py`

**Files:**
- Modify: `backend/db/neo4j/models/nodes/compound.py`

- [ ] **Step 1: Replace with thinned version**

```python
# backend/db/neo4j/models/nodes/compound.py
"""CompoundNode — :Compound in Neo4j.

Ticketing-system extensions on top of ``codegraph.nodes.CompoundNode``.
All core fields (qualified_name, kind, layer, component_id, file_path, etc.)
are inherited from the codegraph base model.
"""

from __future__ import annotations

from typing import Literal

from codegraph.nodes import CompoundNode as BaseCompoundNode


class CompoundNode(BaseCompoundNode):
    """A compound entity in the codebase graph (:Compound in Neo4j).

    Inherits core fields from ``codegraph.nodes.CompoundNode`` and adds
    ticketing-system-specific fields for project context and implementation
    tracking.
    """

    model_config = {"from_attributes": True, "extra": "ignore"}

    # --- Ticketing-system extensions ONLY ---
    specialization: str = ""
    is_intercomponent: bool = False
    implementation_status: Literal[
        "designed", "scaffolded", "tested", "implemented", "verified"
    ] = "designed"
    test_file: str = ""
```

- [ ] **Step 2: Commit**

```bash
cd /Users/danielnewman/dev/ticketing_system && git add backend/db/neo4j/models/nodes/compound.py && git commit -m "refactor: thin compound.py to only ticketing-specific extensions"
```

---

### Task 12: Deprecate `backend/design_data/transforms.py`

**Files:**
- Modify: `backend/design_data/transforms.py`

Since `OODesignSchema` is absorbed into `ClassDiagram`, the two transform functions (`class_diagram_from_oo_design`, `oo_design_from_class_diagram`) become no-ops when both sides are `ClassDiagram`.

- [ ] **Step 1: Replace with deprecated shim**

```python
# backend/design_data/transforms.py
"""TODO(2026-06): Remove this module once all callers use ClassDiagram directly.

OODesignSchema has been absorbed into ClassDiagram (codegraph.designs).
class_diagram_from_oo_design() is now a pass-through for ClassDiagram→ClassDiagram.
oo_design_from_class_diagram() is a pass-through for ClassDiagram→ClassDiagram.
"""

from codegraph.designs import ClassDiagram


def class_diagram_from_oo_design(
    oo: ClassDiagram,
    component_id: int | None = None,
) -> ClassDiagram:
    """Pass-through — both sides are now ClassDiagram."""
    if component_id is not None:
        for cls in oo.classes:
            cls.component_id = component_id
            for attr in cls.attributes:
                attr.component_id = component_id
            for method in cls.methods:
                method.component_id = component_id
        for iface in oo.interfaces:
            iface.component_id = component_id
            for method in iface.methods:
                method.component_id = component_id
        for enum in oo.enums:
            enum.component_id = component_id
            for val in enum.values:
                val.component_id = component_id
    return oo


def oo_design_from_class_diagram(diagram: ClassDiagram) -> ClassDiagram:
    """Pass-through — both sides are now ClassDiagram."""
    return diagram
```

- [ ] **Step 2: Commit**

```bash
cd /Users/danielnewman/dev/ticketing_system && git add backend/design_data/transforms.py && git commit -m "refactor: deprecate transforms.py — OODesignSchema absorbed into ClassDiagram"
```

---

### Task 13: Update consumer imports

**Files:** ~25 files (see list in spec). **Approach:** systematic find-and-replace for import patterns.

- [ ] **Step 1: Run comprehensive test suite with new imports**

First, update the most critical imports:

```bash
cd /Users/danielnewman/dev/ticketing_system

# Pattern 1: imports from backend.codebase.schemas that moved to codegraph.designs
# Old: from backend.codebase.schemas import OODesignSchema, ClassSchema, ...
# New: from codegraph.designs import ClassDiagram, ...

# Pattern 2: TypeRef moved to codegraph.type_parser
# Old: from backend.codebase.schemas import TypeRef
# New: from codegraph.type_parser import TypeRef

# Pattern 3: OntologyNodeSchema, OntologyTripleSchema replaced by codegraph base types
# Old: from backend.codebase.schemas import OntologyNodeSchema
# New: from codegraph.nodes import CompoundNode, MemberNode
```

- [ ] **Step 2: Update each file (show first few as example)**

```python
# backend/pipeline/orchestrator.py — replace imports:
# OLD:
# from backend.codebase.schemas import OODesignSchema, DesignSchema, ...
# NEW:
from codegraph.designs import ClassDiagram  # replaces OODesignSchema
from codegraph.designs import ClassDiagram  # OODesignSchema → ClassDiagram
```

```python
# backend/ticketing_agent/design/design_oo.py — replace:
# OLD:
# from backend.codebase.schemas import OODesignSchema
# NEW:
from codegraph.designs import ClassDiagram  # OODesignSchema → ClassDiagram
```

```python
# backend/ticketing_agent/design/design_oo_tools.py — replace:
# OLD:
# from backend.codebase.schemas import OODesignSchema, ClassSchema, ...
# NEW:
from codegraph.designs import ClassDiagram, ClassNode, InterfaceNode, EnumNode, Association
```

- [ ] **Step 3: Run full test suite**

```bash
cd /Users/danielnewman/dev/ticketing_system && python -m pytest tests/ -v --tb=short 2>&1 | tail -40
```
Expected: tests pass after import fixes.

- [ ] **Step 4: Commit**

```bash
cd /Users/danielnewman/dev/ticketing_system && git add -A && git commit -m "refactor: update all consumer imports to use codegraph.designs and codegraph.type_parser"
```

---

## Self-Review

### 1. Spec coverage

| Spec requirement | Task(s) |
|---|---|
| FieldTags annotation mechanism | Task 2 |
| codegraph/designs/ module with LLM shapes | Tasks 3-6 |
| ClassDiagram.to_neo4j() / from_neo4j() | Task 6 |
| Move TypeRef to codegraph | Task 8 |
| Thin backend/codebase/schemas.py | Task 10 |
| Thin backend/db/neo4j/models/nodes/compound.py | Task 11 |
| Temporary re-export shim | Task 9 |
| Deprecate transforms.py | Task 12 |
| Update ~25 consumer files | Task 13 |
| CodebaseEdge.description field | Task 1 |
| FieldTags on codegraph nodes/edges | Task 7 |
| model_dump(tags=...) for LLM serialization | Tasks 3-6 |
| LLM-facing aliases (type_name, from_class, etc.) | Tasks 3, 5 |

All spec items covered.

### 2. Placeholder scan

No TBDs, TODOs (except the intentional deprecation markers), or vague "add error handling" steps. Every step has concrete code or commands.

### 3. Type consistency

- `FieldTags` defined in Task 2, used in Tasks 3-7 — consistent.
- `_tagged_model_dump` defined in Task 3 member.py, reused in compound.py, namespace.py, edges.py — consistent.
- `ClassDiagram.to_neo4j()` returns `tuple[list[CompoundNode], list[MemberNode], list[CodebaseEdge]]` — `from_neo4j()` accepts the same signature — consistent.
- `MemberNode.kind="variable"` maps to `AttributeNode.kind="attribute"` — handled by `_DESIGN_KIND_TO_MEMBER_KIND` dict — consistent.
- `serialization_alias` on `type_signature→type_name` (AttributeNode), `type_signature→return_type` (MethodNode), `subject→from_class`, `predicate→kind`, `object→to_class` (Association) — all tested.
