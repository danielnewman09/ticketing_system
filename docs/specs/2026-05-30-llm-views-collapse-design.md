# Collapse Codebase Schemas into Codegraph OO Design Models

2026-05-30

## Problem

Three separate places define representations of the same codebase entities,
creating duplication and divergence:

1. **`backend/codebase/schemas.py`** — Pydantic schemas for the design pipeline
   (Stage 1 OO shapes for LLM interaction, Stage 2 ontology shapes for Neo4j).
2. **`backend/db/neo4j/models/nodes/compound.py`** — Neo4j node model extending
   `codegraph.nodes.CompoundNode` with ticketing-specific fields.
3. **`backend/design_data/models.py`** — Rich Pydantic read models
   (`ClassDiagram`, `ClassNode`, `InterfaceNode`, `EnumNode`, etc.) providing
   the object-oriented view of design data with nested members, cross-entity
   associations, and query/transformation methods.

The goal: two layers maximum. `codegraph` as the universal base, and one thin
ticketing-system extension for fields that are genuinely novel to this repo.

## Key Insight

The LLM "views" and the ClassDiagram read models are structurally nearly
identical (both have classes, interfaces, enums, associations with nested
members). Rather than create a third parallel representation, `ClassDiagram`
becomes the single canonical OO design model in codegraph. It handles three
concerns:

1. **LLM serialization** — a thin subset (no file_path, layer, code flags)
2. **Neo4j round-tripping** — `from_neo4j()` / `to_neo4j()`
3. **Query and transformation methods** — `get_entity()`, `to_verification_dicts()`, etc.

```
LLM → thin ClassDiagram → enrichment → rich ClassDiagram ↔ Neo4j
```

## Scope

### In scope

- Move `ClassDiagram`, `ClassNode`, `InterfaceNode`, `EnumNode`, `ModuleNode`,
  `Association`, `AttributeNode`, `MethodNode`, `EnumValueNode` from
  `backend/design_data/models.py` into `codegraph/designs/`.
- File layout mirrors `codegraph/nodes/`: `designs/compound.py`,
  `designs/member.py`, `designs/edges.py`, etc.
- Absorb `OODesignSchema` (from `backend/codebase/schemas.py`) into
  `ClassDiagram` — the LLM reads and writes ClassDiagram directly.
- Add `ClassDiagram.to_neo4j()` and `ClassDiagram.from_neo4j()` for
  round-tripping between ClassDiagram and codegraph nodes/edges.
- Add `FieldTags` annotation mechanism on ClassDiagram member models to control
  which fields appear in LLM serialization vs. Neo4j-only fields.
- Move `TypeRef` from `backend/codebase/schemas.py` into codegraph.
- Thin `backend/codebase/schemas.py` to only ticketing-specific schemas
  (`RequirementTripleLinkSchema`, `DesignSchema`).
- Thin `backend/db/neo4j/models/nodes/compound.py` to only
  `specialization`, `is_intercomponent`, `implementation_status`, `test_file`.
- `backend/design_data/models.py` → temporary re-export shim (deprecated).
- `backend/design_data/transforms.py` → `class_diagram_from_oo_design()` and
  `oo_design_from_class_diagram()` become no-ops or are absorbed into
  ClassDiagram enrichment.

### Deferred

- Moving `DesignDataRepository` to codegraph — stays in ticketing system for
  now. ClassDiagram gets `from_neo4j()` / `to_neo4j()` as methods; the
  repository's Cypher queries remain in the ticketing layer.
- Full enrichment logic (`ClassDiagram.enrich()`) — deferred until a follow-up
  design. The enrichment step (resolving type signatures, file paths, code
  flags) will eventually live in codegraph.

### Out of scope

- Changing LLM prompt contracts — field names visible to the LLM stay the same
  (aliases preserve backward compatibility).
- Removing `backend/design_data/repository.py` — stays as-is; import paths
  updated.

## Architecture

### codegraph

```
codegraph/src/codegraph/
├── designs/
│   ├── __init__.py              # ClassDiagram, FieldTags, re-exports
│   ├── tags.py                  # FieldTags class + LLM/NEO4J/READ tag constants
│   ├── compound.py              # ClassNode, InterfaceNode, EnumNode
│   ├── member.py                # AttributeNode, MethodNode, EnumValueNode
│   ├── namespace.py             # ModuleNode
│   └── edges.py                 # Association
├── type_parser.py               # MOVED: TypeRef + parsing utilities
├── nodes/                       # unchanged
│   ├── compound_node.py         # + Annotated[FieldTags(...)]
│   ├── member_node.py           # + Annotated[FieldTags(...)]
│   └── *
├── edges.py                     # + Annotated[FieldTags(...)]
└── constants.py                 # unchanged
```

### Ticketing system (after collapse)

