# Codebase Graph Primitives Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the tangled codebase data models with clean Pydantic graph primitives that mirror Neo4j node types, remove deprecated SQLAlchemy ontology models, and update all consumers.

**Architecture:** Three new Pydantic node models (`CompoundNode`, `MemberNode`, `NamespaceNode`) replace the single `DesignNode`. A `CodebaseEdge` model replaces `DesignTripleUpdate`. Constants move from `db/models/ontology.py` to `db/neo4j/models/constants.py`. Repository and connection code are updated. Deprecated ORM models are deleted. Adapter functions bridge new models to old shapes (`ClassDiagram`, `OODesignSchema`) during transition.

**Tech Stack:** Python 3.12+, Pydantic v2, Neo4j, SQLAlchemy (for removal only)

---

## File Structure

### Created files

| File | Responsibility |
|------|---------------|
| `backend/db/neo4j/models/__init__.py` | Package init, re-exports all primitives |
| `backend/db/neo4j/models/constants.py` | `COMPOUND_KINDS`, `MEMBER_KINDS`, `NAMESPACE_KINDS`, `NODE_KINDS`, `TYPE_KINDS`, `VALUE_KINDS`, `VISIBILITY_CHOICES`, `LAYERS`, `LANGUAGE_SPECIALIZATIONS`, `SUPPORTED_LANGUAGES`, `PREDICATES`, `valid_specializations()`, `PREDICATE_TO_REL_TYPE` |
| `backend/db/neo4j/models/nodes/__init__.py` | Package init, re-exports node models |
| `backend/db/neo4j/models/nodes/compound.py` | `CompoundNode` Pydantic model |
| `backend/db/neo4j/models/nodes/member.py` | `MemberNode` Pydantic model |
| `backend/db/neo4j/models/nodes/namespace.py` | `NamespaceNode` Pydantic model |
| `backend/db/neo4j/models/edges.py` | `CodebaseEdge` model, `PREDICATES` list |
| `tests/test_codebase_graph_primitives.py` | Tests for all new models and constants |

### Modified files

| File | Change |
|------|--------|
| `backend/db/neo4j/repositories/design.py` | Use `CompoundNode`/`MemberNode`/`NamespaceNode`/`CodebaseEdge` instead of `DesignNode`/`DesignTripleUpdate`. Update Cypher queries to use `:Compound`/`:Member`/`:Namespace` labels + `layer` property. |
| `backend/db/neo4j/repositories/models/__init__.py` | Remove `DesignNode`/`DesignTripleUpdate` re-exports, re-export from new models location |
| `backend/db/neo4j/repositories/__init__.py` | Update imports |
| `backend/db/neo4j/__init__.py` | Update imports |
| `backend/db/neo4j/connection.py` | Update `ensure_constraints()` and `ensure_design_constraints()` to create `:Compound`/`:Member`/`:Namespace` indexes instead of `:Design` |
| `backend/db/models/__init__.py` | Remove all ontology re-exports (`OntologyNode`, `OntologyTriple`, `Predicate`, constants). Keep only the remaining models. |
| `backend/db/models/tasks.py` | Remove `OntologyNode` import/relationship |
| `backend/db/models/components.py` | Remove `OntologyNode` import/relationship |
| `backend/codebase/schemas.py` | Change import from `backend.db.models.ontology` to `backend.db.neo4j.models.constants` |
| `backend/ticketing_agent/design/design_oo_prompt.py` | Change import from `backend.db.models.ontology` to `backend.db.neo4j.models.constants` |
| `backend/ticketing_agent/design/design_ontology.py` | Change imports from `backend.db.models` and `backend.db.models.ontology` to `backend.db.neo4j.models` and `backend.db.neo4j.models.constants` |
| `backend/ticketing_agent/design/design_ontology_prompt.py` | Change import from `backend.db.models.ontology` to `backend.db.neo4j.models.constants` |
| `backend/requirements/services/persistence.py` | Change import from `backend.db.neo4j.repositories.models.design` to `backend.db.neo4j.models` |
| `backend/pipeline/orchestrator.py` | Update imports |
| `scripts/migrate_phase1_design_to_neo4j.py` | Update to use new models or mark as legacy |
| Various test files | Update imports |

### Deleted files

| File | Reason |
|------|--------|
| `backend/db/models/ontology.py` | Deprecated SQLAlchemy ORM models — replaced by Neo4j models |
| `backend/db/neo4j/repositories/models/design.py` | Replaced by typed node models |

### Left intact (Phase 2)

- `backend/codebase/schemas.py` — Adapter functions bridge to old shapes
- `backend/design_data/` — Adapter functions bridge to `ClassDiagram` etc.

---

## Task 1: Create Constants Module

**Files:**
- Create: `backend/db/neo4j/models/constants.py`
- Create: `backend/db/neo4j/models/__init__.py` (placeholder)
- Test: `tests/test_codebase_graph_primitives.py`

- [ ] **Step 1: Write the failing test for constants**

Create `tests/test_codebase_graph_primitives.py`:

```python
"""Tests for codebase graph primitives — constants, node models, and edge models."""

import pytest


class TestConstants:
    """Tests for constant values moved from db/models/ontology.py."""

    def test_compound_kinds(self):
        from backend.db.neo4j.models.constants import COMPOUND_KINDS
        assert "class" in COMPOUND_KINDS
        assert "interface" in COMPOUND_KINDS
        assert "enum" in COMPOUND_KINDS
        assert "method" not in COMPOUND_KINDS

    def test_member_kinds(self):
        from backend.db.neo4j.models.constants import MEMBER_KINDS
        assert "method" in MEMBER_KINDS
        assert "attribute" in MEMBER_KINDS
        assert "class" not in MEMBER_KINDS

    def test_namespace_kinds(self):
        from backend.db.neo4j.models.constants import NAMESPACE_KINDS
        assert "namespace" in NAMESPACE_KINDS
        assert "package" in NAMESPACE_KINDS

    def test_node_kinds_is_union(self):
        from backend.db.neo4j.models.constants import NODE_KINDS, COMPOUND_KINDS, MEMBER_KINDS, NAMESPACE_KINDS
        assert set(NODE_KINDS) == set(COMPOUND_KINDS + MEMBER_KINDS + NAMESPACE_KINDS)

    def test_type_kinds(self):
        from backend.db.neo4j.models.constants import TYPE_KINDS
        assert "class" in TYPE_KINDS
        assert "interface" in TYPE_KINDS
        assert "method" not in TYPE_KINDS

    def test_value_kinds(self):
        from backend.db.neo4j.models.constants import VALUE_KINDS
        assert "method" in VALUE_KINDS
        assert "attribute" in VALUE_KINDS
        assert "class" not in VALUE_KINDS

    def test_visibility_choices(self):
        from backend.db.neo4j.models.constants import VISIBILITY_CHOICES
        assert "public" in VISIBILITY_CHOICES
        assert "private" in VISIBILITY_CHOICES

    def test_layers(self):
        from backend.db.neo4j.models.constants import LAYERS
        assert LAYERS == ["design", "as-built", "dependency"]

    def test_predicates_list(self):
        from backend.db.neo4j.models.constants import PREDICATES
        assert "composes" in PREDICATES
        assert "aggregates" in PREDICATES
        assert "generalizes" in PREDICATES

    def test_predicate_to_rel_type_mapping(self):
        from backend.db.neo4j.models.constants import PREDICATE_TO_REL_TYPE
        assert PREDICATE_TO_REL_TYPE["composes"] == "COMPOSES"
        assert PREDICATE_TO_REL_TYPE["depends_on"] == "DEPENDS_ON"

    def test_valid_specializations_cpp(self):
        from backend.db.neo4j.models.constants import valid_specializations
        cpp_class = valid_specializations("cpp", "class")
        assert "struct" in cpp_class
        assert "abstract_class" in cpp_class

    def test_valid_specializations_unknown_language(self):
        from backend.db.neo4j.models.constants import valid_specializations
        assert valid_specializations("rust", "class") == set()

    def test_supported_languages(self):
        from backend.db.neo4j.models.constants import SUPPORTED_LANGUAGES
        assert "cpp" in SUPPORTED_LANGUAGES
        assert "python" in SUPPORTED_LANGUAGES
        assert "javascript" in SUPPORTED_LANGUAGES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_codebase_graph_primitives.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.db.neo4j.models'`

