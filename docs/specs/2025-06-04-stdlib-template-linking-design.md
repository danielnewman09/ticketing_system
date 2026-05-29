# Stdlib Template Linking Design

## Problem

Design methods reference standard library types in their signatures (e.g.,
`CalculationEngine::add(const std::string& operand1, const std::string& operand2)`)
but the ontology graph has no edges connecting those methods to the actual
cppreference nodes. `std::string` appears only as text in `argsstring` and
`type_signature` fields — it's marked with a ● builtin marker and treated as
opaque. Meanwhile, the cppreference data in Neo4j includes `std::basic_string`
(the real class behind `std::string`) with full member data, but no path
connects design methods to it.

This also affects any template type: `std::vector<std::string>` in a return
type is also completely opaque. The type extraction regex
`_TYPE_EXTRACT_RE = r"\b([A-Z]\w+)\b"` only matches uppercase-starting names,
so it can't capture `std::string` or parse template nesting at all.

## Solution Overview

Link design methods to their stdlib type dependencies through structured type
extraction and alias resolution, laying the groundwork for a full template
type model in the ontology graph. The core ideas:

1. **Edge-centric template model** — Template-specific concerns (type
   parameters, arguments) are expressed as edges (`TYPE_ARGUMENT`,
   `TEMPLATE_PARAM`), not as node fields. This avoids polluting every node
   with empty template metadata.

2. **Alias resolution** — `std::string` resolves to `std::basic_string` via a
   runtime alias registry (queried from Neo4j cppreference data + hardcoded
   fallback). Edges target the real node but carry a `display_name` property
   showing the developer-friendly alias.

3. **Structured type extraction** — Replace the regex-based type extraction
   with a proper parser that handles qualified names, template nesting, and
   const/ref/pointer qualifiers. Produces `TypeRef` structures that the
   mapping pipeline resolves recursively.

---

## Section 1: Node Model & Type Representation

### No new node fields for templates

Template concerns are modeled as edges, not node properties. The existing
`OntologyNode` schema gains only one change:

- **New kind:** `type_parameter` added to `NODE_KINDS` — represents an
  abstract type parameter slot like `T` or `Key` in a template declaration.

Template parameter metadata (position, name, constraint) lives on the
`TEMPLATE_PARAM` edge, not on the node. This keeps the 90%+ of non-template
nodes clean.

### `TypeRef` — Structured type reference

A new dataclass extracted from type signature strings:

```python
@dataclass
class TypeRef:
    name: str                    # "std::vector" or "Calculator"
    template_args: list[TypeRef] # [] for non-templates, or nested
    is_builtin: bool             # True for int, double, void, etc.
    original_text: str           # "std::vector<const std::string&>"
```

This replaces both `_TYPE_EXTRACT_RE` and `_add_depends_from_type`.

### Template instantiation representation

A template class like `std::vector` is **one node**. Different instantiations
are represented by edges that carry `type_arguments` metadata:

| Scenario | Edge | Properties |
|---|---|---|
| `parse` returns `std::vector<std::string>` | `parse` `RETURNS` → `std::vector` | `type_arguments: ["std::string"]` |
| `push_back` takes `std::string` | `push_back` `HAS_ARGUMENT` → `std::basic_string` | `display_name: "std::string"` |
| `std::vector` declares parameter `T` | `std::vector` `TEMPLATE_PARAM` → `type_parameter` node | `position: 0`, `name: "T"` |
| Usage binds `T` to `std::string` | `std::vector` `TYPE_ARGUMENT` → `std::basic_string` | `position: 0`, `display_name: "std::string"` |

No separate node for `std::vector<std::string>` — the instantiation info is on
the edges.

### Template parameter placeholder nodes

When the design agent creates a template class like `Result<T>`, it produces:
- A `class` node for `Result`
- A `type_parameter` node for `Result::T`
- A `TEMPLATE_PARAM(pos=0, name="T")` edge from `Result` to `Result::T`

For stdlib templates, `TEMPLATE_PARAM` edges are only created if the
cppreference data includes parameter info. They are not required — the
essential edges are `TYPE_ARGUMENT` for the specific instantiations used.

---

## Section 2: Alias Resolution

### The alias registry

A runtime lookup structure that maps common type names to their underlying
cppreference nodes:

| Alias | Resolves To | Source |
|---|---|---|
| `std::string` | `std::basic_string` | cppreference typedef query |
| `std::wstring` | `std::basic_string` | cppreference typedef query |
| `std::string_view` | `std::basic_string_view` | cppreference typedef query |
| `std::vector` | `std::vector` | direct (no alias needed) |

### Sources

1. **Primary:** Query Neo4j for `Member` nodes with `kind='type_alias'`
   from the cppreference data. Build the alias map from these.

2. **Fallback:** A hardcoded `STD_ALIAS_MAP` dict for common C++ typedefs
   that cppreference may not index cleanly. Covers `std::string`,
   `std::wstring`, `std::u16string`, `std::u32string`, etc. This ensures
   zero-gaps coverage for the types developers actually write.

3. **Template stripping:** For `std::vector<std::string>`, parse the outer
   template name (`std::vector`) and resolve inner type arguments recursively.
   Template names that already exist as-is in cppreference don't need aliasing.

### How aliases appear in the graph

Edges target the real node (`std::basic_string`) in Neo4j, but carry a
`display_name` property (`std::string`). The graph rendering layer uses
`display_name` for node labels, edge labels, and member type signatures.

The alias registry is a Python dict built at pipeline runtime — queried from
Neo4j first, then augmented with the hardcoded fallback. It is passed into
the mapping functions as a parameter. Not a database table. Migrating it to
a table is a future option when user-defined aliases are needed.

---

## Section 3: Mapping Pipeline Changes

### Current pipeline (replaced)

Two type-extraction paths:

1. **Design-internal:** `_resolve_ref()` and the main loop extract
   uppercase-starting names via `_TYPE_EXTRACT_RE = r"\b([A-Z]\w+)\b"`.
   Creates `has_argument`/`returns`/`composes` edges.

2. **External dependencies:** `_add_depends_from_type()` scans type strings
   for names in `dep_lookup`. Creates `depends_on` edges and stub nodes.

Both are replaced by the `TypeRef` parser and resolution pipeline.

### New pipeline

For each `TypeRef` extracted from a method/attribute type signature:

1. **Resolve alias** — Look up the name in the alias registry.
   `std::string` → `std::basic_string`.

2. **Check design-internal lookup** (`class_lookup`) — If found, create
   `has_argument` / `returns` edge to the design node.

3. **Check cppreference lookup** (`dep_lookup`) — If found, create
   `has_argument` / `returns` edge to the dependency node. Set
   `display_name` on the edge if the name was aliased.

4. **Recursive template args** — For each `TypeRef` in `template_args`,
   resolve it the same way. Create `TYPE_ARGUMENT` edges from the outer
   template node to each resolved inner type.

### New predicates

| Predicate | Description |
|---|---|
| `type_argument` | A template node accepts a type argument at a given position. Edge property `position` (int). Optional `display_name` for aliased types. |
| `template_param` | A template declares a type parameter slot. Edge property `position` (int), `name` (string). |

Both are added to `Predicate.DEFAULT_PREDICATES` in `ontology.py`.

### When TEMPLATE_PARAM edges are created

Only for **design-authored templates** — when the design agent produces a
template class like `Result<T>`. For stdlib dependency templates, `TEMPLATE_PARAM`
edges are optional — only created if the cppreference data includes parameter
info. The essential edges are `TYPE_ARGUMENT` for specific instantiations.

---

## Section 4: Graph Rendering

### Template node rendering

A template class node (e.g. `std::vector`) gets a distinct UML treatment:

- Stereotype: `«class template»` (instead of `«class»`)
- Type parameter slots shown in a header compartment above members
- Inner border color: purple (`#9b59b6`) from `KIND_BORDER_COLORS` with a
  `"class_template"` entry

Example label for `std::vector`:

```
«class template»
std::vector
─────────────────
T₁ : T
─────────────────
+ push_back()
+ size()
+ operator[]()
```

### Alias display

When an edge targets a node with an alias (`std::basic_string` displayed as
`std::string`), the `display_name` property on the edge controls what the
graph shows:

- Node label: uses `display_name` if present, otherwise `name`
- Member type signatures: `std::string` shown with ◆ (linked) marker instead
  of ● (builtin)
- Edge labels: show the alias name

### TYPE_ARGUMENT edges