```
backend/
├── codebase/
│   ├── schemas.py               # reduced: RequirementTripleLinkSchema, DesignSchema
│   ├── type_parser.py           # DELETED (moved to codegraph)
│   └── indexing.py              # unchanged
├── db/neo4j/models/nodes/
│   ├── compound.py              # thinned: only ticketing-specific fields
│   └── member.py                # unchanged (already thin)
└── design_data/
    ├── models.py                # TEMPORARY re-export shim (→ codegraph.designs)
    ├── repository.py            # unchanged (import paths updated)
    └── transforms.py            # deprecated — OODesignSchema removed
```

## Field Tagging

`FieldTags` lives in `codegraph/designs/tags.py` and is applied via
`typing.Annotated` on the design model fields (ClassNode, InterfaceNode, etc.).

```python
# codegraph/designs/tags.py

class FieldTags:
    LLM: str = "llm"          # serialized to LLM
    NEO4J: str = "neo4j"       # persisted to Neo4j
    READ: str = "read"         # internal read-only
    TICKETING: str = "ticketing"  # ticketing-system extension

    def __init__(self, *tags: str) -> None: ...
```

Usage on design model fields:

```python
class ClassNode(BaseModel):
    name: Annotated[str, FieldTags(LLM, NEO4J, READ)]
    qualified_name: Annotated[str, FieldTags(LLM, NEO4J, READ)]
    kind: Annotated[str, FieldTags(LLM, NEO4J, READ)]
    description: Annotated[str, FieldTags(LLM, NEO4J, READ)]
    file_path: Annotated[str, FieldTags(NEO4J, READ)]       # NOT in LLM
    line_number: Annotated[int | None, FieldTags(NEO4J, READ)]
    is_static: Annotated[bool, FieldTags(NEO4J, READ)]
    implementation_status: Annotated[str, FieldTags(TICKETING)]
    # ...
```

### Serialization modes

ClassDiagram and its member models provide a `model_dump(tags=...)` override
that filters fields based on their `FieldTags` annotation:

```python
diagram.model_dump()                    # all fields (Neo4j, debug)
diagram.model_dump(tags={"LLM"})        # LLM subset — no file_path, layer, flags
diagram.model_dump(tags={"LLM", "TICKETING"})  # LLM + ticketing fields
```

Implementation: a shared mixin or base-class override on DiagramNode walks
`typing.get_type_hints(include_extras=True)` at call time, inspects the
`FieldTags` metadata on each field, and excludes fields whose tags have no
intersection with the requested set. Recurses into nested model lists
(attributes, methods, values) so `ClassDiagram.model_dump(tags={"LLM"})`
produces a fully tagged output with nested members filtered as well.

## Design Models (moved to codegraph/designs/)

### `DiagramNode` (base) — `designs/compound.py`

Common fields for every diagram node. Moves unchanged from
`backend/design_data/models.py`, with `FieldTags` annotations added.

| Field | Tags | Notes |
|---|---|---|
| `name` | LLM, NEO4J, READ | |
| `qualified_name` | LLM, NEO4J, READ | Identity anchor |
| `kind` | LLM, NEO4J, READ | |
| `layer` | NEO4J, READ | NOT in LLM |
| `description` | LLM, NEO4J, READ | |
| `visibility` | LLM, NEO4J, READ | |
| `specialization` | TICKETING | Ticketing extension |
| `component_id` | NEO4J, READ | NOT in LLM |
| `is_intercomponent` | TICKETING | Ticketing extension |
| `type_signature` | LLM, NEO4J, READ | LLM sees as `type_name` (alias) |
| `argsstring` | LLM, NEO4J, READ | |
| `definition` | NEO4J, READ | NOT in LLM |
| `source_type` | NEO4J, READ | NOT in LLM |
| `source` | NEO4J, READ | NOT in LLM |
| `file_path` | NEO4J, READ | NOT in LLM |
| `line_number` | NEO4J, READ | NOT in LLM |
| `is_static` | NEO4J, READ | NOT in LLM |
| `is_const` | NEO4J, READ | NOT in LLM |
| `is_virtual` | NEO4J, READ | NOT in LLM |
| `is_abstract` | NEO4J, READ | NOT in LLM |
| `is_final` | NEO4J, READ | NOT in LLM |
| `implementation_status` | TICKETING | Ticketing extension |
| `test_file` | TICKETING | Ticketing extension |

### `ClassNode` — `designs/compound.py`

| Field | Tags | Notes |
|---|---|---|
| *(all DiagramNode fields)* | | |
| `module` | LLM, NEO4J, READ | |
| `inherits_from` | LLM, NEO4J, READ | |
| `realizes` | LLM, NEO4J, READ | |
| `attributes` | LLM, NEO4J, READ | list[AttributeNode] |
| `methods` | LLM, NEO4J, READ | list[MethodNode] |

### `InterfaceNode` — `designs/compound.py`

