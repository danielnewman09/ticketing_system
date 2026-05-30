# Codegraph Constants Consolidation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge all Neo4j graph constants into `codegraph/constants.py` and delete the two duplicate ticketing-system copies.

**Architecture:** Single source of truth in `codegraph`. Subnode-type lists become `(key, label)` tuples. Consumers that previously used flat-list membership now use `NODE_KIND_KEYS` or inline key extraction.

**Tech Stack:** Python 3.12, codegraph library, pytest

---

### Task 1: Update codegraph/constants.py

**Files:**
- Modify: `/Users/danielnewman/dev/codegraph/src/codegraph/constants.py`

- [ ] **Step 1: Rewrite constants.py with all canonical content**

Replace the entire file:

```python
"""Constants for the Neo4j codebase graph layer.

Defines the vocabulary of node kinds, layers, visibility, predicates,
schema DDL, language specializations, and semantic groupings used by
both the ticketing system and Doxygen parser.
"""

# ---------------------------------------------------------------------------
# Subnode-type lists — source of truth; (key, Display) tuples
# ---------------------------------------------------------------------------

COMPOUND_KINDS: list[tuple[str, str]] = [
    ("class", "Class"),
    ("struct", "Struct"),
    ("template_class", "Template Class"),
    ("interface", "Interface"),
    ("abstract_class", "Abstract Class"),
    ("enum", "Enum"),
    ("enum_class", "Enum Class"),
    ("union", "Union"),
]

MEMBER_KINDS: list[tuple[str, str]] = [
    ("method", "Method"),
    ("variable", "Variable"),
    ("define", "Define"),
    ("enumvalue", "Enum Value"),
    ("function", "Function"),
]

NAMESPACE_KINDS: list[tuple[str, str]] = [
    ("namespace", "Namespace"),
    ("package", "Package"),
    ("module", "Module"),
]

UNCLASSIFIED_KINDS: list[tuple[str, str]] = [
    ("primitive", "Primitive Type"),
    ("type_alias", "Type Alias"),
    ("type_parameter", "Type Parameter"),
]

# ---------------------------------------------------------------------------
# Composed node kinds
# ---------------------------------------------------------------------------

NODE_KINDS: list[tuple[str, str]] = (
    COMPOUND_KINDS + MEMBER_KINDS + NAMESPACE_KINDS + UNCLASSIFIED_KINDS
)
NODE_KIND_KEYS: set[str] = {k for k, _ in NODE_KINDS}

# ---------------------------------------------------------------------------
# Semantic groupings
# ---------------------------------------------------------------------------

TYPE_KINDS: set[str] = {
    "class", "struct", "template_class", "interface",
    "abstract_class", "enum", "enum_class", "union", "type_alias",
}
VALUE_KINDS: set[str] = {"method", "variable", "define", "enumvalue", "function"}

# ---------------------------------------------------------------------------
# Source provenance
# ---------------------------------------------------------------------------

SOURCE_TYPES: list[tuple[str, str]] = [
    ("compound", "Compound"),
    ("member", "Member"),
    ("namespace", "Namespace"),
]
SOURCE_TYPE_KEYS: set[str] = {k for k, _ in SOURCE_TYPES}

# ---------------------------------------------------------------------------
# Layers — where a node originates
# ---------------------------------------------------------------------------

LAYERS: list[str] = ["design", "as-built", "dependency"]

# ---------------------------------------------------------------------------
# Visibility / access specifiers
# ---------------------------------------------------------------------------

VISIBILITY_CHOICES: list[tuple[str, str]] = [
    ("public", "Public"),
    ("private", "Private"),
    ("protected", "Protected"),
]

# ---------------------------------------------------------------------------
# Predicates — lowercase names mapped to UPPER_SNAKE_CASE Neo4j rel types
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
    ("aggregates", "Whole-part relationship where the part can exist independently. "
     "Specify mechanism for container types (e.g., std::vector, std::list)"),
    ("composes", "Strong whole-part relationship where the part is owned by the whole"),
    ("depends_on", "One entity depends on another (e.g., for a header include)"),
    ("generalizes", "Inheritance / is-a relationship"),
    ("realizes", "A class implements/realizes an interface or contract"),
    ("references", "One entity holds a reference or pointer to another. "
     "Specify mechanism (e.g., std::unique_ptr, std::shared_ptr, raw_pointer, reference)"),
    ("invokes", "Weak association, signifying a caller-callee relationship"),
    ("has_argument", "A method accepts a parameter of the given type (method → type)"),
    ("returns", "A method returns a value of the given entity type (method → type)"),
    ("type_argument", "A template accepts a type argument at a given position"),
    ("template_param", "A template declares a type parameter slot"),
]

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
        "define": [
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
        "define": [
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

# ---------------------------------------------------------------------------
# Schema DDL — constraints and indexes for Neo4j
# ---------------------------------------------------------------------------

CONSTRAINTS_AND_INDEXES: list[str] = [
    # Uniqueness constraints
    "CREATE CONSTRAINT file_refid IF NOT EXISTS FOR (f:File) REQUIRE f.refid IS UNIQUE",
    # Use INDEX instead of CONSTRAINT for refid to allow design-layer nodes
    # (which have no refid) to coexist with as-built/dependency nodes.
    "CREATE INDEX namespace_refid IF NOT EXISTS FOR (n:Namespace) ON (n.refid)",
    "CREATE INDEX compound_refid IF NOT EXISTS FOR (c:Compound) ON (c.refid)",
    "CREATE INDEX member_refid IF NOT EXISTS FOR (m:Member) ON (m.refid)",
    # Lookup indexes
    "CREATE INDEX file_name IF NOT EXISTS FOR (f:File) ON (f.name)",
    "CREATE INDEX file_path IF NOT EXISTS FOR (f:File) ON (f.path)",
    "CREATE INDEX namespace_name IF NOT EXISTS FOR (n:Namespace) ON (n.name)",
    "CREATE INDEX compound_name IF NOT EXISTS FOR (c:Compound) ON (c.name)",
    "CREATE INDEX compound_qualified IF NOT EXISTS FOR (c:Compound) ON (c.qualified_name)",
    "CREATE INDEX compound_kind IF NOT EXISTS FOR (c:Compound) ON (c.kind)",
    "CREATE INDEX member_name IF NOT EXISTS FOR (m:Member) ON (m.name)",
    "CREATE INDEX member_qualified IF NOT EXISTS FOR (m:Member) ON (m.qualified_name)",
    "CREATE INDEX member_kind IF NOT EXISTS FOR (m:Member) ON (m.kind)",
    # Layer indexes
    "CREATE INDEX compound_layer IF NOT EXISTS FOR (c:Compound) ON (c.layer)",
    "CREATE INDEX member_layer IF NOT EXISTS FOR (m:Member) ON (m.layer)",
    "CREATE INDEX namespace_layer IF NOT EXISTS FOR (n:Namespace) ON (n.layer)",
    # Source provenance
    "CREATE INDEX file_source IF NOT EXISTS FOR (f:File) ON (f.source)",
    "CREATE INDEX compound_source IF NOT EXISTS FOR (c:Compound) ON (c.source)",
    "CREATE INDEX member_source IF NOT EXISTS FOR (m:Member) ON (m.source)",
    "CREATE INDEX namespace_source IF NOT EXISTS FOR (n:Namespace) ON (n.source)",
    # Full-text search
    "CREATE FULLTEXT INDEX doc_search IF NOT EXISTS FOR (n:Compound|Member) ON EACH [n.name, n.qualified_name, n.brief_description, n.detailed_description]",
]
```

