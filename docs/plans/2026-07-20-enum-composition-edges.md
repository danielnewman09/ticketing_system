# Enum Composition Edges Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect enums (and other design-internal entity types) to the classes that use them as member variables via `COMPOSES` edges, add `RETURNS` and `HAS_ARGUMENT` edges for method type references, and ensure the graph transforms keep composed enums visible in the dashboard.

**Architecture:** Fix three layers — predicates/constants (add `returns`, remove `has_type`), deterministic ontology mapping (add enums to `class_lookup`, emit class-level `composes` for attributes, emit `returns` for method return types), and graph transforms (keep entity-to-entity composition targets visible as separate nodes alongside their collapsed representation).

**Tech Stack:** Python 3.12, Pydantic, Neo4j, Cytoscape.js graph transforms

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/db/neo4j/repositories/constants.py` | Modify | Add `returns`, remove `has_type` from predicates |
| `backend/db/models/ontology.py` | Modify | Add `returns`, remove `has_type` from DEFAULT_PREDICATES |
| `backend/codebase/schemas.py` | Modify | Add `composes`, `returns` to AssociationSchema.kind |
| `backend/ticketing_agent/design/map_to_ontology.py` | Modify | Add enums to class_lookup; emit class-level `composes` for attr types; emit `returns` for method return types; remove `has_type`; simplify `_add_depends_from_type` |
| `backend/ticketing_agent/design/design_oo_prompt.py` | Modify | Add `composes`/`returns` association guidance |
| `backend/ticketing_agent/design/design_ontology_prompt.py` | Modify | Add enum composition and returns/has_argument guidance |
| `backend/graph/transforms.py` | Modify | Add `enum` to `_ENTITY_KINDS`; add entity-composition preservation in `_collect_collapsible` |
| `tests/test_design_repository.py` | Modify | Update predicate mapping tests (add `returns`, remove `has_type`) |
| `tests/test_map_to_ontology.py` | Modify | Add tests for enum class_lookup, `composes` edges, `returns` edges |
| `tests/test_collapse_external_entities.py` | Modify | Add tests for enum dual-visibility under COMPOSES |

---

### Task 1: Update predicate constants — add `returns`, remove `has_type`

**Files:**
- Modify: `backend/db/neo4j/repositories/constants.py:21-35`
- Modify: `backend/db/models/ontology.py:243-252`
- Test: `tests/test_design_repository.py:71-95`

- [ ] **Step 1: Write the failing test**

In `tests/test_design_repository.py`, update `TestDesignConstants`:

```python
def test_predicate_mapping(self):
    from backend.db.neo4j.repositories.constants import PREDICATE_TO_REL_TYPE

    assert PREDICATE_TO_REL_TYPE["composes"] == "COMPOSES"
    assert PREDICATE_TO_REL_TYPE["depends_on"] == "DEPENDS_ON"
    assert PREDICATE_TO_REL_TYPE["has_argument"] == "HAS_ARGUMENT"
    assert PREDICATE_TO_REL_TYPE["returns"] == "RETURNS"
    assert "has_type" not in PREDICATE_TO_REL_TYPE
    assert len(PREDICATE_TO_REL_TYPE) == 10
```

Also update `test_default_predicates`:

```python
def test_default_predicates(self):
    from backend.db.neo4j.repositories.constants import DEFAULT_PREDICATES

    names = {name for name, _ in DEFAULT_PREDICATES}
    assert "composes" in names
    assert "returns" in names
    assert "has_argument" in names
    assert "has_type" not in names
    assert "depends_on" in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_design_repository.py::TestDesignConstants -v`
Expected: FAIL — `RETURNS` not in `PREDICATE_TO_REL_TYPE`, `has_type` still present

- [ ] **Step 3: Update `backend/db/neo4j/repositories/constants.py`**

In `PREDICATE_TO_REL_TYPE`, replace `"has_type": "HAS_TYPE"` with `"returns": "RETURNS"`.

In `DEFAULT_PREDICATES`, replace:
```python
("has_type", "An attribute or field is typed by the given entity (attribute → type)"),
```
with:
```python
("returns", "A method returns a value of the given entity type (method → type)"),
```

- [ ] **Step 4: Update `backend/db/models/ontology.py`**

In `Predicate.DEFAULT_PREDICATES`, replace:
```python
# remove the has_type entry if it exists
```
Add:
```python
("returns", "A method returns a value of the given entity type"),
```

Check that `has_type` is not in `DEFAULT_PREDICATES` list.

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_design_repository.py::TestDesignConstants -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/db/neo4j/repositories/constants.py backend/db/models/ontology.py tests/test_design_repository.py
git commit -m "feat: add returns predicate, remove has_type predicate"
```