- Color: purple/indigo (distinct from `DEPENDS_ON` gray, `HAS_ARGUMENT` green,
  `RETURNS` red)
- Label: `TYPE_ARGUMENT(0)` showing parameter position on hover
- Line style: solid

### `type_parameter` placeholder nodes

- Light dashed border
- Italic label showing the parameter name (`T`, `Key`)
- No member compartment
- Connected to parent template via `TEMPLATE_PARAM` edges (dashed, showing
  `pos=0`)

### Type signature markers

Currently: `+ parse(const std::string& expression): ● std::vector<std::string>`

After: `+ parse(const std::string& expression): ◆ std::vector<std::string>`

`std::string` inside the template gets the ◆ linked marker (resolves to a real
node) instead of the ● builtin marker. The `std::vector` also gets ◆. Both
are clickable to navigate to their dependency node.

### Stdlib node header indicator

Dependency nodes from cppreference get an additional header line showing the
header they're defined in, sourced from the `DEFINED_IN` edges already in
Neo4j (`std::basic_string` → `<string>`).

---

## Section 5: Implementation Scope

### In scope

1. Type signature parser (`TypeRef` extraction from strings)
2. Alias registry (Neo4j cppreference query + hardcoded fallback)
3. New predicates: `type_argument`, `template_param`
4. New node kind: `type_parameter`
5. Mapping pipeline changes in `map_to_ontology.py`
6. Graph query updates in `backend/db/neo4j/queries/graph.py`
7. Cytoscape rendering updates in `backend/graph/transforms.py`
8. Schema changes in `backend/codebase/schemas.py` and
   `backend/db/models/ontology.py`
9. New module: `backend/ticketing_agent/design/container_lookup.py`
   (alias registry builder)

### File change list

| File | What Changes |
|---|---|
| `backend/codebase/schemas.py` | Add `TypeRef` model, `template_params` to `OntologyNodeSchema`, `position`/`name`/`display_name` to `OntologyTripleSchema` |
| `backend/db/models/ontology.py` | Add `type_parameter` to `NODE_KINDS`, `type_argument` and `template_param` to `Predicate.DEFAULT_PREDICATES` |
| `backend/ticketing_agent/design/map_to_ontology.py` | Replace `_TYPE_EXTRACT_RE` and `_add_depends_from_type` with `TypeRef` parser + registry. Create `TYPE_ARGUMENT`/`TEMPLATE_PARAM` edges. Resolve aliases. |
| `backend/ticketing_agent/design/container_lookup.py` | New module: alias registry builder (Neo4j typedef query + hardcoded fallback) |
| `backend/db/neo4j/queries/graph.py` | `fetch_design_graph` includes `TYPE_ARGUMENT` edges. Return `display_name` property. |
| `backend/graph/transforms.py` | Template node rendering, alias display in member lines, `TYPE_ARGUMENT` edge styling, `type_parameter` node rendering, header indicator for stdlib nodes |
| `backend/graph/builders.py` | Pass through `template_params`, `display_name`, alias properties from Neo4j to Cytoscape |
| `frontend/data/ontology.py` | Handle `TYPE_ARGUMENT`/`TEMPLATE_PARAM` edges in graph data, return alias display names |
| `backend/db/models/associations.py` | No changes expected — predicates live in Neo4j |

### Explicitly deferred

- **User-defined templates in the LLM prompt** — The design agent prompt
  doesn't yet instruct it to produce `template_params` or `TEMPLATE_PARAM`
  edges. Follow-up when designing template classes in the agent.
- **C++20 concepts as nodes** — Will add `concept` kind and `CONSTRAINED_BY`
  predicate when needed. Not in scope now.
- **Template specialization resolution in the detail panel** — Clicking a
  `TYPE_ARGUMENT` edge could show "T₁ = std::string → std::basic_string".
  Nice-to-have.
- **Scaffold code generation from templates** — Using template info to
  generate `.h`/`.cpp` files with proper `#include` directives. Future work.

### Not in scope

- Removing `_BUILTIN_TYPES` or builtin marker logic — `std::string` becomes a
  ◆ linked marker instead of ● builtin, but actual builtins (`int`, `double`,
  `void`) stay as-is.
- Changes to the dependency research or assessment agents — they don't produce
  type signatures.