- [ ] **Step 2: Commit codegraph changes**

```bash
cd /Users/danielnewman/dev/codegraph
git add src/codegraph/constants.py
git commit -m "feat: consolidate all graph constants, add (key,label) tuples, language specializations, semantic groupings"
```

---

### Task 2: Update codegraph/__init__.py exports

**Files:**
- Modify: `/Users/danielnewman/dev/codegraph/src/codegraph/__init__.py`

- [ ] **Step 1: Add new exports**

Replace the imports and `__all__` block:

```python
from codegraph.constants import (
    COMPOUND_KINDS,
    CONSTRAINTS_AND_INDEXES,
    DEFAULT_PREDICATES,
    LANGUAGE_SPECIALIZATIONS,
    LAYERS,
    MEMBER_KINDS,
    NAMESPACE_KINDS,
    NODE_KIND_KEYS,
    NODE_KINDS,
    PREDICATES,
    PREDICATE_TO_REL_TYPE,
    SOURCE_TYPE_KEYS,
    SOURCE_TYPES,
    SUPPORTED_LANGUAGES,
    TYPE_KINDS,
    UNCLASSIFIED_KINDS,
    VALUE_KINDS,
    VISIBILITY_CHOICES,
    valid_specializations,
)

__all__ = [
    # Nodes
    "CompoundNode",
    "FileNode",
    "MemberNode",
    "NamespaceNode",
    "ParameterNode",
    # Edges
    "CodebaseEdge",
    "PREDICATES",
    # Constants
    "COMPOUND_KINDS",
    "CONSTRAINTS_AND_INDEXES",
    "DEFAULT_PREDICATES",
    "LANGUAGE_SPECIALIZATIONS",
    "LAYERS",
    "MEMBER_KINDS",
    "NAMESPACE_KINDS",
    "NODE_KIND_KEYS",
    "NODE_KINDS",
    "PREDICATE_TO_REL_TYPE",
    "SOURCE_TYPE_KEYS",
    "SOURCE_TYPES",
    "SUPPORTED_LANGUAGES",
    "TYPE_KINDS",
    "UNCLASSIFIED_KINDS",
    "VALUE_KINDS",
    "VISIBILITY_CHOICES",
    "valid_specializations",
]
```