---

### Task 2: Add `composes` and `returns` to AssociationSchema

**Files:**
- Modify: `backend/codebase/schemas.py:79`
- Test: `tests/test_map_to_ontology.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_map_to_ontology.py`, add a new test class:

```python
class TestAssociationSchemaKinds:
    """AssociationSchema.kind should accept composes and returns."""

    def test_composes_association(self):
        assoc = AssociationSchema(
            from_class="CalculatorResult",
            to_class="ErrorType",
            kind="composes",
            description="ErrorType member variable",
        )
        assert assoc.kind == "composes"

    def test_returns_association(self):
        assoc = AssociationSchema(
            from_class="CalculatorEngine",
            to_class="CalculationResult",
            kind="returns",
            description="Returns calculation result",
        )
        assert assoc.kind == "returns"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_map_to_ontology.py::TestAssociationSchemaKinds -v`
Expected: FAIL — validation error from Literal not including `"composes"` or `"returns"`

- [ ] **Step 3: Update `backend/codebase/schemas.py`**

Change `AssociationSchema.kind` from:
```python
kind: Literal["associates", "aggregates", "depends_on", "references", "invokes"]
```
to:
```python
kind: Literal["associates", "aggregates", "composes", "depends_on", "references", "returns", "invokes"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_map_to_ontology.py::TestAssociationSchemaKinds -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/codebase/schemas.py tests/test_map_to_ontology.py
git commit -m "feat: add composes and returns to AssociationSchema.kind"
```

---

### Task 3: Add enums to `class_lookup` and emit class-level `composes` for attribute types

**Files:**
- Modify: `backend/ticketing_agent/design/map_to_ontology.py:195-198, 312-333`
- Test: `tests/test_map_to_ontology.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_map_to_ontology.py`, add:

