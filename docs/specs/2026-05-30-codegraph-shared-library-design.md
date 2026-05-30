# Codegraph Shared Library — Design Spec

**Date**: 2026-05-30  
**Status**: draft  

## Motivation

The [ticketing system](https://github.com/danielnewman09/ticketing-system) and the
[Doxygen Dependency Parser](https://github.com/danielnewman09/Doxygen-Dependency-Parser)
share a Neo4j graph data model for codebase nodes and edges. Currently each
repository defines its own representation of the same concepts — node labels
(`:File`, `:Namespace`, `:Compound`, `:Member`, `:Parameter`), edge types, and
constants — leading to divergence risk and making cross-layer comparisons
fragile.

A single library ensures that both systems speak the same data language:
the Doxygen parser populates `as-built` and `dependency` layers, the ticketing
system adds the `design` layer on top, and direct comparison across layers is
guaranteed by a shared schema.

## Design

### Package

Separate repository at `github.com/danielnewman09/codegraph`, published to
PyPI as `codegraph`.

```
codegraph/
  pyproject.toml
  src/codegraph/
    __init__.py       # re-exports public API
    nodes.py          # 5 Pydantic BaseModel classes
    edges.py          # CodebaseEdge + PREDICATES list
    constants.py      # kinds, layers, visibility, predicate maps, indexes
  tests/
    test_nodes.py
    test_edges.py
    test_constants.py
```

**Dependencies**: `pydantic>=2.0`. No Neo4j driver dependency — this library defines
the *data model*, not how it's written to a database.

### Node models (5 Pydantic BaseModel classes)

All models use `qualified_name` as the logical identity and `layer` to
distinguish origin. Every field is optional with sensible defaults unless
marked otherwise.

#### FileNode → label `:File`

| Field     | Type        | Notes                                                                 |
|-----------|-------------|-----------------------------------------------------------------------|
| `refid`   | `str`       | **Required**. Doxygen refid; unique.                                  |
| `name`    | `str = ""`  |                                                                       |
| `path`    | `str = ""`  |                                                                       |
| `language`| `str = ""`  |                                                                       |
| `source`  | `str = ""`  | Provenance label.                                                     |

#### NamespaceNode → label `:Namespace`

| Field            | Type                                                | Notes |
|------------------|-----------------------------------------------------|-------|
| `qualified_name` | `str`                                               | **Required**. |
| `name`           | `str = ""`                                          |       |
| `kind`           | `Literal["namespace", "package", "module"] = "namespace"` | |
| `layer`          | `Literal["design", "as-built", "dependency"] = "design"` | |
| `refid`          | `str = ""`                                          | Doxygen refid (empty for design-layer). |
| `description`    | `str = ""`                                          |       |
| `source`         | `str = ""`                                          |       |

#### CompoundNode → label `:Compound`

| Field                  | Type      | Notes |
|------------------------|-----------|-------|
| `qualified_name`       | `str`     | **Required**. |
| `name`                 | `str = ""`|       |
| `kind`                 | `Literal["class", "struct", "template_class", "interface", "abstract_class", "enum", "enum_class"]` | **Required**. |
| `layer`                | `Literal["design", "as-built", "dependency"] = "design"` | |
| `refid`                | `str = ""` | Doxygen refid. |
| `description`          | `str = ""` | Unified description (maps from `brief_description` in Doxygen parser). |
| `brief_description`    | `str = ""` | Doxygen brief. |
| `detailed_description` | `str = ""` | Doxygen detailed. |
| `base_classes`         | `list[str] = []` | |
| `file_path`            | `str = ""` | |
| `line_number`          | `int|None = None` | |
| `source`               | `str = ""` | Provenance. |
| `protection`           | `Literal["public", "private", "protected", ""] = ""` | Access specifier. |
| `is_final`             | `bool = False` | |
| `is_abstract`          | `bool = False` | |

#### MemberNode → label `:Member`

| Field                  | Type      | Notes |
|------------------------|-----------|-------|
| `qualified_name`       | `str`     | **Required**. |
| `name`                 | `str = ""`|       |
| `kind`                 | `Literal["method", "attribute", "constant", "enum_value", "function"]` | **Required**. |
| `layer`                | `Literal["design", "as-built", "dependency"] = "design"` | |
| `refid`                | `str = ""` | Doxygen refid. |
| `compound_refid`       | `str = ""` | Doxygen refid of owning compound. |
| `description`          | `str = ""` | Unified description. |
| `brief_description`    | `str = ""` | Doxygen brief. |
| `detailed_description` | `str = ""` | Doxygen detailed. |
| `type_signature`       | `str = ""` | Return type for methods, field type for attributes. Maps from Doxygen `type`. |
| `definition`           | `str = ""` | |
| `argsstring`           | `str = ""` | |
| `file_path`            | `str = ""` | |
| `line_number`          | `int|None = None` | |
| `source`               | `str = ""` | |
| `protection`           | `Literal["public", "private", "protected", ""] = ""` | |
| `is_static`            | `bool = False` | |
| `is_const`             | `bool = False` | |
| `is_constexpr`         | `bool = False` | |
| `is_virtual`           | `bool = False` | |
| `is_inline`            | `bool = False` | |
| `is_explicit`          | `bool = False` | |

#### ParameterNode → label `:Parameter`

| Field            | Type   | Notes |
|------------------|--------|-------|
| `position`       | `int`  | **Required**. Parameter index (0-based). |
| `name`           | `str`  | **Required**. |
| `type`           | `str = ""` | |
| `default_value`  | `str = ""` | |
| `member_refid`   | `str = ""` | Doxygen refid of owning member. |

**Subclassing**: Each consumer may subclass to add domain-specific fields:
- Ticketing system: `component_id`, `implementation_status`, `is_intercomponent`, `source_file`, `test_file` on `CompoundNode`
- Doxygen parser: no subclassing needed; uses models directly

### Edge definitions

#### Shared CodebaseEdge model

```python
class CodebaseEdge(BaseModel):
    subject_qualified_name: str
    predicate: str           # Must be one of PREDICATES
    object_qualified_name: str
    mechanism: str = ""      # Container/smart-pointer type
    position: int | None = None  # For TYPE_ARGUMENT edges
    name: str = ""           # For TEMPLATE_PARAM edges
    display_name: str = ""   # Alias display name
```

#### Core edge types (used by both systems)

| Predicate       | Direction              | Description               |
|-----------------|------------------------|---------------------------|
| `COMPOSES`      | Compound→Member, Namespace→Compound, Namespace→Namespace | Ownership hierarchy |
| `DEFINED_IN`    | Compound→File, Member→File | Source file location   |
| `INCLUDES`      | File→File              | `#include` resolution      |
| `INHERITS_FROM` | Compound→Compound      | Class inheritance          |
| `CALLS`         | Member→Member          | Function call              |
| `HAS_PARAMETER` | Member→Parameter       | Method parameters          |

#### Full predicate vocabulary (shared vocabulary for all consumers)

```
associates, aggregates, composes, depends_on, generalizes, realizes,
references, invokes, has_argument, returns, type_argument, template_param,
implements
```

### Constants

All constants in `codegraph.constants`:

| Constant                   | Values                                                                              |
|----------------------------|-------------------------------------------------------------------------------------|
| `COMPOUND_KINDS`           | `class`, `struct`, `template_class`, `interface`, `abstract_class`, `enum`, `enum_class` |
| `MEMBER_KINDS`             | `method`, `attribute`, `constant`, `enum_value`, `function`                         |
| `NAMESPACE_KINDS`          | `namespace`, `package`, `module`                                                    |
| `NODE_KINDS`               | Union of all three above                                                            |
| `LAYERS`                   | `design`, `as-built`, `dependency`                                                  |
| `VISIBILITY_CHOICES`       | `public`, `private`, `protected`                                                    |
| `PREDICATES`               | All 13 lowercase predicate names                                                    |
| `PREDICATE_TO_REL_TYPE`    | `{"composes": "COMPOSES", ...}` mapping                                             |
| `CONSTRAINTS_AND_INDEXES`  | Cypher DDL statements for uniqueness constraints and indexes                        |

### Constraints and indexes

Canonical Cypher DDL (migrated from the Doxygen parser's current schema):

```cypher
CREATE CONSTRAINT file_refid IF NOT EXISTS FOR (f:File) REQUIRE f.refid IS UNIQUE
CREATE INDEX namespace_refid IF NOT EXISTS FOR (n:Namespace) ON (n.refid)
CREATE INDEX compound_refid IF NOT EXISTS FOR (c:Compound) ON (c.refid)
CREATE INDEX member_refid IF NOT EXISTS FOR (m:Member) ON (m.refid)
CREATE INDEX file_name IF NOT EXISTS FOR (f:File) ON (f.name)
CREATE INDEX file_path IF NOT EXISTS FOR (f:File) ON (f.path)
CREATE INDEX namespace_name IF NOT EXISTS FOR (n:Namespace) ON (n.name)
CREATE INDEX compound_name IF NOT EXISTS FOR (c:Compound) ON (c.name)
CREATE INDEX compound_qualified IF NOT EXISTS FOR (c:Compound) ON (c.qualified_name)
CREATE INDEX compound_kind IF NOT EXISTS FOR (c:Compound) ON (c.kind)
CREATE INDEX member_name IF NOT EXISTS FOR (m:Member) ON (m.name)
CREATE INDEX member_qualified IF NOT EXISTS FOR (m:Member) ON (m.qualified_name)
CREATE INDEX member_kind IF NOT EXISTS FOR (m:Member) ON (m.kind)
CREATE INDEX compound_layer IF NOT EXISTS FOR (c:Compound) ON (c.layer)
CREATE INDEX member_layer IF NOT EXISTS FOR (m:Member) ON (m.layer)
CREATE INDEX namespace_layer IF NOT EXISTS FOR (n:Namespace) ON (n.layer)
CREATE INDEX file_source IF NOT EXISTS FOR (f:File) ON (f.source)
CREATE INDEX compound_source IF NOT EXISTS FOR (c:Compound) ON (c.source)
CREATE INDEX member_source IF NOT EXISTS FOR (m:Member) ON (m.source)
CREATE INDEX namespace_source IF NOT EXISTS FOR (n:Namespace) ON (n.source)
CREATE FULLTEXT INDEX doc_search IF NOT EXISTS FOR (n:Compound|Member) ON EACH [n.name, n.qualified_name, n.brief_description, n.detailed_description]
```

### Public API

`from codegraph import ...` exports:

- `FileNode`, `NamespaceNode`, `CompoundNode`, `MemberNode`, `ParameterNode`
- `CodebaseEdge`
- `PREDICATES`, `PREDICATE_TO_REL_TYPE`
- `COMPOUND_KINDS`, `MEMBER_KINDS`, `NAMESPACE_KINDS`, `NODE_KINDS`
- `LAYERS`, `VISIBILITY_CHOICES`
- `CONSTRAINTS_AND_INDEXES`

### What is NOT in scope

- Neo4j driver or Cypher write helpers
- Repository / data-access layer (stays in ticketing system)
- Parse result types (`ParseResult`, include/call structs — stay in Doxygen parser)
- Design-layer node properties (`component_id`, `implementation_status`, etc.)
- Graph visualization containers (`CompoundGraph`, `OntologyGraph`)

## Migration plan

1. **Create `codegraph` repo**, implement models/edges/constants, publish v0.1.0
2. **Doxygen parser**: depend on `codegraph`; replace local `dataclass` parse result types
   with `codegraph` Pydantic models; replace `asdict()` with `model_dump()`
3. **Ticketing system**: depend on `codegraph`; rebase
   `backend/db/neo4j/models/nodes/` on `codegraph` base classes by:
   - Renaming `visibility` → `protection` throughout
   - Subclassing `CompoundNode` to add `component_id`, `implementation_status`, `source_file`, `test_file`, `is_intercomponent`
   - Removing any fields already present in the base models
   - Updating imports throughout the codebase

## Testing

Pure unit tests in the `codegraph` repo:

- Pydantic validation (required fields, type coercion, invalid values rejected)
- Serialization round-trips (`model_dump()` then `model_validate()` yields identical object)
- Edge identity (subject + predicate + object uniqueness)
- Constant consistency (no duplicate predicates, every predicate has a rel-type mapping, all kind lists are disjoint)