- [ ] **Step 3: Create the constants module**

Create `backend/db/neo4j/models/__init__.py`:

```python
"""Neo4j codebase graph models — primitives for nodes, edges, and constants."""
```

Create `backend/db/neo4j/models/constants.py`:

```python
"""Constants for the Neo4j codebase graph layer.

Moved from backend.db.models.ontology during graph primitives restructuring.
These constants define the vocabulary of predicates, node kinds,
and specializations used by the design repository and Cypher queries.

Node kinds are now organized by Neo4j node label:
  - COMPOUND_KINDS: entities that own members (classes, interfaces, enums)
  - MEMBER_KINDS: entities owned by compounds (methods, attributes, enum values)
  - NAMESPACE_KINDS: grouping entities (namespaces, packages)
"""

# ---------------------------------------------------------------------------
# Node kinds — organized by Neo4j label
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
]

NAMESPACE_KINDS: list[str] = [
    "namespace",
    "package",
]

# All node kinds flattened (for validation, prompts, etc.)
NODE_KINDS: list[str] = COMPOUND_KINDS + MEMBER_KINDS + NAMESPACE_KINDS

# ---------------------------------------------------------------------------
# Semantic groupings
# ---------------------------------------------------------------------------

TYPE_KINDS: set[str] = {"class", "struct", "template_class", "interface", "abstract_class", "enum", "enum_class"}
VALUE_KINDS: set[str] = {"method", "attribute", "constant", "enum_value"}

# ---------------------------------------------------------------------------
# Visibility / access specifiers
# ---------------------------------------------------------------------------

VISIBILITY_CHOICES: list[str] = ["public", "private", "protected"]

# ---------------------------------------------------------------------------
# Layers — where a node originates from
# ---------------------------------------------------------------------------

LAYERS: list[str] = ["design", "as-built", "dependency"]

# ---------------------------------------------------------------------------
# Predicates — mapping lowercase names to UPPER_SNAKE_CASE Neo4j rel types
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

DEFAULT_PREDICATES: list[tuple[str, str]] = [
    ("associates", "General association between two entities"),
    ("aggregates", "Whole-part relationship where the part can exist independently. Specify mechanism for container types (e.g., std::vector, std::list)"),
    ("composes", "Strong whole-part relationship where the part is owned by the whole"),
    ("depends_on", "One entity depends on another (e.g., for a header include)"),
    ("generalizes", "Inheritance / is-a relationship"),
    ("realizes", "A class implements/realizes an interface or contract"),
    ("references", "One entity holds a reference or pointer to another. Specify mechanism (e.g., std::unique_ptr, std::shared_ptr, raw_pointer, reference)"),
    ("invokes", "Weak association, signifying a caller-callee relationship"),
    ("has_argument", "A method accepts a parameter of the given type (method → type)"),
    ("returns", "A method returns a value of the given entity type (method → type)"),
    ("type_argument", "A template accepts a type argument at a given position"),
    ("template_param", "A template declares a type parameter slot"),
]

# ---------------------------------------------------------------------------
# Source types (kept for backward compatibility during transition;
# will be removed once all code uses node labels)
# ---------------------------------------------------------------------------

SOURCE_TYPES: list[tuple[str, str]] = [
    ("compound", "Compound"),
    ("member", "Member"),
    ("namespace", "Namespace"),
]
SOURCE_TYPE_VALUES: set[str] = {k for k, _ in SOURCE_TYPES}

# ---------------------------------------------------------------------------
# Language-specific specializations
# ---------------------------------------------------------------------------

LANGUAGE_SPECIALIZATIONS: dict[str, dict[str, list[str]]] = {
    "cpp": {
        "class": [
            "struct",
            "template_class",
            "abstract_class",
        ],
        "method": [
            "virtual_method",
            "pure_virtual_method",
            "template_method",
            "static_method",
            "const_method",
            "operator_overload",
        ],
        "function": [
            "template_function",
        ],
        "constant": [
            "constexpr",
            "const",
        ],
        "enum": [
            "enum_class",
        ],
        "type_alias": [
            "using",
            "typedef",
        ],
        "module": [
            "namespace",
        ],
    },
    "python": {
        "class": [
            "dataclass",
            "namedtuple",
        ],
        "method": [
            "classmethod",
            "staticmethod",
            "property",
            "abstractmethod",
            "async_method",
        ],
        "function": [
            "async_function",
            "generator",
            "decorator",
        ],
        "interface": [
            "protocol",
            "abc",
        ],
        "constant": [
            "final",
        ],
        "module": [
            "package",
        ],
    },
    "javascript": {
        "class": [],
        "method": [
            "getter",
            "setter",
            "static_method",
            "async_method",
        ],
        "function": [
            "arrow_function",
            "async_function",
            "generator",
        ],
        "module": [
            "es_module",
            "commonjs_module",
        ],
    },
}

SUPPORTED_LANGUAGES: set[str] = set(LANGUAGE_SPECIALIZATIONS.keys())


def valid_specializations(language: str, kind: str) -> set[str]:
    """Return the set of valid specializations for a language + kind."""
    lang_spec = LANGUAGE_SPECIALIZATIONS.get(language, {})
    return set(lang_spec.get(kind, []))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_codebase_graph_primitives.py::TestConstants -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/db/neo4j/models/__init__.py backend/db/neo4j/models/constants.py tests/test_codebase_graph_primitives.py
git commit -m "feat: add constants module for codebase graph primitives"
```

---

## Task 2: Create Node Models

**Files:**
- Create: `backend/db/neo4j/models/nodes/__init__.py`
- Create: `backend/db/neo4j/models/nodes/compound.py`
- Create: `backend/db/neo4j/models/nodes/member.py`
- Create: `backend/db/neo4j/models/nodes/namespace.py`
- Test: `tests/test_codebase_graph_primitives.py` (append)

- [ ] **Step 1: Write the failing tests for node models**

Append to `tests/test_codebase_graph_primitives.py`:

```python


class TestCompoundNode:
    """Tests for CompoundNode Pydantic model."""

    def test_create_minimal(self):
        from backend.db.neo4j.models.nodes.compound import CompoundNode
        node = CompoundNode(qualified_name="ns::Foo", name="Foo", kind="class")
        assert node.qualified_name == "ns::Foo"
        assert node.name == "Foo"
        assert node.kind == "class"
        assert node.layer == "design"
        assert node.specialization == ""
        assert node.visibility == ""
        assert node.description == ""
        assert node.implementation_status == "designed"

    def test_create_all_fields(self):
        from backend.db.neo4j.models.nodes.compound import CompoundNode
        node = CompoundNode(
            qualified_name="ns::Foo",
            name="Foo",
            kind="struct",
            layer="as-built",
            specialization="template_class",
            visibility="public",
            description="A struct",
            type_signature="int",
            argsstring="(int x)",
            definition="int Foo::calc(int x)",
            refid="classns_1_1Foo",
            file_path="src/foo.h",
            line_number=42,
            is_static=True,
            is_const=False,
            is_virtual=False,
            is_abstract=False,
            is_final=False,
            component_id=1,
            is_intercomponent=True,
            implementation_status="implemented",
            source_file="src/foo.cpp",
            test_file="test_foo.cpp",
        )
        assert node.kind == "struct"
        assert node.layer == "as-built"
        assert node.is_static is True
        assert node.is_intercomponent is True
        assert node.file_path == "src/foo.h"
        assert node.line_number == 42

    def test_invalid_kind_rejected(self):
        from backend.db.neo4j.models.nodes.compound import CompoundNode
        with pytest.raises(Exception):
            CompoundNode(qualified_name="X", name="X", kind="method")

    def test_invalid_layer_rejected(self):
        from backend.db.neo4j.models.nodes.compound import CompoundNode
        with pytest.raises(Exception):
            CompoundNode(qualified_name="X", name="X", kind="class", layer="invalid")

    def test_dependency_layer(self):
        from backend.db.neo4j.models.nodes.compound import CompoundNode
        node = CompoundNode(qualified_name="std::vector", name="vector", kind="class", layer="dependency",
                           is_intercomponent=True, description="Standard library: std::vector")
        assert node.layer == "dependency"
        assert node.is_intercomponent is True


class TestMemberNode:
    """Tests for MemberNode Pydantic model."""

    def test_create_minimal(self):
        from backend.db.neo4j.models.nodes.member import MemberNode
        node = MemberNode(qualified_name="ns::Foo::calculate", name="calculate", kind="method")
        assert node.qualified_name == "ns::Foo::calculate"
        assert node.kind == "method"
        assert node.layer == "design"

    def test_create_attribute(self):
        from backend.db.neo4j.models.nodes.member import MemberNode
        node = MemberNode(
            qualified_name="ns::Foo::count",
            name="count",
            kind="attribute",
            visibility="private",
            type_signature="int",
        )
        assert node.kind == "attribute"
        assert node.type_signature == "int"

    def test_invalid_kind_rejected(self):
        from backend.db.neo4j.models.nodes.member import MemberNode
        with pytest.raises(Exception):
            MemberNode(qualified_name="X", name="X", kind="class")


class TestNamespaceNode:
    """Tests for NamespaceNode Pydantic model."""

    def test_create_minimal(self):
        from backend.db.neo4j.models.nodes.namespace import NamespaceNode
        node = NamespaceNode(qualified_name="std", name="std", kind="namespace")
        assert node.qualified_name == "std"
        assert node.kind == "namespace"

    def test_create_package(self):
        from backend.db.neo4j.models.nodes.namespace import NamespaceNode
        node = NamespaceNode(qualified_name="my_pkg", name="my_pkg", kind="package")
        assert node.kind == "package"

    def test_no_irrelevant_fields(self):
        """NamespaceNode should not have implementation_status or is_intercomponent."""
        from backend.db.neo4j.models.nodes.namespace import NamespaceNode
        node = NamespaceNode(qualified_name="ns", name="ns")
        assert not hasattr(node, "implementation_status")
        assert not hasattr(node, "is_intercomponent")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_codebase_graph_primitives.py::TestCompoundNode -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Create node package and models**

Create `backend/db/neo4j/models/nodes/__init__.py`:

```python
"""Codebase graph node models — one per Neo4j label."""

from backend.db.neo4j.models.nodes.compound import CompoundNode
from backend.db.neo4j.models.nodes.member import MemberNode
from backend.db.neo4j.models.nodes.namespace import NamespaceNode

__all__ = ["CompoundNode", "MemberNode", "NamespaceNode"]
```

Create `backend/db/neo4j/models/nodes/compound.py`:

```python
"""CompoundNode — :Compound in Neo4j.

Compounds are top-level containers — classes, structs, interfaces, enums —
that own members and participate in associations. The `kind` field refines
the specific type. The `layer` field indicates origin: 'design' (agent-created),
'as-built' (parsed from code), or 'dependency' (external library).

Identified by `qualified_name`, used as the MERGE key in Neo4j.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class CompoundNode(BaseModel):
    """A compound entity in the codebase graph (:Compound in Neo4j).

    Compounds are the top-level containers — classes, structs, interfaces,
    enums — that own members and participate in associations.

    The `kind` field refines the specific type. The `layer` field indicates
    origin: 'design' (agent-created), 'as-built' (parsed from code), or
    'dependency' (external library).

    Identified by `qualified_name`, used as the MERGE key in Neo4j.
    """

    # --- Identity & classification ---
    qualified_name: str
    name: str
    kind: Literal["class", "struct", "template_class", "interface", "abstract_class", "enum", "enum_class"]
    layer: Literal["design", "as-built", "dependency"] = "design"
    specialization: str = ""
    visibility: Literal["public", "private", "protected", ""] = ""
    description: str = ""

    # --- Code-level detail ---
    type_signature: str = ""
    argsstring: str = ""
    definition: str = ""

    # --- Source location (populated for as-built layer) ---
    refid: str = ""
    file_path: str = ""
    line_number: int | None = None

    # --- Flags ---
    is_static: bool = False
    is_const: bool = False
    is_virtual: bool = False
    is_abstract: bool = False
    is_final: bool = False

    # --- Project context ---
    component_id: int | None = None
    is_intercomponent: bool = False

    # --- Implementation tracking (design layer) ---
    implementation_status: Literal["designed", "scaffolded", "tested", "implemented", "verified"] = "designed"
    source_file: str = ""
    test_file: str = ""

    model_config = {"from_attributes": True}
```

Create `backend/db/neo4j/models/nodes/member.py`:

```python
"""MemberNode — :Member in Neo4j.

Members are owned by compounds — methods and attributes on classes,
values inside enums, constants inside namespaces. The `kind` field refines
the specific member type. The `layer` field indicates origin.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class MemberNode(BaseModel):
    """A member entity in the codebase graph (:Member in Neo4j).

    Members are owned by compounds — methods and attributes on classes,
    values inside enums, constants inside namespaces.

    The `kind` field refines the specific member type. The `layer` field
    indicates origin.
    """

    # --- Identity & classification ---
    qualified_name: str
    name: str
    kind: Literal["method", "attribute", "constant", "enum_value"]
    layer: Literal["design", "as-built", "dependency"] = "design"
    visibility: Literal["public", "private", "protected", ""] = ""
    description: str = ""

    # --- Code-level detail ---
    type_signature: str = ""
    argsstring: str = ""
    definition: str = ""

    # --- Source location ---
    refid: str = ""
    file_path: str = ""
    line_number: int | None = None

    # --- Flags ---
    is_static: bool = False
    is_const: bool = False
    is_virtual: bool = False
    is_abstract: bool = False
    is_final: bool = False

    # --- Project context ---
    component_id: int | None = None

    model_config = {"from_attributes": True}