```python
class TestEnumInClassLookup:
    """Enums should be added to class_lookup so attribute type
    references to enums can be resolved."""

    def test_class_composes_enum_from_attribute_type(self):
        """When a class has an attribute typed by an enum, a class-level
        composes edge should be emitted (class → enum)."""
        oo = OODesignSchema(
            modules=["calc_engine"],
            enums=[
                EnumSchema(
                    name="ErrorType",
                    module="calc_engine",
                    description="Error types",
                    values=["MALFORMED_STRING", "NULL_INPUT"],
                ),
            ],
            classes=[
                ClassSchema(
                    name="CalculationResult",
                    module="calc_engine",
                    attributes=[
                        AttributeSchema(
                            name="error_signal",
                            type_name="ErrorType",
                            visibility="private",
                            description="Error indicator",
                        ),
                    ],
                    methods=[],
                ),
            ],
        )
        result = map_oo_to_ontology(oo)

        # Class-level composes edge: CalculationResult → ErrorType
        composes_triples = [
            t for t in result.triples
            if t.predicate == "composes"
            and t.subject_qualified_name == "calc_engine::CalculationResult"
            and t.object_qualified_name == "calc_engine::ErrorType"
        ]
        assert len(composes_triples) == 1, (
            f"Expected 1 class-level composes edge from CalculationResult to ErrorType, "
            f"got {composes_triples}. "
            f"All triples: {[(t.predicate, t.subject_qualified_name, t.object_qualified_name) for t in result.triples]}"
        )

    def test_class_composes_class_from_attribute_type(self):
        """When a class has an attribute typed by another design class,
        a class-level composes edge should be emitted."""
        oo = OODesignSchema(
            modules=["core"],
            classes=[
                ClassSchema(
                    name="Engine",
                    module="core",
                    attributes=[],
                    methods=[],
                ),
                ClassSchema(
                    name="Controller",
                    module="core",
                    attributes=[
                        AttributeSchema(
                            name="engine",
                            type_name="Engine",
                            visibility="private",
                            description="The engine",
                        ),
                    ],
                    methods=[],
                ),
            ],
        )
        result = map_oo_to_ontology(oo)

        composes_triples = [
            t for t in result.triples
            if t.predicate == "composes"
            and t.subject_qualified_name == "core::Controller"
            and t.object_qualified_name == "core::Engine"
        ]
        assert len(composes_triples) == 1

    def test_class_composes_interface_from_attribute_type(self):
        """When a class has an attribute typed by a design interface,
        a class-level composes edge should be emitted."""
        oo = OODesignSchema(
            modules=["app"],
            interfaces=[
                InterfaceSchema(
                    name="IHandler",
                    module="app",
                    description="Handler interface",
                    methods=[],
                ),
            ],
            classes=[
                ClassSchema(
                    name="Processor",
                    module="app",
                    attributes=[
                        AttributeSchema(
                            name="handler",
                            type_name="IHandler",
                            visibility="private",
                            description="The handler",
                        ),
                    ],
                    methods=[],
                ),
            ],
        )
        result = map_oo_to_ontology(oo)

        composes_triples = [
            t for t in result.triples
            if t.predicate == "composes"
            and t.subject_qualified_name == "app::Processor"
            and t.object_qualified_name == "app::IHandler"
        ]
        assert len(composes_triples) == 1

    def test_no_composes_for_primitive_attribute_type(self):
        """Primitive types (bool, int, string) should not produce composes edges."""
        oo = OODesignSchema(
            modules=["core"],
            classes=[
                ClassSchema(
                    name="Config",
                    module="core",
                    attributes=[
                        AttributeSchema(
                            name="enabled",
                            type_name="bool",
                            visibility="public",
                            description="Enabled flag",
                        ),
                    ],
                    methods=[],
                ),
            ],
        )
        result = map_oo_to_ontology(oo)

        composes_triples = [
            t for t in result.triples
            if t.predicate == "composes"
            and t.subject_qualified_name == "core::Config"
        ]
        # Only the attribute containment composes (Config → Config::enabled)
        # No class-level composes to a primitive
        entity_composes = [
            t for t in composes_triples
            if "::" not in t.object_qualified_name.replace("core::", "")
        ]
        assert len(entity_composes) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_map_to_ontology.py::TestEnumInClassLookup -v`
Expected: FAIL — no class-level `composes` edge from class to enum

- [ ] **Step 3: Update `map_to_ontology.py` — add enums to `class_lookup`**

After the interface loop (around line 198), add:

```python
for enum in oo.enums:
    class_lookup[enum.name] = _qualify(enum.module, enum.name)
```

- [ ] **Step 4: Update `map_to_ontology.py` — emit class-level `composes` for attribute types**

Replace the current `has_type` attribute edge block (around lines 325-333):

```python
# has_type edge: attribute → design-internal type (enum, class, interface)
if attr.type_name:
    for match in _TYPE_EXTRACT_RE.finditer(attr.type_name):
        type_name = match.group(1)
        if type_name in class_lookup:
            target_qname = class_lookup[type_name]
            _add_triple(attr_qname, "has_type", target_qname)
```

with:

```python
# composes edge: class → design-internal entity type (member variable composition)
if attr.type_name:
    for match in _TYPE_EXTRACT_RE.finditer(attr.type_name):
        type_name = match.group(1)
        if type_name in class_lookup:
            target_qname = class_lookup[type_name]
            _add_triple(cls_qname, "composes", target_qname)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_map_to_ontology.py::TestEnumInClassLookup -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/ticketing_agent/design/map_to_ontology.py tests/test_map_to_ontology.py
git commit -m "feat: add enums to class_lookup and emit class-level composes for attribute types"
```

