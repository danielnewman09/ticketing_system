# Codebase Graph Primitives — Design Spec

## Problem

The codebase currently has at least four overlapping data models for representing design/codebase data:

1. **`db/models/ontology.py`** — SQLAlchemy ORM models (`OntologyNode`, `OntologyTriple`, `Predicate`) backed by SQLite. Deprecated; design data now lives in Neo4j.
2. **`codebase/schemas.py`** — Pydantic schemas (`OODesignSchema`, `OntologyNodeSchema`, `DesignSchema`) for LLM agent input/output.
3. **`design_data/models.py`** — Rich Pydantic read models (`ClassDiagram`, `ClassNode`, `DiagramNode`, etc.) for querying Neo4j.
4. **`db/neo4j/repositories/models/design.py`** — `DesignNode` and `DesignTripleUpdate`, the Neo4j write contract.

These share overlapping fields (`kind`, `name`, `qualified_name`, `visibility`, `specialization`, `type_signature`, etc.) with slight variations. The SQLAlchemy models are confirmed deprecated and should be removed.

Additionally, the Neo4j schema conflates two orthogonal concepts: `source_type` (what kind of code object: compound/member/namespace) and `layer` (where it came from: design/as-built/dependency). These are currently mashed into a single `source_type` property, and all nodes share a `:Design` label regardless of type.

## Goal

Phase 1: Replace the tangled data models with clean graph primitives that directly mirror the Neo4j node types, making `source_type` and `layer` orthogonal, and removing the deprecated ORM models. Phase 2 (future) will add domain objects on top.

## Design Decisions

1. **SQLAlchemy ontology models are deleted** — design data lives in Neo4j.
2. **Three distinct node types** — `:Compound`, `:Member`, `:Namespace` replace `:Design` as Neo4j labels. Each is a separate Pydantic model.
3. **`layer` is an explicit property** — `design`, `as-built`, or `dependency`. It replaces the overloaded `source_type` for distinguishing data origin.
4. **`source_type` is removed** — the node label (Compound/Member/Namespace) now conveys what was previously `source_type`. A dependency class is `:Compound {layer: 'dependency'}`, not a single `:Design` node with `source_type='dependency'`.
5. **Pydantic models are the source of truth** — no separate schema definition file. Documentation comes from model docstrings and field descriptions.
6. **Agent schemas are absorbed later** — `codebase/schemas.py` and `design_data/` are left alone in Phase 1, with adapter functions bridging new primitives to old shapes. They'll be replaced in Phase 2 when domain objects are built.

---

## Graph Primitives

### CompoundNode — `:Compound` in Neo4j

Top-level containers: classes, structs, interfaces, enums. Own members via COMPOSES edges.

```python
class CompoundNode(BaseModel):
    """A compound entity in the codebase graph (:Compound in Neo4j).

    Compounds are the top-level containers — classes, structs, interfaces,
    enums — that own members and participate in associations.

    The `kind` field refines the specific type. The `layer` field indicates
    origin: 'design' (agent-created), 'as-built' (parsed from code), or
    'dependency' (external library).

    Identified by `qualified_name`, used as the MERGE key in Neo4j.
    """
    qualified_name: str
    name: str
    kind: Literal["class", "struct", "template_class", "interface", "abstract_class", "enum", "enum_class"]
    layer: Literal["design", "as-built", "dependency"] = "design"
    specialization: str = ""
    visibility: Literal["public", "private", "protected", ""] = ""
    description: str = ""

    # Code-level detail
    type_signature: str = ""
    argsstring: str = ""
    definition: str = ""

    # Source location (populated for as-built layer)
    refid: str = ""
    file_path: str = ""
    line_number: int | None = None

    # Flags
    is_static: bool = False
    is_const: bool = False
    is_virtual: bool = False
    is_abstract: bool = False
    is_final: bool = False

    # Project context
    component_id: int | None = None
    is_intercomponent: bool = False

    # Implementation tracking (design layer)
    implementation_status: Literal["designed", "scaffolded", "tested", "implemented", "verified"] = "designed"
    source_file: str = ""
    test_file: str = ""
```

### MemberNode — `:Member` in Neo4j

Owned by compounds: methods, attributes, constants, enum values.

```python
class MemberNode(BaseModel):
    """A member entity in the codebase graph (:Member in Neo4j).

    Members are owned by compounds — methods and attributes on classes,
    values inside enums, constants inside namespaces.

    The `kind` field refines the specific member type. The `layer` field
    indicates origin.
    """
    qualified_name: str
    name: str
    kind: Literal["method", "attribute", "constant", "enum_value"]
    layer: Literal["design", "as-built", "dependency"] = "design"
    visibility: Literal["public", "private", "protected", ""] = ""
    description: str = ""

    # Code-level detail
    type_signature: str = ""
    argsstring: str = ""
    definition: str = ""

    # Source location
    refid: str = ""
    file_path: str = ""
    line_number: int | None = None

    # Flags
    is_static: bool = False
    is_const: bool = False
    is_virtual: bool = False
    is_abstract: bool = False
    is_final: bool = False

    # Project context
    component_id: int | None = None
```