```

Create `backend/db/neo4j/models/nodes/namespace.py`:

```python
"""NamespaceNode — :Namespace in Neo4j.

Namespaces group compounds into modules. They form a hierarchy via
COMPOSES edges (e.g. `std` COMPOSES `std::chrono`).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class NamespaceNode(BaseModel):
    """A namespace entity in the codebase graph (:Namespace in Neo4j).

    Namespaces group compounds into modules. They form a hierarchy via
    COMPOSES edges (e.g. `std` COMPOSES `std::chrono`).
    """

    # --- Identity & classification ---
    qualified_name: str
    name: str
    kind: Literal["namespace", "package"] = "namespace"
    layer: Literal["design", "as-built", "dependency"] = "design"
    description: str = ""

    # --- Source location ---
    refid: str = ""
    file_path: str = ""

    # --- Project context ---
    component_id: int | None = None

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Update models __init__.py to re-export nodes**

Update `backend/db/neo4j/models/__init__.py`:

```python
"""Neo4j codebase graph models — primitives for nodes, edges, and constants."""

from backend.db.neo4j.models.nodes import CompoundNode, MemberNode, NamespaceNode

__all__ = [
    "CompoundNode",
    "MemberNode",
    "NamespaceNode",
]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_codebase_graph_primitives.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/db/neo4j/models/ tests/test_codebase_graph_primitives.py
git commit -m "feat: add CompoundNode, MemberNode, NamespaceNode graph primitive models"
```

---

## Task 3: Create Edge Model

**Files:**
- Create: `backend/db/neo4j/models/edges.py`
- Test: `tests/test_codebase_graph_primitives.py` (append)

- [ ] **Step 1: Write the failing test for CodebaseEdge**

Append to `tests/test_codebase_graph_primitives.py`:

```python


class TestCodebaseEdge:
    """Tests for CodebaseEdge model and PREDICATES."""

    def test_create_basic_edge(self):
        from backend.db.neo4j.models.edges import CodebaseEdge
        edge = CodebaseEdge(
            subject_qualified_name="ns::Foo",
            predicate="composes",
            object_qualified_name="ns::Foo::calculate",
        )
        assert edge.predicate == "composes"
        assert edge.mechanism == ""
        assert edge.position is None

    def test_create_edge_with_mechanism(self):
        from backend.db.neo4j.models.edges import CodebaseEdge
        edge = CodebaseEdge(
            subject_qualified_name="ns::Car",
            predicate="aggregates",
            object_qualified_name="ns::Wheel",
            mechanism="std::vector",
        )
        assert edge.mechanism == "std::vector"

    def test_create_edge_with_type_argument(self):
        from backend.db.neo4j.models.edges import CodebaseEdge
        edge = CodebaseEdge(
            subject_qualified_name="std::vector",
            predicate="type_argument",
            object_qualified_name="std::string",
            position=0,
            display_name="std::string",
        )
        assert edge.position == 0
        assert edge.display_name == "std::string"

    def test_predicates_matches_constant(self):
        from backend.db.neo4j.models.edges import CodebaseEdge, PREDICATES
        # Verify PREDICATES list exists and is non-empty
        assert len(PREDICATES) > 0
        assert "composes" in PREDICATES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_codebase_graph_primitives.py::TestCodebaseEdge -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Create the edges module**

Create `backend/db/neo4j/models/edges.py`:

```python
"""CodebaseEdge — a directed relationship between codebase graph nodes.