---

### Task 4: Replace `has_type` method return type edges with `returns` edges

**Files:**
- Modify: `backend/ticketing_agent/design/map_to_ontology.py:355-368`
- Test: `tests/test_map_to_ontology.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_map_to_ontology.py`, add:

```python
class TestReturnsEdge:
    """Methods returning design-internal types should get a returns edge."""

    def test_method_returns_design_class(self):
        oo = OODesignSchema(
            modules=["calc"],
            classes=[
                ClassSchema(
                    name="Calculator",
                    module="calc",
                    attributes=[],
                    methods=[
                        MethodSchema(
                            name="compute",
                            visibility="public",
                            description="Compute result",
                            return_type="CalcResult",
                        ),
                    ],
                ),
                ClassSchema(
                    name="CalcResult",
                    module="calc",
                    attributes=[],
                    methods=[],
                ),
            ],
        )
        result = map_oo_to_ontology(oo)

        returns_triples = [
            t for t in result.triples
            if t.predicate == "returns"
            and t.subject_qualified_name == "calc::Calculator::compute"
            and t.object_qualified_name == "calc::CalcResult"
        ]
        assert len(returns_triples) == 1

    def test_method_returns_design_enum(self):
        oo = OODesignSchema(
            modules=["calc"],
            enums=[
                EnumSchema(
                    name="Status",
                    module="calc",
                    description="Status codes",
                    values=["OK", "ERROR"],
                ),
            ],
            classes=[
                ClassSchema(
                    name="Processor",
                    module="calc",
                    attributes=[],
                    methods=[
                        MethodSchema(
                            name="check",
                            visibility="public",
                            description="Check status",
                            return_type="Status",
                        ),
                    ],
                ),
            ],
        )
        result = map_oo_to_ontology(oo)

        returns_triples = [
            t for t in result.triples
            if t.predicate == "returns"
            and t.subject_qualified_name == "calc::Processor::check"
            and t.object_qualified_name == "calc::Status"
        ]
        assert len(returns_triples) == 1

    def test_no_returns_for_primitive_type(self):
        oo = OODesignSchema(
            modules=["calc"],
            classes=[
                ClassSchema(
                    name="Calculator",
                    module="calc",
                    attributes=[],
                    methods=[
                        MethodSchema(
                            name="count",
                            visibility="public",
                            description="Count items",
                            return_type="int",
                        ),
                    ],
                ),
            ],
        )
        result = map_oo_to_ontology(oo)

        returns_triples = [
            t for t in result.triples
            if t.predicate == "returns"
            and t.subject_qualified_name == "calc::Calculator::count"
        ]
        assert len(returns_triples) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_map_to_ontology.py::TestReturnsEdge -v`
Expected: FAIL — `returns` triples not emitted (current code uses `has_type`)

- [ ] **Step 3: Update `map_to_ontology.py` — replace `has_type` with `returns` for method return types**

Replace the `has_type` block for method return types (around lines 360-368):

```python
# has_type edge: method → design-internal return type
if method.return_type:
    for match in _TYPE_EXTRACT_RE.finditer(method.return_type):
        type_name = match.group(1)
        if type_name in class_lookup:
            target_qname = class_lookup[type_name]
            _add_triple(method_qname, "has_type", target_qname)
```

with:

```python
# returns edge: method → design-internal return type
if method.return_type:
    for match in _TYPE_EXTRACT_RE.finditer(method.return_type):
        type_name = match.group(1)
        if type_name in class_lookup:
            target_qname = class_lookup[type_name]
            _add_triple(method_qname, "returns", target_qname)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_map_to_ontology.py::TestReturnsEdge -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/ticketing_agent/design/map_to_ontology.py tests/test_map_to_ontology.py
git commit -m "feat: replace has_type with returns for method return type edges"
```

---

### Task 5: Simplify `_add_depends_from_type` — remove design-internal `references` fallback

