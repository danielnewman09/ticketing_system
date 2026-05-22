# Dependency Graph Linkages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure design nodes link to dependency Compound nodes in Neo4j via edges (aggregates, generalizes, depends_on), so the graph view shows dependencies as connected nodes rather than orphaned.

**Architecture:** Pass dependency metadata from `discover_classes` through `design_hlr` to `map_oo_to_ontology`, which uses it to resolve dependency references and produce dependency-targeting triples. `persist_design` creates stub OntologyNode entries for dependency targets (satisfying the FK), and the Neo4j sync skips these stubs while the edge creation routes them to real Compound nodes.

**Tech Stack:** Python, SQLAlchemy, Neo4j/Cypher, Pydantic

---

### Task 1: Add `"dependency"` source type to the schema and model

**Files:**
- Modify: `backend/db/models/ontology.py` (SOURCE_TYPES list)
- Modify: `backend/codebase/schemas.py` (SourceType literal)
- Test: `tests/test_codebase_schemas.py`

- [ ] **Step 1: Add `"dependency"` to SOURCE_TYPES in ontology.py**

In `backend/db/models/ontology.py`, add the `"dependency"` entry to the `SOURCE_TYPES` list:

```python
SOURCE_TYPES = [
    ("namespace", "Namespace"),
    ("compound", "Compound"),
    ("member", "Member"),
    ("dependency", "Dependency Reference"),
]
```

- [ ] **Step 2: Add `"dependency"` to SourceType literal in schemas.py**

In `backend/codebase/schemas.py`, the `SourceType` literal is derived from `SOURCE_TYPES` via:

```python
SourceType = Literal[tuple(k for k, _ in SOURCE_TYPES)]
```

Since we added `("dependency", ...)` to `SOURCE_TYPES`, this automatically includes `"dependency"` in the `SourceType` literal. Verify by reading the import:

```python
from backend.db.models.ontology import NODE_KINDS, SOURCE_TYPES, VISIBILITY_CHOICES
```

No code change needed here — it's derived dynamically.

- [ ] **Step 3: Run the existing schema test to verify**

Run: `source .venv/bin/activate && python -m pytest tests/test_codebase_schemas.py::TestSourceTypeLiteral -v`

Expected: PASS — the test iterates SOURCE_TYPES and checks each is in SourceType, and `"dependency"` is now included.

- [ ] **Step 4: Commit**

```bash
git add backend/db/models/ontology.py
git commit -m "feat: add 'dependency' source type for cross-layer reference stubs"
```

---

### Task 2: Add `dependency_lookup` parameter to `map_oo_to_ontology`

**Files:**
- Modify: `backend/ticketing_agent/design/map_to_ontology.py`
- Test: `tests/test_map_to_ontology.py` (new file)

This is the core change. The mapper needs dependency context to resolve references and produce `depends_on` triples from type signatures.

- [ ] **Step 1: Write failing tests for dependency resolution**

Create `tests/test_map_to_ontology.py`:

```python
"""Tests for map_oo_to_ontology dependency resolution."""

import pytest
from backend.codebase.schemas import (
    AssociationSchema,
    AttributeSchema,
    ClassSchema,
    DesignSchema,
    MethodSchema,
    OODesignSchema,
)
from backend.ticketing_agent.design.map_to_ontology import map_oo_to_ontology


class TestDependencyLookupInAssociations:
    """When an association targets a dependency class, the triple should
    use the dependency's qualified name from the lookup."""

    def test_association_to_dependency_resolved(self):
        oo = OODesignSchema(
            modules=["calc"],
            classes=[
                ClassSchema(
                    name="Calculator",
                    module="calc",
                    attributes=[],
                    methods=[],
                ),
            ],
            associations=[
                AssociationSchema(
                    from_class="Calculator",
                    to_class="Fl_Window",
                    kind="aggregates",
                    description="Calculator window",
                ),
            ],
        )
        dep_lookup = {"Fl_Window": "Fl_Window"}
        result = map_oo_to_ontology(
            oo, dependency_lookup=dep_lookup, component_id=1
        )
        # There should be a triple: calc::Calculator -[aggregates]-> Fl_Window
        dep_agg = [
            t for t in result.triples
            if t.predicate == "aggregates" and t.object_qualified_name == "Fl_Window"
        ]
        assert len(dep_agg) == 1
        # There should also be a dependency stub node for Fl_Window
        dep_node = [n for n in result.nodes if n.qualified_name == "Fl_Window"]
        assert len(dep_node) == 1
        assert dep_node[0].source_type == "dependency"
        assert dep_node[0].is_intercomponent is True

    def test_association_to_dependency_with_namespaced_qname(self):
        oo = OODesignSchema(
            modules=["calc"],
            classes=[
                ClassSchema(
                    name="Calculator",
                    module="calc",
                    attributes=[],
                    methods=[],
                ),
            ],
            associations=[
                AssociationSchema(
                    from_class="Calculator",
                    to_class="string",
                    kind="depends_on",
                    description="Uses strings",
                ),
            ],
        )
        dep_lookup = {"string": "std::string"}
        result = map_oo_to_ontology(
            oo, dependency_lookup=dep_lookup
        )
        dep_triples = [
            t for t in result.triples
            if t.object_qualified_name == "std::string"
        ]
        assert len(dep_triples) >= 1
        dep_node = [n for n in result.nodes if n.qualified_name == "std::string"]
        assert len(dep_node) == 1
        assert dep_node[0].source_type == "dependency"


class TestDependencyLookupInInheritance:
    """When a class inherits from a dependency class, the generalizes
    triple should use the dependency's qualified name."""

    def test_inherits_from_dependency(self):
        oo = OODesignSchema(
            modules=["ui"],
            classes=[
                ClassSchema(
                    name="MyWindow",
                    module="ui",
                    inherits_from=["Fl_Window"],
                    attributes=[],
                    methods=[],
                ),
            ],
        )
        dep_lookup = {"Fl_Window": "Fl_Window"}
        result = map_oo_to_ontology(
            oo, dependency_lookup=dep_lookup
        )
        gen_triples = [
            t for t in result.triples
            if t.predicate == "generalizes" and t.object_qualified_name == "Fl_Window"
        ]
        assert len(gen_triples) == 1
        dep_node = [n for n in result.nodes if n.qualified_name == "Fl_Window"]
        assert len(dep_node) == 1
        assert dep_node[0].source_type == "dependency"


class TestDependsOnFromTypeSignatures:
    """When an attribute or method return type references a dependency class,
    a depends_on triple should be synthesized from the design class."""

    def test_attribute_type_references_dependency(self):
        oo = OODesignSchema(
            modules=["ui"],
            classes=[
                ClassSchema(
                    name="Calculator",
                    module="ui",
                    attributes=[
                        AttributeSchema(
                            name="display",
                            type_name="Fl_Output",
                            visibility="private",
                            description="The display",
                        ),
                    ],
                    methods=[],
                ),
            ],
        )
        dep_lookup = {"Fl_Output": "Fl_Output"}
        result = map_oo_to_ontology(
            oo, dependency_lookup=dep_lookup
        )
        dep_triples = [
            t for t in result.triples
            if t.predicate == "depends_on"
            and t.subject_qualified_name == "ui::Calculator"
            and t.object_qualified_name == "Fl_Output"
        ]
        assert len(dep_triples) == 1
        dep_node = [n for n in result.nodes if n.qualified_name == "Fl_Output"]
        assert len(dep_node) == 1
        assert dep_node[0].source_type == "dependency"

    def test_pointer_type_still_resolves(self):
        """Fl_Output* should still resolve Fl_Output."""
        oo = OODesignSchema(
            modules=["ui"],
            classes=[
                ClassSchema(
                    name="Calculator",
                    module="ui",
                    attributes=[
                        AttributeSchema(
                            name="display",
                            type_name="Fl_Output*",
                            visibility="private",
                            description="Pointer to display",
                        ),
                    ],
                    methods=[],
                ),
            ],
        )
        dep_lookup = {"Fl_Output": "Fl_Output"}
        result = map_oo_to_ontology(
            oo, dependency_lookup=dep_lookup
        )
        dep_triples = [
            t for t in result.triples
            if t.predicate == "depends_on"
            and t.object_qualified_name == "Fl_Output"
        ]
        assert len(dep_triples) == 1

    def test_no_depends_on_for_design_internal_classes(self):
        """If the type name matches a design class, no depends_on should be created."""
        oo = OODesignSchema(
            modules=["calc"],
            classes=[
                ClassSchema(
                    name="Calculator",
                    module="calc",
                    attributes=[
                        AttributeSchema(
                            name="result",
                            type_name="CalculationResult",
                            visibility="private",
                            description="The result",
                        ),
                    ],
                    methods=[],
                ),
                ClassSchema(
                    name="CalculationResult",
                    module="calc",
                    attributes=[],
                    methods=[],
                ),
            ],
        )
        dep_lookup = {}  # No dependencies
        result = map_oo_to_ontology(
            oo, dependency_lookup=dep_lookup
        )
        dep_triples = [
            t for t in result.triples if t.predicate == "depends_on"
        ]
        assert len(dep_triples) == 0


class TestNoDependencyLookup:
    """Without a dependency_lookup, behavior should be unchanged."""

    def test_association_to_unknown_name_uses_bare_name(self):
        oo = OODesignSchema(
            modules=["calc"],
            classes=[
                ClassSchema(name="Calculator", module="calc", attributes=[], methods=[]),
            ],
            associations=[
                AssociationSchema(
                    from_class="Calculator",
                    to_class="RandomThing",
                    kind="associates",
                    description="Something",
                ),
            ],
        )
        result = map_oo_to_ontology(oo)
        # Triple uses bare name (no resolution)
        assoc_triples = [
            t for t in result.triples
            if t.predicate == "associates" and t.object_qualified_name == "RandomThing"
        ]
        assert len(assoc_triples) == 1
        # No dependency stub node
        random_nodes = [n for n in result.nodes if n.qualified_name == "RandomThing"]
        assert len(random_nodes) == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_map_to_ontology.py -v`

