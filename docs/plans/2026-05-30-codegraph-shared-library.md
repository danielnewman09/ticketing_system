# Codegraph Shared Library — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a standalone `codegraph` Python package with Pydantic models, edge definitions, and constants for the shared Neo4j codebase graph data model.

**Architecture:** A single `codegraph` package with three modules — `nodes.py` (5 Pydantic BaseModel classes), `edges.py` (CodebaseEdge + predicate lists), `constants.py` (kinds, layers, visibility, predicate mappings, schema DDL). No database driver dependency. Both the ticketing system and Doxygen Dependency Parser will depend on it via `pip install`.

**Tech Stack:** Python 3.12+, Pydantic 2.x, pytest

**Repo location:** `/Users/danielnewman/dev/codegraph` (new directory, will become a git repo)

---

## File Structure

```
codegraph/
  pyproject.toml          # package metadata, depends on pydantic>=2
  src/codegraph/
    __init__.py            # re-exports FileNode, NamespaceNode, CompoundNode, MemberNode, ParameterNode, CodebaseEdge, PREDICATES, PREDICATE_TO_REL_TYPE, COMPOUND_KINDS, MEMBER_KINDS, NAMESPACE_KINDS, NODE_KINDS, LAYERS, VISIBILITY_CHOICES, CONSTRAINTS_AND_INDEXES
    nodes.py               # FileNode, NamespaceNode, CompoundNode, MemberNode, ParameterNode
    edges.py               # CodebaseEdge, PREDICATES
    constants.py           # kind lists, LAYERS, VISIBILITY_CHOICES, PREDICATE_TO_REL_TYPE, CONSTRAINTS_AND_INDEXES
  tests/
    __init__.py
    test_nodes.py
    test_edges.py
    test_constants.py
```

---

### Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "codegraph"
version = "0.1.0"
description = "Shared Neo4j codebase graph data model — Pydantic models for File, Namespace, Compound, Member, and Parameter nodes"
readme = "README.md"
license = "MIT"
requires-python = ">=3.12"
authors = [
    { name = "Daniel Newman" },
]
keywords = ["neo4j", "codegraph", "data-model", "codebase"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.12",
    "Topic :: Database",
]