| Field | Tags |
|---|---|
| *(all DiagramNode fields)* | |
| `module` | LLM, NEO4J, READ |
| `methods` | LLM, NEO4J, READ | list[MethodNode] |

### `EnumNode` — `designs/compound.py`

| Field | Tags |
|---|---|
| *(all DiagramNode fields)* | |
| `module` | LLM, NEO4J, READ |
| `values` | LLM, NEO4J, READ | list[EnumValueNode] |

### `AttributeNode` — `designs/member.py`

| Field | Tags | Notes |
|---|---|---|
| `name` | LLM, NEO4J, READ | |
| `qualified_name` | LLM, NEO4J, READ | |
| `kind` | LLM, NEO4J, READ | Literal["attribute"] |
| `description` | LLM, NEO4J, READ | |
| `visibility` | LLM, NEO4J, READ | |
| `type_signature` | LLM, NEO4J, READ | LLM serialized as `type_name` (alias) |
| `owner` | NEO4J, READ | NOT in LLM |
| `component_id` | NEO4J, READ | NOT in LLM |

### `MethodNode` — `designs/member.py`

| Field | Tags | Notes |
|---|---|---|
| `name` | LLM, NEO4J, READ | |
| `qualified_name` | LLM, NEO4J, READ | |
| `kind` | LLM, NEO4J, READ | Literal["method"] |
| `description` | LLM, NEO4J, READ | |
| `visibility` | LLM, NEO4J, READ | |
| `type_signature` | LLM, NEO4J, READ | LLM sees as `return_type` (alias) |
| `argsstring` | LLM, NEO4J, READ | |
| `owner` | NEO4J, READ | NOT in LLM |
| `component_id` | NEO4J, READ | NOT in LLM |

### `Association` — `designs/edges.py`

| Field | Tags | Notes |
|---|---|---|
| `subject` | LLM, NEO4J, READ | LLM sees as `from_class` (alias) |
| `predicate` | LLM, NEO4J, READ | LLM sees as `kind` (alias) |
| `object` | LLM, NEO4J, READ | LLM sees as `to_class` (alias) |
| `mechanism` | LLM, NEO4J, READ | |
| `description` | LLM, NEO4J, READ | |

### `ClassDiagram` — `designs/__init__.py`

Container with all existing methods preserved:
- `get_entity()`, `associations_for()`, `associations_involving()`
- `classes_in_module()`
- `to_verification_dicts()`, `to_draft_lookup()`, `to_class_lookup()`, `to_summary()`
- `_entity_index` (PrivateAttr)

**New methods:**

```python
def to_neo4j(self) -> tuple[list[CompoundNode], list[MemberNode], list[CodebaseEdge]]:
    """Decompose ClassDiagram into codegraph node/edge models for Neo4j persistence."""

@classmethod
def from_neo4j(
    cls,
    compounds: list[CompoundNode],
    members: list[MemberNode],
    edges: list[CodebaseEdge],
) -> ClassDiagram:
    """Reconstruct ClassDiagram from Neo4j query results."""

def model_dump(self, *, tags: set[str] | None = None) -> dict:
    """Serialize with optional field-tag filtering for LLM consumption."""
```

## OODesignSchema absorbed into ClassDiagram

`OODesignSchema` (currently in `backend/codebase/schemas.py`) is removed.
The LLM now reads and writes `ClassDiagram` directly. The LLM receives a tagged
subset (`tags={"LLM", "TICKETING"}`) that includes only the fields it needs:

- `name`, `qualified_name`, `kind`, `description`, `visibility`
- `specialization`, `is_intercomponent` (ticketing)
- `type_name` (alias), `parameters`, `return_type` (aliases)
- `from_class`, `to_class`, `kind` (aliases on Association)
- `requirement_ids` (ticketing, on ClassNode)

Fields like `layer`, `file_path`, `line_number`, `is_static`, `is_final`,
`component_id` are excluded from LLM serialization.

### LLM-facing aliases

To preserve backward compatibility with existing prompt contracts:

| Canonical field | LLM serialized name | On type |
|---|---|---|
| `type_signature` | `type_name` | AttributeNode |
| `type_signature` | `return_type` | MethodNode |
| `subject` | `from_class` | Association |
| `predicate` | `kind` | Association |
| `object` | `to_class` | Association |
| `argsstring` | `parameters` | MethodNode |

Aliases are implemented via Pydantic `serialization_alias` on the canonical field.

## ClassDiagram ↔ Neo4j Round-Trip

### `to_neo4j()`

1. For each `ClassNode`, `InterfaceNode`, `EnumNode` in the diagram:
   - Create a `CompoundNode` with fields from the design model (name,
     qualified_name, kind, description, etc.)
   - Compute `layer = "design"` (or pass through if already set)
   - For each nested `AttributeNode`/`MethodNode`, create a `MemberNode`
     with `compound_refid` or compound qualified_name linkage