- [ ] **Step 2: Commit and reinstall**

```bash
cd /Users/danielnewman/dev/codegraph
git add src/codegraph/__init__.py
git commit -m "feat: export all new constants from codegraph package"
cd /Users/danielnewman/dev/ticketing_system
source .venv/bin/activate
pip install -e ../codegraph
```

- [ ] **Step 3: Verify import works**

```bash
cd /Users/danielnewman/dev/ticketing_system
source .venv/bin/activate
python -c "from codegraph.constants import NODE_KIND_KEYS, DEFAULT_PREDICATES, TYPE_KINDS, LANGUAGE_SPECIALIZATIONS; print('NODE_KIND_KEYS:', len(NODE_KIND_KEYS)); print('DEFAULT_PREDICATES:', len(DEFAULT_PREDICATES)); print('TYPE_KINDS:', TYPE_KINDS); print('LANGUAGES:', list(LANGUAGE_SPECIALIZATIONS.keys()))"
```

Expected: `NODE_KIND_KEYS: 16`, `DEFAULT_PREDICATES: 12`, `TYPE_KINDS` with 9 items, `LANGUAGES: ['cpp', 'python', 'javascript']`

---

### Task 3: Update backend/codebase/schemas.py

**Files:**
- Modify: `backend/codebase/schemas.py`

- [ ] **Step 1: Change import to codegraph and fix NODE_KINDS usage**

The import line changes and `NodeKind`/`Visibility` Literals need to extract keys from the new tuple format:

```python
# Old (lines 14, 20-22):
from backend.db.neo4j.models.constants import NODE_KINDS, VISIBILITY_CHOICES
...
NodeKind = Literal[tuple(NODE_KINDS)]
Visibility = Literal[tuple(VISIBILITY_CHOICES)]

# New:
from codegraph.constants import NODE_KIND_KEYS, VISIBILITY_CHOICES
...
NodeKind = Literal[tuple(NODE_KIND_KEYS)]
Visibility = Literal[tuple(k for k, _ in VISIBILITY_CHOICES)]
```

Also update the comment on lines 17-19 that says "flat string lists":

```python
# Derived from the canonical NODE_KIND_KEYS set so there is one place to
# add or remove kinds.
NodeKind = Literal[tuple(NODE_KIND_KEYS)]
Visibility = Literal[tuple(k for k, _ in VISIBILITY_CHOICES)]
```

- [ ] **Step 2: Commit**

```bash
git add backend/codebase/schemas.py
git commit -m "refactor: switch schemas.py to codegraph constants, use NODE_KIND_KEYS"
```

---

### Task 4: Update backend/requirements/services/persistence.py

**Files:**
- Modify: `backend/requirements/services/persistence.py`

- [ ] **Step 1: Change import**