Expected: FAIL — `dependency_lookup` parameter doesn't exist yet, and the dependency resolution logic isn't implemented.

- [ ] **Step 3: Implement dependency resolution in `map_oo_to_ontology`**

In `backend/ticketing_agent/design/map_to_ontology.py`:

1. Add `dependency_lookup: dict[str, str] | None = None` parameter to `map_oo_to_ontology`.

2. After the class_lookup is built (around line 230), add the dependency resolution logic. The key additions:
   - Build a combined resolution lookup: first check `class_lookup` (design-internal names), then `dependency_lookup` (dependency names). Names not in either are left as bare strings (existing behavior).
   - When resolving references in associations, `inherits_from`, and `realizes_interfaces`, use the combined lookup.
   - For references that resolve via `dependency_lookup` only (not in `class_lookup`), create a dependency stub node with `source_type="dependency"`.
   - Scan attribute `type_name` and method `return_type` for dependency class names and create `depends_on` triples.

Add the `_resolve_ref` helper and dependency node/triple creation after the existing class/interface/enum processing and class_lookup construction:

```python
def _resolve_ref(name: str, class_lookup: dict, dep_lookup: dict, dep_stubs: dict) -> str | None:
    """Resolve a class/interface name to its qualified name.
    
    Checks class_lookup first (design-internal), then dep_lookup (dependency).
    Returns None if the name is not found in either lookup.
    """
    if name in class_lookup:
        return class_lookup[name]
    if name in dep_lookup:
        qname = dep_lookup[name]
        # Create a dependency stub node if not already created
        if qname not in node_index:
            _add_node(
                "class",
                name,
                qname,
                is_intercomponent=True,
                description=f"External dependency: {qname}",
                source_type="dependency",
            )
            dep_stubs[qname] = name
        return qname
    return None
```

Then update the reference resolution sections to use `_resolve_ref`:

For associations:
```python
for assoc in oo.associations:
    from_qname = _resolve_ref(assoc.from_class, class_lookup, dep_lookup, dep_stubs) or assoc.from_class
    to_qname = _resolve_ref(assoc.to_class, class_lookup, dep_lookup, dep_stubs) or assoc.to_class
    triple_idx = _add_triple(from_qname, assoc.kind, to_qname)
    _link_reqs(assoc.requirement_ids, triple_idx)
```

For `inherits_from`:
```python
for parent_name in cls.inherits_from:
    parent_qname = _resolve_ref(parent_name, class_lookup, dep_lookup, dep_stubs) or parent_name
    triple_idx = _add_triple(cls_qname, "generalizes", parent_qname)
    _link_reqs(cls.requirement_ids, triple_idx)
```

For `realizes_interfaces`:
```python
for iface_name in cls.realizes_interfaces:
    iface_qname = _resolve_ref(iface_name, class_lookup, dep_lookup, dep_stubs) or iface_name
    triple_idx = _add_triple(cls_qname, "realizes", iface_qname)
    _link_reqs(cls.requirement_ids, triple_idx)
```

For type-signature dependency inference (after the classes section):
```python
# --- Dependency type inference from attribute types and return types ---
_TYPE_EXTRACT_RE = re.compile(r"\b([A-Z]\w+)\b")

for cls in oo.classes:
    cls_qname = _qualify(cls.module, cls.name)
    seen_dep_types: set[str] = set()
    for attr in cls.attributes:
        _add_depends_from_type(attr.type_name, cls_qname, dep_lookup, class_lookup, seen_dep_types)
    for method in cls.methods:
        _add_depends_from_type(method.return_type, cls_qname, dep_lookup, class_lookup, seen_dep_types)
        for param in method.parameters:
            _add_depends_from_type(param, cls_qname, dep_lookup, class_lookup, seen_dep_types)

def _add_depends_from_type(type_str, cls_qname, dep_lookup, class_lookup, seen_dep_types):
    """Scan a type string for dependency class names and add depends_on triples."""
    if not type_str:
        return
    for match in _TYPE_EXTRACT_RE.finditer(type_str):
        name = match.group(1)
        if name in class_lookup:
            continue  # design-internal reference, not a dependency
        if name in dep_lookup:
            dep_qname = dep_lookup[name]
            key = f"{cls_qname}->{dep_qname}"
            if key not in seen_dep_types:
                seen_dep_types.add(key)
                _add_triple(cls_qname, "depends_on", dep_qname)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_map_to_ontology.py -v`

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/ticketing_agent/design/map_to_ontology.py tests/test_map_to_ontology.py
git commit -m "feat: map_oo_to_ontology resolves dependency refs and creates depends_on triples"
```

---

### Task 3: Build and pass `dependency_lookup` in `design_hlr`

**Files:**
- Modify: `backend/ticketing_agent/design/design_hlr.py`

- [ ] **Step 1: Build `dependency_lookup` from discovery output and pass it to `map_oo_to_ontology`**

In `backend/ticketing_agent/design/design_hlr.py`, after the `dependency_classes` and `as_built_classes` are set (around line 85), build the lookup:

```python
dependency_lookup = None
if dependency_classes:
    dependency_lookup = {cls["name"]: cls["qualified_name"] for cls in dependency_classes}
```

Then update the `map_oo_to_ontology` call to include `dependency_lookup`:

```python
ontology = map_oo_to_ontology(
    oo,
    component_id=component_id,
    prior_class_lookup=prior_class_lookup,
    component_namespace=component_namespace,
    dependency_lookup=dependency_lookup,
)
```

- [ ] **Step 2: Run existing design tests to verify nothing broke**

Run: `source .venv/bin/activate && python -m pytest tests/test_oo_design_schema.py tests/test_codebase_schemas.py -v`

Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/ticketing_agent/design/design_hlr.py
git commit -m "feat: pass dependency_lookup from discovery through design_hlr to mapper"
```

---

### Task 4: Persist dependency stub nodes in `persist_design`

**Files:**
- Modify: `backend/requirements/services/persistence.py`
- Test: `tests/test_persistence.py` (new file)