dependencies = [
    "pydantic>=2.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[tool.hatch.build.targets.wheel]
packages = ["src/codegraph"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create tests/__init__.py (empty)**

```python
```

- [ ] **Step 3: Install in dev mode and verify**

```bash
cd /Users/danielnewman/dev/codegraph
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -c "import codegraph; print('ok')"
```

Expected: ImportError (no module yet — package dir doesn't exist, but hatch should create the stub)

- [ ] **Step 4: Commit**

```bash
cd /Users/danielnewman/dev/codegraph
git init
git add pyproject.toml tests/__init__.py
git commit -m "chore: scaffold codegraph project"
```

---

### Task 2: Constants module

**Files:**
- Create: `src/codegraph/constants.py`
- Test: `tests/test_constants.py`

- [ ] **Step 1: Write failing tests for constants**

Create `tests/test_constants.py`:

```python
from codegraph.constants import (
    COMPOUND_KINDS,
    MEMBER_KINDS,
    NAMESPACE_KINDS,
    NODE_KINDS,
    LAYERS,
    VISIBILITY_CHOICES,
    PREDICATES,
    PREDICATE_TO_REL_TYPE,
    CONSTRAINTS_AND_INDEXES,
)


class TestKinds:
    def test_compound_kinds_contains_expected(self):
        assert "class" in COMPOUND_KINDS
        assert "struct" in COMPOUND_KINDS
        assert "template_class" in COMPOUND_KINDS
        assert "interface" in COMPOUND_KINDS
        assert "abstract_class" in COMPOUND_KINDS
        assert "enum" in COMPOUND_KINDS
        assert "enum_class" in COMPOUND_KINDS
        assert len(COMPOUND_KINDS) == 7

    def test_member_kinds_contains_expected(self):
        assert "method" in MEMBER_KINDS
        assert "attribute" in MEMBER_KINDS
        assert "constant" in MEMBER_KINDS
        assert "enum_value" in MEMBER_KINDS
        assert "function" in MEMBER_KINDS
        assert len(MEMBER_KINDS) == 5

    def test_namespace_kinds_contains_expected(self):
        assert "namespace" in NAMESPACE_KINDS
        assert "package" in NAMESPACE_KINDS
        assert "module" in NAMESPACE_KINDS
        assert len(NAMESPACE_KINDS) == 3

    def test_node_kinds_is_union_of_all(self):
        all_kinds = set(COMPOUND_KINDS + MEMBER_KINDS + NAMESPACE_KINDS)
        assert set(NODE_KINDS) == all_kinds

    def test_kinds_are_disjoint(self):
        c = set(COMPOUND_KINDS)
        m = set(MEMBER_KINDS)
        n = set(NAMESPACE_KINDS)
        assert c.isdisjoint(m)
        assert c.isdisjoint(n)
        assert m.isdisjoint(n)


class TestLayers:
    def test_layers_contain_expected(self):
        assert LAYERS == ["design", "as-built", "dependency"]


class TestVisibility:
    def test_visibility_choices(self):
        assert VISIBILITY_CHOICES == ["public", "private", "protected"]


class TestPredicateMapping:
    def test_all_predicates_have_rel_type(self):
        for predicate in PREDICATES:
            assert predicate in PREDICATE_TO_REL_TYPE, f"Missing rel type for {predicate}"
            rel_type = PREDICATE_TO_REL_TYPE[predicate]
            assert rel_type == rel_type.upper(), f"{rel_type} must be UPPER_SNAKE_CASE"
            assert " " not in rel_type, f"{rel_type} must not contain spaces"

    def test_rel_types_map_back_to_predicates(self):
        # Every rel type value should map to exactly one predicate
        seen = set()
        for predicate, rel_type in PREDICATE_TO_REL_TYPE.items():
            assert rel_type not in seen, f"Duplicate rel type {rel_type}"
            seen.add(rel_type)

    def test_no_duplicate_predicates(self):
        assert len(PREDICATES) == len(set(PREDICATES))


class TestConstraintsAndIndexes:
    def test_is_list_of_strings(self):
        assert isinstance(CONSTRAINTS_AND_INDEXES, list)
        assert all(isinstance(s, str) for s in CONSTRAINTS_AND_INDEXES)
        assert len(CONSTRAINTS_AND_INDEXES) > 0

    def test_contains_file_constraint(self):
        assert any("CREATE CONSTRAINT file_refid" in s for s in CONSTRAINTS_AND_INDEXES)

    def test_contains_compound_indexes(self):
        statements = "\n".join(CONSTRAINTS_AND_INDEXES)
        assert "compound_refid" in statements
        assert "compound_name" in statements
        assert "compound_qualified" in statements
        assert "compound_kind" in statements
        assert "compound_layer" in statements
        assert "compound_source" in statements

    def test_contains_fulltext_search(self):
        statements = "\n".join(CONSTRAINTS_AND_INDEXES)
        assert "FULLTEXT INDEX doc_search" in statements
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/danielnewman/dev/codegraph && source .venv/bin/activate && pytest tests/test_constants.py -v
```

Expected: FAIL — ModuleNotFoundError for `codegraph.constants`

- [ ] **Step 3: Create src/codegraph/constants.py**

```python
"""Constants for the Neo4j codebase graph layer.

Defines the vocabulary of node kinds, layers, visibility, predicates,
and schema DDL used by both the ticketing system and Doxygen parser.
"""

# ---------------------------------------------------------------------------
# Node kinds — organized by Neo4j node label
# ---------------------------------------------------------------------------

COMPOUND_KINDS: list[str] = [
    "class",
    "struct",
    "template_class",
    "interface",
    "abstract_class",
    "enum",
    "enum_class",
]

MEMBER_KINDS: list[str] = [
    "method",
    "attribute",
    "constant",
    "enum_value",
    "function",
]

NAMESPACE_KINDS: list[str] = [
    "namespace",
    "package",
    "module",
]

NODE_KINDS: list[str] = COMPOUND_KINDS + MEMBER_KINDS + NAMESPACE_KINDS

# ---------------------------------------------------------------------------
# Layers — where a node originates
# ---------------------------------------------------------------------------

LAYERS: list[str] = ["design", "as-built", "dependency"]

# ---------------------------------------------------------------------------
# Visibility / access specifiers
# ---------------------------------------------------------------------------

VISIBILITY_CHOICES: list[str] = ["public", "private", "protected"]

# ---------------------------------------------------------------------------
# Predicates — lowercase names mapped to UPPER_SNAKE_CASE Neo4j rel types
# ---------------------------------------------------------------------------

PREDICATE_TO_REL_TYPE: dict[str, str] = {
    "associates": "ASSOCIATES",
    "aggregates": "AGGREGATES",
    "composes": "COMPOSES",
    "depends_on": "DEPENDS_ON",
    "generalizes": "GENERALIZES",
    "realizes": "REALIZES",
    "references": "REFERENCES",
    "invokes": "INVOKES",
    "has_argument": "HAS_ARGUMENT",
    "returns": "RETURNS",
    "type_argument": "TYPE_ARGUMENT",
    "template_param": "TEMPLATE_PARAM",
    "implements": "IMPLEMENTS",
}

PREDICATES: list[str] = list(PREDICATE_TO_REL_TYPE.keys())

# ---------------------------------------------------------------------------
# Schema DDL — constraints and indexes for Neo4j
# ---------------------------------------------------------------------------

CONSTRAINTS_AND_INDEXES: list[str] = [
    # Uniqueness constraints
    "CREATE CONSTRAINT file_refid IF NOT EXISTS FOR (f:File) REQUIRE f.refid IS UNIQUE",
    # Use INDEX instead of CONSTRAINT for refid to allow design-layer nodes
    # (which have no refid) to coexist with as-built/dependency nodes.
    "CREATE INDEX namespace_refid IF NOT EXISTS FOR (n:Namespace) ON (n.refid)",
    "CREATE INDEX compound_refid IF NOT EXISTS FOR (c:Compound) ON (c.refid)",
    "CREATE INDEX member_refid IF NOT EXISTS FOR (m:Member) ON (m.refid)",
    # Lookup indexes
    "CREATE INDEX file_name IF NOT EXISTS FOR (f:File) ON (f.name)",
    "CREATE INDEX file_path IF NOT EXISTS FOR (f:File) ON (f.path)",
    "CREATE INDEX namespace_name IF NOT EXISTS FOR (n:Namespace) ON (n.name)",
    "CREATE INDEX compound_name IF NOT EXISTS FOR (c:Compound) ON (c.name)",
    "CREATE INDEX compound_qualified IF NOT EXISTS FOR (c:Compound) ON (c.qualified_name)",
    "CREATE INDEX compound_kind IF NOT EXISTS FOR (c:Compound) ON (c.kind)",
    "CREATE INDEX member_name IF NOT EXISTS FOR (m:Member) ON (m.name)",
    "CREATE INDEX member_qualified IF NOT EXISTS FOR (m:Member) ON (m.qualified_name)",
    "CREATE INDEX member_kind IF NOT EXISTS FOR (m:Member) ON (m.kind)",
    # Layer indexes
    "CREATE INDEX compound_layer IF NOT EXISTS FOR (c:Compound) ON (c.layer)",
    "CREATE INDEX member_layer IF NOT EXISTS FOR (m:Member) ON (m.layer)",
    "CREATE INDEX namespace_layer IF NOT EXISTS FOR (n:Namespace) ON (n.layer)",
    # Source provenance
    "CREATE INDEX file_source IF NOT EXISTS FOR (f:File) ON (f.source)",
    "CREATE INDEX compound_source IF NOT EXISTS FOR (c:Compound) ON (c.source)",
    "CREATE INDEX member_source IF NOT EXISTS FOR (m:Member) ON (m.source)",
    "CREATE INDEX namespace_source IF NOT EXISTS FOR (n:Namespace) ON (n.source)",
    # Full-text search
    "CREATE FULLTEXT INDEX doc_search IF NOT EXISTS FOR (n:Compound|Member) ON EACH [n.name, n.qualified_name, n.brief_description, n.detailed_description]",
]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/danielnewman/dev/codegraph && source .venv/bin/activate && pytest tests/test_constants.py -v
```

Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/danielnewman/dev/codegraph
git add src/codegraph/constants.py tests/test_constants.py
git commit -m "feat: add constants module (kinds, layers, predicates, schema DDL)"
```

---

### Task 3: Node models — FileNode

**Files:**
- Create: `src/codegraph/nodes.py`
- Test: `tests/test_nodes.py`

- [ ] **Step 1: Write failing tests for FileNode**

Create `tests/test_nodes.py`:

```python
import pytest
from pydantic import ValidationError

from codegraph.nodes import FileNode


class TestFileNode:
    def test_minimal_creation(self):
        f = FileNode(refid="file_abc123")
        assert f.refid == "file_abc123"
        assert f.name == ""
        assert f.path == ""
        assert f.language == ""
        assert f.source == ""

    def test_full_creation(self):
        f = FileNode(
            refid="file_abc123",
            name="main.cpp",
            path="/src/main.cpp",
            language="C++",
            source="msd",
        )
        assert f.name == "main.cpp"
        assert f.path == "/src/main.cpp"
        assert f.language == "C++"
        assert f.source == "msd"

    def test_refid_is_required(self):
        with pytest.raises(ValidationError):
            FileNode()

    def test_extra_fields_ignored(self):
        f = FileNode(refid="file_abc123", extra_field="ignored")
        assert f.refid == "file_abc123"
        assert not hasattr(f, "extra_field")

    def test_model_dump_roundtrip(self):
        f = FileNode(
            refid="file_abc123",
            name="main.cpp",
            path="/src/main.cpp",
            language="C++",
            source="msd",
        )
        data = f.model_dump()
        f2 = FileNode.model_validate(data)
        assert f == f2

    def test_default_values_in_dump(self):
        f = FileNode(refid="file_abc123")
        data = f.model_dump()
        assert data["name"] == ""
        assert data["path"] == ""
        assert data["language"] == ""
        assert data["source"] == ""
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/danielnewman/dev/codegraph && source .venv/bin/activate && pytest tests/test_nodes.py -v
```

Expected: FAIL — ModuleNotFoundError for `codegraph.nodes`

- [ ] **Step 3: Create src/codegraph/nodes.py with FileNode**

```python
"""Node models for the Neo4j codebase graph.

Each class corresponds to a Neo4j node label and uses Pydantic for
validation and serialization. All fields have sensible defaults
unless marked as required.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class FileNode(BaseModel):
    """A source file in the codebase (:File in Neo4j).

    Unique by `refid` (Doxygen refid).
    """

    refid: str
    name: str = ""
    path: str = ""
    language: str = ""
    source: str = ""

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/danielnewman/dev/codegraph && source .venv/bin/activate && pytest tests/test_nodes.py -v
```

Expected: PASS (6 tests — all TestFileNode)

- [ ] **Step 5: Commit**

```bash
cd /Users/danielnewman/dev/codegraph
git add src/codegraph/nodes.py tests/test_nodes.py
git commit -m "feat: add FileNode model"
```

---

### Task 4: Node models — NamespaceNode

- [ ] **Step 1: Add failing tests for NamespaceNode**

Append to `tests/test_nodes.py`:

```python
class TestNamespaceNode:
    def test_minimal_creation(self):
        n = NamespaceNode(qualified_name="std")
        assert n.qualified_name == "std"
        assert n.name == ""
        assert n.kind == "namespace"
        assert n.layer == "design"
        assert n.refid == ""
        assert n.description == ""
        assert n.source == ""

    def test_full_creation(self):
        n = NamespaceNode(
            qualified_name="std::chrono",
            name="chrono",
            kind="namespace",
            layer="dependency",
            refid="namespacestd_1_1chrono",
            description="C++ chrono library",
            source="stdlib",
        )
        assert n.qualified_name == "std::chrono"
        assert n.name == "chrono"
        assert n.kind == "namespace"
        assert n.layer == "dependency"
        assert n.refid == "namespacestd_1_1chrono"
        assert n.description == "C++ chrono library"
        assert n.source == "stdlib"

    def test_qualified_name_required(self):
        with pytest.raises(ValidationError):
            NamespaceNode()

    def test_invalid_kind_rejected(self):
        with pytest.raises(ValidationError):
            NamespaceNode(qualified_name="std", kind="invalid_kind")

    def test_invalid_layer_rejected(self):
        with pytest.raises(ValidationError):
            NamespaceNode(qualified_name="std", layer="unknown_layer")

    def test_allowed_kinds(self):
        for kind in ["namespace", "package", "module"]:
            n = NamespaceNode(qualified_name="std", kind=kind)
            assert n.kind == kind

    def test_allowed_layers(self):
        for layer in ["design", "as-built", "dependency"]:
            n = NamespaceNode(qualified_name="std", layer=layer)
            assert n.layer == layer

    def test_model_dump_roundtrip(self):
        n = NamespaceNode(
            qualified_name="std::chrono",
            name="chrono",
            kind="namespace",
            layer="dependency",
            refid="ref123",
            description="desc",
            source="stdlib",
        )
        data = n.model_dump()
        n2 = NamespaceNode.model_validate(data)
        assert n == n2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/danielnewman/dev/codegraph && source .venv/bin/activate && pytest tests/test_nodes.py::TestNamespaceNode -v
```

Expected: FAIL — `NameError: name 'NamespaceNode' is not defined`

- [ ] **Step 3: Add NamespaceNode to src/codegraph/nodes.py**

Append after `FileNode`:

```python
class NamespaceNode(BaseModel):
    """A namespace entity in the codebase graph (:Namespace in Neo4j).

    Namespaces group compounds into modules. They form a hierarchy via
    COMPOSES edges (e.g. `std` COMPOSES `std::chrono`).
    """

    qualified_name: str
    name: str = ""
    kind: Literal["namespace", "package", "module"] = "namespace"
    layer: Literal["design", "as-built", "dependency"] = "design"
    refid: str = ""
    description: str = ""
    source: str = ""

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/danielnewman/dev/codegraph && source .venv/bin/activate && pytest tests/test_nodes.py -v
```

Expected: PASS (14 tests — 6 TestFileNode + 8 TestNamespaceNode)

- [ ] **Step 5: Commit**

```bash
cd /Users/danielnewman/dev/codegraph
git add src/codegraph/nodes.py tests/test_nodes.py
git commit -m "feat: add NamespaceNode model"
```

---

### Task 5: Node models — CompoundNode

- [ ] **Step 1: Add failing tests for CompoundNode**

Append to `tests/test_nodes.py`:

```python
class TestCompoundNode:
    def test_minimal_creation(self):
        c = CompoundNode(qualified_name="calc::Calculator", kind="class")
        assert c.qualified_name == "calc::Calculator"
        assert c.name == ""
        assert c.kind == "class"
        assert c.layer == "design"
        assert c.refid == ""
        assert c.description == ""
        assert c.brief_description == ""
        assert c.detailed_description == ""
        assert c.base_classes == []
        assert c.file_path == ""
        assert c.line_number is None
        assert c.source == ""
        assert c.protection == ""
        assert c.is_final is False
        assert c.is_abstract is False

    def test_full_creation(self):
        c = CompoundNode(
            qualified_name="calc::Calculator",
            name="Calculator",
            kind="class",
            layer="as-built",
            refid="classcalc_1_1Calculator",
            description="A simple calculator",
            brief_description="A simple calculator class",
            detailed_description="Performs arithmetic operations with precision tracking.",
            base_classes=["BaseCalc", "IPrintable"],
            file_path="/src/calculator.h",
            line_number=42,
            source="msd",
            protection="public",
            is_final=True,
            is_abstract=False,
        )
        assert c.name == "Calculator"
        assert c.layer == "as-built"
        assert c.refid == "classcalc_1_1Calculator"
        assert c.description == "A simple calculator"
        assert c.brief_description == "A simple calculator class"
        assert c.detailed_description == "Performs arithmetic operations with precision tracking."
        assert c.base_classes == ["BaseCalc", "IPrintable"]
        assert c.file_path == "/src/calculator.h"
        assert c.line_number == 42
        assert c.source == "msd"
        assert c.protection == "public"
        assert c.is_final is True
        assert c.is_abstract is False

    def test_qualified_name_required(self):
        with pytest.raises(ValidationError):
            CompoundNode(kind="class")

    def test_kind_required(self):
        with pytest.raises(ValidationError):
            CompoundNode(qualified_name="calc::Calculator")

    def test_invalid_kind_rejected(self):
        with pytest.raises(ValidationError):
            CompoundNode(qualified_name="calc::Calculator", kind="not_a_kind")

    def test_invalid_layer_rejected(self):
        with pytest.raises(ValidationError):
            CompoundNode(qualified_name="calc::Calculator", kind="class", layer="bogus")

    def test_allowed_kinds(self):
        for kind in ["class", "struct", "template_class", "interface", "abstract_class", "enum", "enum_class"]:
            c = CompoundNode(qualified_name="calc::Foo", kind=kind)
            assert c.kind == kind

    def test_base_classes_default_empty(self):
        c = CompoundNode(qualified_name="calc::Foo", kind="class")
        assert c.base_classes == []

    def test_model_dump_roundtrip(self):
        c = CompoundNode(
            qualified_name="calc::Calculator",
            name="Calculator",
            kind="class",
            layer="as-built",
            refid="ref123",
            description="desc",
            brief_description="brief",
            detailed_description="detailed",
            base_classes=["Base"],
            file_path="/src/calc.h",
            line_number=42,
            source="msd",
            protection="public",
            is_final=False,
            is_abstract=True,
        )
        data = c.model_dump()
        c2 = CompoundNode.model_validate(data)
        assert c == c2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/danielnewman/dev/codegraph && source .venv/bin/activate && pytest tests/test_nodes.py::TestCompoundNode -v
```

Expected: FAIL — `NameError: name 'CompoundNode' is not defined`

- [ ] **Step 3: Add CompoundNode to src/codegraph/nodes.py**

Append after `NamespaceNode`:

```python
class CompoundNode(BaseModel):
    """A compound entity in the codebase graph (:Compound in Neo4j).

    Compounds are the top-level containers — classes, structs, interfaces,
    enums — that own members and participate in associations.

    The `kind` field refines the specific type. The `layer` field indicates
    origin: 'design' (agent-created), 'as-built' (parsed from code), or
    'dependency' (external library).
    """

    qualified_name: str
    name: str = ""
    kind: Literal["class", "struct", "template_class", "interface", "abstract_class", "enum", "enum_class"]
    layer: Literal["design", "as-built", "dependency"] = "design"
    refid: str = ""
    description: str = ""
    brief_description: str = ""
    detailed_description: str = ""
    base_classes: list[str] = []
    file_path: str = ""
    line_number: int | None = None
    source: str = ""
    protection: Literal["public", "private", "protected", ""] = ""
    is_final: bool = False
    is_abstract: bool = False

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/danielnewman/dev/codegraph && source .venv/bin/activate && pytest tests/test_nodes.py -v
```

Expected: PASS (23 tests — 6 FileNode + 8 NamespaceNode + 9 CompoundNode)

- [ ] **Step 5: Commit**

```bash
cd /Users/danielnewman/dev/codegraph
git add src/codegraph/nodes.py tests/test_nodes.py
git commit -m "feat: add CompoundNode model"
```

---

### Task 6: Node models — MemberNode

- [ ] **Step 1: Add failing tests for MemberNode**

Append to `tests/test_nodes.py`:

```python
class TestMemberNode:
    def test_minimal_creation(self):
        m = MemberNode(qualified_name="calc::Calculator::add", kind="method")
        assert m.qualified_name == "calc::Calculator::add"
        assert m.name == ""
        assert m.kind == "method"
        assert m.layer == "design"
        assert m.refid == ""
        assert m.compound_refid == ""
        assert m.description == ""
        assert m.brief_description == ""
        assert m.detailed_description == ""
        assert m.type_signature == ""
        assert m.definition == ""
        assert m.argsstring == ""
        assert m.file_path == ""
        assert m.line_number is None
        assert m.source == ""
        assert m.protection == ""
        assert m.is_static is False
        assert m.is_const is False
        assert m.is_constexpr is False
        assert m.is_virtual is False
        assert m.is_inline is False
        assert m.is_explicit is False

    def test_full_creation(self):
        m = MemberNode(
            qualified_name="calc::Calculator::add",
            name="add",
            kind="method",
            layer="as-built",
            refid="classcalc_1_1Calculator_1a123",
            compound_refid="classcalc_1_1Calculator",
            description="Add two numbers",
            brief_description="Addition operation",
            detailed_description="Adds two integers and returns the result.",
            type_signature="int",
            definition="int Calculator::add(int a, int b)",
            argsstring="(int a, int b)",
            file_path="/src/calculator.cpp",
            line_number=15,
            source="msd",
            protection="public",
            is_static=False,
            is_const=True,
            is_constexpr=False,
            is_virtual=False,
            is_inline=True,
            is_explicit=False,
        )
        assert m.name == "add"
        assert m.layer == "as-built"
        assert m.type_signature == "int"
        assert m.definition == "int Calculator::add(int a, int b)"
        assert m.argsstring == "(int a, int b)"
        assert m.compound_refid == "classcalc_1_1Calculator"
        assert m.protection == "public"
        assert m.is_const is True
        assert m.is_inline is True

    def test_qualified_name_required(self):
        with pytest.raises(ValidationError):
            MemberNode(kind="method")

    def test_kind_required(self):
        with pytest.raises(ValidationError):
            MemberNode(qualified_name="calc::Calculator::add")

    def test_invalid_kind_rejected(self):
        with pytest.raises(ValidationError):
            MemberNode(qualified_name="calc::Calculator::add", kind="not_a_kind")

    def test_allowed_kinds(self):
        for kind in ["method", "attribute", "constant", "enum_value", "function"]:
            m = MemberNode(qualified_name="calc::foo", kind=kind)
            assert m.kind == kind

    def test_boolean_flags_default_false(self):
        m = MemberNode(qualified_name="calc::Calculator::add", kind="method")
        assert m.is_static is False
        assert m.is_const is False
        assert m.is_constexpr is False
        assert m.is_virtual is False
        assert m.is_inline is False
        assert m.is_explicit is False

    def test_model_dump_roundtrip(self):
        m = MemberNode(
            qualified_name="calc::Calculator::add",
            name="add",
            kind="method",
            layer="as-built",
            refid="ref123",
            compound_refid="compound_ref456",
            description="desc",
            brief_description="brief",
            detailed_description="detailed",
            type_signature="int",
            definition="def",
            argsstring="(int a)",
            file_path="/src/calc.cpp",
            line_number=15,
            source="msd",
            protection="public",
            is_static=False,
            is_const=True,
            is_constexpr=False,
            is_virtual=False,
            is_inline=True,
            is_explicit=False,
        )
        data = m.model_dump()
        m2 = MemberNode.model_validate(data)
        assert m == m2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/danielnewman/dev/codegraph && source .venv/bin/activate && pytest tests/test_nodes.py::TestMemberNode -v
```

Expected: FAIL — `NameError: name 'MemberNode' is not defined`

- [ ] **Step 3: Add MemberNode to src/codegraph/nodes.py**

Append after `CompoundNode`:

```python
class MemberNode(BaseModel):
    """A member entity in the codebase graph (:Member in Neo4j).

    Members are owned by compounds — methods and attributes on classes,
    values inside enums, constants inside namespaces.
    """

    qualified_name: str
    name: str = ""
    kind: Literal["method", "attribute", "constant", "enum_value", "function"]
    layer: Literal["design", "as-built", "dependency"] = "design"
    refid: str = ""
    compound_refid: str = ""
    description: str = ""
    brief_description: str = ""
    detailed_description: str = ""
    type_signature: str = ""
    definition: str = ""
    argsstring: str = ""
    file_path: str = ""
    line_number: int | None = None
    source: str = ""
    protection: Literal["public", "private", "protected", ""] = ""
    is_static: bool = False
    is_const: bool = False
    is_constexpr: bool = False
    is_virtual: bool = False
    is_inline: bool = False
    is_explicit: bool = False

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/danielnewman/dev/codegraph && source .venv/bin/activate && pytest tests/test_nodes.py -v
```

Expected: PASS (31 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/danielnewman/dev/codegraph
git add src/codegraph/nodes.py tests/test_nodes.py
git commit -m "feat: add MemberNode model"
```

---

### Task 7: Node models — ParameterNode

- [ ] **Step 1: Add failing tests for ParameterNode**

Append to `tests/test_nodes.py`:

```python
class TestParameterNode:
    def test_minimal_creation(self):
        p = ParameterNode(position=0, name="x")
        assert p.position == 0
        assert p.name == "x"
        assert p.type == ""
        assert p.default_value == ""
        assert p.member_refid == ""

    def test_full_creation(self):
        p = ParameterNode(
            position=1,
            name="epsilon",
            type="double",
            default_value="1e-6",
            member_refid="method_ref_123",
        )
        assert p.position == 1
        assert p.name == "epsilon"
        assert p.type == "double"
        assert p.default_value == "1e-6"
        assert p.member_refid == "method_ref_123"

    def test_position_required(self):
        with pytest.raises(ValidationError):
            ParameterNode(name="x")

    def test_name_required(self):
        with pytest.raises(ValidationError):
            ParameterNode(position=0)

    def test_model_dump_roundtrip(self):
        p = ParameterNode(
            position=0,
            name="x",
            type="int",
            default_value="0",
            member_refid="ref123",
        )
        data = p.model_dump()
        p2 = ParameterNode.model_validate(data)
        assert p == p2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/danielnewman/dev/codegraph && source .venv/bin/activate && pytest tests/test_nodes.py::TestParameterNode -v
```

Expected: FAIL — `NameError: name 'ParameterNode' is not defined`

- [ ] **Step 3: Add ParameterNode to src/codegraph/nodes.py**

Append after `MemberNode`:

```python
class ParameterNode(BaseModel):
    """A function/method parameter (:Parameter in Neo4j).

    Connected to its owning member via HAS_PARAMETER edge.
    """

    position: int
    name: str
    type: str = ""
    default_value: str = ""
    member_refid: str = ""

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/danielnewman/dev/codegraph && source .venv/bin/activate && pytest tests/test_nodes.py -v
```

Expected: PASS (36 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/danielnewman/dev/codegraph
git add src/codegraph/nodes.py tests/test_nodes.py
git commit -m "feat: add ParameterNode model"
```

---

### Task 8: Edge model — CodebaseEdge

**Files:**
- Create: `src/codegraph/edges.py`
- Test: `tests/test_edges.py`

- [ ] **Step 1: Write failing tests for CodebaseEdge**

Create `tests/test_edges.py`:

```python
import pytest
from pydantic import ValidationError

from codegraph.edges import CodebaseEdge, PREDICATES


class TestCodebaseEdge:
    def test_minimal_creation(self):
        e = CodebaseEdge(
            subject_qualified_name="calc::Calculator",
            predicate="composes",
            object_qualified_name="calc::Calculator::add",
        )
        assert e.subject_qualified_name == "calc::Calculator"
        assert e.predicate == "composes"
        assert e.object_qualified_name == "calc::Calculator::add"
        assert e.mechanism == ""
        assert e.position is None
        assert e.name == ""
        assert e.display_name == ""

    def test_full_creation(self):
        e = CodebaseEdge(
            subject_qualified_name="calc::Calculator",
            predicate="aggregates",
            object_qualified_name="calc::Logger",
            mechanism="std::shared_ptr",
            position=None,
            name="",
            display_name="",
        )
        assert e.mechanism == "std::shared_ptr"

    def test_with_template_param_fields(self):
        e = CodebaseEdge(
            subject_qualified_name="calc::Container",
            predicate="template_param",
            object_qualified_name="T",
            position=0,
            name="T",
            display_name="typename T",
        )
        assert e.position == 0
        assert e.name == "T"
        assert e.display_name == "typename T"

    def test_subject_required(self):
        with pytest.raises(ValidationError):
            CodebaseEdge(predicate="composes", object_qualified_name="calc::foo")

    def test_predicate_required(self):
        with pytest.raises(ValidationError):
            CodebaseEdge(
                subject_qualified_name="calc::Calculator",
                object_qualified_name="calc::foo",
            )

    def test_object_required(self):
        with pytest.raises(ValidationError):
            CodebaseEdge(
                subject_qualified_name="calc::Calculator",
                predicate="composes",
            )

    def test_any_predicate_in_list_is_accepted(self):
        for predicate in PREDICATES:
            e = CodebaseEdge(
                subject_qualified_name="a",
                predicate=predicate,
                object_qualified_name="b",
            )
            assert e.predicate == predicate

    def test_model_dump_roundtrip(self):
        e = CodebaseEdge(
            subject_qualified_name="calc::Calculator",
            predicate="composes",
            object_qualified_name="calc::Calculator::add",
            mechanism="",
            position=None,
            name="",
            display_name="",
        )
        data = e.model_dump()
        e2 = CodebaseEdge.model_validate(data)
        assert e == e2

    def test_position_stays_none_when_not_set(self):
        e = CodebaseEdge(
            subject_qualified_name="a",
            predicate="composes",
            object_qualified_name="b",
        )
        data = e.model_dump()
        assert data["position"] is None


class TestPredicatesImport:
    def test_predicates_is_list_of_strings(self):
        assert isinstance(PREDICATES, list)
        assert all(isinstance(p, str) for p in PREDICATES)
        assert len(PREDICATES) > 0

    def test_predicates_contain_core_edges(self):
        for pred in ["composes", "depends_on", "generalizes", "references", "invokes", "returns"]:
            assert pred in PREDICATES
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/danielnewman/dev/codegraph && source .venv/bin/activate && pytest tests/test_edges.py -v
```

Expected: FAIL — ModuleNotFoundError for `codegraph.edges`

- [ ] **Step 3: Create src/codegraph/edges.py**

```python
"""Edge definitions for the Neo4j codebase graph.

CodebaseEdge represents a directed relationship between two codebase
nodes. Stored in Neo4j as a typed relationship with the predicate name
uppercased (e.g. 'composes' → COMPOSES).
"""

from __future__ import annotations

from pydantic import BaseModel

from codegraph.constants import PREDICATES


class CodebaseEdge(BaseModel):
    """A directed relationship between two codebase nodes.

    Stored in Neo4j as a typed relationship with the predicate name
    uppercased (e.g. 'composes' → COMPOSES). Identified by subject +
    predicate + object.
    """

    subject_qualified_name: str
    predicate: str  # Must be one of PREDICATES
    object_qualified_name: str
    mechanism: str = ""           # Container type (e.g. "std::vector" for aggregates)
    position: int | None = None   # Position for type_argument edges (0-based)
    name: str = ""                # Parameter name for template_param edges
    display_name: str = ""        # Alias display name (e.g. "std::string" for std::basic_string)

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/danielnewman/dev/codegraph && source .venv/bin/activate && pytest tests/test_edges.py -v
```

Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/danielnewman/dev/codegraph
git add src/codegraph/edges.py tests/test_edges.py
git commit -m "feat: add CodebaseEdge model"
```

---

### Task 9: Package __init__.py — re-exports

**Files:**
- Create: `src/codegraph/__init__.py`

- [ ] **Step 1: Write test for public API**

Create `tests/test_public_api.py`:

```python
"""Test that the public API surface is importable from codegraph directly."""


def test_import_nodes():
    from codegraph import FileNode, NamespaceNode, CompoundNode, MemberNode, ParameterNode
    assert FileNode is not None
    assert NamespaceNode is not None
    assert CompoundNode is not None
    assert MemberNode is not None
    assert ParameterNode is not None


def test_import_edges():
    from codegraph import CodebaseEdge, PREDICATES
    assert CodebaseEdge is not None
    assert isinstance(PREDICATES, list)


def test_import_constants():
    from codegraph import (
        COMPOUND_KINDS,
        MEMBER_KINDS,
        NAMESPACE_KINDS,
        NODE_KINDS,
        LAYERS,
        VISIBILITY_CHOICES,
        PREDICATE_TO_REL_TYPE,
        CONSTRAINTS_AND_INDEXES,
    )
    assert isinstance(COMPOUND_KINDS, list)
    assert isinstance(MEMBER_KINDS, list)
    assert isinstance(NAMESPACE_KINDS, list)
    assert isinstance(NODE_KINDS, list)
    assert isinstance(LAYERS, list)
    assert isinstance(VISIBILITY_CHOICES, list)
    assert isinstance(PREDICATE_TO_REL_TYPE, dict)
    assert isinstance(CONSTRAINTS_AND_INDEXES, list)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/danielnewman/dev/codegraph && source .venv/bin/activate && pytest tests/test_public_api.py -v
```

Expected: FAIL — ModuleNotFoundError for `codegraph` (no __init__.py yet)

- [ ] **Step 3: Create src/codegraph/__init__.py**

```python
"""Codegraph — shared Neo4j codebase graph data model.

Provides Pydantic models for Nodes (File, Namespace, Compound, Member, Parameter),
edge definitions (CodebaseEdge), and constants (kinds, layers, predicates,
schema DDL).
"""

from codegraph.constants import (
    COMPOUND_KINDS,
    CONSTRAINTS_AND_INDEXES,
    LAYERS,
    MEMBER_KINDS,
    NAMESPACE_KINDS,
    NODE_KINDS,
    PREDICATES,
    PREDICATE_TO_REL_TYPE,
    VISIBILITY_CHOICES,
)
from codegraph.edges import CodebaseEdge
from codegraph.nodes import (
    CompoundNode,
    FileNode,
    MemberNode,
    NamespaceNode,
    ParameterNode,
)

__all__ = [
    # Nodes
    "CompoundNode",
    "FileNode",
    "MemberNode",
    "NamespaceNode",
    "ParameterNode",
    # Edges
    "CodebaseEdge",
    "PREDICATES",
    # Constants
    "COMPOUND_KINDS",
    "CONSTRAINTS_AND_INDEXES",
    "LAYERS",
    "MEMBER_KINDS",
    "NAMESPACE_KINDS",
    "NODE_KINDS",
    "PREDICATE_TO_REL_TYPE",
    "VISIBILITY_CHOICES",
]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/danielnewman/dev/codegraph && source .venv/bin/activate && pytest tests/test_public_api.py -v
```

Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/danielnewman/dev/codegraph
git add src/codegraph/__init__.py tests/test_public_api.py
git commit -m "feat: add package __init__.py with public re-exports"
```

---

### Task 10: README and final verification

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create README.md**

Create `README.md`:

```markdown
# Codegraph

Shared Neo4j codebase graph data model.

Provides Pydantic models for codebase graph nodes (`File`, `Namespace`,
`Compound`, `Member`, `Parameter`), edge definitions (`CodebaseEdge`),
and constants (kinds, layers, predicates, schema DDL).

Used by:
- [Doxygen Dependency Parser](https://github.com/danielnewman09/Doxygen-Dependency-Parser) — populates `as-built` and `dependency` layers
- [Ticketing System](https://github.com/danielnewman09/ticketing-system) — adds the `design` layer

## Install

```bash
pip install codegraph
```

## Usage

```python
from codegraph import CompoundNode, MemberNode, CodebaseEdge

# Create a design-layer class
calc = CompoundNode(
    qualified_name="calc::Calculator",
    name="Calculator",
    kind="class",
    layer="design",
    protection="public",
)

# Add a method
add = MemberNode(
    qualified_name="calc::Calculator::add",
    name="add",
    kind="method",
    layer="design",
    type_signature="int",
    argsstring="(int a, int b)",
    protection="public",
)

# Define a relationship
edge = CodebaseEdge(
    subject_qualified_name="calc::Calculator",
    predicate="composes",
    object_qualified_name="calc::Calculator::add",
)

# Serialize to dict for Neo4j driver
calc_dict = calc.model_dump()
```
```

- [ ] **Step 2: Run full test suite**

```bash
cd /Users/danielnewman/dev/codegraph && source .venv/bin/activate && pytest -v
```

Expected: PASS (50 tests across all test files)

- [ ] **Step 3: Commit**

```bash
cd /Users/danielnewman/dev/codegraph
git add README.md
git commit -m "docs: add README"
```