### NamespaceNode — `:Namespace` in Neo4j

Namespaces and packages that group compounds.

```python
class NamespaceNode(BaseModel):
    """A namespace entity in the codebase graph (:Namespace in Neo4j).

    Namespaces group compounds into modules. They form a hierarchy via
    COMPOSES edges (e.g. `std` COMPOSES `std::chrono`).
    """
    qualified_name: str
    name: str
    kind: Literal["namespace", "package"] = "namespace"
    layer: Literal["design", "as-built", "dependency"] = "design"
    description: str = ""

    # Source location
    refid: str = ""
    file_path: str = ""

    # Project context
    component_id: int | None = None
```

### CodebaseEdge — Relationships between nodes

```python
PREDICATES = [
    "composes",       # Ownership: namespace→compound, compound→member
    "aggregates",     # Whole-part (part can exist independently)
    "references",     # Type reference (attribute type, parameter type)
    "depends_on",     # Header/library dependency
    "associates",     # Generic association
    "invokes",        # Caller-callee
    "returns",        # Method return type reference
    "generalizes",    # Inheritance (child → parent)
    "realizes",       # Interface implementation
    "implements",     # Alternative for realizes
    "has_argument",   # Method parameter
    "type_argument",  # Template type argument
    "template_param", # Template parameter declaration
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

---

## File and Module Structure

```
backend/db/neo4j/models/
├── __init__.py              # Re-exports all primitives
├── constants.py             # KINDS, PREDICATES, LANGUAGE_SPECIALIZATIONS, etc.
├── nodes/
│   ├── __init__.py          # Re-exports CompoundNode, MemberNode, NamespaceNode
│   ├── compound.py          # CompoundNode
│   ├── member.py            # MemberNode
│   └── namespace.py          # NamespaceNode
└── edges.py                 # CodebaseEdge, PREDICATES

backend/models/              # (Phase 2 — domain objects, empty for now)
└── __init__.py
```

### Constants module

`backend/db/neo4j/models/constants.py` reorganizes the enum-like definitions from `db/models/ontology.py`:

```python
COMPOUND_KINDS = ["class", "struct", "template_class", "interface", "abstract_class", "enum", "enum_class"]
MEMBER_KINDS = ["method", "attribute", "constant", "enum_value"]
NAMESPACE_KINDS = ["namespace", "package"]
NODE_KINDS = COMPOUND_KINDS + MEMBER_KINDS + NAMESPACE_KINDS

TYPE_KINDS = {"class", "struct", "template_class", "interface", "abstract_class", "enum", "enum_class"}
VALUE_KINDS = {"method", "attribute", "constant", "enum_value"}

VISIBILITY_CHOICES = ["public", "private", "protected"]
LAYERS = ["design", "as-built", "dependency"]

LANGUAGE_SPECIALIZATIONS = { ... }  # Same as current, kept verbatim
SUPPORTED_LANGUAGES = set(LANGUAGE_SPECIALIZATIONS.keys())

def valid_specializations(language, kind):
    """Return the set of valid specializations for a language + kind."""
    ...
