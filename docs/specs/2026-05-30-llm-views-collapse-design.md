# Collapse Codebase Schemas into Codegraph LLM Views

2026-05-30

## Problem

Three separate places define representations of the same codebase entities,
creating duplication and divergence:

1. **`backend/codebase/schemas.py`** — Pydantic schemas for the design pipeline
   (Stage 1 OO shapes for LLM interaction, Stage 2 ontology shapes for Neo4j).
2. **`backend/db/neo4j/models/nodes/compound.py`** — Neo4j node model extending
   `codegraph.nodes.CompoundNode` with ticketing-specific fields.
3. **`backend/design_data/models.py`** — Rich Pydantic read models
   (`DiagramNode`, `ClassNode`, `ClassDiagram`, etc.) for the frontend and agent
   prompts. *(Deferred — not in scope for this design.)*

The goal: two layers maximum. `codegraph` as the universal base, and one thin
ticketing-system extension for fields that are genuinely novel to this repo.

## Scope

### In scope

- Add `FieldTags` annotation mechanism to codegraph node/edge models, marking
  field relevance for LLM, Neo4j, and read use cases.
- Create `codegraph/views/` module with LLM view shapes (`ClassView`,
  `AttributeView`, `MethodView`, `InterfaceView`, `EnumView`, `AssociationView`,
  `OODesignView`) — these are the round-trippable schemas the LLM reads and
  writes.
- Add `to_llm_view()`, `from_llm_view()`, and `apply_to()` methods on codegraph
  nodes/edges for projection and merging.
- Move `TypeRef` dataclass from `backend/codebase/schemas.py` into codegraph as
  `codegraph/type_parser.py`.
- Thin `backend/codebase/schemas.py` to only ticketing-specific schemas
  (`RequirementTripleLinkSchema`, `DesignSchema`).
- Thin `backend/db/neo4j/models/nodes/compound.py` to only
  `specialization`, `is_intercomponent`, `implementation_status`, `test_file`.
- Update all ~25 consumer files to import from new locations.

### Deferred

- `backend/design_data/models.py` (`DiagramNode`, `ClassDiagram`, read models) —
  stays as-is until a follow-up design.
- `backend/design_data/transforms.py` — updated import paths only; logic
  unchanged.

### Out of scope

- Changing LLM prompt contracts — field names visible to the LLM stay the same
  (aliases preserve backward compatibility).

## Architecture

```
codegraph/src/codegraph/
├── views/
│   ├── __init__.py              # OODesignView, FieldTags, re-exports
│   ├── tags.py                  # FieldTags class + LLM/NEO4J/READ tag constants
│   ├── compound.py              # ClassView, InterfaceView, EnumView
│   ├── member.py                # AttributeView, MethodView, EnumValueView
│   ├── namespace.py             # ModuleView (if LLM prompts need it)
│   └── edges.py                 # AssociationView
├── type_parser.py               # MOVED: TypeRef + parsing utilities
├── nodes/
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
    ├── models.py                # deferred
    ├── repository.py            # deferred
    └── transforms.py            # updated imports only
```

## Field Tagging

```python
# codegraph/views/tags.py

class FieldTags:
    LLM: str = "llm"
    NEO4J: str = "neo4j"
    READ: str = "read"
    TICKETING: str = "ticketing"

    def __init__(self, *tags: str) -> None: ...
```

Usage on node fields:

```python
from codegraph.views.tags import FieldTags

class CompoundNode(BaseModel):
    qualified_name: Annotated[str, FieldTags(LLM, NEO4J, READ)]
    kind: Annotated[str, FieldTags(LLM, NEO4J, READ)]
    component_id: Annotated[int | None, FieldTags(NEO4J)]
    brief_description: Annotated[str, FieldTags(LLM, NEO4J, READ)]
    is_final: Annotated[bool, FieldTags(NEO4J, READ)]
    # ...
```

`FieldTags` is stored in `typing.Annotated` metadata and is inspectable at
runtime via `typing.get_type_hints(include_extras=True)`. The `.to_llm_view()`
method uses this metadata to decide which fields to project.