When a triple's `object_qualified_name` isn't in `qname_to_node`, check if it exists as a dependency stub in the `DesignSchema.nodes` (source_type="dependency") and create a corresponding `OntologyNode` in SQLite.

- [ ] **Step 1: Write failing test for dependency stub persistence**

Create `tests/test_persistence.py` with a test that verifies stub nodes are created for dependency targets:

```python
"""Tests for persist_design with dependency stub nodes."""
import pytest
from backend.codebase.schemas import (
    AssociationSchema,
    ClassSchema,
    DesignSchema,
    OntologyNodeSchema,
    OntologyTripleSchema,
    OODesignSchema,
)
from backend.requirements.services.persistence import persist_design, DesignResult


@pytest.fixture
def db_session():
    from backend.db import init_db, get_session
    from backend.db.models import Predicate
    init_db()
    with get_session() as session:
        Predicate.ensure_defaults(session)
        yield session


class TestPersistDependencyStubs:
    def test_dependency_stub_created_for_triple_target(self, db_session):
        """When a triple targets a dependency qualified name that's in
        the DesignSchema nodes (source_type='dependency'), a stub
        OntologyNode should be created in SQLite."""
        from backend.db.models import OntologyNode, OntologyTriple, Predicate

        nodes = [
            OntologyNodeSchema(
                kind="class",
                name="Calculator",
                qualified_name="calc::Calculator",
                source_type="compound",
            ),
            OntologyNodeSchema(
                kind="class",
                name="Fl_Button",
                qualified_name="Fl_Button",
                source_type="dependency",
                is_intercomponent=True,
                description="External dependency: Fl_Button",
            ),
        ]
        triples = [
            OntologyTripleSchema(
                subject_qualified_name="calc::Calculator",
                predicate="depends_on",
                object_qualified_name="Fl_Button",
            ),
        ]
        design = DesignSchema(nodes=nodes, triples=triples)

        qname_to_node: dict = {}
        result = persist_design(db_session, design, qname_to_node=qname_to_node)

        assert result.triples_created == 1
        assert result.triples_skipped == 0

        # The dependency stub should exist in the DB
        dep_node = db_session.query(OntologyNode).filter_by(
            qualified_name="Fl_Button"
        ).first()
        assert dep_node is not None
        assert dep_node.source_type == "dependency"
        assert dep_node.is_intercomponent is True

        # The triple should reference the stub node
        triple = db_session.query(OntologyTriple).first()
        assert triple is not None
        assert triple.object_id == dep_node.id
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest tests/test_persistence.py::TestPersistDependencyStubs -v`

Expected: FAIL — dependency stubs are currently skipped (triples_skipped increments).

- [ ] **Step 3: Modify `persist_design` to handle dependency node targets**

In `backend/requirements/services/persistence.py`, in the `persist_design` function, update the triple-persistence section. Currently, when `obj` is `None` (not in `qname_to_node`), the triple is skipped. Change it to also check the `DesignSchema.nodes` for dependency stubs.

After the existing node-creation loop, build a map of dependency-stub qnames from the design schema. Then, in the triple loop, if `obj` is None, check if the target qualified name is a dependency stub node and create it:

```python
# After node creation loop, build dependency stub map
dep_stub_qnames = {
    nd.qualified_name for nd in design.nodes if nd.source_type == "dependency"
}

# In the triple loop, replace:
#   if subj and obj and pred:
# with:
#   if subj and pred:
#       if obj is None and triple_data.object_qualified_name in dep_stub_qnames:
#           # Create a dependency stub node
#           stub_data = next(nd for nd in design.nodes if nd.qualified_name == triple_data.object_qualified_name)
#           stub_node, _ = get_or_create(session, OntologyNode, ...)
#           obj = stub_node
#           qname_to_node[stub_data.qualified_name] = stub_node
```

Add a new counter to `DesignResult`:

```python
dependency_stubs_created: int = 0
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `source .venv/bin/activate && python -m pytest tests/test_persistence.py::TestPersistDependencyStubs -v`

Expected: PASS.

- [ ] **Step 5: Run all existing tests to ensure nothing regressed**

Run: `source .venv/bin/activate && python -m pytest tests/test_codebase_schemas.py tests/test_oo_design_schema.py -v`

Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/requirements/services/persistence.py tests/test_persistence.py
git commit -m "feat: persist_design creates stub nodes for dependency targets"
```

---

### Task 5: Skip dependency stubs in Neo4j sync

**Files:**
- Modify: `backend/db/neo4j/sync.py`
- Test: `tests/test_neo4j_sync.py` (new file)

When `sync_design_node` is called on a dependency stub (source_type="dependency"), skip it — the real node exists as a Compound in Neo4j.

- [ ] **Step 1: Add skip logic to `sync_design_node`**

In `backend/db/neo4j/sync.py`, at the start of `sync_design_node`, add:

```python
def sync_design_node(neo4j_session: Neo4jSession, node) -> None:
    """MERGE a Design node by qualified_name, setting all properties.
    
    Skips dependency-reference stubs — their real nodes exist as
    Compound nodes in Neo4j and edges are created via sync_design_triple.
    """
    if getattr(node, 'source_type', None) == 'dependency':
        log.debug("Skipping dependency stub %s in Neo4j sync", node.qualified_name)
        return
    # ... existing code ...
```

Also update `try_sync_design_nodes_and_triples` to filter out dependency stubs from the nodes list before syncing:

```python
def try_sync_design_nodes_and_triples(nodes, triples):
    """Sync a batch of design nodes and triples to Neo4j."""
    try:
        with get_neo4j().session() as session:
            for node in nodes:
                if getattr(node, 'source_type', None) == 'dependency':
                    continue
                sync_design_node(session, node)
            for triple in triples:
                sync_design_triple(session, triple)
        return True
    except Exception:
        log.warning("Neo4j sync failed — design sync deferred", exc_info=True)
        return False
```

- [ ] **Step 2: Commit**

```bash
git add backend/db/neo4j/sync.py
git commit -m "feat: skip dependency stub nodes in Neo4j sync"
```

---

### Task 6: Filter dependency stubs from design-intent queries

**Files:**
- Modify: `backend/requirements/services/graph_tags.py`

Dependency stubs (source_type="dependency") should not receive requirement tag badges — they're not part of the design intent.

- [ ] **Step 1: Exclude dependency stubs from `enrich_with_requirement_tags`**

In `backend/requirements/services/graph_tags.py`, in `enrich_with_requirement_tags`, add a filter to skip nodes with `source_type == "dependency"`:

After the `node_qns` set is built, add:

```python
# Skip dependency stubs — they are cross-references, not design intent
dependency_qns = {
    n["data"]["qualified_name"]
    for n in nodes
    if n["data"].get("source_type") == "dependency"
}
```

Then when building `qn_to_reqs`, skip nodes in `dependency_qns`.

This is an optimization — dependency stubs won't have HLR nodes linked to them anyway, so the query just returns empty results. But it's cleaner to filter explicitly.

- [ ] **Step 2: Commit**

```bash
git add backend/requirements/services/graph_tags.py
git commit -m "feat: exclude dependency stubs from requirement tag enrichment"
```

---

### Task 7: Integration test — full pipeline verification

**Files:**
- Create: `tests/test_dependency_pipeline.py`

- [ ] **Step 1: Write an end-to-end test that exercises the full mapper→persistence path with dependency classes**