Stored in Neo4j as a typed relationship with the predicate name
uppercased (e.g. 'composes' → COMPOSES). Identified by subject +
predicate + object.
"""

from __future__ import annotations

from pydantic import BaseModel

PREDICATES: list[str] = [
    "composes",
    "aggregates",
    "references",
    "depends_on",
    "associates",
    "invokes",
    "returns",
    "generalizes",
    "realizes",
    "implements",
    "has_argument",
    "type_argument",
    "template_param",
]


class CodebaseEdge(BaseModel):
    """A directed relationship between two codebase nodes.

    Stored in Neo4j as a typed relationship with the predicate name
    uppercased (e.g. 'composes' → COMPOSES). Identified by subject +
    predicate + object.
    """

    subject_qualified_name: str
    predicate: str   # Must be one of PREDICATES
    object_qualified_name: str
    mechanism: str = ""           # Container type (e.g. "std::vector" for aggregates)
    position: int | None = None   # Position for type_argument edges (0-based)
    name: str = ""                # Parameter name for template_param edges
    display_name: str = ""        # Alias display name (e.g. "std::string" for std::basic_string)
```

- [ ] **Step 4: Update models __init__.py to include edges**

Update `backend/db/neo4j/models/__init__.py`:

```python
"""Neo4j codebase graph models — primitives for nodes, edges, and constants."""

from backend.db.neo4j.models.edges import CodebaseEdge, PREDICATES
from backend.db.neo4j.models.nodes import CompoundNode, MemberNode, NamespaceNode

__all__ = [
    "CodebaseEdge",
    "CompoundNode",
    "MemberNode",
    "NamespaceNode",
    "PREDICATES",
]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_codebase_graph_primitives.py::TestCodebaseEdge -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/db/neo4j/models/ tests/test_codebase_graph_primitives.py
git commit -m "feat: add CodebaseEdge model and PREDICATES list"
```

---

## Task 4: Redirect Constants Imports

Redirect all imports from `backend.db.models.ontology` to `backend.db.neo4j.models.constants`. This is a find-and-replace task, but each file must be verified.

**Files:**
- Modify: `backend/codebase/schemas.py`
- Modify: `backend/ticketing_agent/design/design_oo_prompt.py`
- Modify: `backend/ticketing_agent/design/design_ontology.py`
- Modify: `backend/ticketing_agent/design/design_ontology_prompt.py`

- [ ] **Step 1: Update codebase/schemas.py**

In `backend/codebase/schemas.py`, change:
```python
from backend.db.models.ontology import NODE_KINDS, SOURCE_TYPES, VISIBILITY_CHOICES
```
to:
```python
from backend.db.neo4j.models.constants import NODE_KINDS, VISIBILITY_CHOICES
```
Note: `SOURCE_TYPES` is no longer needed here since `NodeKind` and `SourceType` literals in the same file reference the lists. Remove the `SourceType` literal derivation from `SOURCE_TYPES` and instead define it directly. Update `SourceType` to use the new `SOURCE_TYPE_VALUES`:

```python
SourceType = Literal["compound", "member", "namespace"]
```

- [ ] **Step 2: Update design_oo_prompt.py**

In `backend/ticketing_agent/design/design_oo_prompt.py`, change:
```python
from backend.db.models.ontology import LANGUAGE_SPECIALIZATIONS
```
to:
```python
from backend.db.neo4j.models.constants import LANGUAGE_SPECIALIZATIONS
```

- [ ] **Step 3: Update design_ontology.py**

In `backend/ticketing_agent/design/design_ontology.py`, change:
```python
from backend.db.models import Predicate
from backend.db.models.ontology import NODE_KIND_VALUES
```
to:
```python
from backend.db.neo4j.repositories.constants import DEFAULT_PREDICATES
from backend.db.neo4j.models.constants import NODE_KINDS
```
Note: `NODE_KIND_VALUES` was a set; replace usages with `set(NODE_KINDS)` or `NODE_KINDS` list as appropriate. Review the file for all references to `NODE_KIND_VALUES` and `Predicate` and update them.

- [ ] **Step 4: Update design_ontology_prompt.py**

In `backend/ticketing_agent/design/design_ontology_prompt.py`, change:
```python
from backend.db.models.ontology import LANGUAGE_SPECIALIZATIONS
```
to:
```python
from backend.db.neo4j.models.constants import LANGUAGE_SPECIALIZATIONS
```

- [ ] **Step 5: Run existing tests to verify nothing is broken**

Run: `pytest tests/test_codebase_schemas.py tests/test_map_to_ontology.py tests/test_design_oo.py -v`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: redirect constant imports from ontology to neo4j.models.constants"
```

---

## Task 5: Update DesignRepository to Use New Models

Update `DesignRepository.merge_node()` to dispatch based on node model type and use new Neo4j labels and `layer` property. Update `find_nodes()` to filter by `layer` instead of `source_type`. Update `merge_triple()` to use `CodebaseEdge`.

**Files:**
- Modify: `backend/db/neo4j/repositories/design.py`
- Modify: `backend/db/neo4j/repositories/models/__init__.py`

- [ ] **Step 1: Update DesignRepository imports and merge_node**

In `backend/db/neo4j/repositories/design.py`, replace the import of `DesignNode` and `DesignTripleUpdate` with:
```python
from backend.db.neo4j.models.nodes import CompoundNode, MemberNode, NamespaceNode
from backend.db.neo4j.models.edges import CodebaseEdge
```

Replace `merge_node(self, node: DesignNode)` with a Union type signature:
```python
from typing import Union
NodeModel = Union[CompoundNode, MemberNode, NamespaceNode]
```

Rewrite `merge_node` to dispatch based on `type(node)`:

```python
def merge_node(self, node: NodeModel) -> NodeModel:
    """Create or update a node by qualified_name.

    Dispatches to the appropriate Neo4j label (:Compound, :Member, :Namespace)
    based on the node model type.
    """
    if isinstance(node, CompoundNode):
        label = "Compound"
    elif isinstance(node, MemberNode):
        label = "Member"
    elif isinstance(node, NamespaceNode):
        label = "Namespace"
    else:
        raise ValueError(f"Unknown node type: {type(node)}")

    props = node.model_dump(exclude_none=True)
    cypher = f"""
    MERGE (n:{label} {{qualified_name: $qualified_name}})
    SET n += $props, n.layer = $layer
    """
    self._session.run(cypher, {"qualified_name": node.qualified_name, "props": props, "layer": node.layer})
    return node
```

- [ ] **Step 2: Update find_nodes to use layer instead of source_type**

Replace the `exclude_source_types` parameter with `layer` and `exclude_layers`:

```python
def find_nodes(
    self,
    kind: str | None = None,
    search: str | None = None,
    component_id: int | None = None,
    layer: str | None = None,
    exclude_layers: list[str] | None = None,
) -> list[NodeModel]:
    """Find nodes matching optional filters.

    Searches across :Compound, :Member, and :Namespace labels.
    """
    conditions = []
    params: dict = {}

    if kind:
        # Determine which label(s) to search based on kind
        labels = []
        from backend.db.neo4j.models.constants import COMPOUND_KINDS, MEMBER_KINDS, NAMESPACE_KINDS
        if kind in COMPOUND_KINDS:
            labels.append("Compound")
        if kind in MEMBER_KINDS:
            labels.append("Member")
        if kind in NAMESPACE_KINDS:
            labels.append("Namespace")

    if component_id is not None:
        conditions.append("n.component_id = $comp_id")
        params["comp_id"] = component_id
    if search:
        conditions.append("(n.name CONTAINS $search OR n.qualified_name CONTAINS $search)")
        params["search"] = search
    if layer is not None:
        conditions.append("n.layer = $layer")
        params["layer"] = layer
    if exclude_layers:
        conditions.append("NOT n.layer IN $exclude_layers")
        params["exclude_layers"] = exclude_layers

    where = " AND ".join(conditions) if conditions else "true"
    label_clause = " OR ".join(f"n:{label}" for label in labels) if kind else "true"
    cypher = f"MATCH (n) WHERE ({label_clause}) AND ({where}) RETURN n"

    result = self._session.run(cypher, params)
    nodes = []
    for record in result:
        props = dict(record["n"])
        # Determine node type from labels in the result
        node_labels = set(record["n"].labels) if hasattr(record["n"], "labels") else set()
        if "Compound" in node_labels:
            nodes.append(CompoundNode(**props))
        elif "Member" in node_labels:
            nodes.append(MemberNode(**props))
        elif "Namespace" in node_labels:
            nodes.append(NamespaceNode(**props))
    return nodes
```

- [ ] **Step 3: Update merge_triple to use CodebaseEdge**

Replace `merge_triple` signature and update Cypher to match both `:Design` (legacy) and `:Compound`/`:Member`/`:Namespace` labels:

```python
def merge_triple(
    self,
    subject_qualified_name: str,
    predicate: str,
    object_qualified_name: str,
    mechanism: str = "",
    position: int | None = None,
    name: str = "",
    display_name: str = "",
) -> None:
    """MERGE a typed relationship between two codebase nodes.

    Matches subject and object across all node labels (:Compound, :Member, :Namespace).
    Falls back to :Design for backward compatibility during migration.
    """
...
```

The Cypher query should match across all labels:
```cypher
MATCH (s) WHERE s.qualified_name = $subj AND (s:Compound OR s:Member OR s:Namespace OR s:Design)
OPTIONAL MATCH (o) WHERE o.qualified_name = $obj AND (o:Compound OR o:Member OR o:Namespace OR o:Design)
WITH s, coalesce(...) AS target
...
```

- [ ] **Step 4: Update other methods (get_by_qualified_name, delete_node, clear_design_graph, sync_implementation_status)**

Update these methods to work across all three labels plus `:Design` for backward compatibility.

- [ ] **Step 5: Update models/__init__.py to re-export new types**

Update `backend/db/neo4j/repositories/models/__init__.py`:

```python
"""Neo4j repository data models."""

from backend.db.neo4j.models.edges import CodebaseEdge
from backend.db.neo4j.models.nodes import CompoundNode, MemberNode, NamespaceNode
from backend.db.neo4j.repositories.models.requirement import (
    HLRNode,
    LLRNode,
)
from backend.db.neo4j.repositories.models.verification import (
    ActionNode,
    ConditionNode,
    VerificationMethodNode,
)

__all__ = [
    "CodebaseEdge",
    "CompoundNode",
    "MemberNode",
    "NamespaceNode",
    "HLRNode",
    "LLRNode",
    "VerificationMethodNode",
    "ConditionNode",
    "ActionNode",
]
```

- [ ] **Step 6: Run DesignRepository tests**

Run: `pytest tests/test_design_repository.py -v`
Expected: All pass (with backward-compatible :Design matching still in place)

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: update DesignRepository to use CompoundNode/MemberNode/NamespaceNode with layer property"
```

---

## Task 6: Update persistence.py and other direct consumers of DesignNode

**Files:**
- Modify: `backend/requirements/services/persistence.py`
- Modify: `backend/pipeline/orchestrator.py`
- Modify: `backend/db/neo4j/__init__.py`
- Modify: `backend/db/neo4j/repositories/__init__.py`

- [ ] **Step 1: Update persistence.py**

In `backend/requirements/services/persistence.py`, change:
```python
from backend.db.neo4j.repositories.models.design import DesignNode
```
to:
```python
from backend.db.neo4j.models.nodes import CompoundNode, MemberNode, NamespaceNode
from backend.db.neo4j.models.edges import CodebaseEdge
```

Update `persist_design()` function to convert `OntologyNodeSchema` entries to the correct node model based on `kind`:

```python
def _to_node_model(node_schema):
    """Convert an OntologyNodeSchema to the correct node model based on kind."""
    from backend.db.neo4j.models.constants import COMPOUND_KINDS, MEMBER_KINDS, NAMESPACE_KINDS
    kind = node_schema.kind
    common_kwargs = dict(
        qualified_name=node_schema.qualified_name,
        name=node_schema.name,
        kind=kind,
        specialization=node_schema.specialization,
        visibility=node_schema.visibility,
        description=node_schema.description,
        component_id=node_schema.component_id,
        is_intercomponent=node_schema.is_intercomponent,
        type_signature=node_schema.type_signature,
        argsstring=node_schema.argsstring,
        definition=node_schema.definition,
        refid=node_schema.refid,
        file_path=node_schema.file_path,
        line_number=node_schema.line_number,
        is_static=node_schema.is_static,
        is_const=node_schema.is_const,
        is_virtual=node_schema.is_virtual,
        is_abstract=node_schema.is_abstract,
        is_final=node_schema.is_final,
    )
    # Determine layer from source_type (backward compatible mapping)
    layer = _map_source_type_to_layer(node_schema.source_type)
    common_kwargs["layer"] = layer

    if kind in COMPOUND_KINDS:
        return CompoundNode(**common_kwargs, implementation_status=node_schema.implementation_status or "designed",
                           source_file=getattr(node_schema, 'source_file', ''),
                           test_file=getattr(node_schema, 'test_file', ''),
                           is_intercomponent=node_schema.is_intercomponent)
    elif kind in MEMBER_KINDS:
        return MemberNode(**common_kwargs)
    elif kind in NAMESPACE_KINDS:
        return NamespaceNode(**common_kwargs)
    else:
        # Fallback to Compound for unknown kinds
        return CompoundNode(**common_kwargs, implementation_status="designed",
                           source_file="", test_file="", is_intercomponent=node_schema.is_intercomponent)


def _map_source_type_to_layer(source_type: str, refid: str = "") -> str:
    """Map legacy source_type to the new layer property.
    
    Matches the migration script logic:
    - source_type='dependency' → layer='dependency'
    - source_type='compound' with non-empty refid → layer='as-built'
    - source_type='compound' with empty refid → layer='design'
    - source_type='namespace' or 'member' or empty → layer='design'
    """
    if source_type == "dependency":
        return "dependency"
    elif source_type == "compound":
        if refid:
            return "as-built"
        return "design"
    else:
        return "design"
```

Update all places that create `DesignNode` objects to use `_to_node_model()`.

- [ ] **Step 2: Update orchestrator.py and other consumers**

In `backend/pipeline/orchestrator.py`, update the `DesignNode` import to use new models. Search for any direct `DesignNode(...)` constructor calls and replace with the appropriate typed model.

In `backend/db/neo4j/__init__.py`, update imports:
```python
from backend.db.neo4j.models.nodes import CompoundNode, MemberNode, NamespaceNode
from backend.db.neo4j.models.edges import CodebaseEdge
```

Remove `DesignNode` and `DesignTripleUpdate` from `__all__` and replace with new types.

In `backend/db/neo4j/repositories/__init__.py`, do the same.

- [ ] **Step 3: Run all design-related tests**

Run: `pytest tests/test_persistence.py tests/test_design_repository.py -v`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: update persistence, orchestrator, and Neo4j package to use new node models"
```

---

## Task 7: Update Neo4j Connection Constraints and Indexes

**Files:**
- Modify: `backend/db/neo4j/connection.py`

- [ ] **Step 1: Update ensure_constraints to create Compound/Member/Namespace constraints**

In `backend/db/neo4j/connection.py`, update `ensure_constraints()` to add constraints for the new node labels, while keeping existing `:Design` constraints for backward compatibility during migration:

```python
statements = [
    # New node label constraints
    "CREATE CONSTRAINT compound_qualified_name IF NOT EXISTS FOR (n:Compound) REQUIRE n.qualified_name IS UNIQUE",
    "CREATE CONSTRAINT member_qualified_name IF NOT EXISTS FOR (n:Member) REQUIRE n.qualified_name IS UNIQUE",
    "CREATE CONSTRAINT namespace_qualified_name IF NOT EXISTS FOR (n:Namespace) REQUIRE n.qualified_name IS UNIQUE",
    # Legacy Design constraint (kept for migration period)
    "CREATE CONSTRAINT design_qualified_name IF NOT EXISTS FOR (n:Design) REQUIRE n.qualified_name IS UNIQUE",
    "CREATE CONSTRAINT hlr_id IF NOT EXISTS FOR (n:HLR) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT llr_id IF NOT EXISTS FOR (n:LLR) REQUIRE n.id IS UNIQUE",
    "CREATE INDEX design_kind IF NOT EXISTS FOR (n:Design) ON (n.kind)",
    "CREATE INDEX compound_layer IF NOT EXISTS FOR (n:Compound) ON (n.layer)",
    "CREATE INDEX compound_kind IF NOT EXISTS FOR (n:Compound) ON (n.kind)",
    "CREATE INDEX compound_component_id IF NOT EXISTS FOR (n:Compound) ON (n.component_id)",
    "CREATE INDEX member_layer IF NOT EXISTS FOR (n:Member) ON (n.layer)",
    "CREATE INDEX member_kind IF NOT EXISTS FOR (n:Member) ON (n.kind)",
    "CREATE INDEX namespace_layer IF NOT EXISTS FOR (n:Namespace) ON (n.layer)",
    "CREATE CONSTRAINT verification_method_id IF NOT EXISTS FOR (n:VerificationMethod) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT condition_id IF NOT EXISTS FOR (n:Condition) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT action_id IF NOT EXISTS FOR (n:Action) REQUIRE n.id IS UNIQUE",
]
```

- [ ] **Step 2: Update ensure_design_constraints for new indexes**

Replace the current `ensure_design_constraints` method:

```python
def ensure_design_constraints(self):
    """Create additional constraints and indexes for the design layer.

    Includes both new Compound/Member/Namespace indexes and legacy Design
    indexes for migration compatibility.
    """
    if not self.verify_connectivity():
        log.warning("Neo4j not reachable — skipping design constraint setup")
        return False
    statements = [
        # Legacy Design indexes (kept during migration)
        "CREATE INDEX design_source_type IF NOT EXISTS FOR (n:Design) ON (n.source_type)",
        "CREATE INDEX design_implementation_status IF NOT EXISTS FOR (n:Design) ON (n.implementation_status)",
        "CREATE INDEX design_component_id IF NOT EXISTS FOR (n:Design) ON (n.component_id)",
        # New layer-based indexes
        "CREATE INDEX compound_layer IF NOT EXISTS FOR (n:Compound) ON (n.layer)",
        "CREATE INDEX compound_implementation_status IF NOT EXISTS FOR (n:Compound) ON (n.implementation_status)",
        "CREATE INDEX compound_component_id IF NOT EXISTS FOR (n:Compound) ON (n.component_id)",
        "CREATE INDEX member_layer IF NOT EXISTS FOR (n:Member) ON (n.layer)",
        "CREATE INDEX namespace_layer IF NOT EXISTS FOR (n:Namespace) ON (n.layer)",
    ]
    with self.session() as session:
        for stmt in statements:
            session.run(stmt)
    log.info("Neo4j design constraints and indexes ensured")
    return True
```

- [ ] **Step 3: Run the app and verify constraints are created**

Run: `python -c "from backend.db.neo4j.connection import Neo4jConnection; conn = Neo4jConnection(); conn.ensure_constraints(); conn.ensure_design_constraints(); print('OK')"`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add backend/db/neo4j/connection.py
git commit -m "feat: add Compound/Member/Namespace constraints and indexes to Neo4j connection"
```

---

## Task 8: Write Neo4j Migration Script

Create a script that migrates existing `:Design` nodes to their correct new labels and adds the `layer` property.

**Files:**
- Create: `scripts/migrate_design_labels.py`

- [ ] **Step 1: Write the migration script**

Create `scripts/migrate_design_labels.py`:

```python
#!/usr/bin/env python
"""Migrate :Design nodes to :Compound/:Member/:Namespace labels with layer property.