```python
# Old (line 22):
from backend.db.neo4j.models.constants import COMPOUND_KINDS, MEMBER_KINDS, NAMESPACE_KINDS

# New:
from codegraph.constants import COMPOUND_KINDS, MEMBER_KINDS, NAMESPACE_KINDS
```

- [ ] **Step 2: Verify NO code changes needed** — `persistence.py` only passes these to a query builder that iterates them. Both flat lists and tuples iterate the same way in a `for kind in COMPOUND_KINDS` loop (only the first element matters).

```bash
grep -n "COMPOUND_KINDS\|MEMBER_KINDS\|NAMESPACE_KINDS" backend/requirements/services/persistence.py
```

- [ ] **Step 3: Commit**

```bash
git add backend/requirements/services/persistence.py
git commit -m "refactor: switch persistence.py to codegraph constants"
```

---

### Task 5: Update backend/db/neo4j/repositories/design.py

**Files:**
- Modify: `backend/db/neo4j/repositories/design.py`

- [ ] **Step 1: Change both imports (lines 19, 28)**

```python
# Old:
from backend.db.neo4j.models.constants import COMPOUND_KINDS, MEMBER_KINDS, NAMESPACE_KINDS
from backend.db.neo4j.repositories.constants import PREDICATE_TO_REL_TYPE

# New:
from codegraph.constants import COMPOUND_KINDS, MEMBER_KINDS, NAMESPACE_KINDS, PREDICATE_TO_REL_TYPE
```

- [ ] **Step 2: Verify usage** — `design.py` uses these in query construction. `COMPOUND_KINDS`/etc. are iterated for kind values; the tuple format doesn't change behavior. `PREDICATE_TO_REL_TYPE` is now the canonical version with `implements`.

```bash
grep -n "COMPOUND_KINDS\|MEMBER_KINDS\|NAMESPACE_KINDS\|PREDICATE_TO_REL_TYPE" backend/db/neo4j/repositories/design.py
```

- [ ] **Step 3: Commit**

```bash
git add backend/db/neo4j/repositories/design.py
git commit -m "refactor: switch design.py to codegraph constants"
```

---

### Task 6: Update ticketing_agent design files

**Files:**
- Modify: `backend/ticketing_agent/design/design_ontology.py`
- Modify: `backend/ticketing_agent/design/design_ontology_prompt.py`
- Modify: `backend/ticketing_agent/design/design_oo_prompt.py`

- [ ] **Step 1: Update design_ontology.py (lines 16-17, 52)**

```python
# Old:
from backend.db.neo4j.repositories.constants import DEFAULT_PREDICATES
from backend.db.neo4j.models.constants import NODE_KINDS

# New:
from codegraph.constants import DEFAULT_PREDICATES, NODE_KIND_KEYS
```

And on line 52, `sorted(NODE_KINDS)` becomes `sorted(NODE_KIND_KEYS)` since NODE_KINDS is now tuples:

```python
# Old:
node_kinds=", ".join(f'"{k}"' for k in sorted(NODE_KINDS)),

# New:
node_kinds=", ".join(f'"{k}"' for k in sorted(NODE_KIND_KEYS)),
```

- [ ] **Step 2: Update design_ontology_prompt.py (line 5)**

```python
# Old:
from backend.db.neo4j.models.constants import LANGUAGE_SPECIALIZATIONS

# New:
from codegraph.constants import LANGUAGE_SPECIALIZATIONS
```

- [ ] **Step 3: Update design_oo_prompt.py (line 6)**

```python
# Old:
from backend.db.neo4j.models.constants import LANGUAGE_SPECIALIZATIONS

# New:
from codegraph.constants import LANGUAGE_SPECIALIZATIONS
```

- [ ] **Step 4: Commit**

```bash
git add backend/ticketing_agent/design/design_ontology.py backend/ticketing_agent/design/design_ontology_prompt.py backend/ticketing_agent/design/design_oo_prompt.py
git commit -m "refactor: switch design agent files to codegraph constants"
```

---

### Task 7: Update test files

**Files:**
- Modify: `tests/test_codebase_graph_primitives.py`
- Modify: `tests/test_codebase_schemas.py`
- Modify: `tests/test_design_repository.py`

- [ ] **Step 1: Update test_codebase_graph_primitives.py**

