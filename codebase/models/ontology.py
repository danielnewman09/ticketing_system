"""
Ontology graph layer (Django-managed, lives in the default database).

Provides typed relationships and design annotations on top of the
external codebase index.
"""

from django.db import models

from .codebase import Compound


# ---------------------------------------------------------------------------
# Node kinds — language-agnostic base kinds
# ---------------------------------------------------------------------------

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

# Semantic groupings used by validation and review agents.
TYPE_KINDS = {"class", "interface", "enum", "type_alias"}
VALUE_KINDS = {"enum_value", "function", "method", "attribute", "constant"}

# ---------------------------------------------------------------------------
# Language-specific specializations
# ---------------------------------------------------------------------------
# Each language maps base kinds to their concrete specializations.
# A node's specialization must be valid for its kind + language.
# If a kind is absent, no specializations are available (base kind only).

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

SUPPORTED_LANGUAGES = set(LANGUAGE_SPECIALIZATIONS.keys())


def valid_specializations(language, kind):
    """Return the set of valid specializations for a language + kind."""
    lang_spec = LANGUAGE_SPECIALIZATIONS.get(language, {})
    return set(lang_spec.get(kind, []))


class OntologyNode(models.Model):
    """A node in the design ontology graph.

    Each node references a compound from the external codebase DB by refid,
    or can be free-standing (when compound_refid is blank).
    """

    compound_refid = models.CharField(
        max_length=200, blank=True, default="",
        help_text="Refid linking to a compound in the codebase DB",
    )
    component = models.ForeignKey(
        "components.Component", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="ontology_nodes",
    )
    is_intercomponent = models.BooleanField(
        default=False,
        help_text="Public interface boundary for cross-component use",
    )
    kind = models.CharField(max_length=20, choices=NODE_KINDS)
    specialization = models.CharField(
        max_length=40, blank=True, default="",
        help_text="Language-specific specialization (e.g., template_class, dataclass)",
    )
    visibility = models.CharField(
        max_length=10, choices=VISIBILITY_CHOICES, blank=True, default="",
        help_text="Access specifier (public/private/protected). Blank for nodes where N/A.",
    )
    name = models.CharField(max_length=200)
    qualified_name = models.CharField(max_length=500, blank=True, default="")
    description = models.TextField(blank=True)

    class Meta:
        db_table = "ontology_nodes"

    def __str__(self):
        return self.qualified_name or self.name

    def get_compound(self):
        """Resolve to the external Compound, if linked."""
        if not self.compound_refid:
            return None
        return Compound.objects.using("codebase").filter(
            refid=self.compound_refid,
        ).first()


class NamespaceNodeManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(kind="namespace")


class NamespaceNode(OntologyNode):
    """Proxy model for namespace nodes with hierarchy-aware methods."""

    objects = NamespaceNodeManager()

    class Meta:
        proxy = True

    def save(self, *args, **kwargs):
        self.kind = "namespace"
        super().save(*args, **kwargs)

    def get_children(self):
        """Return direct children (one level deep) based on qualified_name."""
        prefix = self.qualified_name + "::"
        return OntologyNode.objects.filter(
            qualified_name__startswith=prefix,
        ).exclude(
            qualified_name__regex=rf"^{self.qualified_name}::[^:]+::.+",
        )

    def get_descendants(self):
        """Return all nested nodes at any depth."""
        prefix = self.qualified_name + "::"
        return OntologyNode.objects.filter(qualified_name__startswith=prefix)

    def get_child_triples(self):
        """Return all triples where at least one endpoint is a direct child."""
        child_pks = set(self.get_children().values_list("pk", flat=True))
        return OntologyTriple.objects.select_related(
            "subject", "object",
        ).filter(
            models.Q(subject_id__in=child_pks) | models.Q(object_id__in=child_pks)
        )

    @staticmethod
    def parent_lookup():
        """Return a dict mapping qualified_name -> graph node ID for all namespaces."""
        return {
            n.qualified_name: f"node-{n.pk}"
            for n in NamespaceNode.objects.all()
        }

    @staticmethod
    def resolve_parent(qualified_name, ns_lookup):
        """Given a qualified_name and namespace lookup, return the parent graph ID or None."""
        parts = qualified_name.rsplit("::", 1)
        if len(parts) == 2 and parts[0] in ns_lookup:
            return ns_lookup[parts[0]]
        return None


class Predicate(models.Model):
    """A named relationship type for ontology triples.

    Modelled after UML class diagram associations:
    generalizes (inheritance), composes, aggregates, depends_on,
    realizes (implementation), associates (general association).
    """

    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        db_table = "ontology_predicates"
        ordering = ["name"]

    def __str__(self):
        return self.name

    # Seed data: UML-aligned defaults
    DEFAULT_PREDICATES = [
        ("associates", "General association between two entities"),
        ("aggregates", "Whole-part relationship where the part can exist independently"),
        ("composes", "Strong whole-part relationship where the part is owned by the whole"),
        ("depends_on", "One entity depends on another"),
        ("generalizes", "Inheritance / is-a relationship"),
        ("realizes", "A class implements/realizes an interface or contract"),
        ("invokes", "Weak association, signififying a caller-callee relationship")
    ]

    @classmethod
    def ensure_defaults(cls):
        """Create default predicates if they don't exist."""
        for name, description in cls.DEFAULT_PREDICATES:
            cls.objects.get_or_create(name=name, defaults={"description": description})


class OntologyTriple(models.Model):
    """A semantic triple: subject --predicate--> object.

    Unifies ontology edges and requirement-to-ontology links into a single
    structure.
    """

    subject = models.ForeignKey(
        OntologyNode, on_delete=models.CASCADE, related_name="triples_as_subject",
    )
    predicate = models.ForeignKey(
        Predicate, on_delete=models.PROTECT, related_name="triples",
    )
    object = models.ForeignKey(
        OntologyNode, on_delete=models.CASCADE, related_name="triples_as_object",
    )

    class Meta:
        db_table = "ontology_triples"
        unique_together = [("subject", "predicate", "object")]

    def __str__(self):
        return f"{self.subject} --{self.predicate}--> {self.object}"