```python
"""Integration test: design pipeline with dependency linkages."""
import pytest
from backend.codebase.schemas import (
    AssociationSchema,
    AttributeSchema,
    ClassSchema,
    DesignSchema,
    MethodSchema,
    OODesignSchema,
)
from backend.ticketing_agent.design.map_to_ontology import map_oo_to_ontology
from backend.requirements.services.persistence import persist_design


@pytest.fixture
def db_session():
    from backend.db import init_db, get_session
    from backend.db.models import Predicate
    init_db()
    with get_session() as session:
        Predicate.ensure_defaults(session)
        yield session


class TestDependencyPipeline:
    def test_full_pipeline_with_dependency(self, db_session):
        """End-to-end: OO design references dependency class →
        triples created → stubs persisted → graph shows linkage."""
        from backend.db.models import OntologyNode, OntologyTriple

        # Step 1: Map OO design with dependency references
        oo = OODesignSchema(
            modules=["ui"],
            classes=[
                ClassSchema(
                    name="CalculatorWindow",
                    module="ui",
                    inherits_from=["Fl_Window"],
                    attributes=[
                        AttributeSchema(
                            name="display",
                            type_name="Fl_Output*",
                            visibility="private",
                            description="The display widget",
                        ),
                    ],
                    methods=[],
                ),
            ],
            associations=[
                AssociationSchema(
                    from_class="CalculatorWindow",
                    to_class="Fl_Button",
                    kind="aggregates",
                    description="Button widgets",
                    requirement_ids=["hlr:1"],
                ),
            ],
        )
        dep_lookup = {
            "Fl_Window": "Fl_Window",
            "Fl_Output": "Fl_Output",
            "Fl_Button": "Fl_Button",
        }

        design = map_oo_to_ontology(
            oo, dependency_lookup=dep_lookup, component_id=1
        )

        # Verify mapper output
        dep_nodes = [n for n in design.nodes if n.source_type == "dependency"]
        dep_qnames = {n.qualified_name for n in dep_nodes}
        assert "Fl_Window" in dep_qnames, f"Fl_Window missing from deps: {dep_qnames}"
        assert "Fl_Button" in dep_qnames, f"Fl_Button missing from deps: {dep_qnames}"

        # Verify triples targeting dependency nodes
        dep_triple_obj_qnames = {t.object_qualified_name for t in design.triples}
        assert "Fl_Window" in dep_triple_obj_qnames  # generalizes
        assert "Fl_Button" in dep_triple_obj_qnames  # aggregates
        assert "Fl_Output" in dep_triple_obj_qnames  # depends_on from type

        # Step 2: Persist
        qname_to_node = {}
        result = persist_design(db_session, design, qname_to_node=qname_to_node)

        assert result.triples_skipped == 0, f"Some triples were skipped: {result}"

        # Verify stubs in DB
        fl_button = db_session.query(OntologyNode).filter_by(
            qualified_name="Fl_Button"
        ).first()
        assert fl_button is not None
        assert fl_button.source_type == "dependency"
        assert fl_button.is_intercomponent is True

        # Verify triples exist
        dep_triples = db_session.query(OntologyTriple).all()
        agg_to_button = [
            t for t in dep_triples
            if t.object.qualified_name == "Fl_Button" and t.predicate.name == "aggregates"
        ]
        assert len(agg_to_button) == 1
```

- [ ] **Step 2: Run the integration test**

Run: `source .venv/bin/activate && python -m pytest tests/test_dependency_pipeline.py -v`

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_dependency_pipeline.py
git commit -m "test: add integration test for dependency pipeline"
```

---

### Task 8: Run the full pipeline with real data

**Files:** No code changes — manual verification

- [ ] **Step 1: Re-run the design pipeline scripts**

```bash
source .venv/bin/activate
python scripts/01_flush_db.py
python scripts/02_setup_project.py
python scripts/03_design_requirements.py
```

- [ ] **Step 2: Verify dependency edges in the output**

Check the "SUMMARY" output from `03_design_requirements.py`. Look for:
- Ontology triples count should be higher than before (includes dependency edges)
- HLR triples should now show edges to dependency classes
- `triples_skipped` in `persist_design` result should be 0 or lower than before

- [ ] **Step 3: Verify in the graph view**

Start the app (`python nicegui_app.py`), navigate to the ontology graph, and verify:
- Dependency classes (Fl_Window, Fl_Button, Fl_Output, etc.) appear as connected nodes
- Edges from design classes to dependencies are visible (aggregates, generalizes, depends_on)
- Cross-layer edges are styled differently

- [ ] **Commit any remaining changes**

```bash
git add -A
git commit -m "chore: full pipeline verification complete"
```