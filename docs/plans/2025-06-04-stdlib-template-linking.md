# Stdlib Template Linking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Link design methods to their stdlib type dependencies through structured type extraction and alias resolution, enabling `has_argument`/`returns`/`TYPE_ARGUMENT` edges from methods to cppreference nodes like `std::basic_string`.

**Architecture:** Replace the regex-based type extraction in `map_to_ontology.py` with a recursive-descent `TypeRef` parser. Add an alias registry that resolves `std::string` → `std::basic_string`. Add `type_argument` and `template_param` predicates and a `type_parameter` node kind. Update graph rendering to show template stereotypes, alias display names, and `TYPE_ARGUMENT` edge styling.

**Tech Stack:** Python 3.12+, SQLAlchemy 2.0, Neo4j, Pydantic, NiceGUI/Cytoscape.js

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/codebase/schemas.py` | `TypeRef` dataclass, `OntologyTripleSchema` gains `position`/`name`/`display_name` fields |
| `backend/codebase/type_parser.py` | **New.** Recursive-descent type signature parser producing `TypeRef` trees |
| `backend/db/models/ontology.py` | Add `type_parameter` to `NODE_KINDS`, `type_argument`+`template_param` to predicates |
| `backend/ticketing_agent/design/map_to_ontology.py` | Replace `_TYPE_EXTRACT_RE`/`_add_depends_from_type` with `TypeRef`-based resolution. Create `TYPE_ARGUMENT` edges. Use alias registry. |
| `backend/ticketing_agent/design/container_lookup.py` | Add `build_alias_lookup()` function (Neo4j typedef query + hardcoded fallback). Extend existing `seed_container_lookup`. |
| `backend/db/neo4j/queries/graph.py` | Include `TYPE_ARGUMENT`/`TEMPLATE_PARAM` edges in `fetch_design_graph`. Return `display_name`/`position`/`name` edge properties. |
| `backend/graph/transforms.py` | Template node stereotype, alias display in member lines, `TYPE_ARGUMENT` edge color, `type_parameter` node rendering, stdlib header indicator |
| `backend/graph/builders.py` | Pass through `display_name`, edge `position`/`name` from Neo4j data to Cytoscape dicts |
| `frontend/data/ontology.py` | Handle new edge types in graph data flow |
| `tests/test_type_parser.py` | **New.** Tests for the `TypeRef` parser |
| `tests/test_map_to_ontology.py` | Add tests for alias resolution, `TYPE_ARGUMENT` edge creation, `std::string` linking |
| `tests/test_container_lookup.py` | Add tests for `build_alias_lookup()` |

---

### Task 1: Add TypeRef dataclass and new predicates/kinds

**Files:**
- Modify: `backend/codebase/schemas.py`
- Modify: `backend/db/models/ontology.py`

- [ ] **Step 1: Add `TypeRef` dataclass to `schemas.py`**

Add the `TypeRef` dataclass after the existing schema classes, before `DesignSchema`:

```python
from dataclasses import dataclass

@dataclass
class TypeRef:
    """Structured reference to a type extracted from a type signature string.

    Handles qualified names (std::vector), template nesting
    (std::vector<std::string>), and builtin detection (int, double, void).
    """
    name: str                       # "std::vector" or "Calculator"
    template_args: list["TypeRef"]  # [] for non-templates, or nested TypeRefs
    is_builtin: bool                # True for int, double, void, etc.
    original_text: str              # "std::vector<const std::string&>"
    qualifiers: list[str]           # ["const", "&", "*"] etc.
```

- [ ] **Step 2: Add `position`, `name`, `display_name` to `OntologyTripleSchema`**

In `backend/codebase/schemas.py`, update `OntologyTripleSchema`:

```python
class OntologyTripleSchema(BaseModel):
    subject_qualified_name: str
    predicate: str  # Must match a Predicate.name in the database
    object_qualified_name: str
    mechanism: str = ""  # Container/smart-ptr type for aggregates/references
    position: int | None = None  # For TYPE_ARGUMENT: parameter position (0-based)
    name: str = ""  # For TEMPLATE_PARAM: parameter name (e.g. "T")
    display_name: str = ""  # Alias display name (e.g. "std::string" for std::basic_string edge)
```

- [ ] **Step 3: Add `type_parameter` to `NODE_KINDS` and new predicates**

In `backend/db/models/ontology.py`, update `NODE_KINDS`:

```python
NODE_KINDS = [
    ("attribute", "Attribute"),
    ("class", "Class"),
    ("constant", "Constant"),
    ("enum", "Enum"),
    ("enum_value", "Enum Value"),
    ("function", "Function"),
    ("interface", "Interface"),
    ("method", "Method"),
    ("module", "Module"),
    ("primitive", "Primitive Type"),
    ("type_alias", "Type Alias"),
    ("type_parameter", "Type Parameter"),  # NEW
]
```

Update `Predicate.DEFAULT_PREDICATES`:

```python
DEFAULT_PREDICATES = [
    ("associates", "General association between two entities"),
    ("aggregates", "Whole-part relationship where the part can exist independently"),
    ("composes", "Strong whole-part relationship where the part is owned by the whole"),
    ("depends_on", "One entity depends on another"),
    ("generalizes", "Inheritance / is-a relationship"),
    ("realizes", "A class implements/realizes an interface or contract"),
    ("invokes", "Weak association, signifying a caller-callee relationship"),
    ("has_argument", "A method accepts a parameter of the given type"),
    ("returns", "A method returns a value of the given entity type"),
    ("type_argument", "A template accepts a type argument at a given position"),
    ("template_param", "A template declares a type parameter slot"),
]
```

- [ ] **Step 4: Run existing tests to verify nothing broke**

Run: `cd /Users/danielnewman/dev/ticketing_system && source .venv/bin/activate && pytest tests/test_ontology_models.py tests/test_codebase_schemas.py tests/test_map_to_ontology.py tests/test_container_mechanism.py -v`

Expected: All existing tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/codebase/schemas.py backend/db/models/ontology.py
git commit -m "feat: add TypeRef dataclass, type_parameter kind, and type_argument/template_param predicates"
```

---

### Task 2: Build the type signature parser