This script:
1. Adds the correct label (:Compound, :Member, or :Namespace) to each :Design node
2. Sets the `layer` property based on `source_type`:
   - source_type='dependency' → layer='dependency'
   - source_type='compound' and refid is non-empty → layer='as-built'
   - source_type='compound' and refid is empty → layer='design'
   - source_type='member' → inherits from parent compound's layer
   - source_type='namespace' → layer='design'
   - missing/empty source_type → layer='design'
3. Removes the `source_type` property
4. Removes the `:Design` label

Usage:
    python scripts/migrate_design_labels.py [--dry-run]
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from backend.db.neo4j.connection import Neo4jConnection


COMPOUND_KINDS = {"class", "struct", "template_class", "interface", "abstract_class", "enum", "enum_class"}
MEMBER_KINDS = {"method", "attribute", "constant", "enum_value"}
NAMESPACE_KINDS = {"namespace", "module"}


def determine_layer(source_type: str | None, refid: str | None) -> str:
    """Determine the layer value from legacy source_type and refid."""
    if source_type == "dependency":
        return "dependency"
    elif source_type == "compound":
        if refid:
            return "as-built"
        return "design"
    elif source_type == "namespace":
        return "design"
    elif source_type == "member":
        # Members inherit their parent's layer; default to design
        return "design"
    else:
        # Empty or missing source_type → design
        return "design"