**Files:**
- Modify: `backend/ticketing_agent/design/map_to_ontology.py:202-240`
- Test: `tests/test_map_to_ontology.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_map_to_ontology.py`, add:

```python
class TestNoReferencesFromAttributeTypes:
    """Design-internal type references in attribute types should produce
    composes edges (from the attribute processing), NOT references edges
    from _add_depends_from_type."""

    def test_attribute_type_produces_composes_not_references(self):
        oo = OODesignSchema(
            modules=["calc"],
            enums=[
                EnumSchema(
                    name="ErrorType",
                    module="calc",
                    description="Errors",
                    values=["NONE"],
                ),
            ],
            classes=[
                ClassSchema(
                    name="Result",
                    module="calc",
                    attributes=[
                        AttributeSchema(
                            name="error",
                            type_name="ErrorType",
                            visibility="private",
                            description="Error",
                        ),
                    ],
                    methods=[],
                ),
            ],
        )
        result = map_oo_to_ontology(oo)

        # Should have class-level composes
        composes = [
            t for t in result.triples
            if t.predicate == "composes"
            and t.subject_qualified_name == "calc::Result"
            and t.object_qualified_name == "calc::ErrorType"
        ]
        assert len(composes) == 1

        # Should NOT have references from class to enum
        references = [
            t for t in result.triples
            if t.predicate == "references"
            and t.subject_qualified_name == "calc::Result"
            and t.object_qualified_name == "calc::ErrorType"
        ]
        assert len(references) == 0, (
            f"Expected no references edge, got {references}"
        )

    def test_method_return_type_produces_returns_not_references(self):
        oo = OODesignSchema(
            modules=["calc"],
            classes=[
                ClassSchema(
                    name="Engine",
                    module="calc",
                    attributes=[],
                    methods=[
                        MethodSchema(
                            name="run",
                            visibility="public",
                            description="Run",
                            return_type="Result",
                        ),
                    ],
                ),
                ClassSchema(
                    name="Result",
                    module="calc",
                    attributes=[],
                    methods=[],
                ),
            ],
        )
        result = map_oo_to_ontology(oo)

        # Should have returns edge from method
        returns_edges = [
            t for t in result.triples
            if t.predicate == "returns"
            and t.subject_qualified_name == "calc::Engine::run"
            and t.object_qualified_name == "calc::Result"
        ]
        assert len(returns_edges) == 1

        # Should NOT have references from class to class
        references = [
            t for t in result.triples
            if t.predicate == "references"
            and t.subject_qualified_name == "calc::Engine"
            and t.object_qualified_name == "calc::Result"
        ]
        assert len(references) == 0

    def test_external_dependency_still_produces_depends_on(self):
        """External dependencies in attribute types should still produce
        depends_on edges from _add_depends_from_type."""
        oo = OODesignSchema(
            modules=["ui"],
            classes=[
                ClassSchema(
                    name="Window",
                    module="ui",
                    attributes=[
                        AttributeSchema(
                            name="button",
                            type_name="Fl_Button*",
                            visibility="private",
                            description="Button",
                        ),
                    ],
                    methods=[],
                ),
            ],
        )
        dep_lookup = {"Fl_Button": "Fl_Button"}
        result = map_oo_to_ontology(oo, dependency_lookup=dep_lookup)

        dep_triples = [
            t for t in result.triples
            if t.predicate == "depends_on"
            and t.subject_qualified_name == "ui::Window"
            and t.object_qualified_name == "Fl_Button"
        ]
        assert len(dep_triples) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_map_to_ontology.py::TestNoReferencesFromAttributeTypes -v`
Expected: FAIL — `references` edges still being emitted by `_add_depends_from_type`

- [ ] **Step 3: Update `_add_depends_from_type` in `map_to_ontology.py`**

Replace the function to only handle external dependencies:

```python
def _add_depends_from_type(type_str: str, cls_qname: str, seen: set[str]):
    """Scan a type string for dependency class names and add depends_on triples.

    For external dependencies (not in class_lookup), adds depends_on triples.
    Design-internal type references are handled by composes (attributes),
    returns (method return types), and has_argument (method parameters)
    in the main processing loops above.
    """
    if not type_str:
        return
    for match in _TYPE_EXTRACT_RE.finditer(type_str):
        name = match.group(1)
        if name in class_lookup:
            # Design-internal types are handled by composes/returns/has_argument
            continue
        if name in dep_lookup:
            qname = dep_lookup[name]
            key = f"{cls_qname}->{qname}"
            if key not in seen:
                seen.add(key)
                # Ensure the dependency stub node exists
                if qname not in node_index:
                    _add_node(
                        "class",
                        name,
                        qname,
                        is_intercomponent=True,
                        description=f"External dependency: {qname}",
                        source_type="dependency",
                    )
                _add_triple(cls_qname, "depends_on", qname)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_map_to_ontology.py::TestNoReferencesFromAttributeTypes -v`
Expected: PASS

- [ ] **Step 5: Run all map_to_ontology tests to check for regressions**

Run: `pytest tests/test_map_to_ontology.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add backend/ticketing_agent/design/map_to_ontology.py tests/test_map_to_ontology.py
git commit -m "feat: simplify _add_depends_from_type to only handle external dependencies"
```

---

### Task 6: Update agent prompts — `composes` and `returns` guidance

**Files:**
- Modify: `backend/ticketing_agent/design/design_oo_prompt.py`
- Modify: `backend/ticketing_agent/design/design_ontology_prompt.py`

- [ ] **Step 1: Update `design_oo_prompt.py`**

Find the Associations section that starts with `Kind is one of:` and replace:

```
Kind is one of: associates, aggregates, depends_on, references, invokes.
```

with:

```
Kind is one of: associates, aggregates, composes, depends_on, references, returns, invokes.
```

Then, after the existing `**references**` description block (which ends with the `mechanism` guidance example), add two new blocks:

```
**composes** — A class has a member variable of the given entity type (value
composition). Use when a class holds an instance of another design entity
(enum, class, interface) as a direct member — not via pointer or container.
The attribute still belongs in the class's attributes array; the association
records the entity-to-entity relationship.
Example: `{from_class: "CalculationResult", to_class: "ErrorType", kind: "composes"}`

**returns** — A method returns a value of the given entity type. Records the
entity-to-entity relationship for return types.
Example: `{from_class: "CalculationEngine", to_class: "CalculationResult", kind: "returns"}`
```

- [ ] **Step 2: Update `design_ontology_prompt.py`**

In the **enum** node kind guidance line, change:

```
- **enum** — A fixed set of named values. Contains enum_value children.
```

to:

```
- **enum** — A fixed set of named values. Contains enum_value children. When a
  class holds a member variable of an enum type, the class should have a
  `composes` triple to the enum.
```

In the Guidelines section, add after the `generalizes` bullet:

```
- When a method returns a design-internal type (class, enum, interface), add a
  `returns` triple (method → type). When a method accepts a design-internal
  type as a parameter, add a `has_argument` triple (method → type).
```

- [ ] **Step 3: Run existing prompt-related tests**