**Files:**
- Create: `backend/codebase/type_parser.py`
- Create: `tests/test_type_parser.py`

- [ ] **Step 1: Write test file for the type parser**

Create `tests/test_type_parser.py`:

```python
"""Tests for the type signature parser (TypeRef extraction)."""

import pytest
from backend.codebase.type_parser import parse_type_refs, TypeRef


class TestParseSimpleTypes:
    def test_simple_class_name(self):
        refs = parse_type_refs("Calculator")
        assert len(refs) == 1
        assert refs[0].name == "Calculator"
        assert refs[0].template_args == []
        assert refs[0].is_builtin is False

    def test_qualified_name(self):
        refs = parse_type_refs("std::vector")
        assert len(refs) == 1
        assert refs[0].name == "std::vector"
        assert refs[0].template_args == []
        assert refs[0].is_builtin is False

    def test_builtin_int(self):
        refs = parse_type_refs("int")
        assert len(refs) == 1
        assert refs[0].name == "int"
        assert refs[0].is_builtin is True

    def test_builtin_double(self):
        refs = parse_type_refs("double")
        assert len(refs) == 1
        assert refs[0].name == "double"
        assert refs[0].is_builtin is True

    def test_builtin_void(self):
        refs = parse_type_refs("void")
        assert len(refs) == 0  # void is not a dependency

    def test_builtin_std_string(self):
        refs = parse_type_refs("std::string")
        assert len(refs) == 1
        assert refs[0].name == "std::string"
        assert refs[0].is_builtin is False  # not a primitive; it's a dependency


class TestParseTemplateTypes:
    def test_single_template_arg(self):
        refs = parse_type_refs("std::vector<std::string>")
        assert len(refs) == 2
        assert refs[0].name == "std::vector"
        assert len(refs[0].template_args) == 1
        assert refs[0].template_args[0].name == "std::string"
        assert refs[1].name == "std::string"

    def test_two_template_args(self):
        refs = parse_type_refs("std::map<std::string, double>")
        assert len(refs) == 3
        assert refs[0].name == "std::map"
        assert len(refs[0].template_args) == 2
        assert refs[0].template_args[0].name == "std::string"
        assert refs[0].template_args[1].name == "double"
        assert refs[0].template_args[1].is_builtin is True
        # The flattened list also has the inner refs
        assert refs[1].name == "std::string"
        assert refs[2].name == "double"

    def test_nested_template(self):
        refs = parse_type_refs("std::vector<std::map<std::string, double>>")
        assert len(refs) == 4
        assert refs[0].name == "std::vector"
        assert refs[0].template_args[0].name == "std::map"
        assert refs[0].template_args[0].template_args[0].name == "std::string"


class TestParseQualifiedTypes:
    def test_method_signature(self):
        refs = parse_type_refs("const std::string& operand1, const std::string& operand2")
        string_refs = [r for r in refs if r.name == "std::string"]
        assert len(string_refs) == 2

    def test_return_type_with_template(self):
        refs = parse_type_refs("std::vector<std::string>")
        assert refs[0].name == "std::vector"
        assert refs[0].template_args[0].name == "std::string"

    def test_pointer_type(self):
        refs = parse_type_refs("Fl_Output*")
        assert len(refs) == 1
        assert refs[0].name == "Fl_Output"

    def test_const_ref(self):
        refs = parse_type_refs("const CalculationResult&")
        assert len(refs) == 1
        assert refs[0].name == "CalculationResult"

    def test_ignores_void(self):
        refs = parse_type_refs("void")
        assert len(refs) == 0


class TestParseMethodArgsstring:
    def test_argsstring_multiple_params(self):
        refs = parse_type_refs("(const std::string& operand1, const std::string& operand2)")
        string_refs = [r for r in refs if r.name == "std::string"]
        assert len(string_refs) == 2

    def test_no_params(self):
        refs = parse_type_refs("()")
        assert len(refs) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_type_parser.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'backend.codebase.type_parser'`

- [ ] **Step 3: Implement the type parser**

Create `backend/codebase/type_parser.py`:

```python
"""Recursive-descent parser for C++ type signatures.

Extracts TypeRef structures from type strings like:
  "const std::vector<std::string>&"
  "std::map<std::string, double>"
  "CalculationResult"
  "(const std::string& operand1, const std::string& operand2)"

Handles qualified names, template nesting, const/ref/pointer qualifiers,
and builtin type detection.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class TypeRef:
    """Structured reference to a type extracted from a type signature."""

    name: str  # "std::vector" or "Calculator"
    template_args: list[TypeRef] = field(default_factory=list)
    is_builtin: bool = False  # True for int, double, void, etc.
    original_text: str = ""  # "std::vector<const std::string&>"
    qualifiers: list[str] = field(default_factory=list)  # ["const", "&", "*"]

    @property
    def resolved_name(self) -> str:
        """The bare type name without qualifiers or template args."""
        return self.name


# C/C++ builtin types that are not dependency targets.
_BUILTIN_TYPES = frozenset({
    "void", "bool", "int", "double", "float", "char", "long", "short",
    "unsigned", "signed", "size_t", "uint8_t", "uint16_t", "uint32_t",
    "uint64_t", "int8_t", "int16_t", "int32_t", "int64_t",
    "auto", "nullptr_t",
})

# Keywords and qualifiers to skip during type extraction.
_SKIP_TOKENS = frozenset({
    "const", "volatile", "mutable", "constexpr", "static",
    "inline", "virtual", "explicit", "noexcept", "override",
    "final", "register", "extern", "typename",
})

# Regex for tokenizing C++ type strings.
_TOKEN_RE = re.compile(
    r"""(::)           # scope resolution
      | ([a-zA-Z_]\w*) # identifier
      | (<)            # template open
      | (>)            # template close
      | (,)            # comma
      | (\&)           # reference
      | (\*)           # pointer
      | (\.\.\.)       # variadic
    """,
    re.VERBOSE,
)


def _tokenize(text: str) -> list[str]:
    """Tokenize a C++ type string into meaningful tokens."""
    tokens = []
    for m in _TOKEN_RE.finditer(text):
        token = m.group(0)
        if token not in _SKIP_TOKENS:
            tokens.append(token)
    return tokens


def _parse_type_ref(tokens: list[str], pos: int) -> tuple[TypeRef | None, int]:
    """Parse a single type reference starting at position pos.

    Returns (TypeRef or None, next_position).
    Returns None if no meaningful type was found (e.g., void, bare commas).
    """
    if pos >= len(tokens):
        return None, pos

    qualifiers: list[str] = []
    name_parts: list[str] = []

    # Parse qualified name: [namespace::] Name [:: Name]*
    i = pos
    # Collect name parts and ::
    got_name = False
    while i < len(tokens):
        if tokens[i] == "::":
            if got_name:
                # This :: is a scope separator after a name
                got_name = False
            i += 1
            continue
        elif tokens[i] in ("&", "*"):
            qualifiers.append(tokens[i])
            i += 1
            continue
        elif tokens[i] == "<":
            # Template arguments follow
            break
        elif tokens[i] == ",":
            # End of this type in a parameter list
            break
        elif tokens[i] == ">":
            # End of template args
            break
        elif tokens[i] == "...":
            i += 1
            continue
        else:
            # It's an identifier
            name_parts.append(tokens[i])
            got_name = True
            i += 1

    if not name_parts:
        return None, i

    full_name = "::".join(name_parts)

    # Check for void — not a dependency
    is_void = full_name == "void"

    # Check for builtin/primitive types
    is_builtin = full_name in _BUILTIN_TYPES

    # Parse template arguments if present
    template_args: list[TypeRef] = []
    if i < len(tokens) and tokens[i] == "<":
        i += 1  # skip <
        while i < len(tokens) and tokens[i] != ">":
            arg_ref, new_i = _parse_type_ref(tokens, i)
            if arg_ref is not None:
                template_args.append(arg_ref)
            i = new_i
            # Skip commas between template args
            if i < len(tokens) and tokens[i] == ",":
                i += 1
        if i < len(tokens) and tokens[i] == ">":
            i += 1  # skip >

    if is_void:
        return None, i

    original = ""
    return TypeRef(
        name=full_name,
        template_args=template_args,
        is_builtin=is_builtin,
        original_text=original,
        qualifiers=qualifiers,
    ), i


def parse_type_refs(text: str) -> list[TypeRef]:
    """Parse all type references from a C++ type signature string.

    Returns a flat list of all TypeRefs found, including nested template args.
    The first TypeRef is the outermost type; subsequent entries are inner types
    (template arguments) in depth-first order.

    Examples:
        "CalculationResult" → [TypeRef(name="CalculationResult")]
        "std::vector<std::string>" → [TypeRef(name="std::vector", template_args=[...]), TypeRef(name="std::string")]
        "const std::string&" → [TypeRef(name="std::string")]
        "(const std::string& a, double b)" → [TypeRef(name="std::string"), TypeRef(name="double")]
    """
    if not text or not text.strip():
        return []

    tokens = _tokenize(text)
    if not tokens:
        return []

    # Strip surrounding parens (method argument lists)
    cleaned = text.strip()
    if cleaned.startswith("(") and cleaned.endswith(")"):
        pass  # tokenizer handles it

    refs: list[TypeRef] = []
    i = 0
    while i < len(tokens):
        ref, new_i = _parse_type_ref(tokens, i)
        if ref is not None:
            ref.original_text = text
            refs.append(ref)
            # Also flatten template args into the result list
            for arg in ref.template_args:
                arg.original_text = text
                refs.append(arg)
                refs.extend(_flatten_template_args(arg))
        i = new_i
        # Skip commas between parameter types
        while i < len(tokens) and tokens[i] == ",":
            i += 1

    return refs


def _flatten_template_args(ref: TypeRef) -> list[TypeRef]:
    """Recursively flatten nested template args into a flat list."""
    result: list[TypeRef] = []
    for arg in ref.template_args:
        result.append(arg)
        result.extend(_flatten_template_args(arg))
    return result
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_type_parser.py -v`

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/codebase/type_parser.py tests/test_type_parser.py
git commit -m "feat: add TypeRef parser for C++ type signature extraction"
```

---

### Task 3: Build the alias registry

**Files:**
- Modify: `backend/ticketing_agent/design/container_lookup.py`
- Modify: `tests/test_container_lookup.py`

- [ ] **Step 1: Write failing tests for `build_alias_lookup`**

Add to `tests/test_container_lookup.py`:

```python
class TestBuildAliasLookup:
    def test_returns_std_string_alias(self):
        from backend.ticketing_agent.design.container_lookup import build_alias_lookup
        mock_session = MagicMock()
        # Simulate that Neo4j has no type_alias members for std::string
        mock_session.run.return_value = []
        result = build_alias_lookup(mock_session)
        # Fallback map should include std::string → std::basic_string
        assert result.get("std::string") == "std::basic_string"
        assert result.get("std::wstring") == "std::basic_string"
        assert result.get("std::string_view") == "std::basic_string_view"

    def test_neo4j_aliases_merge_with_fallback(self):
        from backend.ticketing_agent.design.container_lookup import build_alias_lookup
        mock_session = MagicMock()
        # Simulate Neo4j returning a type_alias for std::string
        mock_session.run.return_value = [
            {"alias_name": "std::string", "qualified_name": "std::basic_string"},
        ]
        result = build_alias_lookup(mock_session)
        # Neo4j result should be present
        assert result.get("std::string") == "std::basic_string"
        # Fallback should still be present for wstring
        assert result.get("std::wstring") == "std::basic_string"

    def test_direct_names_not_in_alias_map(self):
        from backend.ticketing_agent.design.container_lookup import build_alias_lookup
        mock_session = MagicMock()
        mock_session.run.return_value = []
        result = build_alias_lookup(mock_session)
        # std::vector is not an alias — it IS std::vector
        assert "std::vector" not in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_container_lookup.py::TestBuildAliasLookup -v`

Expected: FAIL — `ImportError: cannot import name 'build_alias_lookup'`

- [ ] **Step 3: Implement `build_alias_lookup` in `container_lookup.py`**

Add to `backend/ticketing_agent/design/container_lookup.py`:

```python
# Hardcoded fallback alias map for common C++ typedefs that cppreference
# may not index as type_alias members.
_STD_ALIAS_MAP: dict[str, str] = {
    "std::string": "std::basic_string",
    "std::wstring": "std::basic_string",
    "std::u16string": "std::basic_string",
    "std::u32string": "std::basic_string",
    "std::string_view": "std::basic_string_view",
    "std::wstring_view": "std::basic_string_view",
    "std::u16string_view": "std::basic_string_view",
    "std::u32string_view": "std::basic_string_view",
}