2. For each `Association`, create a `CodebaseEdge`
3. Return `(compounds, members, edges)` triples

### `from_neo4j()`

1. Accept `list[CompoundNode]`, `list[MemberNode]`, `list[CodebaseEdge]`
2. Group members by parent compound using `compound_refid` or qualified_name
3. For each compound, hydrate the appropriate ClassNode/InterfaceNode/EnumNode
   with nested members
4. Build association list from edges
5. Populate `_entity_index`

The existing `DesignDataRepository._hydrate_class()` logic moves into this
method.

## What Stays in Ticketing System

### `backend/codebase/schemas.py` (reduced)

```python
class RequirementTripleLinkSchema(BaseModel):
    requirement_type: Literal["hlr", "llr"]
    requirement_id: int
    triple_index: int = -1
    subject_qualified_name: str = ""
    predicate: str = ""
    object_qualified_name: str = ""

class DesignSchema(BaseModel):
    nodes: list[CompoundNode | MemberNode | NamespaceNode]  # discriminated by .kind or type
    triples: list[CodebaseEdge]
    requirement_links: list[RequirementTripleLinkSchema] = []
```

`nodes` uses a discriminated union — Pydantic inspects the `kind` field (or
falls back to the class name for untyped dict round-trips) to determine which
node model to validate against.

Removed: `AttributeSchema`, `MethodSchema`, `ClassSchema`, `EnumSchema`,
`InterfaceSchema`, `AssociationSchema`, `OODesignSchema`, `OntologyNodeSchema`,
`OntologyTripleSchema`, `TypeRef`.

### `backend/db/neo4j/models/nodes/compound.py` (thinned)

```python
class CompoundNode(BaseCompoundNode):
    specialization: str = ""
    is_intercomponent: bool = False
    implementation_status: Literal[
        "designed", "scaffolded", "tested", "implemented", "verified"
    ] = "designed"
    test_file: str = ""
```

### Temporary shims

`backend/design_data/models.py`:
```python
# TODO(2026-06): remove this shim — import from codegraph.designs instead
from codegraph.designs import (
    ClassDiagram, ClassNode, InterfaceNode, EnumNode,
    ModuleNode, Association, AttributeNode, MethodNode, EnumValueNode,
    DiagramNode,
)
__all__ = [...]  # same names
```

`backend/design_data/transforms.py`:
```python
# TODO(2026-06): OODesignSchema removed — ClassDiagram is the canonical type.
# class_diagram_from_oo_design() and oo_design_from_class_diagram() are no-ops
# if both sides are already ClassDiagram. Remove once callers updated.
```

## Consumer Impact

~25 files import from `backend.codebase.schemas` or construct schema instances.
All are updated to import from `codegraph.designs` or the temporary shim in
`backend.design_data.models`.

LLM-facing field names are unchanged due to serialization aliases. Consumer
changes are primarily import-path updates.

### Files affected

- `backend/design_data/transforms.py` — deprecated, OODesignSchema removed
- `backend/design_data/models.py` — temporary shim
- `backend/pipeline/orchestrator.py` — updated imports
- `backend/requirements/services/persistence.py`
- `backend/ticketing_agent/design/design_hlr.py`
- `backend/ticketing_agent/design/design_ontology.py`
- `backend/ticketing_agent/design/design_oo.py`
- `backend/ticketing_agent/design/design_oo_prompt.py`
- `backend/ticketing_agent/design/design_oo_tools.py`
- `backend/ticketing_agent/design/design_per_hlr.py`
- `backend/ticketing_agent/design/map_to_ontology.py`
- `backend/ticketing_agent/design_verify/combined_loop.py`
- `backend/ticketing_agent/mcp_server.py`
- `backend/ticketing_agent/tools/design_verify/commit.py`
- `backend/ticketing_agent/tools/design_verify/dispatcher.py`
- `backend/ticketing_agent/tools/design_verify/draft_design.py`
- `backend/ticketing_agent/tools/design_verify/validate_design.py`
- `backend/ticketing_agent/tools/helpers/commit_schema.py`
- `backend/ticketing_agent/tools/helpers/design_validation.py`
- `scripts/03_design_requirements.py`
- `tests/test_codebase_schemas.py`
- `tests/test_combined_handlers.py`
- `tests/test_container_mechanism.py`
- `tests/test_design_data_models.py`
- `tests/test_design_data_transforms.py`
- `tests/test_design_oo_retry.py`
- `tests/test_design_oo_tools.py`
- `tests/test_integration_combined_loop.py`
- `tests/test_map_to_ontology.py`
- `tests/test_mechanism_and_references.py`
- `tests/test_oo_design_schema.py`
- `tests/test_persistence.py`
- `tests/test_pipeline_schemas.py`