```

---

## Neo4j Schema Changes

| Current | New |
|---------|-----|
| `:Design` label on all nodes | `:Compound`, `:Member`, or `:Namespace` label |
| `source_type` property (compound/member/namespace/dependency) | Removed — replaced by node label + `layer` property |
| `source_type='dependency'` on stub nodes | `layer='dependency'` + appropriate node label (e.g. `:Compound {layer: 'dependency'}`) |
| Typed relationships (AGGREGATES, COMPOSES, etc.) | Same — predicates lowercase in model, uppercased in Neo4j |

### Index changes

Current (on `:Design`):

```cypher
CREATE INDEX design_qualified_name IF NOT EXISTS FOR (n:Design) ON (n.qualified_name)
CREATE INDEX design_source_type IF NOT EXISTS FOR (n:Design) ON (n.source_type)
```

New (per node type):

```cypher
CREATE INDEX compound_qualified_name IF NOT EXISTS FOR (n:Compound) ON (n.qualified_name)
CREATE INDEX compound_layer IF NOT EXISTS FOR (n:Compound) ON (n.layer)
CREATE INDEX member_qualified_name IF NOT EXISTS FOR (n:Member) ON (n.qualified_name)
CREATE INDEX member_layer IF NOT EXISTS FOR (n:Member) ON (n.layer)
CREATE INDEX namespace_qualified_name IF NOT EXISTS FOR (n:Namespace) ON (n.qualified_name)
CREATE INDEX namespace_layer IF NOT EXISTS FOR (n:Namespace) ON (n.layer)
```

---

## DesignRepository Updates

`DesignRepository` in `db/neo4j/repositories/design.py` currently uses `DesignNode` and `DesignTripleUpdate`. Changes:

1. **`merge_node()` dispatches by type** — sets `:Compound`, `:Member`, or `:Namespace` label based on the node model.

2. **`source_type` property no longer written** — node label conveys type. `layer` property is written instead.

3. **Read methods return typed models** — `get_class_diagram()` and other queries return `CompoundNode`, `MemberNode`, `NamespaceNode` (or adapter-shaped results during transition).

4. **Edge writes use `CodebaseEdge`** — `merge_triple()` replaces `DesignTripleUpdate`.

### Merge examples

Current:

```cypher
MERGE (d:Design {qualified_name: $qualified_name})
SET d += $props
```

New:

```cypher
MERGE (c:Compound {qualified_name: $qualified_name})
SET c += $props, c.layer = $layer
```

---

## What Gets Deleted

| What | Location | Why |
|------|----------|-----|
| `OntologyNode` | `db/models/ontology.py` | Deprecated SQLAlchemy ORM model |
| `OntologyTriple` | `db/models/ontology.py` | Deprecated SQLAlchemy ORM model |
| `Predicate` | `db/models/ontology.py` | Deprecated SQLAlchemy ORM model |
| `DesignNode` | `db/neo4j/repositories/models/design.py` | Replaced by typed node models |
| `DesignTripleUpdate` | `db/neo4j/repositories/models/design.py` | Replaced by `CodebaseEdge` |

Files left intact for Phase 2:
- `backend/codebase/schemas.py` — adapter functions bridge to old shapes
- `backend/design_data/` — adapter functions bridge to `ClassDiagram` etc.

---

## What Gets Relocated

| What | From | To |
|------|------|----|
| `NODE_KINDS`, `COMPOUND_KINDS`, `MEMBER_KINDS`, etc. | `db/models/ontology.py` | `db/neo4j/models/constants.py` |
| `LANGUAGE_SPECIALIZATIONS`, `SUPPORTED_LANGUAGES`, `valid_specializations()` | `db/models/ontology.py` | `db/neo4j/models/constants.py` |
| `VISIBILITY_CHOICES`, `TYPE_KINDS`, `VALUE_KINDS` | `db/models/ontology.py` | `db/neo4j/models/constants.py` |
| Re-exports from `db/models/__init__.py` | `db/models/__init__.py` | Removed (or replaced with imports from new location) |

---

## Migration Steps

1. **Create new model files** — `nodes/compound.py`, `nodes/member.py`, `nodes/namespace.py`, `edges.py`, `constants.py` in `backend/db/neo4j/models/`.

2. **Update `DesignRepository`** — modify `merge_node()` and read methods to use new models. Write `layer` property, dispatch node label by type.

3. **Write Neo4j migration script** that:
   - Adds `:Compound` labels to nodes with `source_type` in (compound, or missing/empty for top-level design nodes)
   - Adds `:Member` labels to nodes with `source_type='member'`
   - Adds `:Namespace` labels to nodes with `source_type='namespace'`
   - Sets `layer` property: `source_type='dependency'` → `layer='dependency'`, `source_type='compound'` → `layer='as-built'`, `source_type='member'` with no component/design context → `layer='design'`, etc.
   - Removes `source_type` property from all nodes
   - Removes `:Design` label from all nodes
   - Drops old `:Design` indexes, creates new per-type indexes

4. **Add adapter functions** that convert new primitives to old shapes (`ClassDiagram`, `DiagramNode`, `OODesignSchema`, etc.) so existing pipeline and UI code keeps working.

5. **Update `db/models/__init__.py`** — remove ontology ORM re-exports. Code that imported `NODE_KINDS` etc. from there should import from `db.neo4j.models.constants` instead.

6. **Delete `db/models/ontology.py`** and `db/neo4j/repositories/models/design.py`.

7. **Update all imports** across the codebase that referenced the deleted models.

---

## Out of Scope (Phase 2)

- Domain objects in `backend/models/` (`Class`, `Interface`, `Enum`, `Module`) that wrap graph primitives
- Removal of `codebase/schemas.py` (`OODesignSchema` etc.) — absorbed into domain objects later
- Removal of `design_data/` package — replaced by domain objects later
- Agent schema methods (`to_agent_schema()` / `from_agent_schema()`) — built on domain objects later
- `ClassDiagram` hydration query refactoring