def determine_label(kind: str) -> str:
    """Determine the Neo4j label for a node based on its kind."""
    if kind in COMPOUND_KINDS:
        return "Compound"
    elif kind in MEMBER_KINDS:
        return "Member"
    elif kind in NAMESPACE_KINDS:
        return "Namespace"
    else:
        # Default to Compound for unknown kinds
        return "Compound"


def migrate(dry_run: bool = False):
    conn = Neo4jConnection()
    conn.ensure_constraints()
    conn.ensure_design_constraints()

    driver = conn.get_driver()
    with driver.session(database="neo4j") as session:
        # Step 1: Get all Design nodes
        result = session.run("MATCH (d:Design) RETURN d")
        nodes = [dict(record["d"]) for record in result]
        print(f"Found {len(nodes)} :Design nodes")

        if dry_run:
            print("\n--- DRY RUN ---")
            for props in nodes[:10]:
                kind = props.get("kind", "unknown")
                source_type = props.get("source_type", "")
                refid = props.get("refid", "")
                label = determine_label(kind)
                layer = determine_layer(source_type, refid)
                qname = props.get("qualified_name", "?")
                print(f"  {qname}: kind={kind}, source_type={source_type!r} → :{label} {{layer: '{layer}'}}")
            if len(nodes) > 10:
                print(f"  ... and {len(nodes) - 10} more")
            return

        # Step 2: Add new labels and set layer property
        label_counts = {"Compound": 0, "Member": 0, "Namespace": 0}
        for props in nodes:
            kind = props.get("kind", "unknown")
            source_type = props.get("source_type", "")
            refid = props.get("refid", "")
            qname = props.get("qualified_name", "")
            label = determine_label(kind)
            layer = determine_layer(source_type, refid)

            session.run(
                f"MATCH (d:Design {{qualified_name: $qn}}) SET d:{label}, d.layer = $layer",
                {"qn": qname, "layer": layer},
            )
            label_counts[label] += 1

        print(f"Labeled nodes: {label_counts}")

        # Step 3: For member nodes, update layer based on parent compound
        # Members that are children of as-built compounds should be as-built
        session.run("""
            MATCH (parent:Compound {layer: 'as-built'})-[:COMPOSES]->(member:Member {layer: 'design'})
            SET member.layer = 'as-built'
        """)
        print("Updated member layers based on parent compounds")

        # Step 4: Remove source_type property from all nodes
        # (Only after layer is set — both labels exist on nodes at this point)
        session.run("MATCH (n) WHERE n.source_type IS NOT NULL REMOVE n.source_type")
        print("Removed source_type property from all nodes")

        # Step 5: Remove :Design label (nodes now have specific labels)
        session.run("MATCH (d:Design) REMOVE d:Design")
        print("Removed :Design label from all nodes")

        # Step 6: Drop old indexes (they'll be recreated with new labels by ensure_design_constraints)
        # Note: Neo4j doesn't support DROP INDEX IF EXISTS for all versions,
        # so we handle errors gracefully
        for stmt in [
            "DROP INDEX design_kind IF EXISTS",
            "DROP INDEX design_source_type IF EXISTS",
            "DROP INDEX design_component_id IF EXISTS",
            "DROP INDEX design_implementation_status IF EXISTS",
            "DROP INDEX design_qualified_name IF EXISTS",
        ]:
            try:
                session.run(stmt)
            except Exception:
                pass
        print("Dropped legacy :Design indexes (if they existed)")

        # Step 7: Verify
        result = session.run("MATCH (c:Compound) RETURN count(c) AS count")
        compound_count = result.single()["count"]
        result = session.run("MATCH (m:Member) RETURN count(m) AS count")
        member_count = result.single()["count"]
        result = session.run("MATCH (n:Namespace) RETURN count(n) AS count")
        namespace_count = result.single()["count"]
        result = session.run("MATCH (d:Design) RETURN count(d) AS count")
        design_count = result.single()["count"]
        print(f"\nVerification:")
        print(f"  :Compound nodes: {compound_count}")
        print(f"  :Member nodes: {member_count}")
        print(f"  :Namespace nodes: {namespace_count}")
        print(f"  :Design nodes remaining: {design_count}")

    conn.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Migrate :Design nodes to typed labels with layer property")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be migrated without making changes")
    args = parser.parse_args()
    migrate(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test with --dry-run**

Run: `python scripts/migrate_design_labels.py --dry-run`
Expected: Prints summary of nodes that would be migrated, no changes made

- [ ] **Step 3: Commit**

```bash
git add scripts/migrate_design_labels.py
git commit -m "feat: add Neo4j migration script for Design → Compound/Member/Namespace labels"
```

---

## Task 9: Remove SQLAlchemy Ontology Models and Clean Up Imports

Delete the deprecated ORM model file and update all imports and references.

**Files:**
- Delete: `backend/db/models/ontology.py`
- Modify: `backend/db/models/__init__.py`
- Modify: `backend/db/models/tasks.py`
- Modify: `backend/db/models/components.py`
- Modify: `backend/db/models/associations.py`
- Modify: `tests/test_ontology_models.py`
- Modify: Various test files that import from `backend.db.models.ontology`

- [ ] **Step 1: Update db/models/__init__.py to remove ontology re-exports**

Remove all lines referencing `ontology`, `OntologyNode`, `OntologyTriple`, `Predicate`, and their constants from `backend/db/models/__init__.py`. The remaining imports should be only: `tickets_components`, `tickets_languages`, `Component`, `BuildSystem`, `Dependency`, etc., `Ticket*`, `ProjectMeta`, `Task*`, plus the formatting/verification constants.

- [ ] **Step 2: Remove OntologyNode relationship from components.py**

In `backend/db/models/components.py`, remove the `from backend.db.models.ontology import OntologyNode` import and the `ontology_nodes` relationship on the `Component` class. The `back_populates="component"` on `OntologyNode` side is already being deleted.

- [ ] **Step 3: Remove OntologyNode relationship from tasks.py**

In `backend/db/models/tasks.py`, remove the `from backend.db.models.ontology import OntologyNode` import and any `OntologyNode` foreign key or relationship references. The `TaskDesignNode` model should keep its `ontology_node_qualified_name` column.

- [ ] **Step 4: Delete ontology.py**

```bash
rm backend/db/models/ontology.py
```

- [ ] **Step 5: Delete test_ontology_models.py or mark it as skipped**

The `tests/test_ontology_models.py` tests the SQLAlchemy `OntologyNode`, `OntologyTriple`, and `Predicate` models. Since these are being removed, this test file should be deleted or replaced with tests for the new graph primitive models (which we've already written in `tests/test_codebase_graph_primitives.py`).

```bash
rm tests/test_ontology_models.py
```

- [ ] **Step 6: Update remaining test imports**

Search for remaining references to `backend.db.models.ontology` or `OntologyNode`/`OntologyTriple`/`Predicate` in test files and update them:

- `tests/test_dependency_pipeline.py` — update imports to use new models
- `tests/test_codebase_schemas.py` — update import of `NODE_KINDS`, `VISIBILITY_CHOICES`, `SOURCE_TYPES`
- `tests/integration/conftest.py` — update any `OntologyNode` fixture creation
- `tests/test_design_repository.py` — update `DesignNode` to `CompoundNode`/`MemberNode`/`NamespaceNode`

- [ ] **Step 7: Run all tests**

Run: `pytest tests/ -v --timeout=30 -x`
Expected: All tests pass (some may need individual fixes — this is expected during this step)

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor: remove SQLAlchemy ontology models and clean up all imports"
```

---

## Task 10: Delete Old Neo4j Models File and Update design_data Repository Adapters

**Files:**
- Delete: `backend/db/neo4j/repositories/models/design.py`
- Modify: `backend/design_data/repository.py`
- Modify: `backend/design_data/transforms.py`

- [ ] **Step 1: Delete design.py from neo4j repositories models**

```bash
rm backend/db/neo4j/repositories/models/design.py
```

Update `backend/db/neo4j/repositories/models/__init__.py` to not import from `design.py`:

```python
"""Neo4j repository data models."""

from backend.db.neo4j.repositories.models.requirement import (
    HLRNode,
    LLRNode,
)
from backend.db.neo4j.repositories.models.verification import (
    ActionNode,
    ConditionNode,
    VerificationMethodNode,
)

__all__ = [
    "HLRNode",
    "LLRNode",
    "VerificationMethodNode",
    "ConditionNode",
    "ActionNode",
]
```

- [ ] **Step 2: Update design_data/repository.py**

In `backend/design_data/repository.py`, the reads from Neo4j currently create `DiagramNode` objects from raw dicts. These continue to work since the underlying Cypher queries read node properties directly. No changes needed for Phase 1 — the repository reads `:Compound`/`:Member`/`:Namespace` nodes (after migration) or `:Design` nodes (before migration, during transition). Since the design_data module is Phase 2 territory, we leave it as-is but add a comment noting it will be refactored.

- [ ] **Step 3: Update design_data/transforms.py**

In `backend/design_data/transforms.py`, no logic changes needed for Phase 1 since it converts between `OODesignSchema` and `ClassDiagram`, which are separate from the graph primitives. Add a comment noting these are Phase 2 territory.

- [ ] **Step 4: Run design_data tests**

Run: `pytest tests/test_design_data_models.py tests/test_design_data_transforms.py tests/test_design_data_repository.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: delete DesignNode/DesignTripleUpdate, clean up neo4j model exports"
```

---

## Task 11: Update scripts and Fix Remaining References

**Files:**
- Modify: `scripts/migrate_phase1_design_to_neo4j.py`
- Modify: `scripts/01_flush_db.py`
- Modify: `scripts/import_fixtures.py`

- [ ] **Step 1: Update migrate_phase1_design_to_neo4j.py**

This legacy script references `OntologyNode`, `OntologyTriple`, `Predicate`, and `DesignNode`. Mark it as deprecated or update it. Since it's a one-time migration script that may not be needed after the new migration, add a deprecation notice:

```python
"""
DEPRECATED: This script was used for the Phase 1 SQLite → Neo4j migration.
For label migration (:Design → :Compound/:Member/:Namespace), use:
    python scripts/migrate_design_labels.py
"""
```

Update imports to use the new models where `DesignNode` was used.

- [ ] **Step 2: Update scripts/01_flush_db.py**

If it references `Predicate` or `OntologyNode`, update or remove those references.

- [ ] **Step 3: Update scripts/import_fixtures.py**

If it references `OntologyNode`, update to not create ORM objects or mark as deprecated.

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -v --timeout=60`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: update migration scripts for new graph primitives, deprecate old ones"
```

---

## Task 12: Run Full Test Suite and Fix Any Remaining Issues

- [ ] **Step 1: Run complete test suite**

Run: `pytest tests/ -v --timeout=60`
Expected: All pass

- [ ] **Step 2: Grep for any remaining references to deleted models**

```bash
grep -rn "from backend.db.models.ontology import\|from backend.db.models import.*OntologyNode\|from backend.db.models import.*OntologyTriple\|from backend.db.models import.*Predicate" --include='*.py' | grep -v __pycache__ | grep -v "test_ontology"
```

Expected: No results (or only comments/deprecated markers)

- [ ] **Step 3: Grep for any remaining DesignNode/DesignTripleUpdate references**

```bash
grep -rn "DesignNode\|DesignTripleUpdate" --include='*.py' | grep -v __pycache__ | grep -v "test_design_repository"
```

Fix any remaining references found.

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix: clean up remaining references to deleted models"
```