# Design Data Module

**Date:** 2025-05-29
**Status:** Approved

## Problem

OO design data flows through the system in at least 5 different ad-hoc representations:

1. `_extract_existing_classes(oo)` — reconstructs class summaries from `OODesignSchema`
2. `build_verification_context(ns)` — separate Cypher query, builds dicts
3. `_build_class_lookup(oo)` — flat name→qualified_name dict
4. `_extract_intercomponent_context(oo)` — filters public API classes
5. Pipeline orchestrator's `all_oo_classes` — manual field extraction

Each reconstructs the same design data with a slightly different dict shape and different field subsets. There is no unified way to say "give me the class diagram for component X" and get typed, structured objects back. The read path from Neo4j to agents is raw Cypher → ad-hoc dicts → string formatting.

Meanwhile, `OODesignSchema` serves only as the LLM write shape. It doesn't carry qualified names, layer information, code-level detail, or implementation status — all of which exist in Neo4j but are inaccessible to agents without custom Cypher.

## Solution

Create a `backend/design_data/` module with query-focused read models, a repository, and transforms that make Neo4j the single source of truth with a clean typed API.

### Approach

**Keep `OODesignSchema` as the write shape** (what the LLM produces). Add a parallel set of **read models** (`ClassNode`, `InterfaceNode`, `EnumNode`, `Association`, `ClassDiagram`) that represent the ground truth from Neo4j. A `DesignDataRepository` queries Neo4j and returns these typed models. Transform functions bridge between the two shapes.

The read models are unified across layers — a `ClassNode` from the design layer and one from the as-built layer are the same type, distinguished by the `layer` field, not by separate type names.

## Module Structure

```
backend/design_data/
  __init__.py          # Public API: DesignDataRepository, model classes, transforms
  models.py            # Typed read models (ClassNode, InterfaceNode, etc.)
  repository.py        # DesignDataRepository — queries Neo4j, returns typed models
  transforms.py        # OODesignSchema <-> ClassDiagram, replaces ad-hoc conversions
```

## Read Models

### Common Base

Every diagram node shares a base set of fields taken from what Neo4j `:Design` and `:Compound` nodes actually store:

```python
class DiagramNode(BaseModel):
    name: str
    qualified_name: str
    kind: str                          # class, interface, enum, module, attribute, method, enum_value, ...
    layer: Literal["design", "as-built", "dependency"]

    description: str = ""
    visibility: str = ""                # public, private, protected
    specialization: str = ""            # struct, template_class, enum_class, etc.
    component_id: int | None = None
    is_intercomponent: bool = False

    type_signature: str = ""
    argsstring: str = ""
    definition: str = ""
    source_type: str = ""              # namespace, compound, member, dependency
    source: str = ""                    # dependency library name (dependency layer only)

    file_path: str = ""
    line_number: int | None = None

    is_static: bool = False
    is_const: bool = False
    is_virtual: bool = False
    is_abstract: bool = False
    is_final: bool = False

    implementation_status: str = "designed"  # designed, scaffolded, tested, implemented, verified
    source_file: str = ""
    test_file: str = ""
```

### Top-Level Entities

Members (attributes, methods, enum values) are inline on their parent entity. Cross-entity relationships are separate.

```python
class ClassNode(DiagramNode):
    kind: Literal["class"] = "class"
    module: str = ""
    inherits_from: list[str] = []      # qualified names of parent classes
    realizes: list[str] = []           # qualified names of implemented interfaces
    attributes: list[AttributeNode] = []
    methods: list[MethodNode] = []

class InterfaceNode(DiagramNode):
    kind: Literal["interface"] = "interface"
    module: str = ""
    methods: list[MethodNode] = []

class EnumNode(DiagramNode):
    kind: Literal["enum"] = "enum"
    module: str = ""
    values: list[EnumValueNode] = []

class ModuleNode(DiagramNode):
    kind: Literal["module"] = "module"
```

### Members

Members are owned by their parent entity and never appear standalone:

```python
class AttributeNode(DiagramNode):
    kind: Literal["attribute"] = "attribute"
    owner: str = ""                    # qualified name of owning class/interface

class MethodNode(DiagramNode):
    kind: Literal["method"] = "method"
    owner: str = ""                    # qualified name of owning class/interface

class EnumValueNode(DiagramNode):
    kind: Literal["enum_value"] = "enum_value"
    owner: str = ""                    # qualified name of owning enum
```

### Associations (Cross-Entity Relationships)

```python
class Association(BaseModel):
    subject: str                        # qualified name
    predicate: str                      # aggregates, references, depends_on, invokes, etc.
    object: str                         # qualified name
    mechanism: str = ""                 # "std::vector", "std::unique_ptr", etc.
    description: str = ""
```

### Container

```python
class ClassDiagram(BaseModel):
    module_names: list[str] = []
    classes: list[ClassNode] = []
    interfaces: list[InterfaceNode] = []
    enums: list[EnumNode] = []
    associations: list[Association] = []

    def get_entity(self, qualified_name: str) -> ClassNode | InterfaceNode | EnumNode | ModuleNode | None: ...
    def associations_for(self, qualified_name: str) -> list[Association]: ...
    def associations_involving(self, qualified_name: str) -> list[Association]: ...
    def classes_in_module(self, module: str) -> list[ClassNode]: ...
```

`ClassDiagram` mirrors the structure of `OODesignSchema` (classes, interfaces, enums, associations) with richer fields, qualified names, and the `layer` discriminator.

## Repository API

`DesignDataRepository` is the single entry point for reading class diagram data from Neo4j:

```python
class DesignDataRepository:
    def __init__(self, session: Neo4jSession): ...

    # --- Full diagrams ---

    def get_class_diagram(
        self,
        component_id: int | None = None,
        layer: str | None = None,          # "design", "as-built", "dependency", or None for all
    ) -> ClassDiagram: ...

    def get_hlr_subgraph(
        self,
        hlr_id: int,
        component_id: int | None = None,
    ) -> ClassDiagram: ...

    # --- Single entity lookups ---

    def get_class(self, qualified_name: str) -> ClassNode | None: ...
    def get_interface(self, qualified_name: str) -> InterfaceNode | None: ...
    def get_enum(self, qualified_name: str) -> EnumNode | None: ...

    # --- Prompt-building helpers ---

    def get_classes_for_component(self, component_id: int) -> list[ClassNode]: ...
    def get_public_api(self, component_id: int) -> list[ClassNode | InterfaceNode]: ...
```

Single-entity lookups return fully hydrated objects — members and relationship references are included in one query, not fetched separately.

## Transforms

Two conversion functions bridge the LLM write shape and the rich read shape:

```python
# backend/design_data/transforms.py

def class_diagram_from_oo_design(oo: OODesignSchema, component_id: int | None = None) -> ClassDiagram:
    """Convert LLM output to read shape. Used when the agent produces a design
    and we need it in the rich model form (e.g., passing to the next HLR's context,
    skeleton generation, or verification). Does NOT replace map_to_ontology."""

def oo_design_from_class_diagram(diagram: ClassDiagram) -> OODesignSchema:
    """Reconstruct the LLM-friendly shape from stored design data.
    Replaces _extract_existing_classes(), _extract_intercomponent_context(),
    and all ad-hoc dict construction for agent prompts."""
```

### Shape comparison

| Aspect | OODesignSchema | ClassDiagram |
|--------|---------------|--------------|
| Members | Inline on classes (`cls.attributes`, `cls.methods`) | Inline on entities (same) |
| Associations | Flat list at top level | Flat list at top level (same) |
| Requirement IDs | Tagged strings (`"hlr:3"`) | Not present (TRACES_TO edges in Neo4j) |
| Qualified names | Built from `module::name` at persist time | Already present, from Neo4j |
| Layer | Always "design" | Can be design / as-built / dependency |
| Code-level detail | Sparse (LLM doesn't fill it) | Rich (from as-built / dependency nodes) |
| Inheritance | `inherits_from: list[str]` (bare names) | `inherits_from: list[str]` (qualified names, resolved) |

## Integration Points

### Phase 1 — Core module + Repository

| File | Change |
|------|--------|
| `backend/requirements/services/persistence.py` | `build_verification_context()` replaced by `repo.get_class_diagram()` + iteration |

### Phase 2 — Agent pipeline consumers

| File | Current | Replacement |
|------|---------|-------------|
| `backend/ticketing_agent/design/design_per_hlr.py` | `_extract_existing_classes(oo)` | `class_diagram_from_oo_design(oo).classes` |
| `backend/ticketing_agent/design/design_per_hlr.py` | `_extract_intercomponent_context(oo, ...)` | `diagram.get_public_api(component_id=...)` |
| `backend/ticketing_agent/design/design_per_hlr.py` | `_build_class_lookup(oo)` | `diagram` index access |
| `backend/ticketing_agent/tools/helpers/draft_state.py` | `build_draft_lookup(design)` | `class_diagram_from_oo_design(design)` then `diagram.get_entity(qn)` |
| `backend/pipeline/orchestrator.py` | `_get_verification_dicts()` + manual `all_oo_classes` | `repo.get_class_diagram()` + typed access |
| `backend/ticketing_agent/generate_skeleton.py` | Takes `oo_design: dict` | Accepts `ClassDiagram` or converts internally |

### Phase 3 — Cleanup (lower priority)

| File | Change |
|------|--------|
| `backend/ticketing_agent/design/design_oo_prompt.py` | `build_existing_classes_section()` / `build_as_built_section()` can consume typed models instead of raw dicts |
| Graph UI path | No change now. Continues on raw-dict → `format_cytoscape_graph()` path |

### Explicitly unchanged

- `OODesignSchema`, `DesignSchema`, `OntologyNodeSchema` in `backend/codebase/schemas.py`
- `map_to_ontology()` in `backend/codebase/map_to_ontology.py`
- `persist_design()` in `backend/requirements/services/persistence.py`
- `DesignRepository` in `backend/db/neo4j/repositories/design.py`
- Graph rendering pipeline (`format_cytoscape_graph`, `collapse_members`, `assign_namespace_parents`)
- `CombinedDispatcher` and tool loop pipeline
- Neo4j node/edge structure

## Decision Log

- **Unified models across layers:** As-designed and as-built entities use the same types (`ClassNode`, etc.), distinguished by the `layer` field rather than separate `DesignClass` / `BuiltClass` types.
- **All code-level fields on base model:** Empty/defaulted for design-layer data, populated for as-built/dependency. This avoids needing a separate `CodeDetail` embedded model.
- **Members inline, associations separate:** Composition (class owns its attributes/methods) is inline on the parent. Cross-entity relationships (aggregation, dependency, inheritance) are a flat list on `ClassDiagram` with convenience accessor methods.
- **Write path unchanged:** `map_to_ontology()` → `persist_design()` → Neo4j continues as-is. The new module adds the read path and shape conversions, not a parallel write path.
- **Graph UI unchanged for now:** The Cytoscape rendering path stays on its raw-dict pipeline until a future refactor.