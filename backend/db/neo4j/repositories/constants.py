"""Constants for the Neo4j design layer.

Moved from backend.db.models.ontology during Phase 1 migration.
These constants define the vocabulary of predicates, node kinds,
and specializations used by the design repository and Cypher queries.
"""

# ---------------------------------------------------------------------------
# Predicates — mapping lowercase names to UPPER_SNAKE_CASE Neo4j rel types
# ---------------------------------------------------------------------------

PREDICATE_TO_REL_TYPE = {
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
}

DEFAULT_PREDICATES = [
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
# Node kinds — language-agnostic base kinds
# ---------------------------------------------------------------------------

NODE_KINDS = [
    ("class", "Class"),
    ("define", "Define"),
    ("enum", "Enum"),
    ("enumvalue", "Enum Value"),
    ("function", "Function"),
    ("interface", "Interface"),
    ("method", "Method"),
    ("module", "Module"),
    ("primitive", "Primitive Type"),
    ("type_alias", "Type Alias"),
    ("type_parameter", "Type Parameter"),
    ("variable", "Variable"),
]

NODE_KIND_VALUES = {k for k, _ in NODE_KINDS}

# ---------------------------------------------------------------------------
# Visibility / access specifiers
# ---------------------------------------------------------------------------

VISIBILITY_CHOICES = [
    ("public", "Public"),
    ("private", "Private"),
    ("protected", "Protected"),
]

# ---------------------------------------------------------------------------
# Semantic groupings
# ---------------------------------------------------------------------------

TYPE_KINDS = {"class", "interface", "enum", "type_alias"}
VALUE_KINDS = {"enumvalue", "function", "method", "variable", "define"}

# ---------------------------------------------------------------------------
# Codebase source types
# ---------------------------------------------------------------------------

SOURCE_TYPES = [
    ("namespace", "Namespace"),
    ("compound", "Compound"),
    ("member", "Member"),
    ("dependency", "Dependency Reference"),
]

SOURCE_TYPE_VALUES = {k for k, _ in SOURCE_TYPES}

# ---------------------------------------------------------------------------
# Language-specific specializations
# ---------------------------------------------------------------------------

LANGUAGE_SPECIALIZATIONS = {
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

SUPPORTED_LANGUAGES = set(LANGUAGE_SPECIALIZATIONS.keys())


def valid_specializations(language, kind):
    """Return the set of valid specializations for a language + kind."""
    lang_spec = LANGUAGE_SPECIALIZATIONS.get(language, {})
    return set(lang_spec.get(kind, []))