## LLM View Shapes

### File: `views/compound.py`

#### `ClassView` (replaces `ClassSchema`)

| Field | Type | LLM name | Notes |
|---|---|---|---|
| `qualified_name` | `str` | `qualified_name` | **New** — identity anchor |
| `name` | `str` | `name` | |
| `kind` | `Literal["class","struct","template_class"]` | `kind` | **New** — was implicit |
| `specialization` | `str` | `specialization` | |
| `description` | `str` | `description` | Maps to `brief_description` |
| `visibility` | `str` | `visibility` | |
| `is_intercomponent` | `bool` | `is_intercomponent` | |
| `attributes` | `list[AttributeView]` | `attributes` | |
| `methods` | `list[MethodView]` | `methods` | |
| `inherits_from` | `list[str]` | `inherits_from` | |
| `realizes_interfaces` | `list[str]` | `realizes_interfaces` | |
| `requirement_ids` | `list[str]` | `requirement_ids` | |

#### `InterfaceView` (replaces `InterfaceSchema`)

| Field | Type | LLM name |
|---|---|---|
| `qualified_name` | `str` | `qualified_name` |
| `name` | `str` | `name` |
| `kind` | `Literal["interface","abstract_class"]` | `kind` |
| `specialization` | `str` | `specialization` |
| `description` | `str` | `description` |
| `is_intercomponent` | `bool` | `is_intercomponent` |
| `methods` | `list[MethodView]` | `methods` |

#### `EnumView` (replaces `EnumSchema`)

| Field | Type | LLM name |
|---|---|---|
| `qualified_name` | `str` | `qualified_name` |
| `name` | `str` | `name` |
| `kind` | `Literal["enum","enum_class"]` | `kind` |
| `description` | `str` | `description` |
| `values` | `list[str]` | `values` |

### File: `views/member.py`

#### `AttributeView` (replaces `AttributeSchema`)

| Field | Type | LLM name | Notes |
|---|---|---|---|
| `qualified_name` | `str` | `qualified_name` | **New** |
| `name` | `str` | `name` | |
| `type_name` | `str` | `type_name` | **Alias** for `type_signature` |
| `visibility` | `str` | `visibility` | |
| `description` | `str` | `description` | |

`type_name` is a Pydantic field alias that serializes as `type_name` to the LLM
but maps to `type_signature` internally.

#### `MethodView` (replaces `MethodSchema`)

| Field | Type | LLM name | Notes |
|---|---|---|---|
| `qualified_name` | `str` | `qualified_name` | **New** |
| `name` | `str` | `name` | |
| `visibility` | `str` | `visibility` | |
| `description` | `str` | `description` | |
| `parameters` | `list[str]` | `parameters` | |
| `return_type` | `str` | `return_type` | |

#### `EnumValueView`

| Field | Type | LLM name | Notes |
|---|---|---|---|
| `qualified_name` | `str` | `qualified_name` | |
| `name` | `str` | `name` | |
| `description` | `str` | `description` | |

### File: `views/edges.py`

#### `AssociationView` (replaces `AssociationSchema`)

| Field | Type | LLM name | Notes |
|---|---|---|---|
| `from_class` | `str` | `from_class` | **Alias** for `subject` |
| `to_class` | `str` | `to_class` | **Alias** for `object` |
| `kind` | `str` | `kind` | **Alias** for `predicate` |
| `description` | `str` | `description` | |
| `mechanism` | `str` | `mechanism` | |

Aliases preserve the existing LLM-facing vocabulary while internally using
codegraph's canonical field names.

### File: `views/__init__.py`

#### `OODesignView` (replaces `OODesignSchema`)

| Field | Type |
|---|---|
| `modules` | `list[str]` |
| `classes` | `list[ClassView]` |
| `interfaces` | `list[InterfaceView]` |
| `enums` | `list[EnumView]` |
| `associations` | `list[AssociationView]` |

## Projection API

### On nodes (e.g., `CompoundNode`)