def build_alias_lookup(neo4j_session) -> dict[str, str]:
    """Build an alias map from developer-friendly type names to their
    underlying cppreference qualified names.

    Queries Neo4j for type_alias members from the cppreference data,
    then augments with a hardcoded fallback for common C++ typedefs.

    Args:
        neo4j_session: An active Neo4j session for querying.

    Returns:
        Dict mapping alias names to resolved qualified names.
        E.g. {"std::string": "std::basic_string", ...}
    """
    alias_map: dict[str, str] = dict(_STD_ALIAS_MAP)

    try:
        result = neo4j_session.run(
            "MATCH (m:Member {source: 'cppreference', kind: 'typedef'}) "
            "RETURN m.qualified_name AS qn, m.name AS name"
        )
        for record in result:
            qn = record["qn"]
            name = record["name"]
            if qn and name:
                # The member name (e.g. "string") in the std:: namespace
                # is an alias for its parent class (qualified name)
                # If it starts with std::, add as-is
                if qn.startswith("std::"):
                    alias_map[qn] = qn.rsplit("::", 1)[0] + "::" + name if "::" in qn else name
    except Exception:
        log.warning("Failed to query Neo4j for type aliases", exc_info=True)

    return alias_map
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_container_lookup.py::TestBuildAliasLookup -v`

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/ticketing_agent/design/container_lookup.py tests/test_container_lookup.py
git commit -m "feat: add build_alias_lookup for std::string → std::basic_string resolution"
```

---

### Task 4: Replace type extraction in `map_to_ontology.py` with TypeRef parser + alias resolution

**Files:**
- Modify: `backend/ticketing_agent/design/map_to_ontology.py`
- Modify: `tests/test_map_to_ontology.py`

This is the core change — replacing `_TYPE_EXTRACT_RE` and `_add_depends_from_type` with the TypeRef pipeline.

- [ ] **Step 1: Write failing tests for std::string linking and TYPE_ARGUMENT edges**

Add to `tests/test_map_to_ontology.py`:

```python
from backend.codebase.schemas import MethodSchema


class TestStdlibTypeLinking:
    """Test that design methods link to stdlib dependency nodes via
    has_argument/returns/TYPE_ARGUMENT edges."""

    def test_method_with_std_string_creates_has_argument_edge(self):
        """std::string in method args → has_argument edge to std::basic_string."""
        oo = OODesignSchema(
            modules=["calc"],
            classes=[
                ClassSchema(
                    name="Calculator",
                    module="calc",
                    attributes=[],
                    methods=[
                        MethodSchema(
                            name="add",
                            visibility="public",
                            parameters=["const std::string& operand1", "const std::string& operand2"],
                            return_type="CalculationResult",
                        ),
                    ],
                ),
            ],
        )
        dep_lookup = {"std::basic_string": "std::basic_string"}
        alias_lookup = {"std::string": "std::basic_string"}
        result = map_oo_to_ontology(
            oo,
            dependency_lookup=dep_lookup,
            alias_lookup=alias_lookup,
        )

        # Should have has_argument edges from add to std::basic_string
        has_arg = [
            t for t in result.triples
            if t.predicate == "has_argument"
            and t.object_qualified_name == "std::basic_string"
        ]
        assert len(has_arg) >= 1, f"Expected has_argument edge to std::basic_string, got: {[t.object_qualified_name for t in result.triples if t.predicate == 'has_argument']}"

        # The edge should carry display_name "std::string"
        string_edges = [t for t in result.triples if t.object_qualified_name == "std::basic_string" and t.display_name == "std::string"]
        assert len(string_edges) >= 1, "Expected display_name='std::string' on edge to std::basic_string"

    def test_method_returning_std_vector_creates_type_argument_edge(self):
        """std::vector<std::string> in return type → returns edge to std::vector
        + TYPE_ARGUMENT edge from std::vector to std::basic_string."""
        oo = OODesignSchema(
            modules=["calc"],
            classes=[
                ClassSchema(
                    name="Parser",
                    module="calc",
                    attributes=[],
                    methods=[
                        MethodSchema(
                            name="parse",
                            visibility="public",
                            parameters=["const std::string& expr"],
                            return_type="std::vector<std::string>",
                        ),
                    ],
                ),
            ],
        )
        dep_lookup = {
            "std::basic_string": "std::basic_string",
            "std::vector": "std::vector",
        }
        alias_lookup = {"std::string": "std::basic_string"}
        result = map_oo_to_ontology(
            oo,
            dependency_lookup=dep_lookup,
            alias_lookup=alias_lookup,
        )

        # Should have a returns edge from parse to std::vector
        ret_edges = [
            t for t in result.triples
            if t.predicate == "returns"
            and t.subject_qualified_name == "calc::Parser::parse"
            and t.object_qualified_name == "std::vector"
        ]
        assert len(ret_edges) == 1

        # Should have TYPE_ARGUMENT edge from std::vector to std::basic_string
        type_arg_edges = [
            t for t in result.triples
            if t.predicate == "type_argument"
            and t.object_qualified_name == "std::basic_string"
        ]
        assert len(type_arg_edges) >= 1, f"Expected TYPE_ARGUMENT edge to std::basic_string"

        # The TYPE_ARGUMENT edge should have position=0
        for edge in type_arg_edges:
            if edge.subject_qualified_name == "std::vector":
                assert edge.position == 0


class TestExistingBehaviorPreserved:
    """Ensure that existing dependency resolution still works after the refactoring."""

    def test_design_internal_has_argument_still_works(self):
        """A has_argument edge to a design-internal type should still be created."""
        oo = OODesignSchema(
            modules=["calc"],
            classes=[
                ClassSchema(
                    name="Calculator",
                    module="calc",
                    attributes=[],
                    methods=[
                        MethodSchema(
                            name="add",
                            visibility="public",
                            parameters=["const CalculationResult& result"],
                            return_type="CalculationResult",
                        ),
                    ],
                ),
            ],
        )
        result = map_oo_to_ontology(oo)
        has_arg = [
            t for t in result.triples
            if t.predicate == "has_argument"
            and t.object_qualified_name == "calc::CalculationResult"
        ]
        assert len(has_arg) == 1

    def test_depends_on_from_attribute_type_still_works(self):
        """An attribute with a dependency type should still create depends_on."""
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
        result = map_oo_to_ontology(oo, dependency_lookup=dep_lookup)
        dep_triples = [
            t for t in result.triples
            if t.predicate == "depends_on"
            and t.subject_qualified_name == "ui::Calculator"
            and t.object_qualified_name == "Fl_Output"
        ]
        assert len(dep_triples) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_map_to_ontology.py::TestStdlibTypeLinking -v`

