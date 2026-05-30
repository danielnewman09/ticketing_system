# Codegraph Constants Consolidation

**Date:** 2026-05-30
**Status:** approved

## Problem

Three files define overlapping/duplicate Neo4j codebase graph constants:

- `codegraph/constants.py` — shared library, canonical for core vocabulary
- `backend/db/neo4j/models/constants.py` — extends codegraph, adds ticketing concepts
- `backend/db/neo4j/repositories/constants.py` — independent duplicate with minor discrepancies

This causes:
- Duplicate PREDICATE_TO_REL_TYPE (repos version missing `implements`)
- Two different TYPE_KINDS sets (models has broader set; repos narrower)
- Two different SOURCE_TYPES sets (repos has extra `dependency` entry)
- Two identical copies of LANGUAGE_SPECIALIZATIONS and valid_specializations()
- Mixed formats: some flat lists, some (key, label) tuples

## Solution

Move all constants into `codegraph/constants.py` as the single source of truth.
Delete both ticketing constants files. Update all consumers.

## Detailed Design

### codegraph/constants.py — canonical shape

#### Subnode-type lists (source of truth; (key, Display) tuples)

```python
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
```

#### Composed node kinds

```python
NODE_KINDS: list[tuple[str, str]] = (
    COMPOUND_KINDS + MEMBER_KINDS + NAMESPACE_KINDS + UNCLASSIFIED_KINDS
)
NODE_KIND_KEYS: set[str] = {k for k, _ in NODE_KINDS}
```

#### Semantic groupings

```python
TYPE_KINDS: set[str] = {
    "class", "struct", "template_class", "interface",
    "abstract_class", "enum", "enum_class", "union", "type_alias",
}
VALUE_KINDS: set[str] = {"method", "variable", "define", "enumvalue", "function"}
```

#### Source provenance

```python
SOURCE_TYPES: list[tuple[str, str]] = [
    ("compound", "Compound"),
    ("member", "Member"),
    ("namespace", "Namespace"),
]
SOURCE_TYPE_KEYS: set[str] = {k for k, _ in SOURCE_TYPES}
```

#### Visibility

```python
VISIBILITY_CHOICES: list[tuple[str, str]] = [
    ("public", "Public"),
    ("private", "Private"),
    ("protected", "Protected"),
]
```

#### Predicates

```python
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
```

#### Language specializations

```python
LANGUAGE_SPECIALIZATIONS: dict[str, dict[str, list[str]]] = {
    "cpp": {
        "class": ["struct", "template_class", "abstract_class"],
        "method": ["virtual_method", "pure_virtual_method", "template_method",
                    "static_method", "const_method", "operator_overload"],
        "function": ["template_function"],
        "define": ["constexpr", "const"],
        "enum": ["enum_class"],
        "type_alias": ["using", "typedef"],
        "module": ["namespace"],
    },
    "python": {
        "class": ["dataclass", "namedtuple"],
        "method": ["classmethod", "staticmethod", "property",
                    "abstractmethod", "async_method"],
        "function": ["async_function", "generator", "decorator"],
        "interface": ["protocol", "abc"],
        "define": ["final"],
        "module": ["package"],
    },
    "javascript": {
        "class": [],
        "method": ["getter", "setter", "static_method", "async_method"],
        "function": ["arrow_function", "async_function", "generator"],
        "module": ["es_module", "commonjs_module"],
    },
}

SUPPORTED_LANGUAGES: set[str] = set(LANGUAGE_SPECIALIZATIONS.keys())


def valid_specializations(language: str, kind: str) -> set[str]:
    """Return the set of valid specializations for a language + kind."""
    lang_spec = LANGUAGE_SPECIALIZATIONS.get(language, {})
    return set(lang_spec.get(kind, []))
```

#### Layers and DDL (unchanged)

```python
LAYERS: list[str] = ["design", "as-built", "dependency"]

CONSTRAINTS_AND_INDEXES: list[str] = [
    # ... unchanged
]
```

### codegraph/__init__.py — updated exports

Add to `__all__` and re-export: `UNCLASSIFIED_KINDS`, `NODE_KIND_KEYS`, `TYPE_KINDS`, `VALUE_KINDS`, `SOURCE_TYPES`, `SOURCE_TYPE_KEYS`, `DEFAULT_PREDICATES`, `LANGUAGE_SPECIALIZATIONS`, `SUPPORTED_LANGUAGES`, `valid_specializations`.

### ticketing_system deletions

- `backend/db/neo4j/models/constants.py` — delete
- `backend/db/neo4j/repositories/constants.py` — delete

### ticketing_system import updates

All consumers switch to `from codegraph.constants import ...`. Affected files:

| File | Current import source | Imports used |
|------|----------------------|--------------|
| `backend/codebase/schemas.py` | `models.constants` | `NODE_KINDS`, `VISIBILITY_CHOICES` |
| `backend/requirements/services/persistence.py` | `models.constants` | `COMPOUND_KINDS`, `MEMBER_KINDS`, `NAMESPACE_KINDS` |
| `backend/db/neo4j/repositories/design.py` | `models.constants` + `repos.constants` | `COMPOUND_KINDS`, `MEMBER_KINDS`, `NAMESPACE_KINDS`, `PREDICATE_TO_REL_TYPE` |
| `backend/ticketing_agent/design/design_ontology.py` | `repos.constants` + `models.constants` | `DEFAULT_PREDICATES`, `NODE_KINDS` |
| `backend/ticketing_agent/design/design_ontology_prompt.py` | `models.constants` | `LANGUAGE_SPECIALIZATIONS` |
| `backend/ticketing_agent/design/design_oo_prompt.py` | `models.constants` | `LANGUAGE_SPECIALIZATIONS` |
| `tests/test_codebase_graph_primitives.py` | `models.constants` | `COMPOUND_KINDS`, `MEMBER_KINDS`, `NAMESPACE_KINDS`, `NODE_KINDS`, `UNCLASSIFIED_KINDS`, `TYPE_KINDS`, `VALUE_KINDS`, `VISIBILITY_CHOICES`, `LAYERS`, `PREDICATES`, `PREDICATE_TO_REL_TYPE`, `valid_specializations`, `SUPPORTED_LANGUAGES` |
| `tests/test_codebase_schemas.py` | `models.constants` | `NODE_KINDS`, `VISIBILITY_CHOICES`, `SOURCE_TYPES` |
| `tests/test_design_repository.py` | `models.constants` | `PREDICATE_TO_REL_TYPE`, `DEFAULT_PREDICATES`, `NODE_KINDS` |

### Test updates

Tests that assert on specific import paths update to `codegraph.constants`. The test for `UNCLASSIFIED_KINDS` composition (`test_codebase_graph_primitives.py:28-29`) remains valid since the concept stays.

Tests that assert on `PREDICATE_TO_REL_TYPE` will now include `implements` (which was missing from the repos copy). This is a correctness fix, not a regression.

## Migration approach

1. Update `codegraph/constants.py` with all new constants
2. Update `codegraph/__init__.py` exports
3. Reinstall codegraph: `pip install -e ../codegraph`
4. Update all ticketing consumers to import from `codegraph.constants`
5. Delete `backend/db/neo4j/models/constants.py` and `backend/db/neo4j/repositories/constants.py`
6. Run tests: `pytest`
