"""Constants for the Neo4j codebase graph layer.

Core vocabulary (kinds, layers, predicates, schema DDL) is imported from
the ``codegraph`` shared library.  Ticketing-system extensions and
language-specific specializations are defined here.
"""

from codegraph.constants import (
    COMPOUND_KINDS,
    CONSTRAINTS_AND_INDEXES,
    LAYERS,
    MEMBER_KINDS,
    NAMESPACE_KINDS,
    PREDICATES,
    PREDICATE_TO_REL_TYPE,
    VISIBILITY_CHOICES,
)

# Build the unified NODE_KINDS list.  Core kinds come from codegraph;
# UNCLASSIFIED_KINDS are ticketing-system concepts not yet assigned a
# Neo4j node label.
UNCLASSIFIED_KINDS: list[str] = [
    "primitive",
    "type_alias",
    "type_parameter",
]

NODE_KINDS: list[str] = (
    list(COMPOUND_KINDS) + list(MEMBER_KINDS) + list(NAMESPACE_KINDS) + UNCLASSIFIED_KINDS
)

# ---------------------------------------------------------------------------
# Semantic groupings (ticketing-system specific)
# ---------------------------------------------------------------------------

TYPE_KINDS: set[str] = {
    "class", "struct", "template_class", "interface", "abstract_class",
    "enum", "enum_class", "union",
}
VALUE_KINDS: set[str] = {"method", "variable", "define", "enumvalue", "function"}

# ---------------------------------------------------------------------------
# Predicate documentation (ticketing-system extension)
# ---------------------------------------------------------------------------

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