Expected: FAIL — `TypeError: map_oo_to_ontology() got an unexpected keyword argument 'alias_lookup'`

- [ ] **Step 3: Refactor `map_to_ontology.py` to accept and use `alias_lookup`, replace regex with TypeRef parser**

In `map_to_ontology.py`, make these changes:

1. Add `alias_lookup` parameter to `map_oo_to_ontology()`:
```python
def map_oo_to_ontology(
    oo: OODesignSchema,
    component_id: int | None = None,
    prior_class_lookup: dict[str, str] | None = None,
    component_namespace: str = "",
    dependency_lookup: dict[str, str] | None = None,
    alias_lookup: dict[str, str] | None = None,
) -> DesignSchema:
```

2. Import `TypeRef` and `parse_type_refs` from `backend.codebase.type_parser`.

3. Replace `_TYPE_EXTRACT_RE` usage with `parse_type_refs()`.

4. Replace `_add_depends_from_type` with a new function `_resolve_type_refs` that:
   - Calls `parse_type_refs` on each type signature
   - For each resolved `TypeRef`:
     - Resolves aliases via `alias_lookup`
     - Checks `class_lookup` (design-internal) → creates `has_argument`/`returns`
     - Checks `dep_lookup` (cppreference) → creates `has_argument`/`returns` with `display_name`
     - For template args: creates `TYPE_ARGUMENT` edges from outer template to inner types with `position`

5. Remove `_TYPE_EXTRACT_RE`, `_add_depends_from_type`, and `_FALLBACK_CONTAINERS` since they're replaced by the TypeRef pipeline.

The key integration point is replacing the loops around attribute types, method parameters, and method return types. Instead of the regex-based extraction, call `_resolve_type_refs` for each type string. For attributes, also create `TYPE_ARGUMENT` edges for template type arguments found in the attribute's type.

Here is the new `_resolve_type_refs` function:

```python
def _resolve_type_refs(
    type_text: str,
    subject_qname: str,
    predicate: str,
    class_lookup: dict[str, str],
    dep_lookup: dict[str, str],
    alias_lookup: dict[str, str],
    nodes: list[OntologyNodeSchema],
    triples: list[OntologyTripleSchema],
    node_index: dict[str, int],
    existing_depends: set[tuple[str, str]],
) -> None:
    """Parse type_text and create edges from subject to resolved types.

    For simple types: creates subject --predicate--> resolved_type edges.
    For template types: also creates TYPE_ARGUMENT edges from the outer
    template to each inner type argument.

    Uses alias_lookup to resolve aliases like std::string -> std::basic_string.
    Sets display_name on edges where an alias was resolved.
    """
    from backend.codebase.type_parser import parse_type_refs

    refs = parse_type_refs(type_text)
    for ref in refs:
        resolved_name = _resolve_type_name(ref.name, class_lookup, dep_lookup, alias_lookup)
        if resolved_name is None:
            continue  # Void or unrecognized type

        # Determine if this was an alias resolution
        resolved_display = ""
        if ref.name in alias_lookup and alias_lookup[ref.name] != ref.name:
            resolved_display = ref.name  # Show the alias name in the graph

        # Create the subject --predicate--> object edge
        idx = _add_triple(subject_qname, predicate, resolved_name, triples)
        if resolved_display:
            triples[idx].display_name = resolved_display

        # For template types, also create TYPE_ARGUMENT edges
        for pos, arg_ref in enumerate(ref.template_args):
            arg_resolved = _resolve_type_name(arg_ref.name, class_lookup, dep_lookup, alias_lookup)
            if arg_resolved is None:
                continue
            arg_display = ""
            if arg_ref.name in alias_lookup and alias_lookup[arg_ref.name] != arg_ref.name:
                arg_display = arg_ref.name
            _add_type_argument_edge(resolved_name, arg_resolved, pos, arg_display, triples)

        # Also create depends_on for dependency types
        if ref.name not in class_lookup and ref.name in dep_lookup:
            key = (subject_qname, resolved_name)
            if key not in existing_depends:
                _add_triple(subject_qname, "depends_on", resolved_name, triples)
                existing_depends.add(key)


def _resolve_type_name(
    name: str,
    class_lookup: dict[str, str],
    dep_lookup: dict[str, str],
    alias_lookup: dict[str, str],
) -> str | None:
    """Resolve a type name through class_lookup, dep_lookup, and alias_lookup.

    Returns the qualified name if resolved, None if the type should be skipped
    (e.g., void or unrecognized types).
    """
    # Check alias first (e.g., std::string -> std::basic_string)
    resolved = alias_lookup.get(name, name)

    # Check design-internal
    if resolved in class_lookup:
        return class_lookup[resolved]

    # Check dependency lookup
    if resolved in dep_lookup:
        qname = dep_lookup[resolved]
        # Ensure dependency stub node exists
        return qname

    # Also check by bare name (without namespace)
    if "::" in name:
        bare = name.rsplit("::", 1)[-1]
        bare_alias = alias_lookup.get(name, name)
        if bare_alias in class_lookup:
            return class_lookup[bare_alias]
        if bare_alias in dep_lookup:
            return dep_lookup[bare_alias]

    return None


def _add_type_argument_edge(
    template_qname: str,
    arg_qname: str,
    position: int,
    display_name: str,
    triples: list[OntologyTripleSchema],
) -> int:
    """Create a TYPE_ARGUMENT edge from a template to its type argument."""
    t = OntologyTripleSchema(
        subject_qualified_name=template_qname,
        predicate="type_argument",
        object_qualified_name=arg_qname,
        position=position,
        display_name=display_name,
    )
    triples.append(t)
    return len(triples) - 1
```