Run: `pytest tests/test_design_oo_prompt.py tests/test_combined_prompt_rendering.py -v`
Expected: All PASS (prompt changes don't break existing validation)

- [ ] **Step 4: Commit**

```bash
git add backend/ticketing_agent/design/design_oo_prompt.py backend/ticketing_agent/design/design_ontology_prompt.py
git commit -m "feat: add composes and returns guidance to agent prompts"
```

---

### Task 7: Graph transforms — enum dual visibility under entity-to-entity `COMPOSES`

**Files:**
- Modify: `backend/graph/transforms.py:36, 99-115`
- Test: `tests/test_collapse_external_entities.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_collapse_external_entities.py`, add:

```python
class TestComposedEnumDualVisibility:
    """When a class composes an enum (entity-to-entity composition), the
    enum should stay visible as a separate node AND appear in the
    class's UML compartment."""

    def test_class_composes_enum_stays_visible(self):
        """ErrorType composed by CalculationResult should remain as a
        separate enum node with the COMPOSES edge visible."""
        nodes = [
            _make_node("CalcResult", "CalculationResult", "class"),
            _make_node("ErrorType", "ErrorType", "enum"),
        ]
        edges = [
            _make_edge("e1", "CalcResult", "ErrorType", "COMPOSES"),
        ]

        out_nodes, out_edges = collapse_members(nodes, edges)

        node_ids = {n["data"]["id"] for n in out_nodes}
        assert "ErrorType" in node_ids, "Enum should remain visible as separate node"
        assert "CalcResult" in node_ids

        # COMPOSES edge should be visible
        edge_labels = {
            (e["data"]["source"], e["data"]["target"], e["data"]["label"])
            for e in out_edges
        }
        assert ("CalcResult", "ErrorType", "COMPOSES") in edge_labels

    def test_class_composes_enum_with_enum_values(self):
        """An enum with its own enum_values, composed by a class, should
        keep the enum visible with values collapsed into it."""
        nodes = [
            _make_node("CalcResult", "CalculationResult", "class"),
            _make_node("ErrorType", "ErrorType", "enum"),
            _make_node("ev1", "MALFORMED_STRING", "enum_value"),
            _make_node("ev2", "NULL_INPUT", "enum_value"),
        ]
        edges = [
            _make_edge("e1", "CalcResult", "ErrorType", "COMPOSES"),
            _make_edge("e2", "ErrorType", "ev1", "COMPOSES"),
            _make_edge("e3", "ErrorType", "ev2", "COMPOSES"),
        ]

        out_nodes, out_edges = collapse_members(nodes, edges)

        node_ids = {n["data"]["id"] for n in out_nodes}
        # Enum stays visible
        assert "ErrorType" in node_ids
        # Enum values are collapsed into the enum
        assert "ev1" not in node_ids
        assert "ev2" not in node_ids

    def test_module_composes_enum_uses_parent_not_external(self):
        """A module composes an enum (namespace containment) — this should
        use the parent field mechanism, NOT keep it as an external node due
        to entity composition. The module is the source, so this shouldn't
        trigger entity-composition preservation."""
        nodes = [
            _make_node("mod", "calc_engine", "module"),
            _make_node("ErrorType", "ErrorType", "enum"),
        ]
        edges = [
            _make_edge("e1", "mod", "ErrorType", "COMPOSES"),
        ]

        out_nodes, out_edges = collapse_members(nodes, edges)

        # The module → enum COMPOSES should not cause the enum to be
        # treated as an entity-with-external-edges. Module containment
        # is handled by _assign_explicit_parents (parent field), not
        # by the collapse/external-entity logic.
        # In collapse_members, module is in _OWNER_KINDS and enum is in
        # _COLLAPSIBLE_KINDS, so without the entity-composition fix,
        # the enum would be fully collapsed. With module as source,
        # the entity-composition check should NOT apply (modules are
        # not the same as classes composing a type).
        # This test verifies module→enum still works correctly.
        node_ids = {n["data"]["id"] for n in out_nodes}
        # Module is an owner kind but NOT a class composing a type —
        # the enum should be fully collapsed (module→enum is containment)
        assert "ErrorType" not in node_ids

    def test_class_composes_interface_stays_visible(self):
        """Previously only classes with DEPENDS_ON stayed visible.
        Now COMPOSES also triggers dual visibility for entity kinds."""
        nodes = [
            _make_node("Owner", "Owner", "class"),
            _make_node("Iface", "IHandler", "interface"),
        ]
        edges = [
            _make_edge("e1", "Owner", "Iface", "COMPOSES"),
        ]

        out_nodes, out_edges = collapse_members(nodes, edges)

        node_ids = {n["data"]["id"] for n in out_nodes}
        assert "Iface" in node_ids
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_collapse_external_entities.py::TestComposedEnumDualVisibility -v`
Expected: FAIL — enum is fully collapsed and removed from node list

- [ ] **Step 3: Update `backend/graph/transforms.py`**

Change `_ENTITY_KINDS` from:

```python
_ENTITY_KINDS = {"class", "interface", "struct"}
```

to:

```python
_ENTITY_KINDS = {"class", "interface", "enum", "struct"}
```

Add entity-composition preservation in `_collect_collapsible`. After the
existing `external_entity_ids` identification block (around line 115), add:

```python
# Identify entity nodes that are composed by another non-module entity.
# When a design entity (class, interface, enum, struct) is composed
# by another design entity (not a module), the composition relationship
# is meaningful at the entity level and the target should remain visible
# as a separate node in the graph alongside the collapsed representation.
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

# Don't remove entity nodes composed by another entity
remove_node_ids -= entity_composed_by_owner
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_collapse_external_entities.py::TestComposedEnumDualVisibility -v`
Expected: PASS

- [ ] **Step 5: Run all collapse tests to check for regressions**

Run: `pytest tests/test_collapse_external_entities.py -v`
Expected: All PASS

Note: `test_composes_does_not_keep_entity` in `TestComposesNotAffected` will need
updating — it currently asserts that a class COMPOSES a class with no other edges
should fully collapse it. With the new entity-composition logic, a class COMPOSES
class should now keep the target visible. Update this test:

```python
def test_composes_keeps_entity_visible(self):
    """COMPOSES edge to a class node should keep it visible as an
    external node (entity-to-entity composition)."""
    nodes = [
        _make_node("Owner", "Owner", "class"),
        _make_node("Nested", "NestedClass", "class"),
    ]
    edges = [
        _make_edge("e1", "Owner", "Nested", "COMPOSES"),
    ]

    out_nodes, _ = collapse_members(nodes, edges)

    node_ids = {n["data"]["id"] for n in out_nodes}
    assert "Nested" in node_ids
```

Also update `test_aggregated_class_no_edges_fully_collapsed` and
`test_aggregated_class_only_containment_edges_fully_collapsed` — AGGREGATES
from a non-module source now also keeps entity kinds visible. Update:

```python
def test_aggregated_class_no_edges_keeps_visible(self):
    """An aggregated class from a non-module owner stays visible
    (entity-to-entity composition relationship)."""
    nodes = [
        _make_node("Owner", "Owner", "class"),
        _make_node("Agg", "InnerClass", "class"),
    ]
    edges = [
        _make_edge("e1", "Owner", "Agg", "AGGREGATES"),
    ]

    out_nodes, out_edges = collapse_members(nodes, edges)

    node_ids = {n["data"]["id"] for n in out_nodes}
    assert "Agg" in node_ids
    # Shown in compartment
    owner = next(n for n in out_nodes if n["data"]["id"] == "Owner")
    assert "InnerClass" in owner["data"]["label"]
```

```python
def test_aggregated_class_only_containment_edges_keeps_visible(self):
    """An aggregated class with only COMPOSES/CONTAINS edges
    from its owner stays visible."""
    nodes = [
        _make_node("Owner", "Owner", "class"),
        _make_node("Agg", "InnerClass", "class"),
        _make_node("m1", "inner_method", "method"),
    ]
    edges = [
        _make_edge("e1", "Owner", "Agg", "AGGREGATES"),
        _make_edge("e2", "Agg", "m1", "COMPOSES"),
    ]

    out_nodes, _ = collapse_members(nodes, edges)

    node_ids = {n["data"]["id"] for n in out_nodes}
    assert "Agg" in node_ids
    assert "m1" not in node_ids  # method still fully collapsed
```

- [ ] **Step 6: Commit**

```bash
git add backend/graph/transforms.py tests/test_collapse_external_entities.py
git commit -m "feat: keep composed enums visible in graph as separate nodes"
```

---

### Task 8: Full regression run

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All PASS

- [ ] **Step 2: Commit (if any fixes needed)**

If any tests failed and needed fixes, commit them:

```bash
git add -A && git commit -m "fix: address regressions from enum composition edges"
```