Change all imports from `backend.db.neo4j.models.constants` to `codegraph.constants`. Replace `valid_specializations` import if present. Also fix `VISIBILITY_CHOICES` and `NODE_KINDS` membership checks:

```python
# All imports switch to:
from codegraph.constants import (
    COMPOUND_KINDS, MEMBER_KINDS, NAMESPACE_KINDS, NODE_KINDS,
    UNCLASSIFIED_KINDS, TYPE_KINDS, VALUE_KINDS, VISIBILITY_CHOICES,
    LAYERS, PREDICATES, PREDICATE_TO_REL_TYPE, valid_specializations,
    SUPPORTED_LANGUAGES,
)
```

Fix `set(NODE_KINDS)` assertion (line 29) — now NODE_KINDS and the four sub-lists are all tuples, so `set()` comparison still works correctly:

```python
assert set(NODE_KINDS) == set(COMPOUND_KINDS + MEMBER_KINDS + NAMESPACE_KINDS + UNCLASSIFIED_KINDS)
```

Fix `VISIBILITY_CHOICES` membership (lines 45-46) — VISIBILITY_CHOICES is now tuples:

```python
from codegraph.constants import VISIBILITY_CHOICES
assert ("public", "Public") in VISIBILITY_CHOICES
assert ("private", "Private") in VISIBILITY_CHOICES
```

- [ ] **Step 2: Update test_codebase_schemas.py**

Change imports and fix iteration over VISIBILITY_CHOICES and NODE_KINDS (now tuples):

```python
# Old imports:
from backend.db.neo4j.models.constants import NODE_KINDS
from backend.db.neo4j.models.constants import VISIBILITY_CHOICES
from backend.db.neo4j.models.constants import SOURCE_TYPES

# New:
from codegraph.constants import NODE_KIND_KEYS, VISIBILITY_CHOICES, SOURCE_TYPES
```

Fix `for kind_name in NODE_KINDS` (line 388):

```python
for kind_name in NODE_KIND_KEYS:
    assert kind_name in NodeKind.__args__, f"{kind_name} not in NodeKind Literal"
```

Fix `for vis_name in VISIBILITY_CHOICES` (line 396):

```python
for vis_key, _ in VISIBILITY_CHOICES:
    assert vis_key in Visibility.__args__, f"{vis_key} not in Visibility Literal"
```

- [ ] **Step 3: Update test_design_repository.py**

Change imports and fix NODE_KINDS membership checks:

```python
# Old:
from backend.db.neo4j.models.constants import PREDICATE_TO_REL_TYPE
from backend.db.neo4j.models.constants import DEFAULT_PREDICATES
from backend.db.neo4j.models.constants import NODE_KINDS

# New:
from codegraph.constants import PREDICATE_TO_REL_TYPE, DEFAULT_PREDICATES, NODE_KIND_KEYS
```

Fix `"class" in NODE_KINDS` assertions (lines 84-86):

```python
assert "class" in NODE_KIND_KEYS
assert "method" in NODE_KIND_KEYS
assert "namespace" in NODE_KIND_KEYS
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_codebase_graph_primitives.py tests/test_codebase_schemas.py tests/test_design_repository.py
git commit -m "refactor: switch test files to codegraph constants, fix tuple format assertions"
```

---

### Task 8: Delete old constants files

**Files:**
- Delete: `backend/db/neo4j/models/constants.py`
- Delete: `backend/db/neo4j/repositories/constants.py`

- [ ] **Step 1: Delete the files**

```bash
rm backend/db/neo4j/models/constants.py
rm backend/db/neo4j/repositories/constants.py
```

- [ ] **Step 2: Verify no broken imports remain**

```bash
rg "from backend\.db\.neo4j\.(models|repositories)\.constants" --type py
```

Expected: no output (all imports migrated).

- [ ] **Step 3: Commit**

```bash
git add backend/db/neo4j/models/constants.py backend/db/neo4j/repositories/constants.py
git commit -m "refactor: delete ticketing constants files, fully migrated to codegraph"
```

---

### Task 9: Run full test suite

- [ ] **Step 1: Run all tests**

```bash
cd /Users/danielnewman/dev/ticketing_system
source .venv/bin/activate
pytest -v
```

Expected: all tests pass.

- [ ] **Step 2: If any test fails, fix and re-run before proceeding**
