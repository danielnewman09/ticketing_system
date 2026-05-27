# Enum Composition Edges Design

## Problem

When a class has a member variable typed by a design-internal enum, no edge
connects the two entities in the ontology graph. For example,
`CalculationResult` has attribute `error_signal: ErrorType`, but
`ErrorType` appears disconnected — no visible relationship in the dashboard.

Root causes:
1. `class_lookup` in `map_to_ontology.py` only includes classes and
   interfaces — enums are excluded, so type references to enums are silently
   skipped during edge creation.
2. The `_add_depends_from_type` fallback would emit `references`, not
   `composes`, even if it could resolve the enum — wrong for a member
   variable.
3. `RETURNS` isn't a recognized predicate, so method return types have no
   proper entity-level edge.
4. The graph collapse logic treats all `COMPOSES` edges as containment and
   would swallow an enum node even if the edge existed.

## Design

### Section 1: Predicates — add `returns` and finalize `composes`

**`backend/db/neo4j/repositories/constants.py`:**
- Add `"returns": "RETURNS"` to `PREDICATE_TO_REL_TYPE`
- Add `("returns", "A method returns a value of the given entity type (method → type)")` to `DEFAULT_PREDICATES`
- Remove `"has_type"` from `PREDICATE_TO_REL_TYPE` and `DEFAULT_PREDICATES` — replaced by `composes` (for attributes) and `returns` (for method return types)

**`backend/db/models/ontology.py`:**
- Add `("returns", "A method returns a value of the given entity type")` to `Predicate.DEFAULT_PREDICATES`
- Remove `("has_type", ...)` from `Predicate.DEFAULT_PREDICATES`

**`backend/codebase/schemas.py`:**
- Add `"composes"` and `"returns"` to the `AssociationSchema.kind` Literal type
- Remove `"invokes"` is already there; keep all existing values and add the two new ones

### Section 2: Deterministic mapping — `map_to_ontology.py`

**Add enums to `class_lookup`:**
```python
for enum in oo.enums:
    class_lookup[enum.name] = _qualify(enum.module, enum.name)
```

**Attribute processing — class-level `composes` edge:**
When an attribute's `type_name` resolves to a design-internal entity, emit a
class-level `composes` triple (class → entity type). A member variable is
always composition:
```python
if attr.type_name:
    for match in _TYPE_EXTRACT_RE.finditer(attr.type_name):
        type_name = match.group(1)
        if type_name in class_lookup:
            target_qname = class_lookup[type_name]
            _add_triple(cls_qname, "composes", target_qname)
```

**Method processing — `returns` edges for return types:**
Replace the current `has_type` edge for method return types with `returns`:
```python
if method.return_type:
    for match in _TYPE_EXTRACT_RE.finditer(method.return_type):
        type_name = match.group(1)
        if type_name in class_lookup:
            target_qname = class_lookup[type_name]
            _add_triple(method_qname, "returns", target_qname)
```

**Method processing — `has_argument` edges for parameters (unchanged):**
Already emits `has_argument` triples for method parameters that resolve to
design-internal types. No changes needed.

**Remove `has_type` edge creation** from both attribute and method
processing — replaced by `composes` and `returns` respectively.

**Update `_add_depends_from_type`:**
Remove the design-internal `references` fallback. The function should only
handle external dependencies (`depends_on` edges to dependency stubs). The
new `composes`, `returns`, and `has_argument` edges from the main processing
loops cover all design-internal type references.

### Section 3: Agent prompts

**`design_oo_prompt.py` — Associations section:**
Change the kind list from:
> associates, aggregates, depends_on, references, invokes

To:
> associates, aggregates, composes, depends_on, references, returns, invokes

Add guidance:
- **composes** — A class has a member variable of the given entity type (value
  composition). Use when a class holds an instance of another design entity
  (enum, class, interface) as a direct member — not via pointer or container.
  The attribute still belongs in the class's attributes array; the
  association records the entity-to-entity relationship.
  Example: `{from_class: "CalculationResult", to_class: "ErrorType", kind: "composes"}`
- **returns** — A method returns a value of the given entity type. Records
  the entity-to-entity relationship for return types.
  Example: `{from_class: "CalculationEngine", to_class: "CalculationResult", kind: "returns"}`

**`design_ontology_prompt.py` — Node kind and guidelines:**
- Under `enum` guidance, add: "When a class holds a member variable of an
  enum type, the class should have a `composes` triple to the enum."
- In Guidelines, add: "When a method returns a design-internal type (class,
  enum, interface), add a `returns` triple (method → type). When a method
  accepts a design-internal type as a parameter, add a `has_argument` triple
  (method → type)."

### Section 4: Graph transforms — dual visibility for composed enums

**`backend/graph/transforms.py`:**

Add `enum` to `_ENTITY_KINDS`:
```python
_ENTITY_KINDS = {"class", "interface", "enum", "struct"}
```

Add entity-composition preservation to `_collect_collapsible`. When a design
entity (class, interface, enum, struct) is composed by another non-module
entity, keep it visible as a separate node — the composition relationship is
meaningful at the entity level and should be shown in the graph:
```python
entity_composed_by_owner: set[str] = set()
for e in edges:
    d = e["data"]
    if d["label"] not in _CONTAINMENT_RELS:
        continue
    target = node_by_id.get(d["target"])
    source = node_by_id.get(d["source"])
    if target is None or source is None:
        continue
    if source["data"].get("kind") == "module":
        continue  # module containment → parent, not composition
    if target["data"].get("kind") in _ENTITY_KINDS:
        entity_composed_by_owner.add(d["target"])

remove_node_ids -= entity_composed_by_owner
```

Result: `ErrorType` appears both as a typed attribute line inside
`CalculationResult`'s UML compartment (`+ error_signal: ErrorType`) AND as a
separate enum node in the graph with the `COMPOSES` edge visible.

## Deduplication note

When both the LLM agent and the deterministic mapper emit a `composes`
edge between the same class and entity, the Neo4j `MERGE` in
`DesignRepository.merge_triple` deduplicates by (source, target, type),
so no duplicate edge is created. No special handling needed.

## Files changed

- `backend/db/neo4j/repositories/constants.py` — add `returns`, remove `has_type`
- `backend/db/models/ontology.py` — add `returns`, remove `has_type` from defaults
- `backend/codebase/schemas.py` — add `composes`, `returns` to AssociationSchema.kind
- `backend/ticketing_agent/design/map_to_ontology.py` — add enums to class_lookup; emit class-level `composes` for attribute types; emit `returns` for method return types; remove `has_type`; update `_add_depends_from_type`
- `backend/ticketing_agent/design/design_oo_prompt.py` — add `composes`/`returns` association guidance
- `backend/ticketing_agent/design/design_ontology_prompt.py` — add enum composition and returns/has_argument guidance
- `backend/graph/transforms.py` — add `enum` to `_ENTITY_KINDS`; add entity-composition preservation in `_collect_collapsible`