```python
class CompoundNode(BaseModel):
    def to_llm_view(self) -> ClassView:
        """Project fields tagged LLM into ClassView.
        description ← brief_description.
        Ticketing-tagged fields excluded from view but preserved on node.
        """

    @classmethod
    def from_llm_view(
        cls, view: ClassView, *, component_id: int | None = None
    ) -> CompoundNode:
        """Create a new CompoundNode from LLM output.
        Unspecified fields get sensible defaults.
        component_id injected by the caller (not from LLM).
        """
```

### On views (e.g., `ClassView`)

```python
class ClassView(BaseModel):
    def apply_to(self, node: CompoundNode) -> CompoundNode:
        """Merge this view into an existing node.
        Only overwrites fields that were explicitly set (non-default).
        Preserves layer, component_id, detailed_description, flags, etc.

        qualified_name is NEVER overwritten — it is the identity anchor.
        If the LLM intends to rename an entity it must create a new one.
        """
```

**Limitation**: "non-default" detection cannot distinguish between "the LLM
explicitly set this field to its default value" and "the LLM didn't touch this
field at all." For string fields (description, etc.) this is acceptable since
an empty description is semantically equivalent to untouched. For boolean fields
(is_intercomponent), a sentinel approach may be needed if the LLM needs to
clear a previously `true` value.

**Member views**: `apply_to` on `AttributeView`/`MethodView` expects the
`qualified_name` to include the parent prefix (e.g., `"calc::Calculator::add"`).
The caller is responsible for constructing this before calling `apply_to`.

### On edges (`CodebaseEdge`)

Same pattern: `to_llm_view() -> AssociationView`, `from_llm_view()`, `apply_to()`.

## Description Mapping

- `to_llm_view()`: `description` = `node.brief_description`
- `apply_to()`: writes back to `brief_description` only
- `detailed_description` is codegraph-only, never exposed to the LLM

## Round-Trip Semantics

1. **Extract**: `node.to_llm_view()` → `ClassView(qn="calc::Calculator", name="Calculator", description="...")`
2. **LLM modifies**: returns `ClassView(qn="calc::Calculator", name="Calculator", description="adds two numbers")`
3. **Merge**: `view.apply_to(node)` — only `brief_description` changes; `kind`, `layer`, `component_id`, `is_final`, etc. all preserved
4. **Create new**: `CompoundNode.from_llm_view(view, component_id=5)` — creates a fresh node with sensible defaults

## What Stays in Ticketing System

### `backend/codebase/schemas.py` (reduced)

```python
"""Ticketing-system schemas — requirement linkage and design aggregation."""

from pydantic import BaseModel
from typing import Literal

class RequirementTripleLinkSchema(BaseModel):
    requirement_type: Literal["hlr", "llr"]
    requirement_id: int
    triple_index: int = -1
    subject_qualified_name: str = ""
    predicate: str = ""
    object_qualified_name: str = ""

class DesignSchema(BaseModel):
    nodes: list[CompoundNode | MemberNode | NamespaceNode]
    triples: list[CodebaseEdge]
    requirement_links: list[RequirementTripleLinkSchema] = []
```

`DesignSchema` field types switch from the removed schemas to codegraph's
`CompoundNode`, `MemberNode`, `NamespaceNode`, and `CodebaseEdge`.

### `backend/db/neo4j/models/nodes/compound.py` (thinned)

```python
class CompoundNode(BaseCompoundNode):
    """Ticketing extensions on top of codegraph's CompoundNode."""

    specialization: str = ""
    is_intercomponent: bool = False
    implementation_status: Literal[
        "designed", "scaffolded", "tested", "implemented", "verified"
    ] = "designed"
    test_file: str = ""
```

All other fields inherited from `codegraph.nodes.CompoundNode`. These four
fields are ticketing-specific and have no place in the shared codegraph library.

## Consumer Impact

~25 files import from `backend.codebase.schemas` or construct schema instances.
All are updated to import from `codegraph.views` instead. LLM-facing field names
are unchanged due to aliases; only import paths change.

### Files affected (from grep)

- `backend/design_data/transforms.py` — updated imports
- `backend/pipeline/orchestrator.py`
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