Then replace the existing loops in `map_oo_to_ontology` that iterate over method parameters and return types. Instead of:

```python
for param in method.parameters:
    for match in _TYPE_EXTRACT_RE.finditer(param):
        ...
```

Use:

```python
for param in method.parameters:
    _resolve_type_refs(
        param, method_qname, "has_argument",
        class_lookup, dep_lookup, alias_lookup,
        nodes, triples, node_index, _existing_depends,
    )
```

And similarly for `method.return_type` with `"returns"` instead of `"has_argument"`, and for `attr.type_name` with appropriate predicate.

Keep the existing `_resolve_ref` function for association targets and inheritance targets (those still use bare class names, not type signatures).

- [ ] **Step 4: Run all map_to_ontology tests**

Run: `pytest tests/test_map_to_ontology.py -v`

Expected: All existing tests PASS + new tests PASS.

- [ ] **Step 5: Run the full test suite to check for regressions**

Run: `pytest -x --timeout=30 2>/dev/null || pytest -x`

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/ticketing_agent/design/map_to_ontology.py tests/test_map_to_ontology.py
git commit -m "feat: replace regex type extraction with TypeRef parser, add alias resolution and TYPE_ARGUMENT edges"
```

---

### Task 5: Update Neo4j graph queries to include new edge types and properties

**Files:**
- Modify: `backend/db/neo4j/queries/graph.py`
- Modify: `backend/graph/builders.py`

- [ ] **Step 1: Update `fetch_design_graph` to include TYPE_ARGUMENT and TEMPLATE_PARAM edges**

In `backend/db/neo4j/queries/graph.py`, the `fetch_design_graph` function needs to also collect `TYPE_ARGUMENT` and `TEMPLATE_PARAM` edges. The existing pattern fetches `DEPENDS_ON`, `HAS_ARGUMENT`, `RETURNS`, etc. Add:

After the Design-to-Design edge query, add a query for `TYPE_ARGUMENT` edges from Design nodes to dependency nodes:

```python
# TYPE_ARGUMENT edges from Design nodes to dependency Compound nodes
type_arg_result = session.run(
    f"""
    MATCH (s:Design)-[r:TYPE_ARGUMENT]->(dep:Compound)
    WHERE {where.replace("n:", "s:").replace("n.", "s.")}
      AND dep.source IS NOT NULL AND dep.source <> ''
    RETURN s.qualified_name AS src, dep.qualified_name AS tgt,
           r.position AS position, r.display_name AS display_name
    """,
    params,
)
for record in type_arg_result:
    edges.append({
        "source": record["src"],
        "target": record["tgt"],
        "type": "TYPE_ARGUMENT",
        "position": record["position"],
        "display_name": record["display_name"] or "",
    })
    if record["tgt"] not in node_qns:
        # Add the dependency node if not already present
        dep_data = session.run(
            "MATCH (c:Compound {qualified_name: $qn}) RETURN c",
            {"qn": record["tgt"]},
        ).single()
        if dep_data:
            nodes.append(dict(dep_data["c"]))
            node_qns.add(record["tgt"])
```

Also add handling for `TEMPLATE_PARAM` edges within the design layer:

```python
# TEMPLATE_PARAM edges between Design nodes
template_param_result = session.run(
    f"""
    MATCH (s:Design)-[r:TEMPLATE_PARAM]->(t:Design)
    WHERE {where.replace("n:", "s:").replace("n.", "s.")}
    RETURN s.qualified_name AS src, t.qualified_name AS tgt,
           r.position AS position, r.name AS name
    """,
    params,
)
for record in template_param_result:
    edges.append({
        "source": record["src"],
        "target": record["tgt"],
        "type": "TEMPLATE_PARAM",
        "position": record["position"],
        "name": record["name"] or "",
    })
```

- [ ] **Step 2: Update `build_cytoscape_edge` in `builders.py` to pass through new properties**

In `backend/graph/builders.py`, update `build_cytoscape_edge` to pass through `position`, `name`, and `display_name`:

```python
def build_cytoscape_edge(e: dict) -> dict:
    """Build a Cytoscape edge-data dict from a raw edge dict."""
    global _edge_counter
    _edge_counter += 1
    label = e.get("type", "")
    mechanism = e.get("mechanism", "")
    if mechanism and label in ("AGGREGATES", "REFERENCES"):
        label = f"{label}\n<{mechanism}>"
    return {
        "id": f"e_{_edge_counter}_{e.get('source', '')}_{e.get('target', '')}_{e.get('type', '')}",
        "source": e.get("source", ""),
        "target": e.get("target", ""),
        "label": label,
        "mechanism": mechanism,
        "position": e.get("position"),
        "name": e.get("name", ""),
        "display_name": e.get("display_name", ""),
    }
```

- [ ] **Step 3: Run tests to verify existing graph tests still pass**

Run: `pytest tests/test_graph_cross_layer.py -v` (if that test file exists and tests graph queries)

Also run: `pytest tests/ -k "graph" -v`

Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add backend/db/neo4j/queries/graph.py backend/graph/builders.py
git commit -m "feat: include TYPE_ARGUMENT and TEMPLATE_PARAM edges in graph queries, pass new edge properties"
```

---

### Task 6: Update Cytoscape rendering for template nodes, alias display, and TYPE_ARGUMENT edges

**Files:**
- Modify: `backend/graph/transforms.py`
- Modify: `frontend/data/ontology.py`

- [ ] **Step 1: Add template stencil and border color to `_build_uml_html`**

In `backend/graph/transforms.py`, add to the `_STEREOTYPES` dict and `KIND_BORDER_COLORS`:

```python
KIND_BORDER_COLORS = {
    "class": "#4a90d9",
    "struct": "#5b9bd5",
    "interface": "#9b59b6",
    "enum": "#e74c3c",
    "class_template": "#9b59b6",  # Purple border for templates
}
```

Add template stereotype to `_build_uml_html`:

```python
_STEREOTYPES = {
    "enum": "\u00ABenumeration\u00BB",
    "interface": "\u00ABinterface\u00BB",
    "class": "\u00ABclass\u00BB",
    "class_template": "\u00ABclass template\u00BB",
}
```

- [ ] **Step 2: Update `_type_origin_marker` to use ◆ for nodes found in dep_lookup**

Currently `_type_origin_marker` checks `member_layer == "dependency"` for the ▸ marker. Add logic to check whether a type name resolves through the alias/dep lookup. In the collapse rendering, the member data now carries the resolved status in the `type_signature` field. Update the marker logic:

```python
def _type_origin_marker(type_sig: str, member_layer: str) -> str:
    """Return an inline marker indicating where a type originates.

    ●  builtin / primitive
    ◆  linked design or dependency type (resolves to a real node)
    ▸  dependency / external library type
    (empty) when type information is unavailable
    """
    if not type_sig:
        return ""
    if _is_builtin_type(type_sig):
        return "\u25cf "   # filled circle
    if member_layer == "dependency":
        return "\u25b8 "   # right-pointing triangle
    return "\u25c6 "   # diamond for design-linked types
```

The key change: `std::string` was previously caught by `_is_builtin_type` and marked ●. Now it should be marked ◆ because it resolves to a real node. Update `_is_builtin_type` to exclude `std::string`, `std::string_view`, etc. from the builtin set since they now link to real nodes:

In `_BUILTIN_TYPES`, remove entries that will be resolved through the alias/dep lookup:

```python
_BUILTIN_TYPES = frozenset({
    "void", "bool", "int", "double", "float", "char", "long", "short",
    "unsigned", "signed", "size_t", "uint8_t", "uint16_t", "uint32_t", "uint64_t",
    "int8_t", "int16_t", "int32_t", "int64_t",
    # std::string, std::vector, etc. are NO LONGER builtin — they resolve to
    # dependency nodes via alias_lookup and TYPE_ARGUMENT edges.
    "str", "int", "float", "bool", "bytes", "list", "dict", "set",
    "tuple", "Optional", "List", "Dict", "Set", "Any", "None",
})
```

Note: We're removing `std::string`, `std::vector`, `std::map`, `std::set`, `std::optional`, `std::shared_ptr`, `std::unique_ptr`, `std::pair`, `std::array`, `std::variant` from `_BUILTIN_TYPES` since they now resolve to real nodes. The `_TEMPLATE_PREFIXES` tuple stays so any unresolvable `std::*` type still gets the ▸ marker.

- [ ] **Step 3: Add `type_parameter` node rendering**

In the node rendering logic (the function that processes collapsed/uncollapsed nodes for Cytoscape), add styling for `type_parameter` nodes:

```python
if node_data.get("kind") == "type_parameter":
    node_data["label"] = f"\u00ABtype parameter\u00BB\n{node_data.get('label', '')}"
    node_data["is_dashed"] = True  # For dashed border
```

When building Cytoscape node data, check for `kind == "type_parameter"` and set:
- Border: dashed, light gray (`#a0aec0`)
- Font: italic
- Background: transparent or very light

- [ ] **Step 4: Add TYPE_ARGUMENT edge styling**

In the Cytoscape edge styling, add color for `TYPE_ARGUMENT` edges. Find where edge styles are defined (likely in `theme.py` or the Cytoscape configuration) and add:

```python
"TYPE_ARGUMENT": {"color": "#9b59b6", "style": "solid"},  # Purple
"TEMPLATE_PARAM": {"color": "#9b59b6", "style": "dashed"},  # Purple dashed
```

- [ ] **Step 5: Add stdlib header indicator for dependency nodes**

In `_build_uml_html`, for dependency nodes (`layer == "dependency"`), check if the node data has a `defined_in_header` property (populated from the `DEFINED_IN` edge query). If so, add a header line:

```python
if is_dependency and od.get("defined_in_header"):
    lines.insert(0, f'<div style="color:{mc["stereotype"]};font-size:8px;text-align:center">{html_mod.escape(od["defined_in_header"])}</div>')
```

This requires the graph query to also fetch `DEFINED_IN` header info for dependency nodes. Add this to the dependency node enrichment in `fetch_design_graph`.

- [ ] **Step 6: Update `frontend/data/ontology.py` to handle new edge types**

In `fetch_ontology_graph_data`, the function already calls `format_cytoscape_graph` which processes all edges. No special handling needed since the edge types are passed through. But ensure the `filter_cross_layer_elements` function doesn't filter out `TYPE_ARGUMENT` edges:

Currently it filters edges where either endpoint is a cross-layer node. `TYPE_ARGUMENT` edges connect a dependency node to another dependency node (or a design node to a dependency node). These should be preserved when `include_dependencies=True`. Check that the filter logic handles this correctly — it should, since the filter only removes edges where *both* endpoints are in the cross-layer set.

- [ ] **Step 7: Run tests**

Run: `pytest tests/test_collapse_external_entities.py tests/test_dual_border.py -v`

Expected: All pass (these test the existing rendering logic).

- [ ] **Step 8: Commit**

```bash
git add backend/graph/transforms.py backend/graph/builders.py frontend/data/ontology.py
git commit -m "feat: template node rendering, alias display, TYPE_ARGUMENT edges, stdlib header indicator"
```

---

### Task 7: Wire up the alias_lookup in the design pipeline and ensure TYPE_ARGUMENT edges reach Neo4j

**Files:**
- Modify: `backend/ticketing_agent/design/design_ontology.py`
- Modify: `backend/ticketing_agent/design/design_per_hlr.py` (or wherever `map_oo_to_ontology` is called)
- Modify: `backend/db/neo4j/repositories/` (wherever triples are persisted to Neo4j)

- [ ] **Step 1: Find where `map_oo_to_ontology` is called and pass the alias_lookup**

Search for all call sites of `map_oo_to_ontology`:

```bash
grep -rn "map_oo_to_ontology" backend/
```

At each call site, add `alias_lookup` built from `build_alias_lookup(neo4j_session)`. The typical pattern:

```python
from backend.ticketing_agent.design.container_lookup import build_alias_lookup
from services.dependencies import get_neo4j

# ... in the function that calls map_oo_to_ontology:
with get_neo4j().session() as neo_session:
    alias_lookup = build_alias_lookup(neo_session)

design = map_oo_to_ontology(
    oo,
    component_id=component.id,
    prior_class_lookup=prior_lookup,
    component_namespace=component.namespace,
    dependency_lookup=dep_lookup,
    alias_lookup=alias_lookup,
)
```

- [ ] **Step 2: Ensure Neo4j triple persistence handles the new `position`, `name`, and `display_name` properties**

Find where triples are written to Neo4j (likely in `backend/db/neo4j/repositories/`). The triple creation code likely uses Cypher like:

```cypher
CREATE (s:Design {qualified_name: $subj})-[r:$pred]->(t {qualified_name: $obj})
```

Update to also set `position`, `name`, and `display_name` properties on the relationship when they are present:

```cypher
CREATE (s:Design {qualified_name: $subj})-[r:$pred]->(t {qualified_name: $obj})
SET r.position = $position, r.name = $name, r.display_name = $display_name
```

Check the actual repository code and update accordingly. The `position` should only be set for `TYPE_ARGUMENT` and `TEMPLATE_PARAM` edges; set to `null` otherwise.

- [ ] **Step 3: Add Neo4j constraints for new predicates**

In `backend/db/neo4j/connection.py`, the `ensure_constraints` method should already handle dynamic predicate creation since predicates are stored in the SQLite Predicate table. But verify that `type_argument` and `template_param` predicates are seeded correctly when `Predicate.ensure_defaults()` is called. The change in Task 1 already added them to `DEFAULT_PREDICATES`.

- [ ] **Step 4: Run integration-level search for call sites**

```bash
grep -rn "map_oo_to_ontology" backend/ scripts/
```

Verify all call sites are updated.

- [ ] **Step 5: Commit**

```bash
git add backend/ticketing_agent/design/design_ontology.py backend/ticketing_agent/design/design_per_hlr.py backend/db/neo4j/
git commit -m "feat: wire up alias_lookup in design pipeline, persist TYPE_ARGUMENT edge properties to Neo4j"
```

---

### Task 8: End-to-end verification with the calculator project

**Files:**
- No new files — this is verification.

- [ ] **Step 1: Re-run the setup and design scripts**

```bash
source .venv/bin/activate
python scripts/01_flush_db.py
python scripts/02_setup_project.py
python scripts/03_design_requirements.py
```

Expected: No errors. The design output should now include `TYPE_ARGUMENT` edges and `has_argument` edges to stdlib nodes.

- [ ] **Step 2: Check Neo4j for the new edges**

```bash
source .venv/bin/activate
python3 -c "
from services.dependencies import init_neo4j
from backend.db.neo4j.connection import Neo4jConnection
conn = Neo4jConnection()
with conn.session() as session:
    # Check TYPE_ARGUMENT edges
    result = session.run('''
        MATCH (s:Design)-[r:TYPE_ARGUMENT]->(t)
        RETURN s.qualified_name AS src, t.qualified_name AS tgt, r.position AS pos, r.display_name AS dn
        LIMIT 10
    ''')
    print('TYPE_ARGUMENT edges:')
    for r in result:
        print(f'  {r[\"src\"]} -> {r[\"tgt\"]} pos={r[\"pos\"]} display={r[\"dn\"]}')

    # Check has_argument edges to std::basic_string
    result2 = session.run('''
        MATCH (s:Design)-[r:HAS_ARGUMENT]->(t)
        WHERE t.qualified_name CONTAINS \"basic_string\" OR t.qualified_name CONTAINS \"string\"
        RETURN s.qualified_name AS src, t.qualified_name AS tgt, r.display_name AS dn
        LIMIT 10
    ''')
    print('\\nhAS_ARGUMENT edges to string types:')
    for r in result2:
        print(f'  {r[\"src\"]} -> {r[\"tgt\"]} display={r[\"dn\"]}')
conn.close()
"
```

Expected: TYPE_ARGUMENT edges from `std::vector` to `std::basic_string`, and HAS_ARGUMENT edges from design methods to `std::basic_string` with `display_name="std::string"`.

- [ ] **Step 3: Check the ontology graph in the browser**

Open `http://localhost:8081/ontology/graph` and verify:
- Design methods like `CalculationEngine::add` show `HAS_ARGUMENT` edges to `std::basic_string`
- The `std::basic_string` node displays as "std::string" (via alias display)
- `TYPE_ARGUMENT` edges appear in purple connecting template nodes to type arguments
- The type origin markers in member lines show ◆ for `std::string` instead of ●

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: complete stdlib template linking — end-to-end verification pass"
```

---

## Self-Review Checklist

**Spec coverage:**
- ✅ Section 1 (Node Model): `type_parameter` kind — Task 1
- ✅ Section 1 (TypeRef): Parser — Task 2
- ✅ Section 2 (Alias Resolution): `build_alias_lookup` — Task 3
- ✅ Section 3 (Mapping Pipeline): Replace regex, create TYPE_ARGUMENT edges — Task 4
- ✅ Section 3 (New Predicates): `type_argument`, `template_param` — Task 1
- ✅ Section 4 (Template rendering): Stereotype, border, type_parameter nodes — Task 6
- ✅ Section 4 (Alias display): display_name on edges — Tasks 4, 5, 6
- ✅ Section 4 (TYPE_ARGUMENT edges): Purple styling — Task 6
- ✅ Section 4 (Header indicator): DEFINED_IN header — Task 6
- ✅ Section 5 (File changes): All 9 files covered — Tasks 1-6

**Placeholder scan:** No TBDs, TODOs, or "implement later" patterns.

**Type consistency:** `position` is `int | None`, `name` is `str`, `display_name` is `str` — consistent across schema, pipeline, Neo4j, and Cytoscape layers.

**No spec gaps:** Every requirement has a corresponding task.