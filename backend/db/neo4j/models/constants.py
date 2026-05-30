"""Constants for the Neo4j codebase graph layer.

Moved from backend.db.models.ontology during graph primitives restructuring.
These constants define the vocabulary of predicates, node kinds,
and specializations used by the design repository and Cypher queries.

Node kinds are now organized by Neo4j node label:
  - COMPOUND_KINDS: entities that own members (classes, interfaces, enums)
  - MEMBER_KINDS: entities owned by compounds (methods, attributes, enum values)
  - NAMESPACE_KINDS: grouping entities (namespaces, packages)
"""

# ---------------------------------------------------------------------------
# Node kinds — organized by Neo4j label
# ---------------------------------------------------------------------------

COMPOUND_KINDS: list[str] = [
    "class",
    "struct",
    "template_class",
    "interface",
    "abstract_class",
    "enum",
    "enum_class",
]

MEMBER_KINDS: list[str] = [
    "method",
    "attribute",
    "constant",
    "enum_value",
]

NAMESPACE_KINDS: list[str] = [
    "namespace",
    "package",
    "module",  # Legacy: maps to :Namespace in Neo4j, prefer 'namespace' or 'package'
]

# Kinds not yet assigned to a Neo4j node label.
# Kept for backward compatibility with codebase/schemas.py NodeKind Literal.
UNCLASSIFIED_KINDS: list[str] = [
    "function",
    "primitive",
    "type_alias",
    "type_parameter",
]

# All node kinds flattened (for validation, prompts, etc.)
NODE_KINDS: list[str] = COMPOUND_KINDS + MEMBER_KINDS + NAMESPACE_KINDS + UNCLASSIFIED_KINDS

# ---------------------------------------------------------------------------
# Semantic groupings
# ---------------------------------------------------------------------------

TYPE_KINDS: set[str] = {"class", "struct", "template_class", "interface", "abstract_class", "enum", "enum_class"}
VALUE_KINDS: set[str] = {"method", "attribute", "constant", "enum_value"}

# ---------------------------------------------------------------------------
# Visibility / access specifiers
# ---------------------------------------------------------------------------

VISIBILITY_CHOICES: list[str] = ["public", "private", "protected"]

# ---------------------------------------------------------------------------
# Layers — where a node originates from
# ---------------------------------------------------------------------------

LAYERS: list[str] = ["design", "as-built", "dependency"]

# ---------------------------------------------------------------------------
# Predicates — mapping lowercase names to UPPER_SNAKE_CASE Neo4j rel types
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
    ("aggregates", "Whole-part relationship where the part can exist independently. Specify mechanism for container types (e.g., std::vector, std::list)"),
    ("composes", "Strong whole-part relationship where the part is owned by the whole"),
    ("depends_on", "One entity depends on another (e.g., for a header include)"),
    ("generalizes", "Inheritance / is-a relationship"),
    ("realizes", "A class implements/realizes an interface or contract"),
    ("references", "One entity holds a reference or pointer to another. Specify mechanism (e.g., std::unique_ptr, std::shared_ptr, raw_pointer, reference)"),
    ("invokes", "Weak association, signifying a caller-callee relationship"),
    ("has_argument", "A method accepts a parameter of the given type (method → type)"),
    ("returns", "A method returns a value of the given entity type (method → type)"),
    ("type_argument", "A template accepts a type argument at a given position"),
    ("template_param", "A template declares a type parameter slot"),
]

# ---------------------------------------------------------------------------
# Source types (kept for backward compatibility during transition;
# will be removed once all code uses node labels)
# ---------------------------------------------------------------------------

SOURCE_TYPES: list[tuple[str, str]] = [
    ("compound", "Compound"),
    ("member", "Member"),
    ("namespace", "Namespace"),
]
SOURCE_TYPE_VALUES: set[str] = {k for k, _ in SOURCE_TYPES}

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
        "constant": [
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
        "constant": [
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